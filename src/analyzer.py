"""
SentinelCore - Unified Event Analyzer
Version: 2.0.0

Replaces: analyze_logs.py + enhanced_analyzer.py

Modes:
    python analyzer.py                        # stats report to console
    python analyzer.py events.json            # custom input file
    python analyzer.py events.json --export   # also write detailed per-event report
    python analyzer.py events.json --full     # console report + auto-export
"""

import json
import sys
import re
import argparse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# ============================================================================
# CONSTANTS
# ============================================================================

ANALYZER_VERSION = "2.0.0"

LEVEL_NAMES = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}

# Resource alert thresholds (match collector.py)
CPU_ALERT_THRESHOLD    = 90   # percent
MEMORY_ALERT_THRESHOLD = 90   # percent
DISK_LOW_THRESHOLD     = 10   # percent free

# ============================================================================
# UNIFIED KNOWLEDGE BASE
#
# Each entry covers both:
#   - High-level diagnosis (used in console report summary)
#   - Root cause + actionable solutions (used in per-event deep dive)
#
# Key: (provider_name_substring, event_id)   event_id=None → match all IDs
# ============================================================================

KNOWLEDGE_BASE: Dict[Tuple, Dict] = {

    ('Microsoft-Windows-Kernel-Power', 41): {
        'title':       'Unexpected Shutdown / BSOD',
        'diagnosis':   'System experienced an unexpected shutdown or blue screen.',
        'causes': [
            'Hardware failure (RAM, PSU, motherboard)',
            'Driver compatibility issue',
            'Overheating causing thermal shutdown',
            'Power supply instability',
        ],
        'solutions': [
            'Check Windows Reliability Monitor for crash details',
            'Run memory diagnostic: mdsched.exe',
            'Check Event Viewer for related BugCheck events',
            'Monitor CPU/GPU temperatures under load',
        ],
    },

    ('Microsoft-Windows-Kernel-Power', 109): {
        'title':       'Kernel Power Shutdown',
        'diagnosis':   'The kernel power manager initiated a system shutdown or restart.',
        'causes': [
            'Planned or unexpected system shutdown',
            'Power loss event',
        ],
        'solutions': [
            'Verify if shutdown was planned',
            'Check UPS / power supply health',
        ],
    },

    ('Microsoft-Windows-Kernel-PnP', 219): {
        'title':       'Driver Start Timeout',
        'diagnosis':   'A driver failed to start within the allotted time.',
        'causes': [
            'Device driver slow to initialize',
            'Hardware not responding',
            'Driver compatibility issue with current Windows version',
        ],
        'solutions': [
            'Update the device driver to the latest version',
            'Check Windows Update for driver updates',
            'Verify hardware is functioning correctly (Device Manager)',
            'Consider disabling fast startup if issue persists',
        ],
    },

    ('Microsoft-Windows-Kernel-Processor-Power', 37): {
        'title':       'CPU Thermal Throttling',
        'diagnosis':   'Processor speed was limited by system firmware.',
        'causes': [
            'CPU overheating',
            'Power management settings limiting CPU performance',
            'BIOS/UEFI power limits being enforced',
            'Battery saving mode active (laptops)',
        ],
        'solutions': [
            'Check CPU temperatures and improve cooling',
            'Review power plan settings (High Performance vs Balanced)',
            'Update BIOS/UEFI to latest version',
            'Ensure adequate power supply for the system',
        ],
    },

    ('Microsoft-Windows-DistributedCOM', 10016): {
        'title':       'DCOM Permission Violation',
        'diagnosis':   'Application-specific permission settings do not grant Local Activation permission.',
        'causes': [
            'Default DCOM permissions restrict certain apps from starting COM servers',
            'Security hardening removed necessary permissions',
        ],
        'solutions': [
            'Usually benign — can be safely ignored',
            'If problematic: use Component Services (dcomcnfg) to adjust permissions',
            'Identify the CLSID/AppID in event details and grant appropriate permissions',
        ],
    },

    ('Service Control Manager', 7000): {
        'title':       'Service Start Failure',
        'diagnosis':   'A Windows service failed to start.',
        'causes': [
            'Missing service dependencies',
            'Corrupted service binary',
            'Permission issue',
        ],
        'solutions': [
            'Check service dependencies in services.msc',
            'Repair or reinstall the affected service',
            'Run: sfc /scannow',
        ],
    },

    ('Service Control Manager', 7001): {
        'title':       'Service Dependency Failure',
        'diagnosis':   'A service failed to start due to a dependency not being available.',
        'causes': ['Dependent service not running', 'Startup order issue'],
        'solutions': ['Check dependent service status', 'Review service startup order'],
    },

    ('Service Control Manager', 7009): {
        'title':       'Service Start Timeout',
        'diagnosis':   'A service did not respond to the start request in a timely fashion.',
        'causes': ['Service is hung during initialization', 'Resource contention at boot'],
        'solutions': ['Increase service timeout in registry if appropriate', 'Check service logs'],
    },

    ('Service Control Manager', 7023): {
        'title':       'Service Terminated with Error',
        'diagnosis':   'A service terminated with an error code.',
        'causes': ['Application bug', 'Missing DLL or resource'],
        'solutions': ['Check application-specific logs', 'Reinstall the affected application'],
    },

    ('Service Control Manager', 7031): {
        'title':       'Service Crash and Restart',
        'diagnosis':   'A service terminated unexpectedly and was scheduled for restart.',
        'causes': [
            'Software bug',
            'Resource exhaustion',
            'Dependency failure',
        ],
        'solutions': [
            'Check service-specific event logs',
            'Review memory and CPU usage',
            'Update the affected service or application',
        ],
    },

    ('Service Control Manager', 7034): {
        'title':       'Service Unexpected Termination',
        'diagnosis':   'A service terminated unexpectedly without a restart.',
        'causes': ['Application crash', 'Out of memory', 'Unhandled exception'],
        'solutions': [
            'Check Application event log for crash details',
            'Review Windows Error Reporting crash dumps',
            'Consider increasing available memory',
        ],
    },

    ('Microsoft-Windows-DistributedCOM', 10016): {
        'title':       'DCOM Activation Permission Denied',
        'diagnosis':   'App-specific permission settings do not grant COM activation rights.',
        'causes': ['Default DCOM permissions restrict certain apps'],
        'solutions': [
            'Usually benign — safe to ignore',
            'Use dcomcnfg to adjust permissions if blocking functionality',
        ],
    },

    ('Microsoft-Windows-WindowsUpdateClient', 20): {
        'title':       'Windows Update Installation Failure',
        'diagnosis':   'A Windows Update installation failed.',
        'causes': [
            'Insufficient disk space for update',
            'Corrupted Windows Update components',
            'Third-party software interference',
            'System file corruption',
        ],
        'solutions': [
            'Run Windows Update Troubleshooter',
            'Run: DISM /Online /Cleanup-Image /RestoreHealth',
            'Run: sfc /scannow',
            'Clear update cache: delete contents of C:\\Windows\\SoftwareDistribution',
            'Ensure 10GB+ free disk space',
        ],
    },

    ('Volsnap', 25): {
        'title':       'Volume Shadow Copy Failure',
        'diagnosis':   'Shadow copies were aborted due to insufficient resources.',
        'causes': [
            'Low disk space for shadow storage',
            'VSS service configuration issues',
            'Disk I/O bottleneck during snapshot',
        ],
        'solutions': [
            'Free disk space on the affected volume',
            'Resize shadow storage: vssadmin resize shadowstorage',
            'Delete old shadow copies: vssadmin delete shadows',
            'Check disk health with chkdsk',
        ],
    },

    ('disk', 153): {
        'title':       'Disk I/O Delay',
        'diagnosis':   'An I/O operation encountered an unusually long delay.',
        'causes': [
            'Failing or degraded hard drive',
            'Insufficient disk throughput (spinning HDD)',
            'Background processes causing disk contention',
        ],
        'solutions': [
            'Run: chkdsk /f /r',
            'Check SMART status with CrystalDiskInfo or similar',
            'Consider upgrading to SSD',
            'Update storage controller drivers',
        ],
    },

    ('Microsoft-Windows-Hyper-V-Hypervisor', 167): {
        'title':       'Hypervisor Active',
        'diagnosis':   'Hypervisor detected during boot (informational).',
        'causes': ['Hyper-V or WSL2 enabled', 'Virtualization-based security active'],
        'solutions': [
            'No action needed if virtualization is intentional',
            'Disable Hyper-V via Windows Features if not required',
        ],
    },

    ('Netwtw14', 5002): {
        'title':       'Intel WiFi Driver Event',
        'diagnosis':   'Network adapter encountered an issue.',
        'causes': [
            'WiFi driver instability',
            'Network interference or weak signal',
            'Power management settings disabling WiFi adapter',
        ],
        'solutions': [
            'Update Intel WiFi driver to latest version',
            'Disable WiFi power management in Device Manager',
            'Switch to 5GHz band if on 2.4GHz',
        ],
    },

    ('winsrvext', None): {
        'title':       'Windows Service Extension Event',
        'diagnosis':   'Service-related configuration or state change.',
        'causes': ['Service startup/shutdown', 'Scheduled maintenance task'],
        'solutions': [
            'Generally informational — no action required',
            'Check services.msc if service is critical',
        ],
    },
}


