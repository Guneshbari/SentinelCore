"""
SentinelCore - Production-grade Windows Telemetry Agent
Version: 2.0.0
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
"""

import json
import time
import sys
import os
import socket
import hashlib
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
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

# ============================================================================
# CONFIGURATION
# ============================================================================

COLLECTOR_VERSION = "2.0.0"

# Testing Mode - Set to True for local testing without server
LOCAL_TESTING_MODE = os.getenv("SENTINEL_LOCAL_MODE", "true").lower() == "true"

# Server Configuration (only used when LOCAL_TESTING_MODE = False)
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
BATCH_SIZE = 1000
COLLECTION_INTERVAL_SECONDS = 30
CHECKPOINT_FILE = "checkpoint.json"

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.0  # seconds
DUPLICATE_HASH_WINDOW = 10000  # Keep last N event hashes

# Local File Output Configuration
LOCAL_OUTPUT_FILE = "collected_events.json"  # Output file for local testing
MAX_EVENTS_PER_FILE = 500  # Limit events per file to keep size manageable
PRETTY_PRINT_JSON = True  # Make JSON human-readable for analysis

# Fallback Configuration (only for non-testing mode)
ENABLE_LOCAL_FALLBACK = True  # Write to local file if HTTPS fails
FALLBACK_FILE_PREFIX = "events_fallback"

# ============================================================================
# SYSTEM METADATA FUNCTIONS
# ============================================================================

def get_system_id() -> str:
    """Get unique system identifier from Windows Machine GUID"""
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
    
    if LOCAL_TESTING_MODE:
        # Use local file output for testing
        file_mgr = LocalFileManager(LOCAL_OUTPUT_FILE)
        transmission_mgr = None
    else:
        # Use HTTPS transmission for production
        transmission_mgr = TransmissionManager(SERVER_ENDPOINT, AUTH_TOKEN)
        file_mgr = None
    
    # Duplicate detection
    seen_hashes: deque = deque(maxlen=DUPLICATE_HASH_WINDOW)
    
    # Display configuration
    print(f"\nMode:           {'LOCAL TESTING' if LOCAL_TESTING_MODE else 'PRODUCTION'}")
    print(f"Target Logs:    {', '.join(TARGET_LOGS)}")
    
    if LOCAL_TESTING_MODE:
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
                        
                        # Build event payload
                        event_payload = {
                            'log_channel': event['log_channel'],
                            'event_record_id': event['metadata']['event_record_id'],
                            'provider_name': event['metadata']['provider_name'],
                            'event_id': event['metadata']['event_id'],
                            'level': event['metadata']['level'],
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
                        
                        # Save batch (local file or HTTPS depending on mode)
                        if LOCAL_TESTING_MODE:
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
        print("Checkpoints saved")
        print(f"Total cycles completed: {cycle_count}")
        print("Shutdown complete")
        sys.exit(0)
    
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        checkpoint_mgr.save()
        sys.exit(1)


if __name__ == "__main__":
    run_collector()
