"""
SentinelCore LIVE Error Detection Test
======================================
This script tests error detection against REAL system events, not synthetic data.

It does three things:
1. Collects REAL errors/warnings currently in your Windows Event Log
2. Runs the error detector on them and reports what it found
3. Optionally generates a DELIBERATE error (stops/restarts a service) so you
   can watch the collector + detector catch it live

REQUIRES: Administrator privileges for full coverage and error generation.

Usage:
    # Test with existing errors (works without admin too)
    python test_live_errors.py

    # Generate a deliberate error + detect it (REQUIRES ADMIN)
    python test_live_errors.py --generate-error

    # Run collector for N seconds, then analyze (REQUIRES ADMIN for error gen)
    python test_live_errors.py --generate-error --collect-seconds 15
"""

import sys
import os
import json
import time
import subprocess
import ctypes
import tempfile
import shutil
from datetime import datetime, timezone
from collections import Counter

# Add project dir to path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(PROJECT_DIR, '..', 'src'))
sys.path.insert(0, SRC_DIR)

from collector import (
    is_admin, collect_events_from_channel, extract_event_metadata,
    classify_event, build_diagnostic_context, generate_event_hash,
    get_resource_snapshot, get_system_id, CheckpointManager
)
from analyzer import detect_errors, generate_resource_alerts, LEVEL_NAMES


DIVIDER = "=" * 80
THIN_DIVIDER = "-" * 80


def print_header(title):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def print_section(title):
    print(f"\n  {title}")
    print(f"  {THIN_DIVIDER}")


# ============================================================================
# PHASE 1: Detect existing real errors in Windows Event Log
# ============================================================================

