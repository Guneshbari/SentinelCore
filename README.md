# SentinelCore - Production Windows Telemetry Agent

A production-grade Windows telemetry agent focused on **System Stability and Critical Fault Detection**. Uses the modern Windows Eventing API (EvtQuery) to collect high-value system events and transmit them securely to a Linux server via HTTPS.

## Features

### Core Capabilities

- **Targeted Log Collection**: Monitors specific high-value logs (System, Kernel-Power, DriverFrameworks)
- **Multi-Level Filtering**: Filters events by level (Critical/Error/Warning) and excludes network-related providers
- **Modern API**: Uses `win32evtlog.EvtQuery`, `EvtNext`, and `EvtRender` (NOT legacy `OpenEventLog`)
- **Incremental Collection**: Per-channel checkpointing using EventRecordID prevents duplicate collection
- **Graceful Privilege Handling**: Runs without Administrator privileges (limited access) or with full access

### Data Integrity

- **SHA256 Event Hashing**: Generates integrity hash for each event using `SHA256(raw_xml + system_id + event_record_id)`
- **Duplicate Detection**: Maintains rolling window of recent event hashes to prevent duplicates
- **XML Validation**: Validates successful event rendering before processing
- **Atomic Checkpointing**: Safe checkpoint writes ensure recovery after crashes

### System Monitoring

- **Resource Snapshots**: Captures CPU usage, memory usage, and disk free percentage per event
- **Boot Session Tracking**: UUID-based boot session identification for reboot detection
- **System Metadata**: Includes system ID, hostname, OS version, and uptime

### Transmission

- **HTTPS POST**: Sends structured JSON batches to Linux server
- **Retry Logic**: Exponential backoff retry (3 attempts: 1s, 2s, 4s delays)
- **Checkpoint Safety**: Only advances checkpoint on successful transmission (HTTP 200/201/202)
- **Local Fallback**: Optionally saves failed transmissions to local files for manual recovery

## Requirements

- **Platform**: Windows 10 or Windows 11
- **Python**: 3.9 or higher
- **Privileges**: Can run as standard user (limited) or Administrator (recommended for full coverage)

## Installation

1. **Install Python dependencies**:

   ```powershell
   pip install -r requirements.txt
   ```

2. **Verify installation**:
   ```powershell
   python validate_collector.py
   ```

## Configuration

### Server Endpoint

Set the server endpoint URL via environment variable:

```powershell
# Windows PowerShell
$env:SENTINEL_SERVER_URL = "https://your-server.com/api/events"

# Or set system-wide
[System.Environment]::SetEnvironmentVariable("SENTINEL_SERVER_URL", "https://your-server.com/api/events", "User")
```

### Authentication (Optional)

If your server requires authentication, provide a Bearer token:

```powershell
$env:SENTINEL_AUTH_TOKEN = "your-bearer-token-here"
```

### Configuration Constants

Edit `collector.py` to customize behavior:

```python
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

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.0  # seconds

# Fallback Configuration
ENABLE_LOCAL_FALLBACK = True
```

## Usage

### Basic Usage (Standard User)

```powershell
python collector.py
```

The collector will run with limited privileges and skip inaccessible logs gracefully.

### Recommended Usage (Administrator)

For full event coverage, run as Administrator:

```powershell
# Open PowerShell as Administrator
python collector.py
```

### Stopping the Collector

Press `Ctrl+C` to gracefully stop. All checkpoints will be saved automatically.

## Output Format

### Event Payload Structure

Each event batch sent to the server follows this structure:

```json
{
  "system_id": "unique-machine-guid",
  "hostname": "WIN-HOST01",
  "boot_session_id": "550e8400-e29b-41d4-a716-446655440000",
  "os_version": "Windows 11 (Build 22631)",
  "uptime_seconds": 86400,
  "collector_version": "2.0.0",
  "timestamp_collected": "2026-02-16T18:00:00.123456Z",
  "events": [
    {
      "log_channel": "System",
      "event_record_id": 12345,
      "provider_name": "Microsoft-Windows-Kernel-Power",
      "event_id": 41,
      "level": 1,
      "task": 63,
      "opcode": 0,
      "keywords": "0x8000400000000002",
      "process_id": 4,
      "thread_id": 8,
      "event_time": "2026-02-16T17:59:58.000000Z",
      "cpu_usage_percent": 24.5,
      "memory_usage_percent": 63.2,
      "disk_free_percent": 45.1,
      "event_hash": "sha256-hash-here",
      "raw_xml": "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>...</Event>"
    }
  ]
}
```

### Event Levels

- **1**: Critical
- **2**: Error
- **3**: Warning

### Checkpoint File: `checkpoint.json`

Stores the last processed EventRecordID for each channel:

```json
{
  "System": 12345,
  "Microsoft-Windows-Kernel-Power": 67890,
  "Microsoft-Windows-DriverFrameworks-UserMode/Operational": 11111
}
```

## Collection Behavior

### Targeted Logs

SentinelCore focuses on system stability and critical faults by monitoring:

