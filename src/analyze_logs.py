"""
Log Analysis Tool for SentinelCore
Analyzes collected events, detects errors, and generates fault diagnosis reports.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime


# ============================================================================
# ERROR DETECTION ENGINE
# ============================================================================

# Known critical event patterns for fault detection
CRITICAL_PATTERNS = {
    ('Microsoft-Windows-Kernel-Power', 41): {
        'title': 'Unexpected Shutdown / BSOD',
        'diagnosis': 'System experienced an unexpected shutdown or blue screen.',
        'causes': [
            'Hardware failure (RAM, PSU, motherboard)',
            'Driver compatibility issue',
            'Overheating causing thermal shutdown',
            'Power supply instability'
        ],
        'actions': [
            'Check Windows Reliability Monitor for crash details',
            'Run memory diagnostic: mdsched.exe',
            'Check Event Viewer for related BugCheck events',
            'Monitor CPU/GPU temperatures during load'
        ]
    },
    ('Microsoft-Windows-Kernel-Power', 109): {
        'title': 'Kernel Power Shutdown',
        'diagnosis': 'The kernel power manager initiated a system shutdown or restart.',
        'causes': ['Planned or unexpected system shutdown', 'Power loss event'],
        'actions': ['Review if shutdown was planned', 'Check UPS/power supply']
    },
    ('Microsoft-Windows-Kernel-PnP', 219): {
        'title': 'Driver Start Timeout',
        'diagnosis': 'A driver failed to start within the allotted time.',
        'causes': [
            'Device driver slow to initialize',
            'Hardware not responding',
            'Driver compatibility issue'
        ],
        'actions': [
            'Update device drivers',
            'Check Windows Update for driver updates',
            'Verify hardware is functioning (Device Manager)'
        ]
    },
    ('Microsoft-Windows-DistributedCOM', 10016): {
        'title': 'DCOM Permission Violation',
        'diagnosis': 'Application-specific permission settings missing for COM activation.',
        'causes': ['Default DCOM permissions restrict certain apps'],
        'actions': [
            'Usually benign - can be safely ignored',
            'If problematic: use dcomcnfg to adjust permissions'
        ]
    },
    ('Microsoft-Windows-Kernel-Processor-Power', 37): {
        'title': 'CPU Thermal Throttling',
        'diagnosis': 'Processor speed limited by system firmware.',
        'causes': [
            'CPU overheating',
            'Power management settings',
            'BIOS power limits enforced'
        ],
        'actions': [
            'Check CPU temperatures',
            'Clean fans and heatsinks',
            'Review power plan settings',
            'Update BIOS/UEFI'
        ]
    },
    ('Service Control Manager', 7000): {
        'title': 'Service Start Failure',
        'diagnosis': 'A Windows service failed to start.',
        'causes': ['Missing dependencies', 'Corrupted service binary', 'Permission issue'],
        'actions': ['Check service dependencies', 'Repair/reinstall the service', 'Run sfc /scannow']
    },
    ('Service Control Manager', 7031): {
        'title': 'Service Crash and Restart',
        'diagnosis': 'A service terminated unexpectedly and was restarted.',
        'causes': ['Software bug', 'Resource exhaustion', 'Dependency failure'],
        'actions': ['Check service-specific logs', 'Review memory usage', 'Update the service']
    },
    ('Service Control Manager', 7034): {
        'title': 'Service Unexpected Termination',
        'diagnosis': 'A service terminated unexpectedly.',
        'causes': ['Application crash', 'Out of memory', 'Unhandled exception'],
        'actions': ['Check application event log', 'Review crash dumps', 'Increase memory']
    },
    ('Volsnap', 25): {
        'title': 'Shadow Copy Failure',
        'diagnosis': 'Volume shadow copies aborted due to insufficient resources.',
        'causes': ['Low disk space', 'VSS service issue', 'Disk I/O bottleneck'],
        'actions': ['Free disk space', 'Run vssadmin list shadowstorage', 'Check disk health']
    },
    ('disk', 153): {
        'title': 'Disk I/O Delay',
        'diagnosis': 'The IO operation encountered a long delay.',
        'causes': ['Failing hard drive', 'Insufficient disk performance', 'Driver issues'],
        'actions': ['Run chkdsk /f /r', 'Check SMART status', 'Consider SSD upgrade']
    },
    ('Microsoft-Windows-WindowsUpdateClient', 20): {
        'title': 'Windows Update Failure',
        'diagnosis': 'Windows Update installation failed.',
        'causes': ['Insufficient disk space', 'Corrupted update components', 'System file corruption'],
        'actions': [
            'Run Windows Update Troubleshooter',
            'Run DISM /Online /Cleanup-Image /RestoreHealth',
            'Run sfc /scannow',
            'Clear SoftwareDistribution folder'
        ]
    },
}

LEVEL_NAMES = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}


def detect_errors(events):
    """
    Detect and classify errors in collected events.
    Returns a list of detected error dicts with diagnosis info.
    """
    detected = []
    for event in events:
        provider = event.get('provider_name', '')
        event_id = event.get('event_id', 0)
        level = event.get('level', 4)

        # Only detect errors/warnings (level 1-3)
        if level not in [1, 2, 3]:
            continue

        error_info = {
            'event_record_id': event.get('event_record_id', 0),
            'provider_name': provider,
            'event_id': event_id,
            'level': level,
            'level_name': LEVEL_NAMES.get(level, f'LEVEL_{level}'),
            'event_time': event.get('event_time', 'Unknown'),
            'log_channel': event.get('log_channel', 'Unknown'),
            'fault_type': event.get('fault_type', 'UNKNOWN'),
            'cpu_at_time': event.get('cpu_usage_percent', 0),
            'memory_at_time': event.get('memory_usage_percent', 0),
            'disk_at_time': event.get('disk_free_percent', 0),
        }

        # Look up known pattern
        key = (provider, event_id)
        if key in CRITICAL_PATTERNS:
            pattern = CRITICAL_PATTERNS[key]
            error_info['known_pattern'] = True
            error_info['title'] = pattern['title']
            error_info['diagnosis'] = pattern['diagnosis']
            error_info['causes'] = pattern['causes']
            error_info['actions'] = pattern['actions']
        else:
            # Generic classification by provider substring
            error_info['known_pattern'] = False
            error_info['title'] = f'{provider} Event {event_id}'
            error_info['diagnosis'] = f'Unrecognized event from {provider}'
            error_info['causes'] = []
            error_info['actions'] = ['Check Event Viewer for details', 'Search Microsoft docs for this Event ID']

        detected.append(error_info)

    return detected


def generate_resource_alerts(events):
    """Detect resource exhaustion patterns from event snapshots."""
    alerts = []
    high_cpu_events = [e for e in events if e.get('cpu_usage_percent', 0) > 90]
    high_mem_events = [e for e in events if e.get('memory_usage_percent', 0) > 90]
    low_disk_events = [e for e in events if e.get('disk_free_percent', 100) < 10]

    if high_cpu_events:
        alerts.append({
            'type': 'HIGH_CPU',
            'count': len(high_cpu_events),
            'severity': 'WARNING',
            'message': f'CPU usage exceeded 90% during {len(high_cpu_events)} event captures',
            'action': 'Review running processes, check for CPU-intensive tasks'
        })
    if high_mem_events:
        alerts.append({
            'type': 'HIGH_MEMORY',
            'count': len(high_mem_events),
            'severity': 'WARNING',
            'message': f'Memory usage exceeded 90% during {len(high_mem_events)} event captures',
            'action': 'Identify memory-intensive processes, consider adding RAM'
        })
    if low_disk_events:
        alerts.append({
            'type': 'LOW_DISK',
            'count': len(low_disk_events),
            'severity': 'CRITICAL',
            'message': f'Disk free space below 10% during {len(low_disk_events)} event captures',
            'action': 'Free disk space immediately, run Disk Cleanup'
        })
    return alerts


# ============================================================================
# DATA LOADING
# ============================================================================

def load_events(filename="collected_events.json"):
    """Load events from JSON file with robust error handling."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"Error: Expected JSON object in '{filename}', got {type(data).__name__}", file=sys.stderr)
            sys.exit(1)
        return data
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filename}': {e}", file=sys.stderr)
        sys.exit(1)


