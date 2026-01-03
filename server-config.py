#!/usr/bin/env python3
"""
LocalServer Manager
Local Test Server Control for MCC Modpack Development

Usage:
    python server-config.py              # Interactive menu
    python server-config.py start        # Start server
    python server-config.py stop         # Stop server via RCON
    python server-config.py status       # Show current status
    python server-config.py mode <mode>  # Switch mode (production/fresh/vanilla)

Server Modes:
    production  - Uses copy of production backup, all mods installed
    fresh       - Fresh world generation, all mods installed
    vanilla     - Fresh world generation, Fabric API only (for debugging)

Note: World sync commands (world-download, world-upload) are in MCC/server-config.py
"""

import os
import sys
import shutil
import socket
import struct
import subprocess
from datetime import datetime

# Rich library for pretty output
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn, FileSizeColumn
from rich.table import Table
from rich.panel import Panel
from rich import box

# Initialize rich console
console = Console()

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MCC_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "MCC"))

# Java path - defaults to Prism Launcher's bundled JDK
DEFAULT_JAVA = os.path.expandvars(r"%APPDATA%\PrismLauncher\java\java-runtime-delta\bin\java.exe")

# Server settings
SERVER_JAR = "fabric-server-launch.jar"
SERVER_PORT = 25565
RCON_HOST = "127.0.0.1"
RCON_PORT = 25575
RCON_PASSWORD = "testpassword"

# JVM flags (Aikar's optimized G1GC flags)
JVM_FLAGS = [
    "-Xms4G", "-Xmx4G",
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC",
    "-XX:+AlwaysPreTouch",
    "-XX:G1NewSizePercent=30",
    "-XX:G1MaxNewSizePercent=40",
    "-XX:G1HeapRegionSize=8M",
    "-XX:G1ReservePercent=20",
    "-XX:G1HeapWastePercent=5",
    "-XX:G1MixedGCCountTarget=4",
    "-XX:InitiatingHeapOccupancyPercent=15",
    "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5",
    "-XX:SurvivorRatio=32",
    "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1",
    "-Dusing.aikars.flags=https://mcflags.emc.gs",
    "-Daikars.new.flags=true",
]

# Fix Windows console encoding issues
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'


# =============================================================================
# Environment Loading
# =============================================================================

def load_dotenv():
    """Load environment variables from .env file"""
    # Check LocalServer .env first, then fall back to MCC .env
    env_paths = [
        os.path.join(SCRIPT_DIR, '.env'),
        os.path.join(MCC_DIR, '.env'),
    ]

    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
            break

load_dotenv()

# SFTP credentials (for production world sync)
SFTP_HOST = os.environ.get("SFTP_HOST", "")
SFTP_PORT = int(os.environ.get("SFTP_PORT", "2022"))
SFTP_USERNAME = os.environ.get("SFTP_USERNAME", "")
SFTP_PASSWORD = os.environ.get("SFTP_PASSWORD", "")

# Java path (can be overridden via env)
JAVA_PATH = os.environ.get("JAVA_PATH", DEFAULT_JAVA)


# =============================================================================
# RCON Client
# =============================================================================