def test_real_error_detection():
    """
    Collect REAL events from the System event log and run error detection on them.
    This proves the detector works on actual Windows events, not just synthetic data.
    """
    print_header("PHASE 1: DETECTING REAL ERRORS IN WINDOWS EVENT LOG")

    admin = is_admin()
    print(f"  Running as Administrator: {admin}")

    # Collect from System log (record_id=0 = get all available)
    print(f"\n  Collecting events from System log...")
    raw_events = collect_events_from_channel("System", 0)
    print(f"  Raw events collected: {len(raw_events)}")

    if not raw_events:
        print("\n  \u26a0 No events collected from System log.")
        print("  This might mean:")
        print("    - No Critical/Error/Warning events exist")
        print("    - Checkpoint is ahead of all events (reset checkpoint.json)")
        print("    - You need Administrator privileges")
        return [], False

    # Build proper event payloads (same as collector does)
    system_id = get_system_id()
    processed_events = []

    for event in raw_events:
        meta = event['metadata']
        resources = get_resource_snapshot()
        fault_info = classify_event(
            meta['provider_name'], meta['event_id'], meta['level']
        )
        diag_ctx = build_diagnostic_context(resources)

        processed_events.append({
            'log_channel': event['log_channel'],
            'event_record_id': meta['event_record_id'],
            'provider_name': meta['provider_name'],
            'event_id': meta['event_id'],
            'level': meta['level'],
            'task': meta['task'],
            'opcode': meta['opcode'],
            'keywords': meta['keywords'],
            'process_id': meta['process_id'],
            'thread_id': meta['thread_id'],
            'event_time': meta['event_time'],
            'cpu_usage_percent': resources['cpu_usage_percent'],
            'memory_usage_percent': resources['memory_usage_percent'],
            'disk_free_percent': resources['disk_free_percent'],
            'event_hash': generate_event_hash(event['raw_xml'], system_id, meta['event_record_id']),
            'fault_type': fault_info['fault_type'],
            'fault_description': fault_info['fault_description'],
            'severity': fault_info['severity'],
            'diagnostic_context': diag_ctx,
            'raw_xml': event['raw_xml']
        })

    # Run error detection on REAL events
    detected_errors = detect_errors(processed_events)
    resource_alerts = generate_resource_alerts(processed_events)

    # Report results
    print_section("EVENT COLLECTION RESULTS")
    print(f"    Total events collected:  {len(processed_events)}")

    level_counts = Counter(e['level'] for e in processed_events)
    for lvl in sorted(level_counts):
        print(f"      {LEVEL_NAMES.get(lvl, f'Level {lvl}'):12s}: {level_counts[lvl]}")

    fault_counts = Counter(e['fault_type'] for e in processed_events)
    print(f"\n    Fault Classifications:")
    for ft, count in fault_counts.most_common():
        print(f"      {ft:25s}: {count}")

    print_section("ERROR DETECTION RESULTS")
    print(f"    Errors/Warnings detected: {len(detected_errors)}")

    if detected_errors:
        known = [e for e in detected_errors if e.get('known')]
        unknown = [e for e in detected_errors if not e.get('known')]

        print(f"    Known patterns matched:   {len(known)}")
        print(f"    Unknown patterns:         {len(unknown)}")

        # Show unique detected patterns
        pattern_counts = Counter(
            (e['provider_name'], e['event_id'], e.get('title', ''))
            for e in detected_errors
        )

        print(f"\n    Unique Error Patterns Found ({len(pattern_counts)}):")
        for (provider, eid, title), count in pattern_counts.most_common(20):
            is_known = any(
                e['known'] for e in detected_errors
                if e['provider_name'] == provider and e['event_id'] == eid
            )
            marker = "\u2714 DETECTED" if is_known else "? UNKNOWN"
            level = next(
                (e['level_name'] for e in detected_errors
                 if e['provider_name'] == provider and e['event_id'] == eid),
                'N/A'
            )
            print(f"      [{marker:10s}] [{level:8s}] {title:40s} x{count}")

        # Show diagnosed issues with root cause
        diagnosed = [e for e in detected_errors if e.get('known')]
        if diagnosed:
            seen = set()
            print(f"\n    Root Cause Analysis:")
            for err in diagnosed:
                key = (err['provider_name'], err['event_id'])
                if key in seen:
                    continue
                seen.add(key)
                count = pattern_counts.get(
                    (err['provider_name'], err['event_id'], err.get('title', '')), 0
                )
                print(f"\n      [{err['level_name']}] {err['title']} (occurred {count}x)")
                print(f"      Diagnosis: {err['diagnosis']}")
                if err.get('causes'):
                    for c in err['causes'][:3]:
                        print(f"        Cause: {c}")
                if err.get('solutions'):
                    for a in err['solutions'][:3]:
                        print(f"        Action: {a}")
    else:
        print("\n    \u2713 No errors or warnings found in collected events.")
        print("    Your system Event Log appears clean for the targeted channels.")

    if resource_alerts:
        print_section("RESOURCE ALERTS")
        for alert in resource_alerts:
            print(f"    [{alert['severity']}] {alert['message']}")

    # Verdict
    print_section("VERDICT")
    if detected_errors:
        known_count = sum(1 for e in detected_errors if e.get('known'))
        print(f"    \u2714 ERROR DETECTION IS WORKING: Found {len(detected_errors)} real issues")
        print(f"    \u2714 Pattern matching working: {known_count} matched known signatures")
        print(f"    \u2714 Fault classification working: {len(fault_counts)} fault types assigned")
        success = True
    else:
        print(f"    \u2713 No errors in system log (system is clean)")
        print(f"    \u26a0 Cannot verify error detection without errors to detect")
        print(f"    \u2192 Use --generate-error flag to create a test error")
        success = False

    return processed_events, success


# ============================================================================
# PHASE 2: Generate a deliberate error and detect it
# ============================================================================