# ============================================================================
# ANALYSIS AND REPORTS
# ============================================================================

def analyze_events(data):
    """Generate statistics and analysis from events."""
    events = data.get('events', [])

    if not events:
        print("No events found in file")
        return

    total_events = len(events)

    # Group by log channel
    by_channel = Counter(e.get('log_channel') for e in events)

    # Group by event level
    by_level = Counter(e.get('level') for e in events)

    # Group by provider
    by_provider = Counter(e.get('provider_name') for e in events)

    # Group by event ID
    by_event_id = Counter(e.get('event_id') for e in events)

    # Group by fault type (new)
    by_fault = Counter(e.get('fault_type', 'UNKNOWN') for e in events)

    # Resource usage stats
    cpu_values = [e.get('cpu_usage_percent', 0) for e in events if e.get('cpu_usage_percent') is not None]
    mem_values = [e.get('memory_usage_percent', 0) for e in events if e.get('memory_usage_percent') is not None]
    disk_values = [e.get('disk_free_percent', 0) for e in events if e.get('disk_free_percent') is not None]

    # Print report
    print("=" * 80)
    print("SENTINELCORE EVENT ANALYSIS REPORT")
    print("=" * 80)

    # System Info
    system_info = data.get('system_info', {})
    if system_info:
        print("\nSYSTEM INFORMATION")
        print("-" * 80)
        print(f"Hostname:        {system_info.get('hostname', 'Unknown')}")
        print(f"System ID:       {system_info.get('system_id', 'Unknown')}")
        print(f"OS Version:      {system_info.get('os_version', 'Unknown')}")
        print(f"Boot Session:    {system_info.get('boot_session_id', 'Unknown')}")
        print(f"Uptime:          {system_info.get('uptime_seconds', 0)} seconds")

    # Collector info
    collector_info = data.get('collector_info', {})
    if collector_info:
        print(f"\nCollector Version: {collector_info.get('version', 'Unknown')}")
        print(f"Created:           {collector_info.get('created', 'Unknown')}")

    print(f"Last Updated:      {data.get('last_updated', 'Unknown')}")

    # Event summary
    print(f"\nEVENT SUMMARY")
    print("-" * 80)
    print(f"Total Events:    {total_events}")

    # Events by channel
    print(f"\nEvents by Log Channel:")
    for channel, count in by_channel.most_common():
        print(f"  {str(channel):60s} {count:5d} ({count/total_events*100:5.1f}%)")

    # Events by level
    print(f"\nEvents by Severity Level:")
    for level, count in sorted(by_level.items()):
        level_name = LEVEL_NAMES.get(level, f'Unknown({level})')
        print(f"  {level_name:20s} {count:5d} ({count/total_events*100:5.1f}%)")

    # Events by fault type
    print(f"\nEvents by Fault Classification:")
    for fault_type, count in by_fault.most_common():
        if fault_type and fault_type != 'UNKNOWN':
            print(f"  {str(fault_type):30s} {count:5d} ({count/total_events*100:5.1f}%)")
    unknown_count = by_fault.get('UNKNOWN', 0) + by_fault.get(None, 0)
    if unknown_count:
        print(f"  {'UNKNOWN':30s} {unknown_count:5d} ({unknown_count/total_events*100:5.1f}%)")

    # Top providers
    print(f"\nTop 10 Event Providers:")
    for provider, count in by_provider.most_common(10):
        print(f"  {str(provider):60s} {count:5d}")

    # Top event IDs
    print(f"\nTop 10 Event IDs:")
    for event_id, count in by_event_id.most_common(10):
        example = next((e for e in events if e.get('event_id') == event_id), None)
        provider = example.get('provider_name', 'Unknown') if example else 'Unknown'
        print(f"  {event_id:6d} ({str(provider):45s}) {count:5d}")

    # Resource usage
    print(f"\nSYSTEM RESOURCE USAGE (during collection)")
    print("-" * 80)
    if cpu_values:
        print(f"CPU Usage:       Min={min(cpu_values):.1f}%  Max={max(cpu_values):.1f}%  Avg={sum(cpu_values)/len(cpu_values):.1f}%")
    if mem_values:
        print(f"Memory Usage:    Min={min(mem_values):.1f}%  Max={max(mem_values):.1f}%  Avg={sum(mem_values)/len(mem_values):.1f}%")
    if disk_values:
        print(f"Disk Free:       Min={min(disk_values):.1f}%  Max={max(disk_values):.1f}%  Avg={sum(disk_values)/len(disk_values):.1f}%")

    # ============================================================
    # FAULT DIAGNOSIS SECTION
    # ============================================================
    print(f"\n{'=' * 80}")
    print("FAULT DIAGNOSIS REPORT")
    print("=" * 80)

    errors = detect_errors(events)
    resource_alerts = generate_resource_alerts(events)

    if not errors and not resource_alerts:
        print("\n  \u2713 No faults or errors detected. System appears healthy.")
    else:
        # Summarize by severity
        critical_count = sum(1 for e in errors if e['level'] == 1)
        error_count = sum(1 for e in errors if e['level'] == 2)
        warning_count = sum(1 for e in errors if e['level'] == 3)

        print(f"\n  Detected Issues: {len(errors)}")
        if critical_count:
            print(f"    \u2717 CRITICAL:  {critical_count}")
        if error_count:
            print(f"    \u2717 ERROR:     {error_count}")
        if warning_count:
            print(f"    \u26a0 WARNING:   {warning_count}")

        # Show unique error patterns
        pattern_counts = Counter(
            (e['provider_name'], e['event_id'], e.get('title', ''))
            for e in errors
        )
        print(f"\n  Unique Error Patterns ({len(pattern_counts)}):")
        print("  " + "-" * 76)
        for (provider, eid, title), count in pattern_counts.most_common(15):
            known = any(e['known_pattern'] for e in errors
                       if e['provider_name'] == provider and e['event_id'] == eid)
            marker = "\u2714" if known else "?"
            print(f"    [{marker}] {title:45s} x{count:4d}  (EventID {eid})")

        # Show top diagnosed issues
        diagnosed = [e for e in errors if e.get('known_pattern')]
        if diagnosed:
            seen_patterns = set()
            print(f"\n  Diagnosed Issues (with root cause analysis):")
            print("  " + "-" * 76)
            for err in diagnosed:
                key = (err['provider_name'], err['event_id'])
                if key in seen_patterns:
                    continue
                seen_patterns.add(key)
                count = pattern_counts.get(
                    (err['provider_name'], err['event_id'], err.get('title', '')), 0
                )
                print(f"\n    [{err['level_name']}] {err['title']} (x{count})")
                print(f"    Diagnosis: {err['diagnosis']}")
                if err.get('causes'):
                    print(f"    Possible Causes:")
                    for cause in err['causes']:
                        print(f"      \u2022 {cause}")
                if err.get('actions'):
                    print(f"    Recommended Actions:")
                    for action in err['actions']:
                        print(f"      \u2192 {action}")

        # Resource alerts
        if resource_alerts:
            print(f"\n  Resource Alerts:")
            print("  " + "-" * 76)
            for alert in resource_alerts:
                print(f"    [{alert['severity']}] {alert['message']}")
                print(f"      \u2192 {alert['action']}")

    print("\n" + "=" * 80)