class RCONClient:
    """Simple RCON client for Minecraft server communication"""

    SERVERDATA_AUTH = 3
    SERVERDATA_AUTH_RESPONSE = 2
    SERVERDATA_EXECCOMMAND = 2
    SERVERDATA_RESPONSE_VALUE = 0

    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
        self.request_id = 0

    def connect(self):
        """Connect to RCON server"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(5)
        self.socket.connect((self.host, self.port))
        return self._authenticate()

    def _authenticate(self):
        """Authenticate with RCON server"""
        response = self._send_packet(self.SERVERDATA_AUTH, self.password)
        return response is not None and response[0] != -1

    def command(self, cmd):
        """Send a command and return the response"""
        response = self._send_packet(self.SERVERDATA_EXECCOMMAND, cmd)
        if response:
            return response[1]
        return None

    def _send_packet(self, packet_type, payload):
        """Send a packet and receive response"""
        self.request_id += 1
        packet = self._encode_packet(self.request_id, packet_type, payload)
        self.socket.send(packet)
        return self._receive_packet()

    def _encode_packet(self, request_id, packet_type, payload):
        """Encode an RCON packet"""
        payload_bytes = payload.encode('utf-8') + b'\x00\x00'
        length = 4 + 4 + len(payload_bytes)
        return struct.pack('<iii', length, request_id, packet_type) + payload_bytes

    def _receive_packet(self):
        """Receive and decode an RCON packet"""
        try:
            length_data = self.socket.recv(4)
            if len(length_data) < 4:
                return None
            length = struct.unpack('<i', length_data)[0]
            data = self.socket.recv(length)
            request_id = struct.unpack('<i', data[0:4])[0]
            # packet_type = struct.unpack('<i', data[4:8])[0]
            payload = data[8:-2].decode('utf-8')
            return (request_id, payload)
        except socket.timeout:
            return None

    def close(self):
        """Close the connection"""
        if self.socket:
            self.socket.close()
            self.socket = None


# =============================================================================
# Progress Tracking (for SFTP downloads)
# =============================================================================

class RichProgressTracker:
    """Tracks download progress using Rich"""
    def __init__(self, total_files=1, total_size=0):
        self.total_files = total_files
        self.total_size = total_size
        self.current_file = 0
        self.files_succeeded = 0
        self.files_failed = 0
        self.total_bytes_transferred = 0
        self.previous_file_transferred = 0

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}", justify="right"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            "•",
            FileSizeColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=console,
            expand=True
        )

        self.overall_task_id = None
        self.current_file_task_id = None

    def __enter__(self):
        self.progress.__enter__()
        if self.total_files > 1:
            self.overall_task_id = self.progress.add_task(
                f"[cyan]Overall Progress ({self.files_succeeded + self.files_failed}/{self.total_files} files)",
                total=self.total_size
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.__exit__(exc_type, exc_val, exc_tb)

    def start_file(self, filename, file_size):
        self.current_file += 1
        self.previous_file_transferred = 0

        display_name = filename
        if len(display_name) > 60:
            display_name = "..." + display_name[-57:]

        if self.current_file_task_id is not None:
            self.progress.remove_task(self.current_file_task_id)

        self.current_file_task_id = self.progress.add_task(
            f"[green]{display_name}",
            total=file_size
        )

    def update(self, transferred, total):
        if self.current_file_task_id is not None:
            self.progress.update(self.current_file_task_id, completed=transferred)

        if self.overall_task_id is not None:
            delta = transferred - self.previous_file_transferred
            if delta > 0:
                self.total_bytes_transferred += delta
                self.previous_file_transferred = transferred
                self.progress.update(
                    self.overall_task_id,
                    completed=min(self.total_bytes_transferred, self.total_size),
                    description=f"[cyan]Overall Progress ({self.files_succeeded + self.files_failed}/{self.total_files} files)"
                )

    def file_complete(self, success=True):
        if success:
            self.files_succeeded += 1
            if self.current_file_task_id is not None:
                task = self.progress._tasks.get(self.current_file_task_id)
                if task and task.completed < task.total:
                    remaining = task.total - task.completed
                    self.total_bytes_transferred += remaining
                if task:
                    self.progress.update(self.current_file_task_id, completed=task.total)
                self.progress.remove_task(self.current_file_task_id)
                self.current_file_task_id = None

            if self.overall_task_id is not None:
                self.progress.update(
                    self.overall_task_id,
                    completed=min(self.total_bytes_transferred, self.total_size),
                    description=f"[cyan]Overall Progress ({self.files_succeeded + self.files_failed}/{self.total_files} files)"
                )
        else:
            self.files_failed += 1
            if self.current_file_task_id is not None:
                task = self.progress._tasks.get(self.current_file_task_id)
                if task:
                    self.total_bytes_transferred += task.total
                self.progress.remove_task(self.current_file_task_id)
                self.current_file_task_id = None

            if self.overall_task_id is not None:
                self.progress.update(
                    self.overall_task_id,
                    completed=min(self.total_bytes_transferred, self.total_size),
                    description=f"[cyan]Overall Progress ({self.files_succeeded + self.files_failed}/{self.total_files} files)"
                )


def progress_callback(tracker):
    """Create a callback function for paramiko"""
    def callback(transferred, total):
        tracker.update(transferred, total)
    return callback


# =============================================================================
# SFTP Functions
# =============================================================================

def check_sftp_credentials():
    """Check if SFTP credentials are configured"""
    if not SFTP_HOST or not SFTP_USERNAME or not SFTP_PASSWORD:
        console.print("[red]Error: SFTP credentials not configured![/red]")
        console.print("[yellow]Create a .env file with:[/yellow]")
        console.print("  SFTP_HOST=your-server.bloom.host")
        console.print("  SFTP_PORT=2022")
        console.print("  SFTP_USERNAME=your-username")
        console.print("  SFTP_PASSWORD=your-password")
        return False
    return True


def get_sftp_connection():
    """Create and return an SFTP connection"""
    import paramiko

    if not check_sftp_credentials():
        return None, None

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SFTP_HOST, port=SFTP_PORT, username=SFTP_USERNAME, password=SFTP_PASSWORD)
    sftp = ssh.open_sftp()
    return ssh, sftp


# =============================================================================
# Status Functions
# =============================================================================

def is_server_running():
    """Check if Minecraft server is running by testing port"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', SERVER_PORT))
    sock.close()
    return result == 0


def get_current_mode():
    """Get current server mode from server.properties"""
    props_file = os.path.join(SCRIPT_DIR, "server.properties")
    if not os.path.exists(props_file):
        return "unknown"

    with open(props_file, 'r') as f:
        for line in f:
            if line.startswith('level-name='):
                level_name = line.split('=', 1)[1].strip()
                if level_name == "world-local":
                    return "production"
                elif level_name == "world-fresh":
                    return "fresh"
                elif level_name == "world-vanilla":
                    return "vanilla"
    return "unknown"