def lookup_knowledge(provider: str, event_id: int) -> Optional[Dict]:
    """Return knowledge base entry for a given provider + event_id, or None."""
    # Exact match first
    if (provider, event_id) in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[(provider, event_id)]

    # Substring match on provider with wildcard event_id
    for (kb_provider, kb_eid), entry in KNOWLEDGE_BASE.items():
        if kb_provider.lower() in provider.lower() and kb_eid is None:
            return entry

    return None

# ============================================================================
# DATA LOADING
# ============================================================================

def load_events(filename: str) -> Dict:
    """Load and validate events JSON. Exits with a clear message on failure."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filename}': {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"Error: Expected a JSON object in '{filename}', got {type(data).__name__}.", file=sys.stderr)
        sys.exit(1)

    return data

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def detect_errors(events: List[Dict]) -> List[Dict]:
    """Classify error/warning events and attach knowledge base entries."""
    detected = []
    for ev in events:
        level = ev.get('level', 4)
        if level not in (1, 2, 3):
            continue

        provider = ev.get('provider_name') or ''
        event_id = ev.get('event_id') or 0
        kb       = lookup_knowledge(provider, event_id)

        detected.append({
            'event_record_id': ev.get('event_record_id', 0),
            'provider_name':   provider,
            'event_id':        event_id,
            'level':           level,
            'level_name':      LEVEL_NAMES.get(level, f'LEVEL_{level}'),
            'event_time':      ev.get('event_time', 'Unknown'),
            'log_channel':     ev.get('log_channel', 'Unknown'),
            'fault_type':      ev.get('fault_type', 'UNKNOWN'),
            'cpu_at_time':     ev.get('cpu_usage_percent', 0),
            'memory_at_time':  ev.get('memory_usage_percent', 0),
            'disk_at_time':    ev.get('disk_free_percent', 0),
            'known':           kb is not None,
            'title':           kb['title']     if kb else f'{provider} Event {event_id}',
            'diagnosis':       kb['diagnosis'] if kb else f'Unrecognized event from {provider}',
            'causes':          kb.get('causes',    []) if kb else [],
            'solutions':       kb.get('solutions', []) if kb else ['Check Event Viewer for details'],
        })

    return detected


def generate_resource_alerts(events: List[Dict]) -> List[Dict]:
    """Detect resource pressure patterns across the event set."""
    alerts = []
    high_cpu  = [e for e in events if e.get('cpu_usage_percent', 0)    > CPU_ALERT_THRESHOLD]
    high_mem  = [e for e in events if e.get('memory_usage_percent', 0) > MEMORY_ALERT_THRESHOLD]
    low_disk  = [e for e in events if e.get('disk_free_percent', 100)  < DISK_LOW_THRESHOLD]

    if high_cpu:
        alerts.append({
            'type': 'HIGH_CPU', 'severity': 'WARNING', 'count': len(high_cpu),
            'message': f'CPU exceeded {CPU_ALERT_THRESHOLD}% during {len(high_cpu)} event capture(s)',
            'action':  'Review running processes; check for CPU-intensive background tasks',
        })
    if high_mem:
        alerts.append({
            'type': 'HIGH_MEMORY', 'severity': 'WARNING', 'count': len(high_mem),
            'message': f'Memory exceeded {MEMORY_ALERT_THRESHOLD}% during {len(high_mem)} event capture(s)',
            'action':  'Identify memory-intensive processes; consider adding RAM',
        })
    if low_disk:
        alerts.append({
            'type': 'LOW_DISK', 'severity': 'CRITICAL', 'count': len(low_disk),
            'message': f'Disk free below {DISK_LOW_THRESHOLD}% during {len(low_disk)} event capture(s)',
            'action':  'Free disk space immediately; run Disk Cleanup',
        })

    return alerts


def analyze_patterns(events: List[Dict]) -> List[str]:
    """Surface high-level insights from event frequency patterns."""
    insights = []

    dcom_count     = sum(1 for e in events if 'DistributedCOM'    in e.get('provider_name', ''))
    pnp_count      = sum(1 for e in events if 'Kernel-PnP'        in e.get('provider_name', ''))
    throttle_count = sum(1 for e in events if 'Processor-Power'   in e.get('provider_name', '') and e.get('event_id') == 37)
    wifi_count     = sum(1 for e in events if 'Netwtw'            in e.get('provider_name', ''))
    warning_count  = sum(1 for e in events if e.get('level') == 3)

    if warning_count > 100:
        insights.append(f'{warning_count} warning events collected — review patterns for recurring issues')
    if dcom_count > 50:
        insights.append(f'High DCOM event count ({dcom_count}) — typically benign but reducible via permissions config')
    if pnp_count > 20:
        insights.append(f'Multiple Plug-and-Play events ({pnp_count}) — consider updating device drivers')
    if throttle_count > 10:
        insights.append(f'CPU throttling detected ({throttle_count} events) — check cooling and power settings')
    if wifi_count > 15:
        insights.append(f'WiFi driver instability ({wifi_count} events) — update Intel WiFi drivers')

    return insights

# ============================================================================
# XML DESCRIPTION EXTRACTION
# ============================================================================

def extract_event_description(raw_xml: str) -> Optional[str]:
    """Pull a human-readable description from raw event XML."""
    if not raw_xml:
        return None
    try:
        root = ET.fromstring(raw_xml)
        ns = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event'}

        msg = root.find('.//e:RenderingInfo/e:Message', ns)
        if msg is not None and msg.text:
            return msg.text.strip()

        # Fallback: first 3 EventData values
        parts = [
            d.text.strip()
            for d in (root.find('.//e:EventData', ns) or root.find('.//EventData') or [])
            if hasattr(d, 'text') and d.text
        ][:3]
        return ' | '.join(parts) or None

    except ET.ParseError:
        return None

# ============================================================================
# CONSOLE REPORT (statistical overview)
# ============================================================================

def print_report(data: Dict):
    """Print a statistical overview + fault digest to stdout."""
    events = data.get('events', [])
    total  = len(events)

    if not total:
        print("No events found.")
        return

    # Pre-compute once, shared across sections
    errors          = detect_errors(events)
    resource_alerts = generate_resource_alerts(events)
    insights        = analyze_patterns(events)

    div  = "=" * 80
    dash = "-" * 80

    print(div)
    print("SENTINELCORE EVENT ANALYSIS REPORT")
    print(div)

    # ── System info ──────────────────────────────────────────────────────────
    si = data.get('system_info', {})
    if si:
        print("\nSYSTEM INFORMATION")
        print(dash)
        for label, key in [('Hostname', 'hostname'), ('System ID', 'system_id'),
                            ('OS Version', 'os_version'), ('Boot Session', 'boot_session_id'),
                            ('Uptime', 'uptime_seconds')]:
            print(f"  {label:15s}: {si.get(key, 'Unknown')}")

    ci = data.get('collector_info', {})
    if ci:
        print(f"\n  Collector:      v{ci.get('version', '?')}  (created {ci.get('created', '?')})")
    print(f"  Last Updated:   {data.get('last_updated', 'Unknown')}")

    # ── Event counts ─────────────────────────────────────────────────────────
    print(f"\nEVENT SUMMARY  ({total} total)")
    print(dash)

    by_channel  = Counter(e.get('log_channel')    for e in events)
    by_level    = Counter(e.get('level')           for e in events)
    by_fault    = Counter(e.get('fault_type', 'UNKNOWN') for e in events)
    by_provider = Counter(e.get('provider_name')   for e in events)
    by_event_id = Counter(e.get('event_id')        for e in events)

    print("\nBy Channel:")
    for ch, n in by_channel.most_common():
        print(f"  {str(ch):60s} {n:5d}  ({n/total*100:5.1f}%)")

    print("\nBy Severity:")
    for lvl, n in sorted(by_level.items()):
        print(f"  {LEVEL_NAMES.get(lvl, f'LEVEL_{lvl}'):20s} {n:5d}  ({n/total*100:5.1f}%)")

    print("\nBy Fault Type:")
    for ft, n in by_fault.most_common():
        if ft and ft != 'UNKNOWN':
            print(f"  {str(ft):30s} {n:5d}  ({n/total*100:5.1f}%)")
    unk = by_fault.get('UNKNOWN', 0)
    if unk:
        print(f"  {'UNKNOWN':30s} {unk:5d}  ({unk/total*100:5.1f}%)")

    print("\nTop 10 Providers:")
    for pv, n in by_provider.most_common(10):
        print(f"  {str(pv):60s} {n:5d}")

    print("\nTop 10 Event IDs:")
    for eid, n in by_event_id.most_common(10):
        ex = next((e for e in events if e.get('event_id') == eid), None)
        pv = ex.get('provider_name', 'Unknown') if ex else 'Unknown'
        print(f"  {str(eid):6}  ({str(pv):45s}) {n:5d}")

    # ── Resource usage ───────────────────────────────────────────────────────
    cpu_vals  = [e['cpu_usage_percent']    for e in events if 'cpu_usage_percent'    in e]
    mem_vals  = [e['memory_usage_percent'] for e in events if 'memory_usage_percent' in e]
    disk_vals = [e['disk_free_percent']    for e in events if 'disk_free_percent'    in e]

    print(f"\nRESOURCE USAGE (at event capture time)")
    print(dash)
    for label, vals in [('CPU %', cpu_vals), ('Memory %', mem_vals), ('Disk Free %', disk_vals)]:
        if vals:
            print(f"  {label:15s}  min={min(vals):.1f}  max={max(vals):.1f}  avg={sum(vals)/len(vals):.1f}")

    # ── Pattern insights ─────────────────────────────────────────────────────
    if insights:
        print(f"\nKEY INSIGHTS")
        print(dash)
        for insight in insights:
            print(f"  • {insight}")

    # ── Fault digest ─────────────────────────────────────────────────────────
    print(f"\n{div}")
    print("FAULT DIAGNOSIS DIGEST")
    print(div)

    if not errors and not resource_alerts:
        print("\n  ✓ No faults detected. System appears healthy.")
    else:
        crit  = sum(1 for e in errors if e['level'] == 1)
        err   = sum(1 for e in errors if e['level'] == 2)
        warn  = sum(1 for e in errors if e['level'] == 3)
        print(f"\n  Issues detected: {len(errors)}")
        if crit: print(f"    ✗ CRITICAL : {crit}")
        if err:  print(f"    ✗ ERROR    : {err}")
        if warn: print(f"    ⚠ WARNING  : {warn}")

        pattern_counts = Counter((e['provider_name'], e['event_id'], e['title']) for e in errors)

        print(f"\n  Unique Patterns ({len(pattern_counts)}):")
        print("  " + "-" * 76)
        for (pv, eid, title), n in pattern_counts.most_common(15):
            known = any(e['known'] for e in errors if e['provider_name'] == pv and e['event_id'] == eid)
            print(f"    [{'✔' if known else '?'}] {title:45s}  ×{n:<4d}  (EventID {eid})")

        # Diagnosed entries only
        seen = set()
        diagnosed = [e for e in errors if e['known']]
        if diagnosed:
            print(f"\n  Root Cause Analysis (known patterns):")
            print("  " + "-" * 76)
            for e in diagnosed:
                key = (e['provider_name'], e['event_id'])
                if key in seen:
                    continue
                seen.add(key)
                n = pattern_counts.get((e['provider_name'], e['event_id'], e['title']), 0)
                print(f"\n    [{e['level_name']}] {e['title']}  (×{n})")
                print(f"    Diagnosis: {e['diagnosis']}")
                if e['causes']:
                    print(f"    Causes:")
                    for c in e['causes']:
                        print(f"      • {c}")
                if e['solutions']:
                    print(f"    Solutions:")
                    for s in e['solutions']:
                        print(f"      → {s}")

        if resource_alerts:
            print(f"\n  Resource Alerts:")
            print("  " + "-" * 76)
            for a in resource_alerts:
                print(f"    [{a['severity']}] {a['message']}")
                print(f"      → {a['action']}")

    print(f"\n{div}")

# ============================================================================
# DETAILED FILE EXPORT (per-event deep dive)
# ============================================================================

def export_detailed_report(data: Dict, output_file: str = "event_report.txt"):
    """Write full per-event report with descriptions and solutions to a text file."""
    events          = data.get('events', [])
    errors          = detect_errors(events)
    resource_alerts = generate_resource_alerts(events)
    insights        = analyze_patterns(events)
    pattern_counts  = Counter((e['provider_name'], e['event_id'], e['title']) for e in errors)

    div  = "=" * 80
    dash = "-" * 80

    with open(output_file, 'w', encoding='utf-8') as f:

        def w(line=""):
            f.write(line + "\n")

        w("SENTINELCORE DETAILED EVENT REPORT")
        w(div)
        w(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        w(f"Events    : {len(events)}")
        w(f"Analyzer  : v{ANALYZER_VERSION}")
        w()

        # Insights
        if insights:
            w("KEY INSIGHTS")
            w(dash)
            for i in insights:
                w(f"  • {i}")
            w()

        # Fault summary
        w("FAULT SUMMARY")
        w(dash)
        if not errors:
            w("  No faults detected.")
        else:
            crit = sum(1 for e in errors if e['level'] == 1)
            err  = sum(1 for e in errors if e['level'] == 2)
            warn = sum(1 for e in errors if e['level'] == 3)
            w(f"  Total  : {len(errors)}")
            if crit: w(f"  CRITICAL : {crit}")
            if err:  w(f"  ERROR    : {err}")
            if warn: w(f"  WARNING  : {warn}")
            w()

            seen = set()
            for e in errors:
                if not e['known']:
                    continue
                key = (e['provider_name'], e['event_id'])
                if key in seen:
                    continue
                seen.add(key)
                n = pattern_counts.get((e['provider_name'], e['event_id'], e['title']), 0)
                w(f"  [{e['level_name']}] {e['title']}  (×{n})")
                w(f"    Diagnosis: {e['diagnosis']}")
                if e['causes']:
                    w(f"    Causes:")
                    for c in e['causes']:
                        w(f"      - {c}")
                if e['solutions']:
                    w(f"    Solutions:")
                    for s in e['solutions']:
                        w(f"      → {s}")
                w()

        # Resource alerts
        if resource_alerts:
            w("RESOURCE ALERTS")
            w(dash)
            for a in resource_alerts:
                w(f"  [{a['severity']}] {a['message']}")
                w(f"    → {a['action']}")
            w()

        # Per-event details
        w(div)
        w("PER-EVENT DETAILS")
        w(div)
        w()

        # Build a quick error lookup for per-event annotation
        error_map = {(e['provider_name'], e['event_id']): e for e in errors}

        for i, ev in enumerate(events, 1):
            lvl      = ev.get('level', 0)
            provider = ev.get('provider_name', 'Unknown')
            event_id = ev.get('event_id', 0)
            lvl_str  = LEVEL_NAMES.get(lvl, f'LEVEL_{lvl}')

            w(f"{i:4d}. [{lvl_str:8s}] {provider:50s} EventID={event_id:5d}  RecordID={ev.get('event_record_id', 0)}")
            w(f"       Time    : {ev.get('event_time', 'Unknown')}")
            w(f"       Channel : {ev.get('log_channel', 'Unknown')}")
            w(f"       Resources: CPU={ev.get('cpu_usage_percent', 0):.1f}%  MEM={ev.get('memory_usage_percent', 0):.1f}%  DISK={ev.get('disk_free_percent', 0):.1f}% free")

            desc = extract_event_description(ev.get('raw_xml', ''))
            if desc:
                w(f"       Desc    : {desc[:300]}")

            if lvl in (1, 2, 3):
                kb_entry = error_map.get((provider, event_id))
                if kb_entry:
                    w()
                    w(f"       ┌─ {kb_entry['title']}")
                    w(f"       │  {kb_entry['diagnosis']}")
                    if kb_entry['causes']:
                        w(f"       │  Causes:")
                        for c in kb_entry['causes']:
                            w(f"       │    • {c}")
                    if kb_entry['solutions']:
                        w(f"       │  Solutions:")
                        for s in kb_entry['solutions']:
                            w(f"       │    → {s}")
                    w(f"       └{'─' * 60}")
            w()

    print(f"\nDetailed report written to: {output_file}")

# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SentinelCore Event Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyzer.py                           # load collected_events.json
  python analyzer.py my_events.json            # custom file
  python analyzer.py my_events.json --export   # also write event_report.txt
  python analyzer.py my_events.json --full     # console report + auto-export
        """
    )
    parser.add_argument('file',    nargs='?', default='collected_events.json', help='Events JSON file')
    parser.add_argument('--export', action='store_true', help='Export detailed per-event report to file')
    parser.add_argument('--full',   action='store_true', help='Console report + auto-export (shorthand)')
    parser.add_argument('--out',   default='event_report.txt', help='Output filename for export (default: event_report.txt)')
    args = parser.parse_args()

    print(f"Loading: {args.file}\n")
    data = load_events(args.file)

    print_report(data)

    if args.export or args.full:
        export_detailed_report(data, args.out)
    else:
        ans = input("\nExport detailed per-event report? [y/N]: ").strip().lower()
        if ans == 'y':
            export_detailed_report(data, args.out)


if __name__ == "__main__":
    main()