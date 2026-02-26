"""
SentinelCore - Production-grade Windows Telemetry Agent
Version: 3.0.0
Focus: System Stability and Critical Fault Detection

Uses modern Windows Eventing API (EvtQuery) for efficient event collection.
Sends structured, integrity-safe data to Linux server via HTTPS.

PRODUCTION FEATURES:
- Targeted log collection (System, Kernel-Power, DriverFrameworks)
- Multi-level event filtering (level, provider name)
- SHA256 integrity hashing for duplicate detection
- System resource monitoring (CPU, memory, disk)
- HTTPS transmission with exponential backoff retry
- Checkpoint advancement only on successful transmission
- Graceful handling of non-admin execution
- Administrator privilege detection with channel probing
- Error classification for fault diagnosis (7 fault types)
- PID lock file to prevent duplicate instances
- Disk space guard (pauses if < 1GB free)
- File + console logging for headless operation
"""

import json
import time
import sys
import os
import socket
import hashlib
import re
import ctypes
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set, Tuple
from collections import deque
import winreg
import uuid

try:
    import win32evtlog
    import pywintypes
except ImportError:
    print("ERROR: pywin32 is required. Install with: pip install pywin32", file=sys.stderr)
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("ERROR: psutil is required. Install with: pip install psutil", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from kafka import KafkaProducer
    from kafka.errors import KafkaError
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False

# ============================================================================
# CONFIGURATION
# ============================================================================

COLLECTOR_VERSION = "4.0.0"

# Resolve working directory to script location (important for Task Scheduler)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# Project root is one level up from src/
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")


def load_config() -> Dict:
    """Load configuration from config.json. Falls back to defaults if missing."""
    defaults = {
        "kafka": {
            "bootstrap_servers": "<WSL_IP>:9092",
            "topic": "sentinel-events",
            "client_id": "windows-test-agent"
        },
        "agent": {
            "system_id_mode": "AUTO",
            "batch_size": 20,
            "retry_attempts": 3,
            "retry_backoff_seconds": 3
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            # Merge: user values override defaults
            for section in defaults:
                if section in user_config:
                    defaults[section].update(user_config[section])
            print(f"Loaded configuration from {CONFIG_FILE}")
        except Exception as e:
            print(f"Warning: Could not load {CONFIG_FILE}: {e}. Using defaults.", file=sys.stderr)
    else:
        print(f"Warning: {CONFIG_FILE} not found. Using built-in defaults.", file=sys.stderr)
    return defaults


_CONFIG = load_config()

# Testing Mode - Set to True for local testing without server
LOCAL_TESTING_MODE = os.getenv("SENTINEL_LOCAL_MODE", "false").lower() == "true"

# Kafka Pipeline Mode (takes precedence over HTTPS when enabled)
# Defaults to true since Kafka is the primary pipeline
KAFKA_MODE = os.getenv("SENTINEL_KAFKA_MODE", "true").lower() == "true"

# Kafka settings from config.json; KAFKA_BOOTSTRAP env var overrides bootstrap_servers
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP", _CONFIG["kafka"]["bootstrap_servers"])
KAFKA_TOPIC = _CONFIG["kafka"]["topic"]
KAFKA_CLIENT_ID = _CONFIG["kafka"].get("client_id", "windows-test-agent")

# Server Configuration (only used when LOCAL_TESTING_MODE = False and KAFKA_MODE = False)
SERVER_ENDPOINT = os.getenv("SENTINEL_SERVER_URL", "https://your-server.com/api/events")
AUTH_TOKEN = os.getenv("SENTINEL_AUTH_TOKEN", None)  # Optional Bearer token
REQUEST_TIMEOUT = 30  # seconds

# Collection Configuration
TARGET_LOGS = [
    "System",
    "Microsoft-Windows-Kernel-Power",
    "Microsoft-Windows-DriverFrameworks-UserMode/Operational"
]

# Event Filtering
INCLUDE_LEVELS = [1, 2, 3]  # Critical=1, Error=2, Warning=3
EXCLUDE_PROVIDER_KEYWORDS = [
    "tcpip", "dns", "dhcp", "wlan", "smb", "network",
    "firewall", "winhttp", "wininet"
]

# Collection Behavior
BATCH_SIZE = _CONFIG["agent"]["batch_size"]
COLLECTION_INTERVAL_SECONDS = 30
CHECKPOINT_FILE = "checkpoint.json"

# Retry Configuration (from config.json)
MAX_RETRY_ATTEMPTS = _CONFIG["agent"]["retry_attempts"]
RETRY_BACKOFF_BASE = float(_CONFIG["agent"]["retry_backoff_seconds"])
DUPLICATE_HASH_WINDOW = 10000  # Keep last N event hashes

# Local File Output Configuration
LOCAL_OUTPUT_FILE = "collected_events.json"  # Output file for local testing
MAX_EVENTS_PER_FILE = 500  # Limit events per file to keep size manageable
PRETTY_PRINT_JSON = True  # Make JSON human-readable for analysis

# Fallback Configuration (only for non-testing mode)
ENABLE_LOCAL_FALLBACK = True  # Write to local file if HTTPS fails
FALLBACK_FILE_PREFIX = "events_fallback"

# Production Safety
PID_LOCK_FILE = os.path.join(SCRIPT_DIR, "sentinel.pid")  # Prevents duplicate instances
MIN_DISK_FREE_MB = 1024  # Pause collection if disk free < 1GB
LOG_FILE = os.path.join(SCRIPT_DIR, "sentinel.log")  # Log output for headless operation

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger('SentinelCore')

# ============================================================================
# PID LOCK (prevents duplicate instances)
# ============================================================================

def acquire_pid_lock() -> bool:
    """Create PID lock file. Returns False if another instance is running."""
    if os.path.exists(PID_LOCK_FILE):
        try:
            with open(PID_LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if that process is still running
            if psutil.pid_exists(old_pid):
                try:
                    proc = psutil.Process(old_pid)
                    if 'python' in proc.name().lower():
                        print(f"ERROR: Another SentinelCore instance is running (PID {old_pid})", file=sys.stderr)
                        print(f"  To force restart, delete: {PID_LOCK_FILE}", file=sys.stderr)
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # Process died, stale PID file
        except (ValueError, IOError):
            pass  # Corrupt PID file, overwrite it

    # Write our PID
    with open(PID_LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


def release_pid_lock():
    """Remove PID lock file on shutdown."""
    try:
        if os.path.exists(PID_LOCK_FILE):
            os.remove(PID_LOCK_FILE)
    except Exception:
        pass


def check_disk_space() -> bool:
    """Check if there's enough disk space to continue. Returns True if OK."""
    try:
        disk = psutil.disk_usage(SCRIPT_DIR)
        free_mb = disk.free / (1024 * 1024)
        if free_mb < MIN_DISK_FREE_MB:
            logger.warning(f"LOW DISK SPACE: {free_mb:.0f}MB free (minimum: {MIN_DISK_FREE_MB}MB). Pausing collection.")
            return False
        return True
    except Exception:
        return True  # Continue if we can't check

# ============================================================================
# ADMINISTRATOR PRIVILEGE DETECTION
# ============================================================================

def is_admin() -> bool:
    """Check if the current process has Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def check_admin_privileges() -> Tuple[bool, List[str]]:
    """
    Check admin status and determine which channels are accessible.
    Returns (is_admin, list_of_warnings).
    """
    admin = is_admin()
    warnings = []

    if not admin:
        warnings.append(
            "Running WITHOUT Administrator privileges. "
            "Some event channels may be inaccessible."
        )
        # Probe each target channel to see which ones are accessible
        try:
            import win32evtlog
            import pywintypes
            for channel in TARGET_LOGS:
                try:
                    query = f"<QueryList><Query><Select Path='{channel}'>*[System[EventRecordID &gt; 999999999]]</Select></Query></QueryList>"
                    handle = win32evtlog.EvtQuery(
                        channel,
                        win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryForwardDirection,
                        query, None
                    )
                except pywintypes.error as e:
                    if e.winerror in [5, 15001]:
                        warnings.append(f"  ✗ Channel '{channel}' requires admin access")
                    elif e.winerror == 15007:
                        warnings.append(f"  ✗ Channel '{channel}' does not exist")
        except ImportError:
            pass

        warnings.append(
            "\nTo run as Administrator:\n"
            "  1. Open PowerShell as Administrator\n"
            "  2. Navigate to this directory\n"
            "  3. Run: python collector.py"
        )
    return admin, warnings

# ============================================================================
# ERROR CLASSIFICATION FOR FAULT DIAGNOSIS
# ============================================================================

class ErrorClassifier:
    """
    Classifies collected events into fault categories for diagnosis.
    Each event is tagged with a fault_type and fault_details dict.
    """

    FAULT_TYPES = {
        'SYSTEM_FAULT': 'Critical system fault (crash, BSOD, unexpected shutdown)',
        'DRIVER_ISSUE': 'Device driver failure or timeout',
        'RESOURCE_WARNING': 'Resource exhaustion or performance degradation',
        'SERVICE_ERROR': 'Windows service start/stop failure',
        'SECURITY_EVENT': 'Permission violation or security-related event',
        'UPDATE_ERROR': 'Windows Update failure',
        'STORAGE_ERROR': 'Disk or volume shadow copy issues',
        'UNKNOWN': 'Unclassified event'
    }

    # Pattern: (provider_substring, event_id_or_None) -> fault_type
    CLASSIFICATION_RULES = [
        # System faults
        ('Kernel-Power', 41, 'SYSTEM_FAULT'),
        ('Kernel-Power', 109, 'SYSTEM_FAULT'),
        ('BugCheck', None, 'SYSTEM_FAULT'),
        ('BlueScreen', None, 'SYSTEM_FAULT'),
        ('WER-SystemErrorReporting', None, 'SYSTEM_FAULT'),
        # Driver issues
        ('Kernel-PnP', 219, 'DRIVER_ISSUE'),
        ('DriverFrameworks', None, 'DRIVER_ISSUE'),
        # Resource warnings
        ('Kernel-Processor-Power', 37, 'RESOURCE_WARNING'),
        ('disk', 153, 'RESOURCE_WARNING'),
        ('Resource-Exhaustion', None, 'RESOURCE_WARNING'),
        # Service errors
        ('Service Control Manager', 7000, 'SERVICE_ERROR'),
        ('Service Control Manager', 7001, 'SERVICE_ERROR'),
        ('Service Control Manager', 7009, 'SERVICE_ERROR'),
        ('Service Control Manager', 7023, 'SERVICE_ERROR'),
        ('Service Control Manager', 7031, 'SERVICE_ERROR'),
        ('Service Control Manager', 7034, 'SERVICE_ERROR'),
        ('winsrvext', None, 'SERVICE_ERROR'),
        # Security events
        ('DistributedCOM', 10016, 'SECURITY_EVENT'),
        # Update errors
        ('WindowsUpdateClient', None, 'UPDATE_ERROR'),
        # Storage errors
        ('Volsnap', None, 'STORAGE_ERROR'),
        ('Ntfs', None, 'STORAGE_ERROR'),
    ]

    @classmethod
    def classify(cls, provider_name: str, event_id: int, level: int) -> Dict:
        """
        Classify an event and return fault info.
        Returns dict with fault_type, fault_description, severity.
        """
        fault_type = 'UNKNOWN'
        provider_lower = provider_name.lower() if provider_name else ''

        for rule_provider, rule_eid, rule_type in cls.CLASSIFICATION_RULES:
            if rule_provider.lower() in provider_lower:
                if rule_eid is None or rule_eid == event_id:
                    fault_type = rule_type
                    break

        # If still unknown, classify by severity level
        if fault_type == 'UNKNOWN':
            if level == 1:
                fault_type = 'SYSTEM_FAULT'
            elif level == 2:
                fault_type = 'SERVICE_ERROR'

        severity = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING'}.get(level, 'INFO')

        return {
            'fault_type': fault_type,
            'fault_description': cls.FAULT_TYPES.get(fault_type, 'Unknown'),
            'severity': severity
        }

    @classmethod
    def get_diagnostic_context(cls, event: Dict, resources: Dict) -> Dict:
        """
        Build diagnostic context for an event: resource state and process info.
        """
        context = {
            'resource_state': {
                'cpu_percent': resources.get('cpu_usage_percent', 0),
                'memory_percent': resources.get('memory_usage_percent', 0),
                'disk_free_percent': resources.get('disk_free_percent', 0)
            },
            'resource_alerts': []
        }

        # Flag resource anomalies at time of event capture
        cpu = resources.get('cpu_usage_percent', 0)
        mem = resources.get('memory_usage_percent', 0)
        disk = resources.get('disk_free_percent', 100)

        if cpu > 90:
            context['resource_alerts'].append(f'HIGH CPU: {cpu}%')
        if mem > 90:
            context['resource_alerts'].append(f'HIGH MEMORY: {mem}%')
        if disk < 10:
            context['resource_alerts'].append(f'LOW DISK: {disk}% free')

        return context

# ============================================================================
# SYSTEM METADATA FUNCTIONS
# ============================================================================

def get_system_id() -> str:
    """Get unique system identifier. Uses hostname when system_id_mode is AUTO."""
    if _CONFIG["agent"].get("system_id_mode") == "AUTO":
        return socket.gethostname()
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ
        )
        machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return machine_guid
    except Exception as e:
        print(f"Warning: Could not read MachineGuid: {e}", file=sys.stderr)
        return "UNKNOWN"


def get_hostname() -> str:
    """Get system hostname"""
    try:
        return socket.gethostname()
    except Exception as e:
        print(f"Warning: Could not get hostname: {e}", file=sys.stderr)
        return "UNKNOWN"


def get_boot_session_id() -> str:
    """Get current boot session identifier as UUID"""
    try:
        boot_time = psutil.boot_time()
        # Generate deterministic UUID from boot time and system ID
        seed = f"{get_system_id()}-{boot_time}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))
    except Exception as e:
        print(f"Warning: Could not determine boot session: {e}", file=sys.stderr)
        return str(uuid.uuid4())


def get_os_version() -> str:
    """Get Windows OS version information"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0,
            winreg.KEY_READ
        )
        product_name, _ = winreg.QueryValueEx(key, "ProductName")
        current_build, _ = winreg.QueryValueEx(key, "CurrentBuild")
        winreg.CloseKey(key)
        return f"{product_name} (Build {current_build})"
    except Exception as e:
        print(f"Warning: Could not read OS version: {e}", file=sys.stderr)
        return "Windows (Unknown Version)"


def get_uptime_seconds() -> int:
    """Get system uptime in seconds"""
    try:
        return int(time.time() - psutil.boot_time())
    except Exception as e:
        print(f"Warning: Could not calculate uptime: {e}", file=sys.stderr)
        return 0

# ============================================================================
# RESOURCE MONITORING
# ============================================================================

def get_resource_snapshot() -> Dict[str, float]:
    """Get current system resource usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_usage_percent": round(cpu_percent, 2),
            "memory_usage_percent": round(memory.percent, 2),
            "disk_free_percent": round(100.0 - disk.percent, 2)
        }
    except Exception as e:
        print(f"Warning: Could not get resource snapshot: {e}", file=sys.stderr)
        return {
            "cpu_usage_percent": 0.0,
            "memory_usage_percent": 0.0,
            "disk_free_percent": 0.0
        }

# ============================================================================
# EVENT PARSING AND FILTERING
# ============================================================================

def extract_event_metadata(xml: str) -> Optional[Dict]:
    """Extract metadata from event XML"""
    try:
        metadata = {}
        
        # EventRecordID
        match = re.search(r'EventRecordID["\']?>(\d+)<', xml)
        metadata['event_record_id'] = int(match.group(1)) if match else None
        
        # Provider Name
        match = re.search(r'Provider.*?Name=["\']([^"\']+)["\']', xml)
        metadata['provider_name'] = match.group(1) if match else "Unknown"
        
        # Event ID
        match = re.search(r'EventID["\']?>(\d+)<', xml)
        metadata['event_id'] = int(match.group(1)) if match else 0
        
        # Level
        match = re.search(r'Level["\']?>(\d+)<', xml)
        metadata['level'] = int(match.group(1)) if match else 0
        
        # Task
        match = re.search(r'Task["\']?>(\d+)<', xml)
        metadata['task'] = int(match.group(1)) if match else 0
        
        # Opcode
        match = re.search(r'Opcode["\']?>(\d+)<', xml)
        metadata['opcode'] = int(match.group(1)) if match else 0
        
        # Keywords
        match = re.search(r'Keywords["\']?>(0x[0-9a-fA-F]+)<', xml)
        metadata['keywords'] = match.group(1) if match else "0x0"
        
        # Process ID
        match = re.search(r'ProcessID["\']?>(\d+)<', xml)
        metadata['process_id'] = int(match.group(1)) if match else 0
        
        # Thread ID
        match = re.search(r'ThreadID["\']?>(\d+)<', xml)
        metadata['thread_id'] = int(match.group(1)) if match else 0
        
        # TimeCreated SystemTime
        match = re.search(r'SystemTime=["\']([^"\']+)["\']', xml)
        metadata['event_time'] = match.group(1) if match else datetime.now(timezone.utc).isoformat()
        
        return metadata
    except Exception as e:
        print(f"Warning: Could not parse event metadata: {e}", file=sys.stderr)
        return None


def should_exclude_provider(provider_name: str) -> bool:
    """Check if provider should be excluded based on keywords"""
    provider_lower = provider_name.lower()
    for keyword in EXCLUDE_PROVIDER_KEYWORDS:
        if keyword in provider_lower:
            return True
    return False


def generate_event_hash(raw_xml: str, system_id: str, event_record_id: int) -> str:
    """Generate SHA256 hash for event integrity and deduplication"""
    content = f"{raw_xml}{system_id}{event_record_id}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

# ============================================================================
# CHECKPOINT MANAGER
# ============================================================================

class CheckpointManager:
    """Manages per-channel checkpointing using EventRecordID"""
    
    def __init__(self, checkpoint_file: str):
        self.checkpoint_file = checkpoint_file
        self.checkpoints: Dict[str, int] = {}
        self.load()
    
    def load(self):
        """Load checkpoints from file"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    self.checkpoints = json.load(f)
                print(f"Loaded checkpoints for {len(self.checkpoints)} channels")
            except Exception as e:
                print(f"Warning: Could not load checkpoint file: {e}", file=sys.stderr)
                self.checkpoints = {}
        else:
            print("No existing checkpoint file, starting fresh")
    
    def get_last_record_id(self, channel: str) -> int:
        """Get last processed EventRecordID for a channel"""
        return self.checkpoints.get(channel, 0)
    
    def update_checkpoint(self, channel: str, record_id: int):
        """Update checkpoint for a channel"""
        self.checkpoints[channel] = record_id
    
    def save(self):
        """Atomically save checkpoints to file"""
        try:
            # Write to temporary file first
            temp_file = f"{self.checkpoint_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoints, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic rename
            os.replace(temp_file, self.checkpoint_file)
        except Exception as e:
            print(f"Error saving checkpoint: {e}", file=sys.stderr)

# ============================================================================
# LOCAL FILE MANAGER (for testing mode)
# ============================================================================

class LocalFileManager:
    """Handles local file output for testing without server"""
    
    def __init__(self, output_file: str):
        self.output_file = output_file
        self.event_count = 0
        self.file_number = 1
        self._load_or_create_file()
    
    def _load_or_create_file(self):
        """Load existing file or create new one"""
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.event_count = len(data.get('events', []))
                print(f"Loaded existing output file: {self.event_count} events")
            except Exception as e:
                print(f"Warning: Could not load existing file: {e}")
                self.event_count = 0
        else:
            # Create new file with structure
            self._create_new_file()
    
    def _create_new_file(self):
        """Create new JSON file with initial structure"""
        initial_data = {
            "collector_info": {
                "version": COLLECTOR_VERSION,
                "mode": "local_testing",
                "created": datetime.now(timezone.utc).isoformat()
            },
            "events": []
        }
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2 if PRETTY_PRINT_JSON else None)
        self.event_count = 0
        print(f"Created new output file: {self.output_file}")
    
    def _rotate_file_if_needed(self):
        """Rotate file if event limit reached"""
        if self.event_count >= MAX_EVENTS_PER_FILE:
            # Rename current file
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            archived_name = f"collected_events_{timestamp}.json"
            os.rename(self.output_file, archived_name)
            print(f"  → Rotated to {archived_name} ({self.event_count} events)")
            
            # Create new file
            self._create_new_file()
            self.file_number += 1
    
    def save_batch(self, payload: Dict) -> bool:
        """Save event batch to local file. Returns True if successful."""
        try:
            # Check if rotation needed
            self._rotate_file_if_needed()
            
            # Read current file
            with open(self.output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update metadata
            data['last_updated'] = payload.get('timestamp_collected')
            data['system_info'] = {
                'system_id': payload.get('system_id'),
                'hostname': payload.get('hostname'),
                'boot_session_id': payload.get('boot_session_id'),
                'os_version': payload.get('os_version'),
                'uptime_seconds': payload.get('uptime_seconds')
            }
            
            # Add new events
            new_events = payload.get('events', [])
            data['events'].extend(new_events)
            self.event_count += len(new_events)
            
            # Write back to file
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2 if PRETTY_PRINT_JSON else None, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"  ✗ Error saving to local file: {e}", file=sys.stderr)
            return False

# ============================================================================
# KAFKA MANAGER (for pipeline mode)
# ============================================================================

# Read Kafka tuning from config.json (with safe defaults)
KAFKA_ACKS = _CONFIG["kafka"].get("acks", "all")
KAFKA_RETRIES = int(_CONFIG["kafka"].get("retries", 5))
KAFKA_RETRY_BACKOFF_MS = int(_CONFIG["kafka"].get("retry_backoff_ms", 3000))
KAFKA_LINGER_MS = int(_CONFIG["kafka"].get("linger_ms", 50))
KAFKA_REQUEST_TIMEOUT_MS = int(_CONFIG["kafka"].get("request_timeout_ms", 15000))


class KafkaManager:
    """Handles Kafka event publishing with delivery confirmation and auto-reconnect."""

    def __init__(self, bootstrap_servers: str, topic: str):
        if not HAS_KAFKA:
            print("ERROR: kafka-python-ng is required for Kafka mode.", file=sys.stderr)
            print("  Install with: pip install kafka-python-ng", file=sys.stderr)
            sys.exit(1)

        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self._reconnect_attempt = 0
        self._connect()

    def _connect(self):
        """Connect to Kafka broker with retry. Sets self.producer=None on failure."""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    client_id=KAFKA_CLIENT_ID,
                    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None,
                    acks=KAFKA_ACKS,
                    retries=KAFKA_RETRIES,
                    retry_backoff_ms=KAFKA_RETRY_BACKOFF_MS,
                    linger_ms=KAFKA_LINGER_MS,
                    request_timeout_ms=KAFKA_REQUEST_TIMEOUT_MS,
                    max_block_ms=KAFKA_REQUEST_TIMEOUT_MS,
                    batch_size=32768
                )
                logger.info(f"Connected to Kafka at {self.bootstrap_servers} "
                            f"(acks={KAFKA_ACKS}, retries={KAFKA_RETRIES}, "
                            f"linger_ms={KAFKA_LINGER_MS})")
                self._reconnect_attempt = 0
                return
            except Exception as e:
                logger.error(f"Kafka connection failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}")
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.info(f"  Retrying in {backoff:.0f}s...")
                    time.sleep(backoff)
        logger.critical("Could not connect to Kafka broker after all retries. "
                        "Will attempt lazy reconnection on next send.")
        self.producer = None

    def _ensure_connected(self) -> bool:
        """Lazy reconnection: attempt to reconnect if producer is None.
        Uses exponential backoff across calls to avoid hammering the broker."""
        if self.producer is not None:
            return True

        self._reconnect_attempt += 1
        backoff = min(RETRY_BACKOFF_BASE * (2 ** self._reconnect_attempt), 60)
        logger.info(f"Kafka reconnection attempt {self._reconnect_attempt} "
                    f"(backoff {backoff:.0f}s)...")
        time.sleep(backoff)

        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=KAFKA_CLIENT_ID,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks=KAFKA_ACKS,
                retries=KAFKA_RETRIES,
                retry_backoff_ms=KAFKA_RETRY_BACKOFF_MS,
                linger_ms=KAFKA_LINGER_MS,
                request_timeout_ms=KAFKA_REQUEST_TIMEOUT_MS,
                max_block_ms=KAFKA_REQUEST_TIMEOUT_MS,
                batch_size=32768
            )
            logger.info(f"Reconnected to Kafka at {self.bootstrap_servers}")
            self._reconnect_attempt = 0
            return True
        except Exception as e:
            logger.error(f"Kafka reconnection failed: {e}")
            self.producer = None
            return False

    def send_batch(self, payload: Dict) -> Dict:
        """Publish event batch to Kafka with per-message delivery confirmation.

        Returns dict: {'sent': N, 'failed': M, 'success': bool}
        """
        result = {'sent': 0, 'failed': 0, 'success': False}

        if not self._ensure_connected():
            result['failed'] = len(payload.get('events', []))
            return result

        try:
            system_id = payload.get('system_id', 'unknown')
            events = payload.get('events', [])

            for event in events:
                kafka_message = {
                    'system_id': system_id,
                    'hostname': payload.get('hostname'),
                    'collector_version': payload.get('collector_version'),
                    'timestamp_collected': payload.get('timestamp_collected'),
                    'event': event
                }
                try:
                    future = self.producer.send(
                        self.topic,
                        key=system_id,
                        value=kafka_message
                    )
                    # Block until this message is confirmed by broker
                    future.get(timeout=10)
                    result['sent'] += 1
                except KafkaError as e:
                    result['failed'] += 1
                    logger.error(f"Delivery failed for event "
                                 f"{event.get('event_hash', '?')[:12]}: {e}")
                except Exception as e:
                    result['failed'] += 1
                    logger.error(f"Unexpected delivery error for event "
                                 f"{event.get('event_hash', '?')[:12]}: {e}")

            # Flush any remaining buffered messages
            self.producer.flush(timeout=30)

            result['success'] = result['failed'] == 0
            return result

        except KafkaError as e:
            logger.error(f"Kafka batch send failed: {e}")
            self.producer = None  # Mark for reconnection
            result['failed'] = len(payload.get('events', [])) - result['sent']
            return result
        except Exception as e:
            logger.error(f"Unexpected Kafka error during batch send: {e}")
            self.producer = None
            result['failed'] = len(payload.get('events', [])) - result['sent']
            return result

    def close(self):
        """Flush and close the Kafka producer"""
        if self.producer:
            try:
                self.producer.flush(timeout=10)
                self.producer.close(timeout=10)
                logger.info("Kafka producer closed gracefully")
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")

# ============================================================================
# TRANSMISSION MANAGER
# ============================================================================

class TransmissionManager:
    """Handles HTTPS transmission with retry logic and fallback"""
    
    def __init__(self, endpoint: str, auth_token: Optional[str] = None):
        self.endpoint = endpoint
        self.auth_token = auth_token
        self.session = requests.Session()
        
        # Set headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': f'SentinelCore/{COLLECTOR_VERSION}'
        })
        
        if self.auth_token:
            self.session.headers['Authorization'] = f'Bearer {self.auth_token}'
    
    def send_batch(self, payload: Dict) -> bool:
        """Send event batch with retry logic. Returns True if successful."""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                response = self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=REQUEST_TIMEOUT
                )
                
                if response.status_code in [200, 201, 202]:
                    if attempt > 0:
                        print(f"  ✓ Transmission successful on retry {attempt + 1}")
                    return True
                else:
                    print(f"  ✗ Server returned {response.status_code}: {response.text[:100]}", file=sys.stderr)
                    
            except requests.exceptions.RequestException as e:
                print(f"  ✗ Transmission failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}", file=sys.stderr)
            
            # Exponential backoff before retry
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                time.sleep(sleep_time)
        
        return False
    
    def save_to_fallback(self, payload: Dict):
        """Save failed transmission to local fallback file"""
        if not ENABLE_LOCAL_FALLBACK:
            return
        
        try:
            fallback_file = f"{FALLBACK_FILE_PREFIX}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            with open(fallback_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"  ⚠ Saved to fallback file: {fallback_file}")
        except Exception as e:
            print(f"  ✗ Could not save to fallback: {e}", file=sys.stderr)

