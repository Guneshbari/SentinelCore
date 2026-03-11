"""
SentinelCore - Production-grade Windows Telemetry Agent
Version: 4.0.0

CHANGES FROM v3:
- Strategy pattern replaces inline mode branching
- Resource snapshot moved outside event loop (was per-event)
- Checkpoint saved once per cycle (was per-channel)
- ErrorClassifier replaced with module-level functions
- Removed os.chdir() — all paths are now absolute
- Dead HTTPS path clearly separated from Kafka pipeline
- Version string unified
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
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from collections import deque
import winreg
import uuid

try:
    import win32evtlog
    import pywintypes
except ImportError:
    print("ERROR: pywin32 required. pip install pywin32", file=sys.stderr)
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("ERROR: psutil required. pip install psutil", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests required. pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from kafka import KafkaProducer
    from kafka.errors import KafkaError
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False

# ============================================================================
# CONSTANTS
# ============================================================================

COLLECTOR_VERSION = "4.0.0"
AGENT_VERSION = "2.1.0"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")

LEVEL_NAMES = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}

# Resource alert thresholds
CPU_ALERT_THRESHOLD    = 90   # percent
MEMORY_ALERT_THRESHOLD = 90   # percent
DISK_LOW_THRESHOLD     = 10   # percent free

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config() -> Dict:
    """Load config.json, falling back to built-in defaults."""
    defaults = {
        "kafka": {
            "bootstrap_servers": "<WSL_IP>:9092",
            "topic": "sentinel-events",
            "client_id": "windows-test-agent",
            "acks": "all",
            "retries": 5,
            "retry_backoff_ms": 3000,
            "linger_ms": 50,
            "request_timeout_ms": 15000
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
            for section in defaults:
                if section in user_config:
                    defaults[section].update(user_config[section])
            print(f"Loaded config from {CONFIG_FILE}")
        except Exception as e:
            print(f"Warning: Could not load {CONFIG_FILE}: {e}. Using defaults.", file=sys.stderr)
    else:
        print(f"Warning: {CONFIG_FILE} not found. Using built-in defaults.", file=sys.stderr)
    return defaults


_CONFIG = load_config()

# Output mode (resolved once at startup)
LOCAL_TESTING_MODE = os.getenv("SENTINEL_LOCAL_MODE", "false").lower() == "true"
KAFKA_MODE          = os.getenv("SENTINEL_KAFKA_MODE", "true").lower() == "true"

# Kafka
KAFKA_BOOTSTRAP_SERVERS  = os.getenv("KAFKA_BOOTSTRAP", _CONFIG["kafka"]["bootstrap_servers"])
KAFKA_TOPIC              = _CONFIG["kafka"]["topic"]
KAFKA_CLIENT_ID          = _CONFIG["kafka"]["client_id"]
KAFKA_ACKS               = _CONFIG["kafka"]["acks"]
KAFKA_RETRIES            = int(_CONFIG["kafka"]["retries"])
KAFKA_RETRY_BACKOFF_MS   = int(_CONFIG["kafka"]["retry_backoff_ms"])
KAFKA_LINGER_MS          = int(_CONFIG["kafka"]["linger_ms"])
KAFKA_REQUEST_TIMEOUT_MS = int(_CONFIG["kafka"]["request_timeout_ms"])

# HTTPS (only active when KAFKA_MODE=false and LOCAL_TESTING_MODE=false)
SERVER_ENDPOINT       = os.getenv("SENTINEL_SERVER_URL", "https://your-server.com/api/events")
AUTH_TOKEN            = os.getenv("SENTINEL_AUTH_TOKEN", None)
REQUEST_TIMEOUT       = 30
ENABLE_LOCAL_FALLBACK = True
FALLBACK_FILE_PREFIX  = os.path.join(SCRIPT_DIR, "events_fallback")

# Collection
TARGET_LOGS = [
    "System",
    "Microsoft-Windows-Kernel-Power",
    "Microsoft-Windows-DriverFrameworks-UserMode/Operational"
]
INCLUDE_LEVELS = [1, 2, 3]
EXCLUDE_PROVIDER_KEYWORDS = [
    "tcpip", "dns", "dhcp", "wlan", "smb", "network",
    "firewall", "winhttp", "wininet"
]
BATCH_SIZE                  = _CONFIG["agent"]["batch_size"]
COLLECTION_INTERVAL_SECONDS = 30
CHECKPOINT_FILE             = os.path.join(SCRIPT_DIR, "checkpoint.json")
MAX_RETRY_ATTEMPTS          = _CONFIG["agent"]["retry_attempts"]
RETRY_BACKOFF_BASE          = float(_CONFIG["agent"]["retry_backoff_seconds"])
DUPLICATE_HASH_WINDOW       = 10000

# Local file output
LOCAL_OUTPUT_FILE    = os.path.join(SCRIPT_DIR, "collected_events.json")
MAX_EVENTS_PER_FILE  = 500

# Safety
PID_LOCK_FILE   = os.path.join(SCRIPT_DIR, "sentinel.pid")
MIN_DISK_FREE_MB = 1024
LOG_FILE         = os.path.join(SCRIPT_DIR, "sentinel.log")

# ============================================================================
# LOGGING
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
# PID LOCK
# ============================================================================

def acquire_pid_lock() -> bool:
    if os.path.exists(PID_LOCK_FILE):
        try:
            with open(PID_LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid):
                try:
                    if 'python' in psutil.Process(old_pid).name().lower():
                        print(f"ERROR: Another instance running (PID {old_pid}). Delete {PID_LOCK_FILE} to force restart.", file=sys.stderr)
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (ValueError, IOError):
            pass

    with open(PID_LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


def release_pid_lock():
    try:
        if os.path.exists(PID_LOCK_FILE):
            os.remove(PID_LOCK_FILE)
    except Exception:
        pass


def check_disk_space() -> bool:
    try:
        free_mb = psutil.disk_usage(SCRIPT_DIR).free / (1024 * 1024)
        if free_mb < MIN_DISK_FREE_MB:
            logger.warning(f"LOW DISK: {free_mb:.0f}MB free (min: {MIN_DISK_FREE_MB}MB). Pausing.")
            return False
        return True
    except Exception:
        return True

# ============================================================================
# ADMIN PRIVILEGE DETECTION
# ============================================================================

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def check_admin_privileges() -> Tuple[bool, List[str]]:
    admin = is_admin()
    warnings = []
    if not admin:
        warnings.append("Running WITHOUT Administrator privileges. Some channels may be inaccessible.")
        for channel in TARGET_LOGS:
            try:
                query = f"<QueryList><Query><Select Path='{channel}'>*[System[EventRecordID &gt; 999999999]]</Select></Query></QueryList>"
                win32evtlog.EvtQuery(channel, win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryForwardDirection, query, None)
            except pywintypes.error as e:
                if e.winerror in [5, 15001]:
                    warnings.append(f"  ✗ Channel '{channel}' requires admin access")
                elif e.winerror == 15007:
                    warnings.append(f"  ✗ Channel '{channel}' does not exist")
        warnings.append("\nTo run as admin: open PowerShell as Administrator and run: python collector.py")
    return admin, warnings

# ============================================================================
# ERROR CLASSIFICATION (module-level functions, not a class)
# ============================================================================

_FAULT_DESCRIPTIONS = {
    'SYSTEM_FAULT':      'Critical system fault (crash, BSOD, unexpected shutdown)',
    'DRIVER_ISSUE':      'Device driver failure or timeout',
    'RESOURCE_WARNING':  'Resource exhaustion or performance degradation',
    'SERVICE_ERROR':     'Windows service start/stop failure',
    'SECURITY_EVENT':    'Permission violation or security-related event',
    'UPDATE_ERROR':      'Windows Update failure',
    'STORAGE_ERROR':     'Disk or volume shadow copy issues',
    'UNKNOWN':           'Unclassified event'
}

# (provider_substring, event_id_or_None) -> fault_type
_CLASSIFICATION_RULES = [
    ('Kernel-Power', 41,                   'SYSTEM_FAULT'),
    ('Kernel-Power', 109,                  'SYSTEM_FAULT'),
    ('BugCheck', None,                     'SYSTEM_FAULT'),
    ('BlueScreen', None,                   'SYSTEM_FAULT'),
    ('WER-SystemErrorReporting', None,     'SYSTEM_FAULT'),
    ('Kernel-PnP', 219,                    'DRIVER_ISSUE'),
    ('DriverFrameworks', None,             'DRIVER_ISSUE'),
    ('Kernel-Processor-Power', 37,         'RESOURCE_WARNING'),
    ('disk', 153,                          'RESOURCE_WARNING'),
    ('Resource-Exhaustion', None,          'RESOURCE_WARNING'),
    ('Service Control Manager', 7000,      'SERVICE_ERROR'),
    ('Service Control Manager', 7001,      'SERVICE_ERROR'),
    ('Service Control Manager', 7009,      'SERVICE_ERROR'),
    ('Service Control Manager', 7023,      'SERVICE_ERROR'),
    ('Service Control Manager', 7031,      'SERVICE_ERROR'),
    ('Service Control Manager', 7034,      'SERVICE_ERROR'),
    ('winsrvext', None,                    'SERVICE_ERROR'),
    ('DistributedCOM', 10016,              'SECURITY_EVENT'),
    ('WindowsUpdateClient', None,          'UPDATE_ERROR'),
    ('Volsnap', None,                      'STORAGE_ERROR'),
    ('Ntfs', None,                         'STORAGE_ERROR'),
     ('DistributedCOM',         None,       'SECURITY_EVENT'),
    ('Netwtw14',               None,       'DRIVER_ISSUE'),
    ('TPM-WMI',                None,       'SECURITY_EVENT'),
    ('Hyper-V',                None,       'DRIVER_ISSUE'),
    ('NDIS',                   None,       'DRIVER_ISSUE'),
    ('Win32k',                 None,       'SYSTEM_FAULT'),
    ('Application-Experience', None,       'SERVICE_ERROR'),
    ('UserModePowerService',   None,       'RESOURCE_WARNING'),
    ('Time-Service',  None,  'SERVICE_ERROR'),
    ('Server',        None,  'SERVICE_ERROR'),
    ('TPM',           None,  'SECURITY_EVENT'),
    ('WHEA-Logger',   None,  'SYSTEM_FAULT'), 
]


def classify_event(provider_name: str, event_id: int, level: int) -> Dict:
    """Classify an event and return fault_type, fault_description, severity."""
    fault_type = 'UNKNOWN'
    provider_lower = (provider_name or '').lower()

    for rule_provider, rule_eid, rule_type in _CLASSIFICATION_RULES:
        if rule_provider.lower() in provider_lower:
            if rule_eid is None or rule_eid == event_id:
                fault_type = rule_type
                break

    if fault_type == 'UNKNOWN':
        fault_type = 'SYSTEM_FAULT' if level == 1 else 'SERVICE_ERROR' if level == 2 else 'UNKNOWN'

    return {
        'fault_type': fault_type,
        'fault_description': _FAULT_DESCRIPTIONS.get(fault_type, 'Unknown'),
        'severity': LEVEL_NAMES.get(level, 'INFO')
    }


def build_diagnostic_context(resources: Dict) -> Dict:
    """Build diagnostic context from a resource snapshot."""
    cpu  = resources.get('cpu_usage_percent', 0)
    mem  = resources.get('memory_usage_percent', 0)
    disk = resources.get('disk_free_percent', 100)

    alerts = []
    if cpu  > CPU_ALERT_THRESHOLD:    alerts.append(f'HIGH CPU: {cpu}%')
    if mem  > MEMORY_ALERT_THRESHOLD: alerts.append(f'HIGH MEMORY: {mem}%')
    if disk < DISK_LOW_THRESHOLD:     alerts.append(f'LOW DISK: {disk}% free')

    return {
        'resource_state': {
            'cpu_percent':    cpu,
            'memory_percent': mem,
            'disk_free_percent': disk
        },
        'resource_alerts': alerts
    }

# ============================================================================
# SYSTEM METADATA
# ============================================================================

def get_system_id() -> str:
    if _CONFIG["agent"].get("system_id_mode") == "AUTO":
        return socket.gethostname()
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ)
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return guid
    except Exception as e:
        print(f"Warning: Could not read MachineGuid: {e}", file=sys.stderr)
        return "UNKNOWN"


def get_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "UNKNOWN"


def get_boot_session_id() -> str:
    try:
        seed = f"{get_system_id()}-{psutil.boot_time()}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))
    except Exception:
        return str(uuid.uuid4())


def get_os_version() -> str:
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", 0, winreg.KEY_READ)
        name, _  = winreg.QueryValueEx(key, "ProductName")
        build, _ = winreg.QueryValueEx(key, "CurrentBuild")
        winreg.CloseKey(key)
        return f"{name} (Build {build})"
    except Exception:
        return "Windows (Unknown Version)"


def get_uptime_seconds() -> int:
    try:
        return int(time.time() - psutil.boot_time())
    except Exception:
        return 0


def get_local_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "0.0.0.0"
    finally:
        s.close()
    return ip

# ============================================================================
# RESOURCE MONITORING
# ============================================================================

def get_resource_snapshot() -> Dict:
    """Single resource snapshot — call once per cycle, not per event."""
    try:
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            'cpu_usage_percent':    round(psutil.cpu_percent(interval=0.1), 2),
            'memory_usage_percent': round(mem.percent, 2),
            'disk_free_percent':    round(100.0 - disk.percent, 2)
        }
    except Exception:
        return {'cpu_usage_percent': 0.0, 'memory_usage_percent': 0.0, 'disk_free_percent': 0.0}

# ============================================================================
# EVENT PARSING
# ============================================================================

def extract_event_metadata(xml: str) -> Optional[Dict]:
    try:
        def find(pattern, default=None):
            m = re.search(pattern, xml)
            return m.group(1) if m else default

        record_id = find(r'EventRecordID["\']?>(\d+)<')
        if not record_id:
            return None

        return {
            'event_record_id': int(record_id),
            'provider_name':   find(r'Provider.*?Name=["\']([^"\']+)["\']', 'Unknown'),
            'event_id':        int(find(r'EventID["\']?>(\d+)<', '0')),
            'level':           int(find(r'Level["\']?>(\d+)<', '0')),
            'task':            int(find(r'Task["\']?>(\d+)<', '0')),
            'opcode':          int(find(r'Opcode["\']?>(\d+)<', '0')),
            'keywords':        find(r'Keywords["\']?>(0x[0-9a-fA-F]+)<', '0x0'),
            'process_id':      int(find(r'ProcessID["\']?>(\d+)<', '0')),
            'thread_id':       int(find(r'ThreadID["\']?>(\d+)<', '0')),
            'event_time':      find(r'SystemTime=["\']([^"\']+)["\']', datetime.now(timezone.utc).isoformat()),
        }
    except Exception as e:
        print(f"Warning: Could not parse event metadata: {e}", file=sys.stderr)
        return None


def should_exclude_provider(provider_name: str) -> bool:
    p = provider_name.lower()
    return any(kw in p for kw in EXCLUDE_PROVIDER_KEYWORDS)


def generate_event_hash(raw_xml: str, system_id: str, event_record_id: int) -> str:
    return hashlib.sha256(f"{raw_xml}{system_id}{event_record_id}".encode('utf-8')).hexdigest()

# ============================================================================
# CHECKPOINT MANAGER
# ============================================================================

class CheckpointManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.checkpoints: Dict[str, int] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.checkpoints = json.load(f)
                print(f"Loaded checkpoints for {len(self.checkpoints)} channels")
            except Exception as e:
                print(f"Warning: Could not load checkpoint: {e}", file=sys.stderr)
        else:
            print("No checkpoint file found, starting fresh")

    def get(self, channel: str) -> int:
        return self.checkpoints.get(channel, 0)

    def update(self, channel: str, record_id: int):
        self.checkpoints[channel] = record_id

    def save(self):
        """Atomic save via temp file + rename."""
        tmp = f"{self.filepath}.tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoints, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.filepath)
        except Exception as e:
            print(f"Error saving checkpoint: {e}", file=sys.stderr)

# ============================================================================
# LOCAL FILE MANAGER
# ============================================================================

class LocalFileManager:
    def __init__(self, output_file: str):
        self.output_file = output_file
        self.event_count = 0
        self._init_file()

    def _init_file(self):
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    self.event_count = len(json.load(f).get('events', []))
                print(f"Loaded existing output: {self.event_count} events")
                return
            except Exception:
                pass
        self._create_file()

    def _create_file(self):
        data = {
            'collector_info': {'version': COLLECTOR_VERSION, 'created': datetime.now(timezone.utc).isoformat()},
            'events': []
        }
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        self.event_count = 0

    def _rotate_if_needed(self):
        if self.event_count >= MAX_EVENTS_PER_FILE:
            ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            archived = self.output_file.replace('.json', f'_{ts}.json')
            os.rename(self.output_file, archived)
            print(f"  → Rotated to {archived}")
            self._create_file()

    def save_batch(self, payload: Dict) -> bool:
        try:
            self._rotate_if_needed()
            with open(self.output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            data['last_updated'] = payload.get('timestamp_collected')
            data['system_info'] = payload.get('system_info', {k: payload.get(k) for k in ('system_id', 'hostname', 'boot_session_id', 'os_version', 'uptime_seconds')})

            new_events = payload.get('events', [])
            data['events'].extend(new_events)
            self.event_count += len(new_events)

            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"  ✗ Error saving locally: {e}", file=sys.stderr)
            return False

# ============================================================================
# KAFKA MANAGER
# ============================================================================

class KafkaManager:
    def __init__(self, bootstrap_servers: str, topic: str):
        if not HAS_KAFKA:
            print("ERROR: kafka-python-ng required. pip install kafka-python-ng", file=sys.stderr)
            sys.exit(1)
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self._reconnect_attempt = 0
        self._connect()

    def _make_producer(self):
        return KafkaProducer(
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

    def _connect(self):
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                self.producer = self._make_producer()
                logger.info(f"Connected to Kafka at {self.bootstrap_servers}")
                self._reconnect_attempt = 0
                return
            except Exception as e:
                logger.error(f"Kafka connect failed ({attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}")
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
        logger.critical("Could not connect to Kafka. Will retry lazily on next send.")
        self.producer = None

    def _ensure_connected(self) -> bool:
        if self.producer:
            return True
        self._reconnect_attempt += 1
        backoff = min(RETRY_BACKOFF_BASE * (2 ** self._reconnect_attempt), 60)
        logger.info(f"Kafka reconnect attempt {self._reconnect_attempt} (backoff {backoff:.0f}s)...")
        time.sleep(backoff)
        try:
            self.producer = self._make_producer()
            logger.info(f"Reconnected to Kafka at {self.bootstrap_servers}")
            self._reconnect_attempt = 0
            return True
        except Exception as e:
            logger.error(f"Kafka reconnect failed: {e}")
            self.producer = None
            return False

    def send_batch(self, payload: Dict) -> Dict:
        result = {'sent': 0, 'failed': 0, 'success': False}
        if not self._ensure_connected():
            result['failed'] = len(payload.get('events', []))
            return result

        system_id = payload.get('system_id', 'unknown')
        futures = []
        for event in payload.get('events', []):
            msg = {
                'system_id':           system_id,
                'hostname':            payload.get('hostname'),
                'collector_version':   payload.get('collector_version'),
                'timestamp_collected': payload.get('timestamp_collected'),
                'system_info':         payload.get('system_info', {}),
                'event':               event
            }
            try:
                futures.append((event, self.producer.send(self.topic, key=system_id, value=msg)))
            except Exception as e:
                result['failed'] += 1
                logger.error(f"Send error: {e}")

        # Confirm all at once
        for event, future in futures:
            try:
                future.get(timeout=30)
                result['sent'] += 1
            except (KafkaError, Exception) as e:
                result['failed'] += 1
                logger.error(f"Delivery failed for {event.get('event_hash','?')[:12]}: {e}")
                try:
                    self.producer.flush(timeout=30)
                except Exception:
                    pass

        result['success'] = result['failed'] == 0
        return result

    def close(self):
        if self.producer:
            try:
                self.producer.flush(timeout=10)
                self.producer.close(timeout=10)
                logger.info("Kafka producer closed")
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")

# ============================================================================
# TRANSMISSION MANAGER (HTTPS fallback)
# ============================================================================

class TransmissionManager:
    def __init__(self, endpoint: str, auth_token: Optional[str] = None):
        self.endpoint = endpoint
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': f'SentinelCore/{COLLECTOR_VERSION}'
        })
        if auth_token:
            self.session.headers['Authorization'] = f'Bearer {auth_token}'

    def send_batch(self, payload: Dict) -> bool:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                r = self.session.post(self.endpoint, json=payload, timeout=REQUEST_TIMEOUT)
                if r.status_code in [200, 201, 202]:
                    return True
                print(f"  ✗ Server returned {r.status_code}: {r.text[:100]}", file=sys.stderr)
            except requests.exceptions.RequestException as e:
                print(f"  ✗ Transmission failed ({attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}", file=sys.stderr)
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
        return False

    def save_to_fallback(self, payload: Dict):
        if not ENABLE_LOCAL_FALLBACK:
            return
        try:
            path = f"{FALLBACK_FILE_PREFIX}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"  ⚠ Saved to fallback: {path}")
        except Exception as e:
            print(f"  ✗ Could not save fallback: {e}", file=sys.stderr)

# ============================================================================
# OUTPUT STRATEGY (replaces inline if/elif/else branching)
# ============================================================================

class OutputStrategy(ABC):
    @abstractmethod
    def send(self, payload: Dict) -> bool:
        """Send payload. Returns True on full success."""

    def close(self):
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class KafkaOutputStrategy(OutputStrategy):
    def __init__(self):
        self._mgr = KafkaManager(KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC)

    def send(self, payload: Dict) -> bool:
        result = self._mgr.send_batch(payload)
        n, f = result['sent'], result['failed']
        if result['success']:
            logger.info(f"  ✓ Published {n} events to Kafka topic '{KAFKA_TOPIC}'")
        elif n > 0:
            logger.warning(f"  ⚠ Partial publish: {n} sent, {f} failed — checkpoint NOT advanced")
        else:
            logger.error(f"  ✗ Kafka send failed — checkpoint NOT advanced")
        return result['success']

    def close(self):
        self._mgr.close()

    @property
    def name(self) -> str:
        return f"KAFKA  →  {KAFKA_BOOTSTRAP_SERVERS} / {KAFKA_TOPIC}"


class LocalFileOutputStrategy(OutputStrategy):
    def __init__(self):
        self._mgr = LocalFileManager(LOCAL_OUTPUT_FILE)

    def send(self, payload: Dict) -> bool:
        ok = self._mgr.save_batch(payload)
        n = len(payload.get('events', []))
        if ok:
            print(f"  ✓ Saved {n} events to {LOCAL_OUTPUT_FILE}")
        else:
            print(f"  ✗ Failed to save events locally")
        return ok

    @property
    def name(self) -> str:
        return f"LOCAL FILE  →  {LOCAL_OUTPUT_FILE}"


class HttpsOutputStrategy(OutputStrategy):
    def __init__(self):
        self._mgr = TransmissionManager(SERVER_ENDPOINT, AUTH_TOKEN)

    def send(self, payload: Dict) -> bool:
        ok = self._mgr.send_batch(payload)
        if not ok:
            self._mgr.save_to_fallback(payload)
        return ok

    @property
    def name(self) -> str:
        return f"HTTPS  →  {SERVER_ENDPOINT}"


def resolve_output_strategy() -> OutputStrategy:
    """Single point of strategy resolution — called once at startup."""
    if KAFKA_MODE:
        return KafkaOutputStrategy()
    if LOCAL_TESTING_MODE:
        return LocalFileOutputStrategy()
    return HttpsOutputStrategy()

# ============================================================================
# EVENT COLLECTION
# ============================================================================

def collect_events_from_channel(channel: str, last_record_id: int) -> List[Dict]:
    events = []
    level_filter = " or ".join(f"Level={l}" for l in INCLUDE_LEVELS)
    query = f"""
    <QueryList>
        <Query>
            <Select Path="{channel}">
                *[System[({level_filter}) and EventRecordID &gt; {last_record_id}]]
            </Select>
        </Query>
    </QueryList>"""

    try:
        handle = win32evtlog.EvtQuery(
            channel,
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryForwardDirection,
            query, None
        )
        while True:
            try:
                batch = win32evtlog.EvtNext(handle, BATCH_SIZE, 0)
                if not batch:
                    break
                for event in batch:
                    try:
                        xml = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
                        if not xml:
                            continue
                        meta = extract_event_metadata(xml)
                        if not meta:
                            continue
                        if should_exclude_provider(meta['provider_name']):
                            continue
                        events.append({'metadata': meta, 'raw_xml': xml, 'log_channel': channel})
                    except Exception:
                        continue
            except pywintypes.error as e:
                if e.winerror == 259:  # ERROR_NO_MORE_ITEMS
                    break
                raise
    except pywintypes.error as e:
        if e.winerror not in [5, 15001, 15007, 1734]:
            print(f"Error querying {channel}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error in {channel}: {e}", file=sys.stderr)

    return events

# ============================================================================
# MAIN COLLECTOR
# ============================================================================

def run_collector():
    print(f"SentinelCore v{COLLECTOR_VERSION}")
    print("=" * 70)
    print(f"PID:  {os.getpid()}   Dir: {SCRIPT_DIR}")

    if not acquire_pid_lock():
        sys.exit(1)

    admin, warnings = check_admin_privileges()
    print(f"Privileges: {'ADMINISTRATOR' if admin else 'STANDARD USER'}")
    for w in warnings:
        print(f"  ⚠ {w}")

    system_id      = get_system_id()
    hostname       = get_hostname()
    boot_session   = get_boot_session_id()
    os_version     = get_os_version()
    ip_address     = get_local_ip()

    print(f"\nSystem:   {system_id}  ({hostname})")
    print(f"OS:       {os_version}")
    print(f"Uptime:   {get_uptime_seconds()}s")
    print("=" * 70)

    strategy       = resolve_output_strategy()
    checkpoint_mgr = CheckpointManager(CHECKPOINT_FILE)
    seen_hashes: deque = deque(maxlen=DUPLICATE_HASH_WINDOW)

    print(f"\nOutput:   {strategy.name}")
    print(f"Logs:     {', '.join(TARGET_LOGS)}")
    print(f"Interval: {COLLECTION_INTERVAL_SECONDS}s")
    print("=" * 70)
    print("\nStarting collection... (Ctrl+C to stop)\n")

    cycle_count = 0

    try:
        while True:
            cycle_count += 1
            cycle_start = time.time()
            print(f"[Cycle {cycle_count}] {datetime.now(timezone.utc).isoformat()}")

            if not check_disk_space():
                time.sleep(COLLECTION_INTERVAL_SECONDS)
                continue

            # ── Resource snapshot once per cycle (NOT per event) ──────────
            resources = get_resource_snapshot()

            pending_checkpoints: Dict[str, int] = {}

            for channel in TARGET_LOGS:
                raw_events = collect_events_from_channel(channel, checkpoint_mgr.get(channel))
                if not raw_events:
                    continue

                print(f"  {channel}: {len(raw_events)} new event(s)")
                batch_events = []

                for ev in raw_events:
                    h = generate_event_hash(ev['raw_xml'], system_id, ev['metadata']['event_record_id'])
                    if h in seen_hashes:
                        continue
                    seen_hashes.append(h)

                    fault      = classify_event(ev['metadata']['provider_name'], ev['metadata']['event_id'], ev['metadata']['level'])
                    diag       = build_diagnostic_context(resources)
                    level      = ev['metadata']['level']

                    batch_events.append({
                        'log_channel':          ev['log_channel'],
                        'event_record_id':      ev['metadata']['event_record_id'],
                        'provider_name':        ev['metadata']['provider_name'],
                        'event_id':             ev['metadata']['event_id'],
                        'level':                level,
                        'task':                 ev['metadata']['task'],
                        'opcode':               ev['metadata']['opcode'],
                        'keywords':             ev['metadata']['keywords'],
                        'process_id':           ev['metadata']['process_id'],
                        'thread_id':            ev['metadata']['thread_id'],
                        'event_time':           ev['metadata']['event_time'],
                        'cpu_usage_percent':    resources['cpu_usage_percent'],
                        'memory_usage_percent': resources['memory_usage_percent'],
                        'disk_free_percent':    resources['disk_free_percent'],
                        'event_hash':           h,
                        'fault_type':           fault['fault_type'],
                        'fault_description':    fault['fault_description'],
                        'severity':             fault['severity'],
                        'message':              f"{ev['metadata']['provider_name']} Event {ev['metadata']['event_id']} ({fault['severity']}) on {ev['log_channel']}",
                        'created_at':           datetime.now(timezone.utc).isoformat(),
                        'diagnostic_context':   diag,
                        'raw_xml':              ev['raw_xml']
                    })

                if not batch_events:
                    continue

                uptime = get_uptime_seconds()
                payload = {
                    'system_id':           system_id,
                    'hostname':            hostname,
                    'boot_session_id':     boot_session,
                    'os_version':          os_version,
                    'uptime_seconds':      uptime,
                    'collector_version':   COLLECTOR_VERSION,
                    'timestamp_collected': datetime.now(timezone.utc).isoformat(),
                    'system_info': {
                        'system_id': system_id,
                        'hostname': hostname,
                        'ip_address': ip_address,
                        'agent_version': AGENT_VERSION,
                        'os_version': os_version,
                        'uptime_seconds': uptime
                    },
                    'events':              batch_events
                }

                if strategy.send(payload):
                    pending_checkpoints[channel] = max(e['metadata']['event_record_id'] for e in raw_events)

            # ── Save checkpoint once per cycle (NOT per channel) ──────────
            if pending_checkpoints:
                for ch, rid in pending_checkpoints.items():
                    checkpoint_mgr.update(ch, rid)
                checkpoint_mgr.save()

            print(f"Cycle done in {time.time() - cycle_start:.2f}s\n")
            sleep_time = max(0, COLLECTION_INTERVAL_SECONDS - (time.time() - cycle_start))
            if sleep_time:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        checkpoint_mgr.save()
        strategy.close()
        release_pid_lock()
        print(f"Checkpoints saved. Cycles completed: {cycle_count}")
        sys.exit(0)

    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        checkpoint_mgr.save()
        strategy.close()
        release_pid_lock()
        sys.exit(1)


if __name__ == "__main__":
    run_collector()