def show_status():
    """Display current server status"""
    mode = get_current_mode()
    running = is_server_running()

    mode_colors = {
        "production": "cyan",
        "fresh": "green",
        "vanilla": "yellow",
        "unknown": "dim"
    }
    mode_color = mode_colors.get(mode, "dim")
    status_color = "green" if running else "red"
    status_text = "RUNNING" if running else "STOPPED"

    console.print(f"\n[bold]Current Mode:[/bold] [{mode_color}]{mode.upper()}[/{mode_color}]")
    console.print(f"[bold]Server Status:[/bold] [{status_color}]{status_text}[/{status_color}]")

    # Show world folders
    console.print(f"\n[bold]World Folders:[/bold]")
    world_info = [
        ("world-production", "Backup from production (pristine)"),
        ("world-local", "Working copy for Production mode"),
        ("world-fresh", "Fresh World mode"),
        ("world-vanilla", "Vanilla Debug mode"),
    ]
    for world, description in world_info:
        path = os.path.join(SCRIPT_DIR, world)
        if os.path.exists(path):
            size = sum(os.path.getsize(os.path.join(dirpath, filename))
                      for dirpath, dirnames, filenames in os.walk(path)
                      for filename in filenames)
            size_str = f"{size / (1024*1024):.1f} MB" if size < 1024*1024*1024 else f"{size / (1024*1024*1024):.2f} GB"
            console.print(f"  [green]✓[/green] {world}/ ({size_str}) - {description}")
        else:
            console.print(f"  [dim]✗ {world}/ - {description}[/dim]")


# =============================================================================
# Server Control Functions
# =============================================================================

def start_server():
    """Start the Minecraft server"""
    if is_server_running():
        console.print("[yellow]Server is already running![/yellow]")
        return False

    # Check Java exists
    if not os.path.exists(JAVA_PATH):
        console.print(f"[red]Error: Java not found at {JAVA_PATH}[/red]")
        console.print("[yellow]Set JAVA_PATH in .env or install Java 21[/yellow]")
        return False

    # Check server JAR exists
    server_jar = os.path.join(SCRIPT_DIR, SERVER_JAR)
    if not os.path.exists(server_jar):
        console.print(f"[red]Error: {SERVER_JAR} not found![/red]")
        return False

    # Auto-detect vanilla mode from current server.properties
    current_mode = get_current_mode()
    is_vanilla = (current_mode == "vanilla")

    if is_vanilla:
        console.print("[yellow]Starting server in VANILLA mode (no packwiz sync)...[/yellow]")
    else:
        console.print(f"[cyan]Starting server in {current_mode.upper()} mode...[/cyan]")

    # Sync from packwiz if not vanilla mode
    if not is_vanilla:
        packwiz_bootstrap = os.path.join(SCRIPT_DIR, "packwiz-installer-bootstrap.jar")
        if os.path.exists(packwiz_bootstrap):
            console.print("[dim]Syncing mods from packwiz...[/dim]")
            try:
                subprocess.run(
                    [JAVA_PATH, "-jar", packwiz_bootstrap, "-g", "-s", "server", "http://localhost:8080/pack.toml"],
                    cwd=SCRIPT_DIR,
                    timeout=30,
                    capture_output=True
                )
            except subprocess.TimeoutExpired:
                console.print("[yellow]Packwiz sync timed out (packwiz serve may not be running)[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Packwiz sync failed: {e}[/yellow]")

    # Build command
    cmd = [JAVA_PATH] + JVM_FLAGS + ["-jar", SERVER_JAR, "nogui"]

    # Start server in new window
    if sys.platform == 'win32':
        subprocess.Popen(
            ["cmd", "/c", "start", "Minecraft Server", "cmd", "/k"] + cmd,
            cwd=SCRIPT_DIR
        )
    else:
        subprocess.Popen(cmd, cwd=SCRIPT_DIR)

    console.print("[green]✓ Server starting...[/green]")
    console.print("[dim]Server will open in a new window[/dim]")
    return True


def stop_server():
    """Stop the server via RCON"""
    if not is_server_running():
        console.print("[yellow]Server is not running[/yellow]")
        return False

    console.print("[cyan]Stopping server via RCON...[/cyan]")

    try:
        rcon = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
        if rcon.connect():
            rcon.command("stop")
            rcon.close()
            console.print("[green]✓ Stop command sent[/green]")
            return True
        else:
            console.print("[red]RCON authentication failed[/red]")
            return False
    except Exception as e:
        console.print(f"[red]RCON error: {e}[/red]")
        console.print("[yellow]You may need to stop the server manually[/yellow]")
        return False


def send_rcon_command(cmd):
    """Send a command via RCON"""
    if not is_server_running():
        console.print("[yellow]Server is not running[/yellow]")
        return None

    try:
        rcon = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
        if rcon.connect():
            response = rcon.command(cmd)
            rcon.close()
            return response
        else:
            console.print("[red]RCON authentication failed[/red]")
            return None
    except Exception as e:
        console.print(f"[red]RCON error: {e}[/red]")
        return None


# =============================================================================
# Mode Switching Functions
# =============================================================================

