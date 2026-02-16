# Local Testing Guide for SentinelCore

## Quick Start

### 1. Reset Checkpoint (to collect fresh events)

Delete or reset the checkpoint file to start collecting from scratch:

```powershell
# Option 1: Delete checkpoint
Remove-Item checkpoint.json

# Option 2: Reset to zero for target logs only
@"
{
  "System": 0,
  "Microsoft-Windows-Kernel-Power": 0,
  "Microsoft-Windows-DriverFrameworks-UserMode/Operational": 0
}
"@ | Out-File -FilePath checkpoint.json -Encoding UTF8
```

### 2. Run the Collector

```powershell
python collector.py
```

The collector will:

- Run in **LOCAL TESTING MODE** by default
- Collect events from target logs
- Save to `collected_events.json` (pretty-printed for easy reading)
- Automatically rotate files at 500 events

### 3. Stop the Collector

Press **Ctrl+C** to gracefully stop. Checkpoints are saved automatically.

### 4. Analyze the Collected Events

```powershell
python analyze_logs.py
```

This will show:

- Total events collected
- Events by channel
- Events by severity level
- Top providers and event IDs
- System resource usage during collection
- Critical/Error event summary

## Configuration Options

Edit `collector.py` to customize:

```python
# How many events before rotating to a new file
MAX_EVENTS_PER_FILE = 500  # Increase if needed

# JSON formatting
PRETTY_PRINT_JSON = True  # False for compact output

# Collection interval
COLLECTION_INTERVAL_SECONDS = 30  # How often to check for new events

# Event filtering
INCLUDE_LEVELS = [1, 2, 3]  # 1=Critical, 2=Error, 3=Warning
```

## Understanding the Data Size

The collected events file size depends on:

1. **Number of events**: 500 events per file (default)
2. **XML size**: Each event includes full raw XML
3. **Pretty printing**: Adds whitespace for readability

**Typical sizes**:

- 100 events: ~500KB - 1MB
- 500 events: ~2MB - 5MB
- 1000 events: ~5MB - 10MB

**To reduce file size**:

- Set `PRETTY_PRINT_JSON = False` (reduces size by ~30-40%)
- Reduce `MAX_EVENTS_PER_FILE` (smaller files, more frequent rotation)
- Optionally strip raw_xml for analysis (keep hash for integrity)

## File Rotation

When `MAX_EVENTS_PER_FILE` is reached, the collector automatically:

1. Renames `collected_events.json` to `collected_events_YYYYMMDD_HHMMSS.json`
2. Creates a new `collected_events.json`
3. Continues collecting

## Output Format

`collected_events.json` structure:

```json
{
  "collector_info": {
    "version": "2.0.0",
    "mode": "local_testing",
    "created": "2026-02-16T18:00:00.000000Z"
  },
  "system_info": {
    "system_id": "machine-guid",
    "hostname": "hostname",
    "boot_session_id": "uuid",
    "os_version": "Windows 11 (Build 22631)",
    "uptime_seconds": 86400
  },
  "last_updated": "2026-02-16T18:30:00.000000Z",
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
      "raw_xml": "<Event>...</Event>"
    }
  ]
}
```

## Switching to Production Mode

To switch to HTTPS transmission mode:

```powershell
# Set environment variable
$env:SENTINEL_LOCAL_MODE = "false"
$env:SENTINEL_SERVER_URL = "https://your-server.com/api/events"

# Run collector
python collector.py
```

## Tips for Testing

1. **Start small**: Collect 100-200 events first to check filtering is correct
2. **Check event levels**: Use analyze_logs.py to verify only Critical/Error/Warning events
3. **Verify providers**: Check that network providers (tcpip, dns, etc.) are excluded
4. **Monitor file size**: Keep an eye on collected_events.json size
5. **Review raw XML**: Open the JSON file in a text editor to inspect actual event data

## Common Issues

**No events collected?**

- Check checkpoint.json - it may already have all events
- Reset checkpoint and run again
- Verify events exist in Event Viewer for target channels

**File too large?**

- Set `PRETTY_PRINT_JSON = False`
- Reduce `MAX_EVENTS_PER_FILE`
- Consider compressing archived files with gzip

**Wrong events collected?**

- Check `INCLUDE_LEVELS` setting
- Check `EXCLUDE_PROVIDER_KEYWORDS` list
- Review `TARGET_LOGS` list

## Example Workflow

```powershell
# 1. Reset checkpoint for fresh collection
Remove-Item checkpoint.json

# 2. Run collector for 1-2 minutes
python collector.py
# Press Ctrl+C to stop

# 3. Analyze the results
python analyze_logs.py

# 4. Review the JSON file
notepad collected_events.json

# 5. Check file size
Get-Item collected_events.json | Select-Object Length
```
