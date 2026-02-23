# SentinelCore - Production Windows Telemetry Agent

A production-grade Windows telemetry agent focused on **System Stability, Critical Fault Detection, and ML Training Data Generation**. Uses the modern Windows Eventing API (EvtQuery) to collect high-value system events, categorizes them for diagnostic ML pipelines, and transmits them securely.

## Features (v3.0.0)

### Log Collection & Classification

- **Targeted Monitoring**: System, Kernel-Power, and DriverFrameworks logs.
- **Auto-Classification Engine**: Classifies events into ML-ready labels (`SYSTEM_FAULT`, `DRIVER_ISSUE`, `SERVICE_ERROR`, `RESOURCE_WARNING`, `SECURITY_EVENT`, etc.).
- **Diagnostic Context**: Attaches point-in-time system resource snapshots (CPU >90%, Mem >90%, Disk <10%) to the exact moment an error occurred.

### Production Hardening

- **Zero-Overlap Guarantee**: Uses `sentinel.pid` locks to prevent duplicate processes.
- **Storage Guard**: Automatically pauses collection if system disk drops below 1GB free space.
- **Graceful Elevation**: Detects Administrator privileges via channel probing and falls back gracefully when limited.
- **Headless Logging**: Dual console + file (`sentinel.log`) logging.
- **Service Deployment**: Fully automated PowerShell script registers the agent as a SYSTEM service via Windows Task Scheduler.

### Data Integrity & Transmission

- **Hardware-Tied Hashing**: SHA256 hashes for deduplication using `(raw_xml + machine_guid + record_id)`.
- **Atomic Checkpoints**: Checkpoints only advance if transmission to the server succeeds.
- **Fault Tolerance**: 3-stage exponential backoff for network transmission with local fallback storage.

## Project Structure

```text
SentinelCore/
├── src/                      # Core agent log collection and analysis
│   ├── collector.py          # Main log collection (v3.0.0)
│   ├── analyze_logs.py       # Helper functions for log analysis
│   └── enhanced_analyzer.py  # Advanced ML correlation framework
├── tests/                    # End-to-end and live testing suite
│   ├── test_e2e.py           # 46 E2E unit tests
│   ├── test_live_errors.py   # Live testing against real Windows Event Log
│   └── validate_collector.py # Pipeline dependency validator
├── deploy/                   # Fully automated deployment tooling
│   └── deploy_startup.ps1    # Registers agent as a SYSTEM service
├── docs/                     # Documentation and Guides
└── README.md
```

## Setup & Deployment

**Requirements:** Windows 10/11, Python 3.9+

### Automated Deployment (Recommended)

This installs all dependencies and registers SentinelCore to run silently in the background at every startup with SYSTEM privileges.

1. Open **PowerShell as Administrator**.
2. Run:
   ```powershell
   cd C:\path\to\SentinelCore
   .\deploy\deploy_startup.ps1
   ```

### Local Testing

Run the E2E test suite to verify the agent works on your specific machine architecture:

```powershell
pip install -r requirements.txt
python -m pytest tests/test_e2e.py -v
```

## ML Target Schema

The `collected_events.json` payload is designed for direct ingestion into Machine Learning pipelines for predictive maintenance models:

```json
{
  "system_id": "machine-guid",
  "events": [
    {
      "fault_type": "DRIVER_ISSUE",
      "severity": "WARNING",
      "provider_name": "Microsoft-Windows-Kernel-PnP",
      "event_id": 219,
      "cpu_usage_percent": 45.2,
      "memory_usage_percent": 88.1,
      "disk_free_percent": 15.0,
      "diagnostic_context": {
        "high_memory": true
      },
      "raw_xml": "<Event>...</Event>"
    }
  ]
}
```

## License

Production-grade software. Ensure compliance with your organization's telemetry policies before deployment.
