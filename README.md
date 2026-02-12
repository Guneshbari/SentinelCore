# SentinelCore - Windows Telemetry Collector

A production-grade Windows telemetry collector using the modern Windows Eventing API (EvtQuery). SentinelCore dynamically enumerates all event channels on the system, collects events incrementally with checkpointing, and excludes network-related logs.

## Features

- **Modern API**: Uses `win32evtlog.EvtQuery`, `EvtNext`, and `EvtRender` (not legacy `OpenEventLog`)
- **Dynamic Channel Discovery**: Automatically enumerates all available Windows event channels
- **Incremental Collection**: Per-channel checkpointing using EventRecordID prevents duplicate collection
- **Network Log Exclusion**: Filters out network-related channels (TCP, DNS, DHCP, SMB, Firewall, etc.)
- **Privilege Handling**: Gracefully skips channels requiring Administrator privileges without crashing
- **Performance Optimized**: Low CPU usage, batch processing (1000 events/batch), 30-second intervals
- **Compact Storage**: JSON output with optimal formatting
- **Graceful Shutdown**: Handles Ctrl+C cleanly and saves checkpoints

## Requirements

- **Platform**: Windows 10 or Windows 11
- **Python**: 3.9 or higher
- **Privileges**: Can run as standard user (limited collection) or Administrator (full collection)

## Installation

1. **Install Python dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

2. **Verify installation**:
   ```powershell
   python -c "import win32evtlog; print('pywin32 installed successfully')"
   ```

## Usage

### Basic Usage (Standard User)

```powershell
python collector.py
```

The collector will start and collect events from all accessible channels. Some channels may be skipped due to privilege requirements.

### Recommended Usage (Administrator)

For full event coverage, run as Administrator:

1. Open PowerShell as Administrator (Right-click → Run as Administrator)
2. Navigate to the collector directory
3. Run the collector:
   ```powershell
   python collector.py
   ```

### Stopping the Collector

Press `Ctrl+C` to gracefully stop the collector. All checkpoints will be saved automatically.

## Output Files

### Event Data: `events_YYYYMMDD_HHMMSS.json`

Newline-delimited JSON file containing collected events. Each line is a JSON object:

```json
{
  "system_id": "unique-machine-guid",
  "boot_session_id": "20260212232730",
  "os_version": "Windows 11 (Build 22631)",
  "collector_version": "1.0.0",
  "timestamp": "2026-02-12T17:57:30.123456Z",
  "log_channel": "Application",
  "record_id": 12345,
  "xml": "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>...</Event>"
}
```

### Checkpoint Data: `checkpoint.json`

Stores the last processed EventRecordID for each channel:

```json
{
  "Application": 12345,
  "System": 67890,
  "Security": 11111
}
```

The checkpoint file enables incremental collection across restarts—only new events are collected.

## Collection Behavior

### Channel Discovery

At startup, SentinelCore enumerates all available event channels using `EvtOpenChannelEnum()`. Typical systems have 200-400 channels.

### Network Log Exclusion

Channels containing these keywords are automatically excluded:

**Channel Keywords**: tcp, dns, dhcp, wlan, smb, network, winhttp, wininet, firewall, ndis

**Provider Keywords**: tcpip, dns, dhcp, wlan, smb, network

### Incremental Collection

- First run: Collects all existing events from monitored channels
- Subsequent runs: Only collects events with EventRecordID > last checkpoint
- Collection cycles run every 30 seconds

### Error Handling

The collector handles errors gracefully:

- **Access Denied**: Logs warning and skips the channel
- **Channel Not Found**: Logs warning and skips the channel
- **Rendering Errors**: Skips individual events but continues processing

## Performance Characteristics

- **CPU Usage**: Minimal when idle, spikes briefly during collection cycles
- **Memory**: Limited by batch size (1000 events per batch)
- **Disk I/O**: Append-only writes to output file
- **Network**: None (local collection only)

**Initial Collection**: On systems with 300+ channels and many existing events, the first cycle may take several minutes. Subsequent cycles are much faster (typically <30 seconds).

## Privilege Requirements

### Standard User
- Can collect from most application and diagnostic logs
- Cannot access Security, some System, and protected logs
- Suitable for development and testing

### Administrator
- Full access to all event channels including Security logs
- Recommended for production deployment
- Required for complete telemetry coverage

## Troubleshooting

### "pywin32 is required" Error

Install pywin32:
```powershell
pip install pywin32
```

### No Events Collected

1. Verify channels are being enumerated (check console output)
2. Check if running as Administrator for protected logs
3. Ensure system is generating events (view Event Viewer)
4. Delete `checkpoint.json` to reset and collect all events

### High CPU Usage

- Reduce `BATCH_SIZE` in `collector.py` (default: 1000)
- Increase `COLLECTION_INTERVAL_SECONDS` (default: 30)

### Large Output Files

The collector appends indefinitely. Implement log rotation:

```powershell
# Stop collector, archive old file, restart
Stop-Process -Name python
Move-Item events_*.json archive\
python collector.py
```

## Architecture

### Components

1. **System Metadata**: Collects system ID, boot session, OS version
2. **Channel Enumeration**: Uses `EvtOpenChannelEnum()` to discover channels
3. **Checkpoint Manager**: Tracks last EventRecordID per channel
4. **Event Collection**: Uses `EvtQuery()` with XML filters for incremental queries
5. **Event Rendering**: Uses `EvtRenderEventXml()` for performance
6. **JSON Output**: Compact format with metadata

### Data Flow

```
[Channel Enumeration] → [Filter Network Logs] → [For Each Channel]:
  ├─ Load Checkpoint (last EventRecordID)
  ├─ Query Events (EventRecordID > checkpoint)
  ├─ Render Events as XML
  ├─ Write to JSON output
  └─ Update Checkpoint
```

## Version

**Current Version**: 1.0.0

## License

This is production-grade software. Ensure compliance with your organization's policies before deployment.

## Support

For issues or questions, review the implementation code in `collector.py` or check Windows Event Log documentation.