# ============================================================================
# EVENT COLLECTION
# ============================================================================

def collect_events_from_channel(channel: str, last_record_id: int) -> List[Dict]:
    """
    Collect events from a channel with multi-level filtering
    Returns list of events with metadata and raw XML
    """
    events = []
    
    try:
        # Build XPath query for incremental collection with level filtering
        level_filter = " or ".join([f"Level={level}" for level in INCLUDE_LEVELS])
        query = f"""
        <QueryList>
            <Query>
                <Select Path="{channel}">
                    *[System[({level_filter}) and EventRecordID &gt; {last_record_id}]]
                </Select>
            </Query>
        </QueryList>
        """
        
        # Open query handle
        query_handle = win32evtlog.EvtQuery(
            channel,
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryForwardDirection,
            query,
            None
        )
        
        # Fetch events in batches
        while True:
            try:
                event_batch = win32evtlog.EvtNext(query_handle, BATCH_SIZE, 0)
                if not event_batch:
                    break
                
                for event in event_batch:
                    try:
                        # Render event as XML
                        xml = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
                        
                        if not xml:
                            continue  # Skip if render failed
                        
                        # Extract metadata
                        metadata = extract_event_metadata(xml)
                        if not metadata or not metadata['event_record_id']:
                            continue
                        
                        # Filter by provider name
                        if should_exclude_provider(metadata['provider_name']):
                            continue
                        
                        # Add to results
                        events.append({
                            'metadata': metadata,
                            'raw_xml': xml,
                            'log_channel': channel
                        })
                        
                    except Exception as e:
                        # Skip individual event errors
                        continue
                
            except pywintypes.error as e:
                if e.winerror == 259:  # ERROR_NO_MORE_ITEMS
                    break
                else:
                    raise
    
    except pywintypes.error as e:
        error_code = e.winerror
        
        # Handle expected errors gracefully
        if error_code in [15007, 5, 15001, 1734]:  # Access denied, not found, etc.
            pass  # Silently skip in production
        else:
            print(f"Error querying channel {channel}: {e}", file=sys.stderr)
    
    except Exception as e:
        # Log unexpected errors but don't crash
        print(f"Unexpected error in channel {channel}: {e}", file=sys.stderr)
    
    return events