def switch_to_production_mode():
    """Switch local server to production mode"""
    console.print(Panel(
        "[bold]Production Mode Setup[/bold]\n\n"
        "This mode replicates production settings:\n"
        "  • Uses a copy of the production world backup\n"
        "  • Mobs enabled\n"
        "  • Configs synced from MCC\n"
        "  • Production-like server.properties\n\n"
        "[dim]The original backup (world-production) is preserved.[/dim]",
        title="[cyan]Mode Switch[/cyan]",
        border_style="cyan"
    ))

    # Check paths exist
    props_production = os.path.join(SCRIPT_DIR, "server.properties.production")
    if not os.path.exists(props_production):
        console.print(f"[red]Error: {props_production} not found![/red]")
        return False

    # Step 1: Switch server.properties
    console.print("\n[bold]Step 1/4: Switching to production server.properties...[/bold]")
    props_file = os.path.join(SCRIPT_DIR, "server.properties")
    shutil.copy(props_production, props_file)
    console.print("[green]✓ server.properties updated[/green]")

    # Step 2: Sync configs from MCC
    console.print("\n[bold]Step 2/4: Syncing configs from MCC...[/bold]")
    mcc_config = os.path.join(MCC_DIR, "config")
    local_config = os.path.join(SCRIPT_DIR, "config")

    if os.path.exists(mcc_config):
        os.makedirs(local_config, exist_ok=True)
        config_count = 0
        for item in os.listdir(mcc_config):
            src = os.path.join(mcc_config, item)
            dst = os.path.join(local_config, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            config_count += 1
        console.print(f"[green]✓ Synced {config_count} config items[/green]")
    else:
        console.print("[yellow]⚠ MCC config folder not found, skipping sync[/yellow]")

    # Step 3: Copy backup to working directory
    console.print("\n[bold]Step 3/4: Setting up world data...[/bold]")

    # World folder pairs: (backup, working)
    world_pairs = [
        ("world-production", "world-local"),
        ("world-production_nether", "world-local_nether"),
        ("world-production_the_end", "world-local_the_end"),
    ]

    backup_exists = os.path.exists(os.path.join(SCRIPT_DIR, "world-production"))
    working_exists = os.path.exists(os.path.join(SCRIPT_DIR, "world-local"))

    if backup_exists and not working_exists:
        # Copy backup to working directory
        console.print("[cyan]Copying backup to working directory...[/cyan]")
        for backup_name, working_name in world_pairs:
            backup_path = os.path.join(SCRIPT_DIR, backup_name)
            working_path = os.path.join(SCRIPT_DIR, working_name)
            if os.path.exists(backup_path):
                console.print(f"  Copying {backup_name} → {working_name}...")
                shutil.copytree(backup_path, working_path)
                console.print(f"  [green]✓ {working_name}[/green]")
        console.print("[green]✓ Working copy created from backup[/green]")
    elif backup_exists and working_exists:
        console.print("[green]✓ Using existing working copy (world-local)[/green]")
        console.print("[dim]  To reset from backup, use 'Reset Local World' option[/dim]")
    elif not backup_exists and working_exists:
        console.print("[yellow]⚠ No backup found, using existing world-local[/yellow]")
        console.print("[dim]  Run 'world-download' from MCC to get production backup[/dim]")
    else:
        console.print("[yellow]⚠ No world data found[/yellow]")
        console.print("[dim]  Run 'world-download' from MCC to get production backup,[/dim]")
        console.print("[dim]  or a new world will be generated on first start.[/dim]")

    # Step 4: Summary
    console.print("\n[bold]Step 4/4: Verification...[/bold]")
    console.print("[green]✓ Server will use: world-local[/green]")
    console.print("[dim]  Backup preserved: world-production[/dim]")

    # Summary
    console.print("\n" + "="*50)
    console.print("[bold green]✓ Production Mode Ready[/bold green]")
    console.print("="*50)

    return True


def switch_to_fresh_mode():
    """Switch local server to fresh world mode"""
    console.print(Panel(
        "[bold]Fresh World Mode Setup[/bold]\n\n"
        "Clean slate testing with all mods:\n"
        "  • Fresh world (normal terrain generation)\n"
        "  • All modpack mods installed\n"
        "  • Good for testing mod initialization\n\n"
        "[dim]World will be generated on first start.[/dim]",
        title="[green]Mode Switch[/green]",
        border_style="green"
    ))

    # Check paths exist
    props_fresh = os.path.join(SCRIPT_DIR, "server.properties.fresh")
    if not os.path.exists(props_fresh):
        console.print(f"[red]Error: {props_fresh} not found![/red]")
        return False

    # Switch server.properties
    console.print("\n[bold]Switching to fresh world server.properties...[/bold]")
    props_file = os.path.join(SCRIPT_DIR, "server.properties")
    shutil.copy(props_fresh, props_file)
    console.print("[green]✓ server.properties updated[/green]")

    # Summary
    console.print("\n" + "="*50)
    console.print("[bold green]✓ Fresh World Mode Ready[/bold green]")
    console.print("[dim]World folder: world-fresh/[/dim]")
    console.print("="*50)

    return True


def switch_to_vanilla_mode():
    """Switch local server to vanilla debug mode"""

    # Check if server is running
    if is_server_running():
        console.print("[red]Error: Server is currently running![/red]")
        console.print("[yellow]Stop the server first before switching to Vanilla mode.[/yellow]")
        console.print("[dim]Vanilla mode needs to delete mod files, which can't be done while the server has them open.[/dim]")
        return False

    console.print(Panel(
        "[bold]Vanilla Debug Mode Setup[/bold]\n\n"
        "Fabric-only testing (no modpack mods):\n"
        "  • Fresh world (normal terrain generation)\n"
        "  • Only Fabric API installed\n"
        "  • Good for isolating mod issues\n\n"
        "[yellow]Note: This clears all mods except Fabric API.[/yellow]",
        title="[yellow]Mode Switch[/yellow]",
        border_style="yellow"
    ))

    # Check paths exist
    props_vanilla = os.path.join(SCRIPT_DIR, "server.properties.vanilla")
    if not os.path.exists(props_vanilla):
        console.print(f"[red]Error: {props_vanilla} not found![/red]")
        return False

    # Switch server.properties
    console.print("\n[bold]Step 1/2: Switching to vanilla server.properties...[/bold]")
    props_file = os.path.join(SCRIPT_DIR, "server.properties")
    shutil.copy(props_vanilla, props_file)
    console.print("[green]✓ server.properties updated[/green]")

    # Clear mods (keep only Fabric API)
    console.print("\n[bold]Step 2/2: Clearing mods (keeping Fabric API)...[/bold]")
    mods_dir = os.path.join(SCRIPT_DIR, "mods")
    if os.path.exists(mods_dir):
        all_jars = [f for f in os.listdir(mods_dir) if f.endswith('.jar')]
        fabric_api = [f for f in all_jars if 'fabric-api' in f.lower()]
        to_remove = [f for f in all_jars if f not in fabric_api]

        removed = 0
        for f in to_remove:
            try:
                os.remove(os.path.join(mods_dir, f))
                removed += 1
            except PermissionError:
                console.print(f"\n[red]Error: Cannot delete '{f}' - file is locked![/red]")
                console.print("\n[yellow]Something is holding this file open. Common causes:[/yellow]")
                console.print("  • Minecraft client (Prism Launcher instance running)")
                console.print("  • File explorer with mods folder open")
                console.print("  • Antivirus scanning the folder")
                console.print("  • IDE or editor with the folder indexed")
                console.print("\n[cyan]To find the culprit on Windows:[/cyan]")
                console.print("  1. Open Resource Monitor (resmon.exe)")
                console.print("  2. Go to CPU tab → Associated Handles")
                console.print("  3. Search for: LocalServer")
                return False

        # Also remove .pw.toml files
        pw_files = [f for f in os.listdir(mods_dir) if f.endswith('.pw.toml')]
        for f in pw_files:
            try:
                os.remove(os.path.join(mods_dir, f))
            except PermissionError:
                pass  # Not critical

        console.print(f"[green]✓ Removed {removed} mods, kept {len(fabric_api)} Fabric API[/green]")
    else:
        console.print("[yellow]No mods folder found[/yellow]")

    # Summary
    console.print("\n" + "="*50)
    console.print("[bold green]✓ Vanilla Debug Mode Ready[/bold green]")
    console.print("[dim]World folder: world-vanilla/[/dim]")
    console.print("[dim]To restore mods: Switch to Production or Fresh mode[/dim]")
    console.print("="*50)

    return True


# =============================================================================
# World Management Functions
# =============================================================================

def get_remote_directory_info(sftp, path):
    """Calculate total size and file count of a remote directory recursively."""
    total_size = 0
    file_count = 0

    def scan_recursive(remote_path):
        nonlocal total_size, file_count
        try:
            for item in sftp.listdir_attr(remote_path):
                item_path = f"{remote_path}/{item.filename}"
                if item.st_mode & 0o40000:
                    scan_recursive(item_path)
                else:
                    total_size += item.st_size
                    file_count += 1
        except IOError:
            pass

    try:
        sftp.stat(path)
        scan_recursive(path)
    except IOError:
        pass

    return file_count, total_size


def download_directory_recursive(sftp, remote_path, local_path, tracker, base_path=None):
    """Download a remote directory recursively to local path with progress tracking."""
    if base_path is None:
        base_path = local_path

    os.makedirs(local_path, exist_ok=True)

    try:
        for item in sftp.listdir_attr(remote_path):
            remote_item = f"{remote_path}/{item.filename}"
            local_item = os.path.join(local_path, item.filename)

            if item.st_mode & 0o40000:
                download_directory_recursive(sftp, remote_item, local_item, tracker, base_path)
            else:
                try:
                    rel_path = os.path.relpath(local_item, base_path)
                    tracker.start_file(rel_path, item.st_size)
                    sftp.get(remote_item, local_item, callback=progress_callback(tracker))
                    tracker.file_complete(success=True)
                except Exception as e:
                    tracker.file_complete(success=False)
                    console.print(f"[red]Error downloading {item.filename}: {e}[/red]")
    except IOError as e:
        console.print(f"[red]Error accessing {remote_path}: {e}[/red]")


def backup_local_world(world_dirs):
    """Backup existing local world directories before overwriting."""
    existing_dirs = [d for d in world_dirs if os.path.exists(d)]
    if not existing_dirs:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_base = os.path.join(SCRIPT_DIR, f"world-backup-{timestamp}")
    os.makedirs(backup_base, exist_ok=True)

    for world_dir in existing_dirs:
        dir_name = os.path.basename(world_dir)
        backup_dest = os.path.join(backup_base, dir_name)
        console.print(f"[cyan]Backing up {dir_name}...[/cyan]")
        shutil.copytree(world_dir, backup_dest)
        console.print(f"[green]✓ Backed up {dir_name}[/green]")

    return backup_base


def download_world(backup_existing=True, auto_confirm=False):
    """Download world data from production server."""
    from rich.prompt import Confirm

    WORLD_FOLDERS = [
        ("/world", "world-production"),
        ("/world_nether", "world-production_nether"),
        ("/world_the_end", "world-production_the_end"),
    ]

    console.print(Panel(
        "[bold]Download Production World[/bold]\n\n"
        "This will download world data from the production server\n"
        "to your local test environment.",
        title="[cyan]World Sync[/cyan]",
        border_style="cyan"
    ))

    if not check_sftp_credentials():
        return False

    console.print(f"\n[cyan]Connecting to {SFTP_HOST}:{SFTP_PORT}...[/cyan]")

    ssh, sftp = get_sftp_connection()
    if not sftp:
        return False

    console.print("[green]Connected![/green]")
    console.print("\n[cyan]Scanning remote world folders...[/cyan]")

    folder_info = []
    total_files = 0
    total_size = 0

    for remote_path, local_name in WORLD_FOLDERS:
        file_count, size = get_remote_directory_info(sftp, remote_path)
        if file_count > 0:
            folder_info.append({
                'remote': remote_path,
                'local': local_name,
                'files': file_count,
                'size': size
            })
            total_files += file_count
            total_size += size
        else:
            console.print(f"[dim]  {remote_path} (not found, skipping)[/dim]")

    if not folder_info:
        console.print("[red]No world folders found on remote server![/red]")
        sftp.close()
        ssh.close()
        return False

    size_str = f"{total_size/(1024*1024*1024):.2f} GB" if total_size > 1024*1024*1024 else f"{total_size/(1024*1024):.1f} MB"

    table = Table(title="Remote World Folders", box=box.ROUNDED)
    table.add_column("Folder", style="cyan")
    table.add_column("Files", style="white", justify="right")
    table.add_column("Size", style="green", justify="right")

    for info in folder_info:
        folder_size = f"{info['size']/(1024*1024*1024):.2f} GB" if info['size'] > 1024*1024*1024 else f"{info['size']/(1024*1024):.1f} MB"
        table.add_row(info['remote'], str(info['files']), folder_size)

    table.add_row("", "", "", style="dim")
    table.add_row("[bold]Total[/bold]", f"[bold]{total_files}[/bold]", f"[bold]{size_str}[/bold]")

    console.print()
    console.print(table)

    # Check for local server running
    session_lock = os.path.join(SCRIPT_DIR, "world-production", "session.lock")
    if os.path.exists(session_lock):
        console.print("\n[yellow]⚠ Warning: Local server may be running (session.lock exists)[/yellow]")
        if not auto_confirm and not Confirm.ask("Continue anyway?"):
            console.print("[yellow]Cancelled.[/yellow]")
            sftp.close()
            ssh.close()
            return False

    if not auto_confirm:
        console.print()
        if not Confirm.ask(f"Download {size_str} from production server?"):
            console.print("[yellow]Cancelled.[/yellow]")
            sftp.close()
            ssh.close()
            return False

    # Backup existing local world
    if backup_existing:
        local_world_dirs = [os.path.join(SCRIPT_DIR, info['local']) for info in folder_info]
        existing_dirs = [d for d in local_world_dirs if os.path.exists(d)]
        if existing_dirs:
            console.print("\n[bold]Backing up existing world...[/bold]")
            backup_path = backup_local_world(local_world_dirs)
            if backup_path:
                console.print(f"[green]✓ Backup saved to: {os.path.basename(backup_path)}/[/green]")

    # Download each folder
    console.print("\n[bold]Downloading world data...[/bold]\n")

    with RichProgressTracker(total_files=total_files, total_size=total_size) as tracker:
        for info in folder_info:
            local_path = os.path.join(SCRIPT_DIR, info['local'])

            if os.path.exists(local_path):
                shutil.rmtree(local_path)

            console.print(f"[cyan]Downloading {info['remote']}...[/cyan]")
            download_directory_recursive(sftp, info['remote'], local_path, tracker)

    sftp.close()
    ssh.close()

    console.print("\n" + "="*50)
    console.print("[bold green]✓ World download complete![/bold green]")
    console.print(f"\n[cyan]Downloaded {total_files} files ({size_str})[/cyan]")
    console.print("="*50)

    return True


def reset_world(mode):
    """Delete world folders for specified mode"""
    from rich.prompt import Confirm

    world_map = {
        "fresh": ["world-fresh", "world-fresh_nether", "world-fresh_the_end"],
        "vanilla": ["world-vanilla", "world-vanilla_nether", "world-vanilla_the_end"],
        "production": ["world-production", "world-production_nether", "world-production_the_end"],
        "local": ["world-local", "world-local_nether", "world-local_the_end"],
    }

    if mode not in world_map:
        console.print(f"[red]Unknown mode: {mode}[/red]")
        console.print(f"[dim]Valid modes: {', '.join(world_map.keys())}[/dim]")
        return False

    world_dirs = world_map[mode]
    existing = [d for d in world_dirs if os.path.exists(os.path.join(SCRIPT_DIR, d))]

    if not existing:
        console.print(f"[yellow]No {mode} world folders found[/yellow]")
        return True

    console.print(Panel(
        f"[bold red]Delete {mode.upper()} World[/bold red]\n\n"
        f"This will permanently delete:\n" +
        "\n".join(f"  • {d}/" for d in existing),
        title="[red]⚠ Warning[/red]",
        border_style="red"
    ))

    if not Confirm.ask(f"[red]Delete {mode} world folders?[/red]"):
        console.print("[yellow]Cancelled.[/yellow]")
        return False

    for d in existing:
        path = os.path.join(SCRIPT_DIR, d)
        console.print(f"[cyan]Deleting {d}...[/cyan]")
        shutil.rmtree(path)
        console.print(f"[green]✓ Deleted {d}[/green]")

    console.print(f"\n[green]✓ {mode.capitalize()} world reset complete[/green]")
    return True


def reset_local_world():
    """Reset world-local by copying fresh from world-production backup"""
    from rich.prompt import Confirm

    # World folder pairs: (backup, working)
    world_pairs = [
        ("world-production", "world-local"),
        ("world-production_nether", "world-local_nether"),
        ("world-production_the_end", "world-local_the_end"),
    ]

    backup_path = os.path.join(SCRIPT_DIR, "world-production")
    working_path = os.path.join(SCRIPT_DIR, "world-local")

    if not os.path.exists(backup_path):
        console.print("[red]Error: No backup found (world-production)[/red]")
        console.print("[dim]Run 'world-download' from MCC first to get production backup.[/dim]")
        return False

    # Check what exists
    existing_working = [name for _, name in world_pairs
                        if os.path.exists(os.path.join(SCRIPT_DIR, name))]

    console.print(Panel(
        "[bold yellow]Reset Local World[/bold yellow]\n\n"
        "This will:\n"
        "  1. Delete current world-local folders\n"
        "  2. Copy fresh data from world-production backup\n\n"
        "[dim]The backup (world-production) will NOT be modified.[/dim]",
        title="[yellow]⚠ Reset Working Copy[/yellow]",
        border_style="yellow"
    ))

    if existing_working:
        console.print("\n[yellow]Will be deleted:[/yellow]")
        for name in existing_working:
            console.print(f"  • {name}/")

    if not Confirm.ask("\n[yellow]Reset local world from backup?[/yellow]"):
        console.print("[dim]Cancelled.[/dim]")
        return False

    # Delete existing working folders
    for _, working_name in world_pairs:
        working = os.path.join(SCRIPT_DIR, working_name)
        if os.path.exists(working):
            console.print(f"[cyan]Deleting {working_name}...[/cyan]")
            shutil.rmtree(working)

    # Copy from backup
    console.print("\n[cyan]Copying from backup...[/cyan]")
    for backup_name, working_name in world_pairs:
        backup = os.path.join(SCRIPT_DIR, backup_name)
        working = os.path.join(SCRIPT_DIR, working_name)
        if os.path.exists(backup):
            console.print(f"  {backup_name} → {working_name}...")
            shutil.copytree(backup, working)
            console.print(f"  [green]✓ {working_name}[/green]")

    console.print("\n[green]✓ Local world reset from backup[/green]")
    return True


# =============================================================================
# Utility Functions
# =============================================================================

def clear_mods():
    """Remove all mods except Fabric API"""
    from rich.prompt import Confirm

    mods_dir = os.path.join(SCRIPT_DIR, "mods")
    if not os.path.exists(mods_dir):
        console.print("[yellow]No mods folder found[/yellow]")
        return True

    # Count mods
    all_jars = [f for f in os.listdir(mods_dir) if f.endswith('.jar')]
    fabric_api = [f for f in all_jars if 'fabric-api' in f.lower()]
    to_remove = [f for f in all_jars if f not in fabric_api]

    if not to_remove:
        console.print("[green]Only Fabric API found, nothing to remove[/green]")
        return True

    console.print(Panel(
        f"[bold]Clear Mods[/bold]\n\n"
        f"Found {len(all_jars)} mod JARs\n"
        f"  • Keeping: {len(fabric_api)} (Fabric API)\n"
        f"  • Removing: {len(to_remove)} mods",
        title="[cyan]Mod Cleanup[/cyan]",
        border_style="cyan"
    ))

    if not Confirm.ask("Remove non-API mods?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return False

    for f in to_remove:
        os.remove(os.path.join(mods_dir, f))

    # Also remove .pw.toml files
    pw_files = [f for f in os.listdir(mods_dir) if f.endswith('.pw.toml')]
    for f in pw_files:
        os.remove(os.path.join(mods_dir, f))

    console.print(f"[green]✓ Removed {len(to_remove)} mods and {len(pw_files)} .pw.toml files[/green]")
    return True


# =============================================================================
# Interactive Menu
# =============================================================================

def interactive_menu():
    """Show an interactive menu"""
    from rich.prompt import Prompt

    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]LocalServer Manager[/bold cyan]\n"
            "[dim]Local Test Server Control[/dim]",
            border_style="cyan"
        ))

        # Show status
        mode = get_current_mode()
        running = is_server_running()
        mode_colors = {
            "production": "cyan",
            "fresh": "green",
            "vanilla": "yellow",
            "unknown": "dim"
        }
        mode_color = mode_colors.get(mode, "dim")
        status_color = "green" if running else "red"
        status_text = "RUNNING" if running else "STOPPED"

        console.print(f"\nMode: [{mode_color}]{mode.upper()}[/{mode_color}] | Server: [{status_color}]{status_text}[/{status_color}]")
        console.print()

        # Menu options
        table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        table.add_column("Key", style="bold yellow")
        table.add_column("Action", style="white")

        table.add_row("1", "Start Server")
        table.add_row("2", "Stop Server (RCON)")
        table.add_row("", "")
        table.add_row("", "[dim]── Server Mode ──[/dim]")
        table.add_row("p", "[cyan]Production Mode[/cyan] (copy of backup, all mods)")
        table.add_row("f", "[green]Fresh World Mode[/green] (new world, all mods)")
        table.add_row("v", "[yellow]Vanilla Debug Mode[/yellow] (new world, Fabric only)")
        table.add_row("", "")
        table.add_row("", "[dim]── World Management ──[/dim]")
        table.add_row("3", "[dim]Download Backup (use MCC/server-config.py)[/dim]")
        table.add_row("4", "Reset Local World (from backup)")
        table.add_row("5", "Delete Fresh World")
        table.add_row("6", "Delete Vanilla World")
        table.add_row("7", "[red]Delete Production Backup[/red]")
        table.add_row("", "")
        table.add_row("", "[dim]── Utilities ──[/dim]")
        table.add_row("r", "Send RCON Command")
        table.add_row("s", "Show Status")
        table.add_row("", "")
        table.add_row("q", "Quit")

        console.print(table)
        console.print()

        choice = Prompt.ask("Select", choices=["1", "2", "3", "4", "5", "6", "7", "p", "f", "v", "r", "s", "q"], default="q")

        if choice == "1":
            start_server()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "2":
            stop_server()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "p":
            switch_to_production_mode()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "f":
            switch_to_fresh_mode()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "v":
            switch_to_vanilla_mode()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "3":
            console.print("\n[yellow]This command has moved to MCC/server-config.py[/yellow]")
            console.print("[cyan]Run from MCC directory:[/cyan]")
            console.print("  python server-config.py world-download")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "4":
            reset_local_world()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "5":
            reset_world("fresh")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "6":
            reset_world("vanilla")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "7":
            reset_world("production")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "r":
            cmd = Prompt.ask("Enter RCON command")
            if cmd:
                response = send_rcon_command(cmd)
                if response:
                    console.print(f"[green]Response:[/green] {response}")
                else:
                    console.print("[yellow]No response or command failed[/yellow]")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "s":
            show_status()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "q":
            console.print("[dim]Goodbye![/dim]")
            break