def generate_and_detect_error(collect_seconds=15):
    """
    Generate a REAL Windows error by stopping and restarting a safe service,
    then collect and detect the resulting event.

    REQUIRES ADMINISTRATOR PRIVILEGES.
    """
    print_header("PHASE 2: GENERATING DELIBERATE ERROR FOR DETECTION TEST")

    if not is_admin():
        print("  \u2717 ADMINISTRATOR PRIVILEGES REQUIRED")
        print("  Please run this script in an elevated PowerShell:")
        print("    1. Open PowerShell as Administrator")
        print("    2. cd c:\\ProgramData\\LogCollector")
        print("    3. python test_live_errors.py --generate-error")
        return False

    print("  Running as Administrator: Yes")
    print(f"  Collection window: {collect_seconds} seconds")

    # Step 1: Record checkpoint BEFORE generating error
    print(f"\n  Step 1: Recording current event position...")
    pre_events = collect_events_from_channel("System", 0)
    if pre_events:
        max_record_id = max(e['metadata']['event_record_id'] for e in pre_events)
    else:
        max_record_id = 0
    print(f"    Current max EventRecordID: {max_record_id}")

    # Step 2: Generate a deliberate error
    # We'll use 'Print Spooler' service - safe to stop/restart
    test_service = "Spooler"
    print(f"\n  Step 2: Generating test error...")
    print(f"    Stopping service: {test_service} (Print Spooler)")
    print(f"    This is SAFE - it only affects printing temporarily.")

    try:
        # Stop the service
        result = subprocess.run(
            ["net", "stop", test_service],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print(f"    \u2714 Service stopped successfully")
        else:
            # Service might already be stopped
            print(f"    \u26a0 Stop result: {result.stderr.strip() or result.stdout.strip()}")

        # Wait a moment for the event to be logged
        time.sleep(2)

        # Restart the service
        result = subprocess.run(
            ["net", "start", test_service],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print(f"    \u2714 Service restarted successfully")
        else:
            print(f"    \u26a0 Start result: {result.stderr.strip() or result.stdout.strip()}")

    except subprocess.TimeoutExpired:
        print(f"    \u26a0 Service command timed out")
    except Exception as e:
        print(f"    \u2717 Error manipulating service: {e}")
        return False

    # Step 3: Wait for events to propagate
    print(f"\n  Step 3: Waiting {collect_seconds}s for events to propagate...")
    for i in range(collect_seconds, 0, -1):
        print(f"\r    Collecting in {i:2d}s...", end='', flush=True)
        time.sleep(1)
    print(f"\r    Collection window complete.      ")

    # Step 4: Collect NEW events (only those after our checkpoint)
    print(f"\n  Step 4: Collecting new events since RecordID {max_record_id}...")
    new_raw = collect_events_from_channel("System", max_record_id)
    print(f"    New events found: {len(new_raw)}")

    if not new_raw:
        print("    \u26a0 No new events detected.")
        print("    This could mean:")
        print("      - The service stop/start didn't generate a System log event")
        print("      - Events are queued and not yet available")
        print("    Try increasing --collect-seconds")
        return False

    # Step 5: Process and detect errors
    system_id = get_system_id()
    new_events = []
    for event in new_raw:
        meta = event['metadata']
        resources = get_resource_snapshot()
        fault_info = classify_event(
            meta['provider_name'], meta['event_id'], meta['level']
        )
        new_events.append({
            'log_channel': event['log_channel'],
            'event_record_id': meta['event_record_id'],
            'provider_name': meta['provider_name'],
            'event_id': meta['event_id'],
            'level': meta['level'],
            'event_time': meta['event_time'],
            'cpu_usage_percent': resources['cpu_usage_percent'],
            'memory_usage_percent': resources['memory_usage_percent'],
            'disk_free_percent': resources['disk_free_percent'],
            'fault_type': fault_info['fault_type'],
            'fault_description': fault_info['fault_description'],
            'severity': fault_info['severity'],
        })

    detected = detect_errors(new_events)

    print_section("NEW EVENTS CAPTURED")
    for ev in new_events:
        level_name = LEVEL_NAMES.get(ev['level'], f"Lv{ev['level']}")
        print(f"    [{level_name:8s}] {ev['provider_name']:45s} "
              f"EventID={ev['event_id']:5d}  Fault={ev['fault_type']}")

    print_section("ERROR DETECTION ON NEW EVENTS")
    if detected:
        print(f"    \u2714 ERRORS DETECTED: {len(detected)}")
        for err in detected:
            marker = "\u2714 KNOWN" if err.get('known') else "? UNKNOWN"
            print(f"      [{marker}] [{err['level_name']}] {err['title']}")
            if err.get('diagnosis'):
                print(f"        Diagnosis: {err['diagnosis']}")
    else:
        print(f"    No errors in new events (the service events may be level=4 INFO)")
        print(f"    The {len(new_events)} new events were all informational")

    # Final verdict
    print_section("LIVE TEST VERDICT")
    service_events = [e for e in new_events if 'Service Control Manager' in e.get('provider_name', '')]
    if service_events:
        print(f"    \u2714 SERVICE EVENT CAPTURED: Found {len(service_events)} Service Control Manager events")
        print(f"    \u2714 LIVE COLLECTION WORKING: Captured events generated during test")

    if detected:
        print(f"    \u2714 ERROR DETECTION WORKING: Detected {len(detected)} errors from live events")
        return True
    else:
        print(f"    \u2713 All {len(new_events)} new events were informational (no errors to detect)")
        print(f"    \u2714 COLLECTION VERIFIED: Events were captured successfully")
        print(f"    Note: Service stop/start events are often logged as INFO, not ERROR")
        return True


# ============================================================================
# PHASE 3: Save live test report
# ============================================================================

def save_live_report(events, detected_errors, output_file="live_test_report.txt"):
    """Save the live test results to a file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("SENTINELCORE LIVE ERROR DETECTION TEST REPORT\n")
        f.write(f"{'=' * 80}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Admin: {is_admin()}\n\n")

        f.write(f"Total Events Collected: {len(events)}\n")
        f.write(f"Errors Detected: {len(detected_errors)}\n\n")

        if detected_errors:
            f.write("DETECTED ERRORS:\n")
            f.write(f"{'-' * 80}\n")
            for err in detected_errors:
                f.write(f"[{err['level_name']}] {err['title']}\n")
                f.write(f"  Provider: {err['provider_name']}\n")
                f.write(f"  EventID: {err['event_id']}\n")
                f.write(f"  Time: {err['event_time']}\n")
                if err.get('diagnosis'):
                    f.write(f"  Diagnosis: {err['diagnosis']}\n")
                if err.get('causes'):
                    f.write(f"  Causes:\n")
                    for c in err['causes']:
                        f.write(f"    - {c}\n")
                if err.get('solutions'):
                    f.write(f"  Actions:\n")
                    for a in err['solutions']:
                        f.write(f"    -> {a}\n")
                f.write("\n")

    print(f"\n  Report saved to: {output_file}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print(DIVIDER)
    print("  SENTINELCORE - LIVE ERROR DETECTION TEST")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Admin: {is_admin()}")
    print(DIVIDER)

    generate_error = "--generate-error" in sys.argv
    collect_seconds = 15

    # Parse --collect-seconds
    for i, arg in enumerate(sys.argv):
        if arg == "--collect-seconds" and i + 1 < len(sys.argv):
            try:
                collect_seconds = int(sys.argv[i + 1])
            except ValueError:
                pass

    # Phase 1: Test with existing real errors
    events, found_errors = test_real_error_detection()

    # Phase 2: Generate deliberate error (if requested)
    if generate_error:
        generate_and_detect_error(collect_seconds)
    elif not found_errors:
        print(f"\n  {'=' * 78}")
        print(f"  TIP: To generate a real error for testing, run:")
        print(f"    python test_live_errors.py --generate-error")
        print(f"  (Requires Administrator privileges)")
        print(f"  {'=' * 78}")

    # Save report
    if events:
        detected = detect_errors(events)
        save_live_report(events, detected)

    print(f"\n{DIVIDER}")
    print(f"  TEST COMPLETE")
    print(DIVIDER)


if __name__ == "__main__":
    main()