1. **System**: Core Windows system events
2. **Microsoft-Windows-Kernel-Power**: Power events, unexpected shutdowns, crashes
3. **Microsoft-Windows-DriverFrameworks-UserMode/Operational**: Driver framework events

### Multi-Level Filtering

Events are filtered at multiple stages:

1. **XPath Query**: Only fetch Critical (1), Error (2), Warning (3) events
2. **Provider Name**: Exclude network-related providers (tcpip, dns, dhcp, wlan, smb, network, firewall, winhttp, wininet)
3. **Duplicate Detection**: Skip events with duplicate SHA256 hashes

### Incremental Collection

- **First run**: Collects all existing events from target channels
- **Subsequent runs**: Only collects events with EventRecordID > last checkpoint
- **Collection cycles**: Run every 30 seconds (configurable)

### Error Handling

The collector handles errors gracefully:

- **Access Denied (Error 5)**: Skips channel and continues
- **Channel Not Found (Error 15007)**: Skips channel and continues
- **XML Rendering Errors**: Skips individual events but continues processing
- **Transmission Failures**: Retries with exponential backoff, falls back to local file if configured

## Performance Characteristics

- **CPU Usage**: Minimal when idle, brief spikes during collection cycles
- **Memory**: Limited by batch size (1000 events per batch) and hash window (10,000 hashes)
- **Disk I/O**: Minimal (only checkpoint writes and optional fallback files)
- **Network**: HTTPS POST requests on 30-second intervals (only when new events exist)

## Troubleshooting

### "pywin32 is required" Error

```powershell
pip install pywin32
```

### "psutil is required" Error

```powershell
pip install psutil
```

### "requests is required" Error

```powershell
pip install requests
```

### No Events Collected

1. Verify target channels exist (check Event Viewer)
2. Run as Administrator for protected logs
3. Ensure system is generating events in target channels
4. Delete `checkpoint.json` to reset and collect all events

### Transmission Failures

1. Verify server endpoint is accessible: `Test-NetConnection your-server.com -Port 443`
2. Check authentication token if required
3. Review server logs for HTTP error details
4. Check fallback files if `ENABLE_LOCAL_FALLBACK = True`

### High CPU Usage

- Increase `COLLECTION_INTERVAL_SECONDS` (default: 30)
- Reduce `BATCH_SIZE` (default: 1000)
- Reduce `DUPLICATE_HASH_WINDOW` (default: 10000)

## Architecture

### Components

1. **System Metadata Collection**: Gathers system ID, hostname, boot session UUID, OS version, uptime
2. **Event Collection**: Uses `EvtQuery()` with XPath filters for targeted incremental queries
3. **Event Parsing**: Extracts metadata from XML (provider, event ID, level, task, opcode, keywords, PIDs)
4. **Integrity Hashing**: Generates SHA256 hash for duplicate detection
5. **Resource Monitoring**: Captures CPU, memory, disk usage per event
6. **Transmission Manager**: Sends batched events via HTTPS with retry logic
7. **Checkpoint Manager**: Tracks last EventRecordID per channel with atomic writes

### Data Flow

```
[Target Channels] → [Query Events (Level Filter + RecordID > checkpoint)] →
  ├─ Render Event as XML
  ├─ Extract Metadata from XML
  ├─ Filter by Provider Name
  ├─ Generate SHA256 Hash
  ├─ Check for Duplicates
  ├─ Capture Resource Snapshot
  ├─ Build Event Payload
  └─ Batch Events

[Batched Events] → [HTTPS POST to Server] →
  ├─ Success (200/201/202) → Update Checkpoint → Save
  └─ Failure → Retry (3x with backoff) → Fallback to Local File
```

## Version

**Current Version**: 2.0.0

### Changes from 1.x

- Replaced dynamic channel enumeration with targeted log collection
- Added multi-level event filtering (XPath + provider name)
- Added SHA256 integrity hashing
- Added system resource monitoring (CPU, memory, disk)
- Replaced local file storage with HTTPS transmission
- Added retry logic with exponential backoff
- Added boot session UUID tracking
- Improved atomic checkpoint writes
- Removed file rotation (no longer needed)

## Server Integration

### Expected Server Endpoint

- **Method**: POST
- **Content-Type**: application/json
- **Expected Response**: HTTP 200, 201, or 202
- **Payload**: See "Output Format" section above

### Sample Flask Server (for testing)

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/events', methods=['POST'])
def receive_events():
    payload = request.get_json()

    # Process payload
    system_id = payload.get('system_id')
    events = payload.get('events', [])

    print(f"Received {len(events)} events from {system_id}")

    # TODO: Store in database, parse XML, etc.

    return jsonify({"status": "success", "received": len(events)}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, ssl_context='adhoc')
```

## License

Production-grade software. Ensure compliance with your organization's policies before deployment.

## Support

For issues or questions:

1. Run validation script: `python validate_collector.py`
2. Review collector output and error messages
3. Check Windows Event Viewer for event availability
4. Review server logs for transmission issues