# =============================================================================
# Main / CLI
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "start":
            start_server()
        elif command == "stop":
            stop_server()
        elif command == "status":
            show_status()
        elif command == "mode":
            if len(sys.argv) < 3:
                console.print("[yellow]Usage: python server-config.py mode <production|fresh|vanilla>[/yellow]")
            elif sys.argv[2] == "production":
                switch_to_production_mode()
            elif sys.argv[2] == "fresh":
                switch_to_fresh_mode()
            elif sys.argv[2] == "vanilla":
                switch_to_vanilla_mode()
            else:
                console.print(f"[red]Unknown mode: {sys.argv[2]}[/red]")
                console.print("[dim]Valid modes: production, fresh, vanilla[/dim]")
        elif command == "reset-world":
            if len(sys.argv) < 3:
                console.print("[yellow]Usage: python server-config.py reset-world <fresh|vanilla|production|local>[/yellow]")
            else:
                reset_world(sys.argv[2])
        elif command == "reset-local":
            reset_local_world()
        elif command == "clear-mods":
            clear_mods()
        elif command == "rcon":
            if len(sys.argv) < 3:
                console.print("[yellow]Usage: python server-config.py rcon <command>[/yellow]")
            else:
                cmd = " ".join(sys.argv[2:])
                response = send_rcon_command(cmd)
                if response:
                    console.print(response)
        else:
            console.print("[yellow]Usage:[/yellow]")
            console.print("  python server-config.py              # Interactive menu")
            console.print("  python server-config.py start        # Start server")
            console.print("  python server-config.py stop         # Stop server via RCON")
            console.print("  python server-config.py status       # Show current status")
            console.print("")
            console.print("[yellow]Server Mode:[/yellow]")
            console.print("  python server-config.py mode production  # Copy of backup, all mods")
            console.print("  python server-config.py mode fresh       # New world, all mods")
            console.print("  python server-config.py mode vanilla     # New world, Fabric only")
            console.print("")
            console.print("[yellow]World Management:[/yellow]")
            console.print("  python server-config.py reset-local      # Reset world-local from backup")
            console.print("  python server-config.py reset-world <mode>  # Delete world folders")
            console.print("                                           # (fresh, vanilla, production, local)")
            console.print("")
            console.print("[dim]Note: Backup sync commands are in MCC/server-config.py:[/dim]")
            console.print("[dim]  world-download  - Download production → world-production (backup)[/dim]")
            console.print("[dim]  world-upload    - Upload world-production → production server[/dim]")
            console.print("")
            console.print("[yellow]Utilities:[/yellow]")
            console.print("  python server-config.py clear-mods   # Remove non-API mods")
            console.print("  python server-config.py rcon <cmd>   # Send RCON command")
    else:
        interactive_menu()