def export_summary(data, output_file="event_summary.txt"):
    """Export full summary with fault diagnosis to text file."""
    events = data.get('events', [])
    errors = detect_errors(events)
    resource_alerts = generate_resource_alerts(events)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("SENTINELCORE EVENT SUMMARY WITH FAULT DIAGNOSIS\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Total Events: {len(events)}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Fault diagnosis summary at top
        f.write("FAULT DIAGNOSIS SUMMARY\n")
        f.write("-" * 80 + "\n")

        if not errors:
            f.write("No faults detected. System appears healthy.\n\n")
        else:
            critical_count = sum(1 for e in errors if e['level'] == 1)
            error_count = sum(1 for e in errors if e['level'] == 2)
            warning_count = sum(1 for e in errors if e['level'] == 3)
            f.write(f"Total Issues: {len(errors)}\n")
            f.write(f"  CRITICAL:  {critical_count}\n")
            f.write(f"  ERROR:     {error_count}\n")
            f.write(f"  WARNING:   {warning_count}\n\n")

            # Diagnosed issues
            diagnosed = [e for e in errors if e.get('known_pattern')]
            seen = set()
            for err in diagnosed:
                key = (err['provider_name'], err['event_id'])
                if key in seen:
                    continue
                seen.add(key)
                f.write(f"[{err['level_name']}] {err['title']}\n")
                f.write(f"  Diagnosis: {err['diagnosis']}\n")
                if err.get('causes'):
                    f.write(f"  Causes:\n")
                    for c in err['causes']:
                        f.write(f"    - {c}\n")
                if err.get('actions'):
                    f.write(f"  Actions:\n")
                    for a in err['actions']:
                        f.write(f"    -> {a}\n")
                f.write("\n")

        # Resource alerts
        if resource_alerts:
            f.write("RESOURCE ALERTS\n")
            f.write("-" * 80 + "\n")
            for alert in resource_alerts:
                f.write(f"[{alert['severity']}] {alert['message']}\n")
                f.write(f"  Action: {alert['action']}\n")
            f.write("\n")

        # Event details
        f.write("\nEVENT DETAILS\n")
        f.write("-" * 80 + "\n")

        for i, event in enumerate(events, 1):
            level = event.get('level', 0)
            level_str = LEVEL_NAMES.get(level, f'LEVEL_{level}')
            fault = event.get('fault_type', '')

            f.write(f"{i:4d}. [{level_str:8s}] {event.get('provider_name', 'Unknown'):50s} "
                   f"EventID={event.get('event_id', 0):5d} RecordID={event.get('event_record_id', 0):8d}\n")
            f.write(f"      Time: {event.get('event_time', 'Unknown')}\n")
            f.write(f"      Channel: {event.get('log_channel', 'Unknown')}\n")
            if fault:
                f.write(f"      Fault: {fault}\n")
            f.write(f"      CPU={event.get('cpu_usage_percent', 0):.1f}% "
                   f"MEM={event.get('memory_usage_percent', 0):.1f}% "
                   f"DISK={event.get('disk_free_percent', 0):.1f}%\n")
            f.write("\n")

    print(f"\nDetailed summary exported to: {output_file}")


def main():
    """Main function"""
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = "collected_events.json"

    print(f"Loading events from: {filename}\n")
    data = load_events(filename)

    analyze_events(data)

    # Ask if user wants detailed export
    print("\nExport detailed summary to file? (y/n): ", end='')
    try:
        response = input().strip().lower()
        if response == 'y':
            export_summary(data)
    except (KeyboardInterrupt, EOFError):
        print("\nSkipped export")


if __name__ == "__main__":
    main()