# ============================================================================
# MAIN COLLECTOR
# ============================================================================

def run_collector():
    """Main collection loop"""
    print(f"SentinelCore v{COLLECTOR_VERSION} - Production Telemetry Agent")
    print("=" * 70)
    print(f"Working Dir:    {SCRIPT_DIR}")
    print(f"PID:            {os.getpid()}")

    # Acquire PID lock (prevent duplicate instances)
    if not acquire_pid_lock():
        sys.exit(1)

    # Check administrator privileges
    admin_status, admin_warnings = check_admin_privileges()
    privilege_level = "ADMINISTRATOR" if admin_status else "STANDARD USER"
    print(f"Privileges:     {privilege_level}")

    if admin_warnings:
        print("")
        for w in admin_warnings:
            print(f"  ⚠ {w}")
        print("")
    
    # Initialize system metadata
    system_id = get_system_id()
    hostname = get_hostname()
    boot_session_id = get_boot_session_id()
    os_version = get_os_version()
    
    print(f"System ID:      {system_id}")
    print(f"Hostname:       {hostname}")
    print(f"Boot Session:   {boot_session_id}")
    print(f"OS Version:     {os_version}")
    print(f"Uptime:         {get_uptime_seconds()}s")
    print("=" * 70)
    
    # Initialize managers
    checkpoint_mgr = CheckpointManager(CHECKPOINT_FILE)
    kafka_mgr = None
    file_mgr = None
    transmission_mgr = None

    if KAFKA_MODE:
        # Use Kafka pipeline
        kafka_mgr = KafkaManager(KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC)
    elif LOCAL_TESTING_MODE:
        # Use local file output for testing
        file_mgr = LocalFileManager(LOCAL_OUTPUT_FILE)
    else:
        # Use HTTPS transmission for production
        transmission_mgr = TransmissionManager(SERVER_ENDPOINT, AUTH_TOKEN)
    
    # Duplicate detection
    seen_hashes: deque = deque(maxlen=DUPLICATE_HASH_WINDOW)
    
    # Determine mode name
    if KAFKA_MODE:
        mode_name = 'KAFKA PIPELINE'
    elif LOCAL_TESTING_MODE:
        mode_name = 'LOCAL TESTING'
    else:
        mode_name = 'PRODUCTION'

    # Display configuration
    print(f"\nMode:           {mode_name}")
    print(f"Target Logs:    {', '.join(TARGET_LOGS)}")
    
    if KAFKA_MODE:
        print(f"Kafka Broker:   {KAFKA_BOOTSTRAP_SERVERS}")
        print(f"Kafka Topic:    {KAFKA_TOPIC}")
    elif LOCAL_TESTING_MODE:
        print(f"Output File:    {LOCAL_OUTPUT_FILE}")
        print(f"Max Events:     {MAX_EVENTS_PER_FILE} per file")
        print(f"Format:         {'Pretty JSON' if PRETTY_PRINT_JSON else 'Compact JSON'}")
    else:
        print(f"Server:         {SERVER_ENDPOINT}")
        print(f"Auth:           {'Enabled' if AUTH_TOKEN else 'Disabled'}")
        print(f"Fallback:       {'Enabled' if ENABLE_LOCAL_FALLBACK else 'Disabled'}")
    
    print(f"Interval:       {COLLECTION_INTERVAL_SECONDS}s")
    print("=" * 70)
    print("\nStarting collection loop... (Press Ctrl+C to stop)\n")
    
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            cycle_start = time.time()
            batch_events = []
            
            print(f"[Cycle {cycle_count}] {datetime.now(timezone.utc).isoformat()}")

            # Disk space guard
            if not check_disk_space():
                print(f"  Skipping cycle (low disk space). Retrying in {COLLECTION_INTERVAL_SECONDS}s...")
                time.sleep(COLLECTION_INTERVAL_SECONDS)
                continue
            
            # Collect from target channels
            for channel in TARGET_LOGS:
                last_record_id = checkpoint_mgr.get_last_record_id(channel)
                events = collect_events_from_channel(channel, last_record_id)
                
                if events:
                    print(f"  {channel}: {len(events)} new events")
                    
                    for event in events:
                        # Generate event hash
                        event_hash = generate_event_hash(
                            event['raw_xml'],
                            system_id,
                            event['metadata']['event_record_id']
                        )
                        
                        # Skip duplicates
                        if event_hash in seen_hashes:
                            continue
                        
                        seen_hashes.append(event_hash)
                        
                        # Get resource snapshot
                        resources = get_resource_snapshot()
                        
                        # Classify for fault diagnosis
                        fault_info = ErrorClassifier.classify(
                            event['metadata']['provider_name'],
                            event['metadata']['event_id'],
                            event['metadata']['level']
                        )
                        diag_context = ErrorClassifier.get_diagnostic_context(
                            event['metadata'], resources
                        )

                        # Build event payload with required structured fields
                        severity_map = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}
                        event_level = event['metadata']['level']
                        event_payload = {
                            'log_channel': event['log_channel'],
                            'event_record_id': event['metadata']['event_record_id'],
                            'provider_name': event['metadata']['provider_name'],
                            'event_id': event['metadata']['event_id'],
                            'level': event_level,
                            'task': event['metadata']['task'],
                            'opcode': event['metadata']['opcode'],
                            'keywords': event['metadata']['keywords'],
                            'process_id': event['metadata']['process_id'],
                            'thread_id': event['metadata']['thread_id'],
                            'event_time': event['metadata']['event_time'],
                            'cpu_usage_percent': resources['cpu_usage_percent'],
                            'memory_usage_percent': resources['memory_usage_percent'],
                            'disk_free_percent': resources['disk_free_percent'],
                            'event_hash': event_hash,
                            'fault_type': fault_info['fault_type'],
                            'fault_description': fault_info['fault_description'],
                            'severity': severity_map.get(event_level, fault_info['severity']),
                            'message': f"{event['metadata']['provider_name']} Event {event['metadata']['event_id']} "
                                       f"({severity_map.get(event_level, 'UNKNOWN')}) on channel {event['log_channel']}",
                            'created_at': datetime.now(timezone.utc).isoformat(),
                            'diagnostic_context': diag_context,
                            'raw_xml': event['raw_xml']
                        }
                        
                        batch_events.append(event_payload)
                    
                    # Update checkpoint with highest record ID
                    max_record_id = max(e['metadata']['event_record_id'] for e in events)
                    
                    # Transmit batch if we have events
                    if batch_events:
                        # Build transmission payload
                        payload = {
                            'system_id': system_id,
                            'hostname': hostname,
                            'boot_session_id': boot_session_id,
                            'os_version': os_version,
                            'uptime_seconds': get_uptime_seconds(),
                            'collector_version': COLLECTOR_VERSION,
                            'timestamp_collected': datetime.now(timezone.utc).isoformat(),
                            'events': batch_events
                        }
                        
                        # Save batch (Kafka, local file, or HTTPS depending on mode)
                        if KAFKA_MODE:
                            # Kafka pipeline mode with delivery confirmation
                            send_result = kafka_mgr.send_batch(payload)
                            if send_result['success']:
                                logger.info(f"  ✓ Published {send_result['sent']} events "
                                            f"to Kafka topic '{KAFKA_TOPIC}'")
                                checkpoint_mgr.update_checkpoint(channel, max_record_id)
                                checkpoint_mgr.save()
                            elif send_result['sent'] > 0:
                                logger.warning(f"  ⚠ Partial publish: {send_result['sent']} sent, "
                                               f"{send_result['failed']} failed")
                                logger.warning(f"  ⚠ Checkpoint NOT advanced for {channel} "
                                               f"due to partial Kafka failure")
                            else:
                                logger.error(f"  ✗ Failed to publish any events to Kafka")
                                logger.error(f"  ⚠ Checkpoint NOT advanced for {channel} "
                                             f"due to Kafka failure")
                        elif LOCAL_TESTING_MODE:
                            # Local testing mode - write to file
                            if file_mgr.save_batch(payload):
                                print(f"  ✓ Saved {len(batch_events)} events to {LOCAL_OUTPUT_FILE}")
                                # Always advance checkpoint in testing mode
                                checkpoint_mgr.update_checkpoint(channel, max_record_id)
                                checkpoint_mgr.save()
                            else:
                                print(f"  ✗ Failed to save events locally")
                        else:
                            # Production mode - HTTPS transmission
                            if transmission_mgr.send_batch(payload):
                                # Only advance checkpoint on successful transmission
                                checkpoint_mgr.update_checkpoint(channel, max_record_id)
                                checkpoint_mgr.save()
                            else:
                                # Save to fallback if transmission failed
                                transmission_mgr.save_to_fallback(payload)
                                print(f"  ⚠ Checkpoint NOT advanced for {channel} due to transmission failure")
                        
                        batch_events = []  # Clear for next channel
            
            cycle_duration = time.time() - cycle_start
            print(f"Cycle complete in {cycle_duration:.2f}s\n")
            
            # Sleep until next cycle
            sleep_time = max(0, COLLECTION_INTERVAL_SECONDS - cycle_duration)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("\n\nGraceful shutdown initiated...")
        checkpoint_mgr.save()
        if kafka_mgr:
            kafka_mgr.close()
        release_pid_lock()
        print("Checkpoints saved")
        print(f"Total cycles completed: {cycle_count}")
        print("Shutdown complete")
        sys.exit(0)
    
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        checkpoint_mgr.save()
        if kafka_mgr:
            kafka_mgr.close()
        release_pid_lock()
        sys.exit(1)


if __name__ == "__main__":
    run_collector()
