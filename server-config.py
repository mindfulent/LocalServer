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


# =============================================================================
# Git Helpers (for MCC version management)
# =============================================================================

def get_mcc_git_tags():
    """Get all version tags from MCC repository, sorted by version number descending."""
    try:
        result = subprocess.run(
            ["git", "tag", "--list", "v*"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return []

        tags = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]

        # Sort by version number (v0.9.1, v0.9.2, ... v0.9.10, v0.9.11)
        def version_key(tag):
            # Extract version numbers from tag like "v0.9.32"
            parts = tag.lstrip('v').split('.')
            try:
                return tuple(int(p) for p in parts)
            except ValueError:
                return (0, 0, 0)

        tags.sort(key=version_key, reverse=True)
        return tags
    except Exception:
        return []


def get_mcc_current_version():
    """Get the current version/branch of MCC repository."""
    try:
        # First try to get exact tag if HEAD is at a tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip(), "tag"

        # Otherwise get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), "branch"

        # Fallback: detached HEAD, show short commit
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip(), "commit"

        return "unknown", "unknown"
    except Exception:
        return "unknown", "unknown"


def is_mcc_dirty():
    """Check if MCC repository has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def get_mcc_dirty_summary():
    """Get a brief summary of uncommitted changes in MCC."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return []

        lines = result.stdout.strip().split('\n')
        return [l.strip() for l in lines if l.strip()][:10]  # Max 10 lines
    except Exception:
        return []


def stash_mcc_changes():
    """Stash uncommitted changes in MCC repository."""
    try:
        result = subprocess.run(
            ["git", "stash", "push", "-m", "LocalServer: auto-stash before version switch"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def checkout_mcc_version(tag):
    """Checkout a specific tag in MCC repository."""
    try:
        result = subprocess.run(
            ["git", "checkout", tag],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def has_mcc_stash():
    """Check if there are stashed changes in MCC (from our auto-stash)."""
    try:
        result = subprocess.run(
            ["git", "stash", "list"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )
        # Look for our auto-stash message
        return "LocalServer: auto-stash" in result.stdout
    except Exception:
        return False


def pop_mcc_stash():
    """Pop the most recent stash in MCC repository."""
    try:
        result = subprocess.run(
            ["git", "stash", "pop"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stderr.strip() if result.stderr else result.stdout.strip()
    except Exception as e:
        return False, str(e)

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
# Mod Sync Functions
# =============================================================================

def export_mrpack():
    """Export mrpack using packwiz in MCC directory"""
    packwiz_exe = os.path.join(MCC_DIR, "packwiz.exe")
    if not os.path.exists(packwiz_exe):
        console.print(f"[red]Error: packwiz.exe not found at {packwiz_exe}[/red]")
        return False

    console.print("[cyan]Exporting mrpack from MCC...[/cyan]")
    try:
        result = subprocess.run(
            [packwiz_exe, "modrinth", "export"],
            cwd=MCC_DIR,
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes for large packs
        )
        if result.returncode != 0:
            console.print(f"[red]Export failed: {result.stderr[:500] if result.stderr else 'unknown error'}[/red]")
            return False
        console.print("[green]✓ mrpack exported[/green]")
        return True
    except subprocess.TimeoutExpired:
        console.print("[red]Export timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Export error: {e}[/red]")
        return False


def find_latest_mrpack(auto_export=True):
    """Find the most recent .mrpack file in MCC directory.

    If auto_export is True and no mrpack exists, will automatically
    run packwiz modrinth export to create one.
    """
    import glob
    mrpacks = glob.glob(os.path.join(MCC_DIR, "MCC-*.mrpack"))

    if not mrpacks and auto_export:
        console.print("[yellow]No mrpack found - exporting from packwiz...[/yellow]")
        if export_mrpack():
            mrpacks = glob.glob(os.path.join(MCC_DIR, "MCC-*.mrpack"))

    if not mrpacks:
        return None
    # Sort by modification time, newest first
    mrpacks.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return mrpacks[0]


def sync_mods_from_mrpack():
    """Sync mods by extracting from the latest .mrpack file.

    This is more reliable than packwiz-installer because the .mrpack
    already contains all JARs, avoiding CurseForge API restrictions.
    """
    import zipfile
    import json

    mrpack_path = find_latest_mrpack(auto_export=True)
    if not mrpack_path:
        console.print("[red]Failed to find or create mrpack![/red]")
        console.print("[yellow]Check that MCC directory exists and packwiz.exe works.[/yellow]")
        return False

    mrpack_name = os.path.basename(mrpack_path)
    console.print(f"[cyan]Syncing mods from {mrpack_name}...[/cyan]")

    mods_dir = os.path.join(SCRIPT_DIR, "mods")
    config_dir = os.path.join(SCRIPT_DIR, "config")

    try:
        with zipfile.ZipFile(mrpack_path, 'r') as zf:
            # Read manifest to understand structure
            manifest_data = zf.read('modrinth.index.json')
            manifest = json.loads(manifest_data)

            # Count items
            mod_count = 0
            config_count = 0

            # Extract mods (from overrides/mods/)
            for name in zf.namelist():
                if name.startswith('overrides/mods/') and name.endswith('.jar'):
                    # Extract just the filename
                    filename = os.path.basename(name)
                    if filename:  # Skip directory entries
                        dest_path = os.path.join(mods_dir, filename)
                        os.makedirs(mods_dir, exist_ok=True)
                        with zf.open(name) as src, open(dest_path, 'wb') as dst:
                            dst.write(src.read())
                        mod_count += 1

                # Extract configs (from overrides/config/)
                elif name.startswith('overrides/config/'):
                    rel_path = name[len('overrides/config/'):]
                    if rel_path:  # Skip directory entries
                        dest_path = os.path.join(config_dir, rel_path)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        if not name.endswith('/'):  # Skip directories
                            with zf.open(name) as src, open(dest_path, 'wb') as dst:
                                dst.write(src.read())
                            config_count += 1

            # Also handle files listed in manifest (downloaded mods)
            # These are referenced by URL in the manifest
            files_in_manifest = len(manifest.get('files', []))

            console.print(f"[green]✓ Extracted {mod_count} bundled mods, {config_count} configs[/green]")
            if files_in_manifest > 0:
                console.print(f"[dim]  Note: {files_in_manifest} mods referenced by URL (handled by mrpack4server on production)[/dim]")

            return True

    except zipfile.BadZipFile:
        console.print(f"[red]Error: {mrpack_name} is not a valid zip file[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error extracting mrpack: {e}[/red]")
        return False


def download_mod_from_url(url, dest_path):
    """Download a mod JAR from URL"""
    import urllib.request
    import urllib.error

    try:
        # Handle CurseForge edge CDN URLs
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(dest_path, 'wb') as f:
                f.write(response.read())
        return True
    except urllib.error.HTTPError as e:
        console.print(f"[red]HTTP Error {e.code}: {e.reason}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/red]")
        return False


def sync_mods_full():
    """Full mod sync - extracts bundled mods and downloads referenced mods.

    This handles the complete mrpack format where:
    - Some mods are bundled in overrides/mods/
    - Other mods are referenced by URL in the manifest

    Also removes stale mods that are no longer in the pack.
    """
    import zipfile
    import json
    from rich.prompt import Confirm

    # Check if server is running - can't sync while mods are in use
    if is_server_running():
        console.print("[yellow]Server is currently running![/yellow]")
        console.print("[dim]Mod files are locked while the server is running.[/dim]")
        if not Confirm.ask("Stop server before syncing?"):
            console.print("[dim]Sync cancelled.[/dim]")
            return False
        stop_server()
        # Wait a moment for server to release files
        import time
        console.print("[dim]Waiting for server to stop...[/dim]")
        time.sleep(3)

    mrpack_path = find_latest_mrpack(auto_export=True)
    if not mrpack_path:
        console.print("[red]Failed to find or create mrpack![/red]")
        console.print("[yellow]Check that MCC directory exists and packwiz.exe works.[/yellow]")
        return False

    mrpack_name = os.path.basename(mrpack_path)
    console.print(f"[cyan]Full sync from {mrpack_name}...[/cyan]")

    mods_dir = os.path.join(SCRIPT_DIR, "mods")
    config_dir = os.path.join(SCRIPT_DIR, "config")
    os.makedirs(mods_dir, exist_ok=True)

    bundled_count = 0
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0
    config_count = 0
    removed_count = 0
    stale_locked_count = 0

    try:
        with zipfile.ZipFile(mrpack_path, 'r') as zf:
            # Read manifest
            manifest_data = zf.read('modrinth.index.json')
            manifest = json.loads(manifest_data)

            # Build set of expected mod filenames from mrpack
            expected_mods = set()

            # From bundled overrides
            for name in zf.namelist():
                if name.startswith('overrides/mods/') and name.endswith('.jar'):
                    filename = os.path.basename(name)
                    if filename:
                        expected_mods.add(filename)

            # From manifest downloads
            for file_info in manifest.get('files', []):
                path = file_info.get('path', '')
                if path.startswith('mods/') and path.endswith('.jar'):
                    expected_mods.add(os.path.basename(path))

            # 0. Remove stale mods not in the mrpack
            console.print("[cyan]Checking for stale mods...[/cyan]")
            if os.path.exists(mods_dir):
                existing_jars = [f for f in os.listdir(mods_dir) if f.endswith('.jar')]
                for jar in existing_jars:
                    if jar not in expected_mods:
                        jar_path = os.path.join(mods_dir, jar)
                        try:
                            os.remove(jar_path)
                            console.print(f"[yellow]  Removed stale: {jar}[/yellow]")
                            removed_count += 1
                        except PermissionError:
                            console.print(f"[red]  Cannot remove (in use): {jar}[/red]")
                            stale_locked_count += 1

            if removed_count > 0:
                console.print(f"[green]✓ Removed {removed_count} stale mod(s)[/green]")
            if stale_locked_count > 0:
                console.print(f"[red]✗ {stale_locked_count} stale mod(s) locked - stop server and retry[/red]")
            if removed_count == 0 and stale_locked_count == 0:
                console.print("[dim]  No stale mods found[/dim]")

            # 1. Extract bundled files from overrides/
            for name in zf.namelist():
                if name.startswith('overrides/mods/') and name.endswith('.jar'):
                    filename = os.path.basename(name)
                    if filename:
                        dest_path = os.path.join(mods_dir, filename)
                        with zf.open(name) as src, open(dest_path, 'wb') as dst:
                            dst.write(src.read())
                        bundled_count += 1

                elif name.startswith('overrides/config/'):
                    rel_path = name[len('overrides/config/'):]
                    if rel_path and not name.endswith('/'):
                        dest_path = os.path.join(config_dir, rel_path)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with zf.open(name) as src, open(dest_path, 'wb') as dst:
                            dst.write(src.read())
                        config_count += 1

            # 2. Download mods referenced in manifest
            manifest_files = manifest.get('files', [])
            mod_files = [f for f in manifest_files if f.get('path', '').startswith('mods/')]

            if mod_files:
                console.print(f"[cyan]Downloading {len(mod_files)} mods from URLs...[/cyan]")

                for mod_info in mod_files:
                    path = mod_info.get('path', '')
                    filename = os.path.basename(path)
                    dest_path = os.path.join(SCRIPT_DIR, path)

                    # Check if already exists with correct hash
                    if os.path.exists(dest_path):
                        skipped_count += 1
                        continue

                    # Get download URL
                    downloads = mod_info.get('downloads', [])
                    if not downloads:
                        console.print(f"[yellow]  No download URL for {filename}[/yellow]")
                        failed_count += 1
                        continue

                    url = downloads[0]
                    console.print(f"[dim]  Downloading {filename}...[/dim]")

                    if download_mod_from_url(url, dest_path):
                        downloaded_count += 1
                    else:
                        console.print(f"[red]  Failed: {filename}[/red]")
                        failed_count += 1

            # Summary
            console.print(f"\n[green]✓ Sync complete:[/green]")
            if removed_count > 0:
                console.print(f"  • Stale mods removed: {removed_count}")
            if stale_locked_count > 0:
                console.print(f"  [red]• Stale mods locked (couldn't remove): {stale_locked_count}[/red]")
            console.print(f"  • Bundled mods extracted: {bundled_count}")
            console.print(f"  • Mods downloaded: {downloaded_count}")
            if skipped_count > 0:
                console.print(f"  • Already up to date: {skipped_count}")
            if failed_count > 0:
                console.print(f"  [red]• Failed: {failed_count}[/red]")
            console.print(f"  • Config files: {config_count}")

            return failed_count == 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return False


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
        # Set up auto-op for local testing
        setup_auto_op()

    # Sync mods from mrpack if not vanilla mode
    if not is_vanilla:
        # Check if mods are missing
        mods_dir = os.path.join(SCRIPT_DIR, "mods")
        existing_jars = []
        if os.path.exists(mods_dir):
            existing_jars = [f for f in os.listdir(mods_dir) if f.endswith('.jar')]

        if len(existing_jars) < 10:  # Likely missing most mods
            console.print(f"[yellow]Only {len(existing_jars)} mod JARs found - syncing from mrpack...[/yellow]")
            if not sync_mods_full():
                from rich.prompt import Confirm
                if not Confirm.ask("[yellow]Start server anyway (mods may be missing)?[/yellow]", default=False):
                    return False
        else:
            console.print(f"[green]✓ {len(existing_jars)} mods already present[/green]")

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

def setup_auto_op():
    """Configure LuckPerms to auto-op all players on LocalServer.

    This is for local testing only - makes everyone op automatically.
    """
    lp_config = os.path.join(SCRIPT_DIR, "config", "luckperms", "luckperms.conf")
    lp_groups = os.path.join(SCRIPT_DIR, "config", "luckperms", "yaml-storage", "groups")

    if not os.path.exists(lp_config):
        return  # LuckPerms not configured yet, will be set up on first run

    # Check if already configured
    with open(lp_config, 'r') as f:
        content = f.read()

    changes_made = False

    # Switch to YAML storage if needed
    if 'storage-method = "h2"' in content:
        content = content.replace('storage-method = "h2"', 'storage-method = "yaml"')
        changes_made = True

    # Enable auto-op if needed
    if 'auto-op = false' in content:
        content = content.replace('auto-op = false', 'auto-op = true')
        changes_made = True

    if changes_made:
        with open(lp_config, 'w') as f:
            f.write(content)
        console.print("[green]✓ LuckPerms configured for auto-op[/green]")

    # Create default group with autoop permission
    os.makedirs(lp_groups, exist_ok=True)
    default_group = os.path.join(lp_groups, "default.yml")

    if not os.path.exists(default_group):
        with open(default_group, 'w') as f:
            f.write('name: default\npermissions:\n  - "luckperms.autoop"\n  - "*"\n')
        console.print("[green]✓ Created default group with op permissions[/green]")


def switch_to_production_mode():
    """Switch local server to production mode"""

    # Check if mods are missing (e.g., coming from Vanilla mode)
    mods_dir = os.path.join(SCRIPT_DIR, "mods")
    if os.path.exists(mods_dir):
        jar_count = len([f for f in os.listdir(mods_dir) if f.endswith('.jar')])
        if jar_count < 5:
            console.print("[yellow]⚠ Warning: Only {0} mod JAR(s) found in mods/[/yellow]".format(jar_count))
            console.print("[yellow]  Mods will be restored when you start the server[/yellow]")
            console.print("[yellow]  (requires 'packwiz serve' running in MCC directory)[/yellow]")
            console.print()

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

    # Step 1: Restore packwiz-installer if disabled
    console.print("\n[bold]Step 1/5: Checking packwiz-installer...[/bold]")
    if restore_packwiz_installer():
        console.print("[dim]  (Was disabled from Vanilla mode)[/dim]")
    else:
        console.print("[dim]  Packwiz-installer ready[/dim]")

    # Step 2: Switch server.properties
    console.print("\n[bold]Step 2/5: Switching to production server.properties...[/bold]")
    props_file = os.path.join(SCRIPT_DIR, "server.properties")
    shutil.copy(props_production, props_file)
    console.print("[green]✓ server.properties updated[/green]")

    # Step 3: Sync configs from MCC
    console.print("\n[bold]Step 3/5: Syncing configs from MCC...[/bold]")
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

    # Step 4: Copy backup to working directory
    console.print("\n[bold]Step 4/5: Setting up world data...[/bold]")

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

    # Step 5: Summary
    console.print("\n[bold]Step 5/5: Verification...[/bold]")
    console.print("[green]✓ Server will use: world-local[/green]")
    console.print("[dim]  Backup preserved: world-production[/dim]")

    # Summary
    console.print("\n" + "="*50)
    console.print("[bold green]✓ Production Mode Ready[/bold green]")
    console.print("="*50)

    return True


def switch_to_fresh_mode():
    """Switch local server to fresh world mode"""

    # Check if mods are missing (e.g., coming from Vanilla mode)
    mods_dir = os.path.join(SCRIPT_DIR, "mods")
    if os.path.exists(mods_dir):
        jar_count = len([f for f in os.listdir(mods_dir) if f.endswith('.jar')])
        if jar_count < 5:
            console.print("[yellow]⚠ Warning: Only {0} mod JAR(s) found in mods/[/yellow]".format(jar_count))
            console.print("[yellow]  Mods will be restored when you start the server[/yellow]")
            console.print("[yellow]  (requires 'packwiz serve' running in MCC directory)[/yellow]")
            console.print()

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

    # Step 1: Restore packwiz-installer if disabled
    console.print("\n[bold]Step 1/2: Checking packwiz-installer...[/bold]")
    if restore_packwiz_installer():
        console.print("[dim]  (Was disabled from Vanilla mode)[/dim]")
    else:
        console.print("[dim]  Packwiz-installer ready[/dim]")

    # Step 2: Switch server.properties
    console.print("\n[bold]Step 2/2: Switching to fresh world server.properties...[/bold]")
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
        "  • Packwiz-installer disabled\n"
        "  • Good for isolating mod issues\n\n"
        "[yellow]Note: This clears all mods and disables packwiz sync.[/yellow]",
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

    # Disable packwiz-installer to prevent mods from being re-downloaded
    console.print("\n[bold]Step 2/3: Disabling packwiz-installer...[/bold]")
    packwiz_bootstrap = os.path.join(SCRIPT_DIR, "packwiz-installer-bootstrap.jar")
    packwiz_bootstrap_disabled = packwiz_bootstrap + ".disabled"
    packwiz_json = os.path.join(SCRIPT_DIR, "packwiz.json")
    packwiz_json_backup = packwiz_json + ".backup"

    if os.path.exists(packwiz_bootstrap):
        os.rename(packwiz_bootstrap, packwiz_bootstrap_disabled)
        console.print("[green]✓ Renamed packwiz-installer-bootstrap.jar → .disabled[/green]")
    elif os.path.exists(packwiz_bootstrap_disabled):
        console.print("[dim]  packwiz-installer already disabled[/dim]")
    else:
        console.print("[dim]  packwiz-installer-bootstrap.jar not found[/dim]")

    # Backup packwiz.json to prevent cache from being used
    if os.path.exists(packwiz_json):
        if os.path.exists(packwiz_json_backup):
            os.remove(packwiz_json_backup)
        os.rename(packwiz_json, packwiz_json_backup)
        console.print("[green]✓ Backed up packwiz.json[/green]")

    # Clear mods (keep only Fabric API)
    console.print("\n[bold]Step 3/3: Clearing mods (keeping Fabric API)...[/bold]")
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
    console.print("[dim]Packwiz-installer: disabled[/dim]")
    console.print("[dim]To restore mods: Switch to Production or Fresh mode[/dim]")
    console.print("="*50)

    return True


def restore_packwiz_installer():
    """Re-enable packwiz-installer if it was disabled for vanilla mode."""
    packwiz_bootstrap = os.path.join(SCRIPT_DIR, "packwiz-installer-bootstrap.jar")
    packwiz_bootstrap_disabled = packwiz_bootstrap + ".disabled"
    packwiz_json = os.path.join(SCRIPT_DIR, "packwiz.json")
    packwiz_json_backup = packwiz_json + ".backup"

    restored = False

    # Restore packwiz-installer-bootstrap.jar
    if os.path.exists(packwiz_bootstrap_disabled):
        if os.path.exists(packwiz_bootstrap):
            os.remove(packwiz_bootstrap_disabled)  # Already exists, just remove disabled copy
        else:
            os.rename(packwiz_bootstrap_disabled, packwiz_bootstrap)
        console.print("[green]✓ Restored packwiz-installer-bootstrap.jar[/green]")
        restored = True

    # Restore packwiz.json
    if os.path.exists(packwiz_json_backup):
        if os.path.exists(packwiz_json):
            os.remove(packwiz_json_backup)  # Already exists, just remove backup
        else:
            os.rename(packwiz_json_backup, packwiz_json)
        console.print("[green]✓ Restored packwiz.json[/green]")
        restored = True

    return restored


# =============================================================================
# Modpack Version Management
# =============================================================================

def list_versions():
    """Display available MCC modpack versions."""
    console.print(Panel(
        "[bold]MCC Modpack Versions[/bold]\n\n"
        "Available versions from the MCC git repository.\n"
        "Switch to test older versions or validate releases.",
        title="[cyan]Version List[/cyan]",
        border_style="cyan"
    ))

    # Get current version
    current_version, version_type = get_mcc_current_version()
    is_dirty = is_mcc_dirty()

    # Display current state
    if version_type == "tag":
        console.print(f"\n[bold]Current:[/bold] [green]{current_version}[/green] (release tag)")
    elif version_type == "branch":
        console.print(f"\n[bold]Current:[/bold] [cyan]{current_version}[/cyan] (branch)")
    else:
        console.print(f"\n[bold]Current:[/bold] [yellow]{current_version}[/yellow] (detached)")

    if is_dirty:
        console.print("[yellow]⚠ Uncommitted changes present[/yellow]")

    # Get and display tags
    tags = get_mcc_git_tags()
    if not tags:
        console.print("\n[red]No version tags found in MCC repository[/red]")
        console.print("[dim]Make sure MCC directory exists and has git tags[/dim]")
        return False

    console.print(f"\n[bold]Available Versions:[/bold] ({len(tags)} releases)\n")

    # Display in columns for readability
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 3))
    table.add_column("Version", style="white")
    table.add_column("Version", style="white")
    table.add_column("Version", style="white")
    table.add_column("Version", style="white")

    # Group tags into rows of 4
    for i in range(0, len(tags), 4):
        row = tags[i:i+4]
        # Mark current version
        row_display = []
        for tag in row:
            if tag == current_version:
                row_display.append(f"[green]{tag}[/green] ←")
            else:
                row_display.append(tag)
        # Pad row to 4 items
        while len(row_display) < 4:
            row_display.append("")
        table.add_row(*row_display)

    console.print(table)
    console.print(f"\n[dim]Use 'c' to change version, or CLI: python server-config.py version <tag>[/dim]")
    return True


def switch_version(target_version, auto_confirm=False):
    """Switch MCC to a specific version tag."""
    from rich.prompt import Confirm

    # Validate target version exists
    tags = get_mcc_git_tags()
    if not tags:
        console.print("[red]Error: No version tags found in MCC repository[/red]")
        return False

    # Normalize version input (allow "0.9.32" or "v0.9.32")
    if not target_version.startswith('v'):
        target_version = f"v{target_version}"

    if target_version not in tags:
        console.print(f"[red]Error: Version '{target_version}' not found[/red]")
        console.print(f"[dim]Available versions: {', '.join(tags[:10])}{'...' if len(tags) > 10 else ''}[/dim]")
        return False

    # Get current state
    current_version, version_type = get_mcc_current_version()

    if current_version == target_version:
        console.print(f"[yellow]Already on version {target_version}[/yellow]")
        return True

    console.print(Panel(
        f"[bold]Switch MCC Version[/bold]\n\n"
        f"Current: [cyan]{current_version}[/cyan] ({version_type})\n"
        f"Target:  [green]{target_version}[/green]\n\n"
        f"This will checkout the tag in MCC and sync mods.",
        title="[cyan]Version Switch[/cyan]",
        border_style="cyan"
    ))

    # Check for uncommitted changes
    if is_mcc_dirty():
        dirty_files = get_mcc_dirty_summary()
        console.print("\n[yellow]⚠ MCC has uncommitted changes:[/yellow]")
        for f in dirty_files:
            console.print(f"  [dim]{f}[/dim]")
        if len(dirty_files) == 10:
            console.print("  [dim]... (more files)[/dim]")

        if not auto_confirm:
            if not Confirm.ask("\n[yellow]Stash changes and continue?[/yellow]"):
                console.print("[dim]Cancelled.[/dim]")
                return False

        console.print("\n[cyan]Stashing changes...[/cyan]")
        if stash_mcc_changes():
            console.print("[green]✓ Changes stashed[/green]")
            console.print("[dim]  Restore later with: cd MCC && git stash pop[/dim]")
        else:
            console.print("[red]Failed to stash changes[/red]")
            return False

    # Perform checkout
    console.print(f"\n[cyan]Checking out {target_version}...[/cyan]")
    success, error_msg = checkout_mcc_version(target_version)

    if not success:
        console.print(f"[red]Checkout failed: {error_msg}[/red]")
        return False

    console.print(f"[green]✓ Switched to {target_version}[/green]")

    # Delete old mrpack files to force fresh export
    console.print("\n[cyan]Cleaning old mrpack files...[/cyan]")
    import glob
    old_mrpacks = glob.glob(os.path.join(MCC_DIR, "MCC-*.mrpack"))
    for mrpack in old_mrpacks:
        try:
            os.remove(mrpack)
        except Exception:
            pass
    console.print(f"[green]✓ Removed {len(old_mrpacks)} old mrpack file(s)[/green]")

    # Auto-sync mods
    console.print("\n[bold]Syncing mods for this version...[/bold]")
    sync_success = sync_mods_full()

    # Summary
    console.print("\n" + "="*50)
    if sync_success:
        console.print(f"[bold green]✓ Switched to MCC {target_version}[/bold green]")
        console.print("[dim]Mods synced. Start the server to test this version.[/dim]")
    else:
        console.print(f"[bold yellow]⚠ Switched to {target_version} but mod sync had issues[/bold yellow]")
        console.print("[dim]Check mod sync output above for details.[/dim]")
    console.print("="*50)

    return sync_success


def return_to_main():
    """Return MCC to main branch and optionally restore stashed changes."""
    from rich.prompt import Confirm

    current_version, version_type = get_mcc_current_version()

    # Check if already on main
    if version_type == "branch" and current_version == "main":
        console.print("[yellow]Already on main branch[/yellow]")

        # Still offer to pop stash if one exists
        if has_mcc_stash():
            if Confirm.ask("\n[cyan]Found stashed changes. Restore them?[/cyan]"):
                success, msg = pop_mcc_stash()
                if success:
                    console.print("[green]✓ Stashed changes restored[/green]")
                else:
                    console.print(f"[red]Failed to restore stash: {msg}[/red]")
        return True

    console.print(Panel(
        f"[bold]Return to Main Branch[/bold]\n\n"
        f"Current: [yellow]{current_version}[/yellow] ({version_type})\n"
        f"Target:  [green]main[/green] (latest development)\n\n"
        f"This will checkout main and sync mods.",
        title="[cyan]Version Switch[/cyan]",
        border_style="cyan"
    ))

    # Check for stashed changes
    has_stash = has_mcc_stash()
    if has_stash:
        console.print("\n[cyan]ℹ Found stashed changes from previous version switch[/cyan]")

    # Perform checkout
    console.print(f"\n[cyan]Checking out main...[/cyan]")
    success, error_msg = checkout_mcc_version("main")

    if not success:
        console.print(f"[red]Checkout failed: {error_msg}[/red]")
        return False

    console.print(f"[green]✓ Switched to main[/green]")

    # Offer to restore stashed changes
    if has_stash:
        if Confirm.ask("\n[cyan]Restore stashed changes?[/cyan]", default=True):
            success, msg = pop_mcc_stash()
            if success:
                console.print("[green]✓ Stashed changes restored[/green]")
            else:
                console.print(f"[yellow]⚠ Could not restore stash: {msg}[/yellow]")
                console.print("[dim]You can manually run: cd MCC && git stash pop[/dim]")

    # Delete old mrpack files to force fresh export
    console.print("\n[cyan]Cleaning old mrpack files...[/cyan]")
    import glob
    old_mrpacks = glob.glob(os.path.join(MCC_DIR, "MCC-*.mrpack"))
    for mrpack in old_mrpacks:
        try:
            os.remove(mrpack)
        except Exception:
            pass
    console.print(f"[green]✓ Removed {len(old_mrpacks)} old mrpack file(s)[/green]")

    # Auto-sync mods
    console.print("\n[bold]Syncing mods from main...[/bold]")
    sync_success = sync_mods_full()

    # Summary
    console.print("\n" + "="*50)
    if sync_success:
        console.print("[bold green]✓ Returned to main branch[/bold green]")
        console.print("[dim]Mods synced. Ready for development.[/dim]")
    else:
        console.print("[bold yellow]⚠ Returned to main but mod sync had issues[/bold yellow]")
        console.print("[dim]Check mod sync output above for details.[/dim]")
    console.print("="*50)

    return sync_success


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

def grant_permissions(username):
    """Grant all permissions to a player via LuckPerms.

    This uses LuckPerms RCON commands since vanilla /op is disabled
    when auto-op mode is enabled.
    """
    if not username:
        console.print("[yellow]No username provided[/yellow]")
        return False

    if not is_server_running():
        console.print("[yellow]Server is not running[/yellow]")
        return False

    console.print(f"[cyan]Granting permissions to {username}...[/cyan]")

    # Grant wildcard permission
    response1 = send_rcon_command(f"lp user {username} permission set * true")
    if response1:
        console.print(f"[dim]  {response1}[/dim]")

    # Grant autoop permission
    response2 = send_rcon_command(f"lp user {username} permission set luckperms.autoop true")
    if response2:
        console.print(f"[dim]  {response2}[/dim]")

    console.print(f"[green]✓ Permissions granted to {username}[/green]")
    console.print("[dim]  Player should relog to receive op status[/dim]")
    return True


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

        # Show MCC version
        mcc_version, mcc_type = get_mcc_current_version()
        mcc_dirty = is_mcc_dirty()
        mcc_display = f"[magenta]{mcc_version}[/magenta]"
        if mcc_dirty:
            mcc_display += " [yellow]*[/yellow]"

        console.print(f"\nMode: [{mode_color}]{mode.upper()}[/{mode_color}] | Server: [{status_color}]{status_text}[/{status_color}] | MCC: {mcc_display}")
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
        table.add_row("", "")
        table.add_row("", "[dim]── Modpack Version ──[/dim]")
        table.add_row("l", "List Versions")
        table.add_row("c", "Change Version")
        table.add_row("b", "Back to Main Branch")
        table.add_row("", "")
        table.add_row("", "[dim]── Utilities ──[/dim]")
        table.add_row("m", "Sync Mods (from mrpack)")
        table.add_row("o", "Grant Permissions (op via LuckPerms)")
        table.add_row("r", "Send RCON Command")
        table.add_row("s", "Show Status")
        table.add_row("", "")
        table.add_row("q", "Quit")

        console.print(table)
        console.print()

        choice = Prompt.ask("Select", choices=["1", "2", "3", "4", "5", "6", "p", "f", "v", "l", "c", "b", "m", "o", "r", "s", "q"], default="q")

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

        elif choice == "l":
            list_versions()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "c":
            list_versions()
            version = Prompt.ask("\nEnter version to switch to (e.g., v0.9.32)")
            if version:
                switch_version(version)
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "b":
            return_to_main()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "m":
            sync_mods_full()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "o":
            username = Prompt.ask("Enter Minecraft username")
            if username:
                grant_permissions(username)
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
        elif command == "sync-mods":
            sync_mods_full()
        elif command == "version":
            if len(sys.argv) < 3:
                # No subcommand, show current version
                version, vtype = get_mcc_current_version()
                console.print(f"[bold]MCC Version:[/bold] [cyan]{version}[/cyan] ({vtype})")
                if is_mcc_dirty():
                    console.print("[yellow]⚠ Uncommitted changes present[/yellow]")
            elif sys.argv[2] == "list":
                list_versions()
            elif sys.argv[2] == "main":
                # Special case: return to main branch
                return_to_main()
            else:
                # Treat as version tag to switch to
                switch_version(sys.argv[2])
        elif command == "rcon":
            if len(sys.argv) < 3:
                console.print("[yellow]Usage: python server-config.py rcon <command>[/yellow]")
            else:
                cmd = " ".join(sys.argv[2:])
                response = send_rcon_command(cmd)
                if response:
                    console.print(response)
        elif command == "grant-perms" or command == "op":
            if len(sys.argv) < 3:
                console.print("[yellow]Usage: python server-config.py grant-perms <username>[/yellow]")
            else:
                grant_permissions(sys.argv[2])
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
            console.print("[yellow]Modpack Version:[/yellow]")
            console.print("  python server-config.py version          # Show current MCC version")
            console.print("  python server-config.py version list     # List available versions")
            console.print("  python server-config.py version <tag>    # Switch to specific version")
            console.print("  python server-config.py version main     # Return to main branch")
            console.print("")
            console.print("[yellow]Utilities:[/yellow]")
            console.print("  python server-config.py sync-mods        # Sync mods from mrpack")
            console.print("  python server-config.py clear-mods       # Remove non-API mods")
            console.print("  python server-config.py grant-perms <user>  # Grant op via LuckPerms")
            console.print("  python server-config.py rcon <cmd>       # Send RCON command")
    else:
        interactive_menu()
