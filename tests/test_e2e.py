"""
SentinelCore E2E Test Suite
Tests the complete pipeline: collection -> classification -> analysis -> fault diagnosis
Validates admin privilege detection, error detection accuracy, and graceful degradation.

Usage:
    python -m pytest test_e2e.py -v --tb=short
    python test_e2e.py   # standalone execution
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
import hashlib
from datetime import datetime, timezone
from collections import Counter

# Add project directory to path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(PROJECT_DIR, '..', 'src'))
sys.path.insert(0, SRC_DIR)


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

SAMPLE_XML_CRITICAL = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>
    <System>
        <Provider Name='Microsoft-Windows-Kernel-Power' Guid='{331C3B3A-2005-44C2-AC5E-77220C37D6B4}'/>
        <EventID>41</EventID>
        <Level>1</Level>
        <Task>63</Task>
        <Opcode>0</Opcode>
        <Keywords>0x8000400000000002</Keywords>
        <TimeCreated SystemTime='2026-02-20T10:15:30.000000Z'/>
        <EventRecordID>99001</EventRecordID>
        <Execution ProcessID='4' ThreadID='8'/>
    </System>
</Event>"""

SAMPLE_XML_ERROR = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>
    <System>
        <Provider Name='Service Control Manager' Guid='{ABCD1234}'/>
        <EventID>7031</EventID>
        <Level>2</Level>
        <Task>0</Task>
        <Opcode>0</Opcode>
        <Keywords>0x8080000000000000</Keywords>
        <TimeCreated SystemTime='2026-02-20T10:16:00.000000Z'/>
        <EventRecordID>99002</EventRecordID>
        <Execution ProcessID='600' ThreadID='1200'/>
    </System>
</Event>"""

SAMPLE_XML_WARNING = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>
    <System>
        <Provider Name='Microsoft-Windows-Kernel-PnP' Guid='{DCBA4321}'/>
        <EventID>219</EventID>
        <Level>3</Level>
        <Task>0</Task>
        <Opcode>0</Opcode>
        <Keywords>0x8000000000000000</Keywords>
        <TimeCreated SystemTime='2026-02-20T10:17:00.000000Z'/>
        <EventRecordID>99003</EventRecordID>
        <Execution ProcessID='4' ThreadID='12'/>
    </System>
</Event>"""

SAMPLE_XML_NETWORK = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>
    <System>
        <Provider Name='Microsoft-Windows-TCPIP' Guid='{11111111}'/>
        <EventID>4226</EventID>
        <Level>3</Level>
        <Task>0</Task>
        <Opcode>0</Opcode>
        <Keywords>0x8000000000000000</Keywords>
        <TimeCreated SystemTime='2026-02-20T10:18:00.000000Z'/>
        <EventRecordID>99004</EventRecordID>
        <Execution ProcessID='4' ThreadID='16'/>
    </System>
</Event>"""


def build_test_event(provider, event_id, level, record_id, raw_xml="",
                     fault_type="UNKNOWN", cpu=25.0, mem=60.0, disk=50.0):
    """Helper to build a test event dict."""
    return {
        'log_channel': 'System',
        'event_record_id': record_id,
        'provider_name': provider,
        'event_id': event_id,
        'level': level,
        'task': 0,
        'opcode': 0,
        'keywords': '0x0',
        'process_id': 4,
        'thread_id': 8,
        'event_time': '2026-02-20T10:15:30.000000Z',
        'cpu_usage_percent': cpu,
        'memory_usage_percent': mem,
        'disk_free_percent': disk,
        'event_hash': hashlib.sha256(f"{raw_xml}test{record_id}".encode()).hexdigest(),
        'fault_type': fault_type,
        'fault_description': '',
        'severity': {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING'}.get(level, 'INFO'),
        'diagnostic_context': {'resource_state': {}, 'resource_alerts': []},
        'raw_xml': raw_xml or f"<Event><EventID>{event_id}</EventID></Event>"
    }


def build_test_data(events):
    """Wrap events in a full data structure."""
    return {
        'collector_info': {
            'version': '2.0.0',
            'mode': 'local_testing',
            'created': datetime.now(timezone.utc).isoformat()
        },
        'system_info': {
            'system_id': 'TEST-MACHINE-GUID',
            'hostname': 'TEST-HOST',
            'boot_session_id': 'test-boot-session-uuid',
            'os_version': 'Windows 11 (Build 22631)',
            'uptime_seconds': 3600
        },
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'events': events
    }


# ============================================================================
# TEST CLASSES
# ============================================================================

class TestAdminDetection(unittest.TestCase):
    """Test 1: Administrator privilege detection"""

    def test_admin_detection_returns_bool(self):
        """is_admin() should return a boolean value."""
        from collector import is_admin
        result = is_admin()
        self.assertIsInstance(result, bool)
        print(f"  Admin status detected: {result}")

    def test_check_admin_privileges_structure(self):
        """check_admin_privileges() should return (bool, list) tuple."""
        from collector import check_admin_privileges
        admin, warnings = check_admin_privileges()
        self.assertIsInstance(admin, bool)
        self.assertIsInstance(warnings, list)
        if not admin:
            self.assertTrue(len(warnings) > 0,
                            "Non-admin mode should produce warnings")
            print(f"  Non-admin warnings: {len(warnings)}")
        else:
            print("  Running as Administrator - no warnings expected")


class TestSystemMetadata(unittest.TestCase):
    """Test 2: System metadata collection"""

    def test_system_id_not_empty(self):
        """System ID should be a non-empty string."""
        from collector import get_system_id
        sid = get_system_id()
        self.assertIsInstance(sid, str)
        self.assertTrue(len(sid) > 0, "System ID is empty")
        self.assertNotEqual(sid, "UNKNOWN", "System ID should not be UNKNOWN")
        print(f"  System ID: {sid}")

    def test_hostname_not_empty(self):
        """Hostname should be a non-empty string."""
        from collector import get_hostname
        hostname = get_hostname()
        self.assertIsInstance(hostname, str)
        self.assertTrue(len(hostname) > 0)
        print(f"  Hostname: {hostname}")

    def test_os_version_populated(self):
        """OS version should contain version info."""
        from collector import get_os_version
        version = get_os_version()
        self.assertIsInstance(version, str)
        self.assertIn("Windows", version)
        print(f"  OS Version: {version}")

    def test_boot_session_is_uuid(self):
        """Boot session should be a valid UUID string."""
        from collector import get_boot_session_id
        import uuid
        session = get_boot_session_id()
        # Should be parseable as UUID
        parsed = uuid.UUID(session)
        self.assertIsNotNone(parsed)
        print(f"  Boot Session: {session}")

    def test_uptime_positive(self):
        """Uptime should be a positive integer."""
        from collector import get_uptime_seconds
        uptime = get_uptime_seconds()
        self.assertIsInstance(uptime, int)
        self.assertGreater(uptime, 0)
        print(f"  Uptime: {uptime}s")

    def test_resource_snapshot(self):
        """Resource snapshot should have valid percentages."""
        from collector import get_resource_snapshot
        snap = get_resource_snapshot()
        self.assertIn('cpu_usage_percent', snap)
        self.assertIn('memory_usage_percent', snap)
        self.assertIn('disk_free_percent', snap)
        self.assertTrue(0 <= snap['cpu_usage_percent'] <= 100)
        self.assertTrue(0 <= snap['memory_usage_percent'] <= 100)
        self.assertTrue(0 <= snap['disk_free_percent'] <= 100)
        print(f"  CPU={snap['cpu_usage_percent']}% MEM={snap['memory_usage_percent']}% DISK={snap['disk_free_percent']}%")


class TestEventCollectionE2E(unittest.TestCase):
    """Test 3: End-to-end event collection from real Windows logs"""

    def test_collect_system_events(self):
        """Should collect events from System channel with valid structure."""
        from collector import collect_events_from_channel
        # Collect from System log (record_id=0 to get recent events)
        events = collect_events_from_channel("System", 0)
        # It's okay if no events match our filter, but the function shouldn't crash
        self.assertIsInstance(events, list)
        print(f"  Events collected from System: {len(events)}")
        if events:
            event = events[0]
            self.assertIn('metadata', event)
            self.assertIn('raw_xml', event)
            self.assertIn('log_channel', event)
            self.assertEqual(event['log_channel'], 'System')
            # Validate metadata structure
            meta = event['metadata']
            self.assertIn('event_record_id', meta)
            self.assertIn('provider_name', meta)
            self.assertIn('event_id', meta)
            self.assertIn('level', meta)
            self.assertIsInstance(meta['event_record_id'], int)
            print(f"  First event: RecordID={meta['event_record_id']} "
                  f"Provider={meta['provider_name']} Level={meta['level']}")

    def test_collect_from_nonexistent_channel(self):
        """Should gracefully handle non-existent channel without crashing."""
        from collector import collect_events_from_channel
        events = collect_events_from_channel("NonExistentChannel-Test-12345", 0)
        self.assertIsInstance(events, list)
        self.assertEqual(len(events), 0)
        print("  Gracefully returned empty list for non-existent channel")


class TestErrorDetection(unittest.TestCase):
    """Test 4: Error detection from event data"""

    def test_detect_critical_errors(self):
        """Should detect critical power events (Kernel-Power 41)."""
        from analyzer import detect_errors
        events = [
            build_test_event('Microsoft-Windows-Kernel-Power', 41, 1, 1001,
                           SAMPLE_XML_CRITICAL, 'SYSTEM_FAULT'),
        ]
        errors = detect_errors(events)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['level'], 1)
        self.assertEqual(errors[0]['level_name'], 'CRITICAL')
        self.assertTrue(errors[0]['known'])
        self.assertIn('Unexpected Shutdown', errors[0]['title'])
        self.assertTrue(len(errors[0]['causes']) > 0)
        self.assertTrue(len(errors[0]['solutions']) > 0)
        print(f"  Detected: {errors[0]['title']}")

    def test_detect_service_crash(self):
        """Should detect service crash events (SCM 7031)."""
        from analyzer import detect_errors
        events = [
            build_test_event('Service Control Manager', 7031, 2, 1002,
                           SAMPLE_XML_ERROR, 'SERVICE_ERROR'),
        ]
        errors = detect_errors(events)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['level_name'], 'ERROR')
        self.assertTrue(errors[0]['known'])
        self.assertIn('Crash', errors[0]['title'])
        print(f"  Detected: {errors[0]['title']}")

    def test_detect_driver_issue(self):
        """Should detect driver timeout (Kernel-PnP 219)."""
        from analyzer import detect_errors
        events = [
            build_test_event('Microsoft-Windows-Kernel-PnP', 219, 3, 1003,
                           SAMPLE_XML_WARNING, 'DRIVER_ISSUE'),
        ]
        errors = detect_errors(events)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0]['known'])
        self.assertIn('Driver', errors[0]['title'])
        print(f"  Detected: {errors[0]['title']}")

    def test_ignore_info_events(self):
        """Should NOT flag level=4 (Information) events as errors."""
        from analyzer import detect_errors
        events = [
            build_test_event('SomeProvider', 100, 4, 1004),
        ]
        errors = detect_errors(events)
        self.assertEqual(len(errors), 0)
        print("  Correctly ignored Information-level event")

    def test_unknown_pattern_still_detected(self):
        """Unknown provider/event should still be flagged if level is error/warning."""
        from analyzer import detect_errors
        events = [
            build_test_event('UnknownProvider-XYZ', 9999, 2, 1005),
        ]
        errors = detect_errors(events)
        self.assertEqual(len(errors), 1)
        self.assertFalse(errors[0]['known'])
        self.assertIn('UnknownProvider-XYZ', errors[0]['title'])
        print(f"  Detected unknown: {errors[0]['title']}")


class TestCheckpointLifecycle(unittest.TestCase):
    """Test 5: Checkpoint create/save/load/resume cycle"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='sentinel_test_')
        self.ckpt_file = os.path.join(self.test_dir, 'test_checkpoint.json')

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_fresh_checkpoint(self):
        """New checkpoint should start with empty state."""
        from collector import CheckpointManager
        mgr = CheckpointManager(self.ckpt_file)
        self.assertEqual(mgr.get('System'), 0)
        print("  Fresh checkpoint: record_id=0 for new channel")

    def test_save_and_load_checkpoint(self):
        """Saved checkpoint should be recoverable on reload."""
        from collector import CheckpointManager
        mgr = CheckpointManager(self.ckpt_file)
        mgr.update('System', 12345)
        mgr.update('Kernel-Power', 67890)
        mgr.save()

        # Reload
        mgr2 = CheckpointManager(self.ckpt_file)
        self.assertEqual(mgr2.get('System'), 12345)
        self.assertEqual(mgr2.get('Kernel-Power'), 67890)
        print("  Checkpoint save/load verified: System=12345, Kernel-Power=67890")

    def test_checkpoint_file_is_valid_json(self):
        """Checkpoint file should contain valid JSON."""
        from collector import CheckpointManager
        mgr = CheckpointManager(self.ckpt_file)
        mgr.update('Test', 100)
        mgr.save()

        with open(self.ckpt_file, 'r') as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)
        self.assertEqual(data['Test'], 100)
        print("  Checkpoint file is valid JSON")

    def test_checkpoint_atomic_write(self):
        """Checkpoint save should not leave .tmp files behind."""
        from collector import CheckpointManager
        mgr = CheckpointManager(self.ckpt_file)
        mgr.update('System', 999)
        mgr.save()

        tmp_file = self.ckpt_file + '.tmp'
        self.assertFalse(os.path.exists(tmp_file),
                         "Temporary file should be cleaned up after save")
        print("  Atomic write verified: no .tmp file remaining")


class TestErrorClassification(unittest.TestCase):
    """Test 6: ErrorClassifier accuracy"""

    def test_classify_kernel_power_41(self):
        """Kernel-Power 41 should be classified as SYSTEM_FAULT."""
        from collector import classify_event
        result = classify_event('Microsoft-Windows-Kernel-Power', 41, 1)
        self.assertEqual(result['fault_type'], 'SYSTEM_FAULT')
        self.assertEqual(result['severity'], 'CRITICAL')
        print(f"  Kernel-Power 41 -> {result['fault_type']} ({result['severity']})")

    def test_classify_scm_7031(self):
        """Service Control Manager 7031 should be SERVICE_ERROR."""
        from collector import classify_event
        result = classify_event('Service Control Manager', 7031, 2)
        self.assertEqual(result['fault_type'], 'SERVICE_ERROR')
        self.assertEqual(result['severity'], 'ERROR')
        print(f"  SCM 7031 -> {result['fault_type']} ({result['severity']})")

    def test_classify_driver_pnp(self):
        """Kernel-PnP 219 should be DRIVER_ISSUE."""
        from collector import classify_event
        result = classify_event('Microsoft-Windows-Kernel-PnP', 219, 3)
        self.assertEqual(result['fault_type'], 'DRIVER_ISSUE')
        print(f"  Kernel-PnP 219 -> {result['fault_type']}")

    def test_classify_dcom_security(self):
        """DistributedCOM 10016 should be SECURITY_EVENT."""
        from collector import classify_event
        result = classify_event('Microsoft-Windows-DistributedCOM', 10016, 3)
        self.assertEqual(result['fault_type'], 'SECURITY_EVENT')
        print(f"  DCOM 10016 -> {result['fault_type']}")

    def test_classify_update_error(self):
        """WindowsUpdateClient should be UPDATE_ERROR."""
        from collector import classify_event
        result = classify_event('Microsoft-Windows-WindowsUpdateClient', 20, 2)
        self.assertEqual(result['fault_type'], 'UPDATE_ERROR')
        print(f"  WUC 20 -> {result['fault_type']}")

    def test_classify_storage_error(self):
        """Volsnap should be STORAGE_ERROR."""
        from collector import classify_event
        result = classify_event('Volsnap', 25, 2)
        self.assertEqual(result['fault_type'], 'STORAGE_ERROR')
        print(f"  Volsnap 25 -> {result['fault_type']}")

    def test_classify_unknown_by_level(self):
        """Unknown provider at level 1 should still get SYSTEM_FAULT."""
        from collector import classify_event
        result = classify_event('TotallyUnknownProvider', 9999, 1)
        self.assertEqual(result['fault_type'], 'SYSTEM_FAULT')
        self.assertEqual(result['severity'], 'CRITICAL')
        print(f"  Unknown lv1 -> {result['fault_type']} (level-based fallback)")

    def test_diagnostic_context_alerts(self):
        """Diagnostic context should flag high resource usage."""
        from collector import build_diagnostic_context
        resources = {
            'cpu_usage_percent': 95.0,
            'memory_usage_percent': 92.0,
            'disk_free_percent': 5.0
        }
        ctx = build_diagnostic_context(resources)
        alerts = ctx['resource_alerts']
        self.assertTrue(any('HIGH CPU' in a for a in alerts))
        self.assertTrue(any('HIGH MEMORY' in a for a in alerts))
        self.assertTrue(any('LOW DISK' in a for a in alerts))
        print(f"  Resource alerts: {alerts}")


class TestLocalFileOutput(unittest.TestCase):
    """Test 7: Local file manager write and read"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='sentinel_test_')
        self.output_file = os.path.join(self.test_dir, 'test_events.json')

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_and_save(self):
        """Should create file and save events successfully."""
        from collector import LocalFileManager
        mgr = LocalFileManager(self.output_file)
        payload = {
            'system_id': 'test',
            'hostname': 'test-host',
            'boot_session_id': 'test-uuid',
            'os_version': 'Windows Test',
            'uptime_seconds': 100,
            'collector_version': '2.0.0',
            'timestamp_collected': datetime.now(timezone.utc).isoformat(),
            'events': [
                build_test_event('TestProvider', 100, 3, 1),
                build_test_event('TestProvider', 101, 2, 2),
            ]
        }
        result = mgr.save_batch(payload)
        self.assertTrue(result)

        # Verify file is readable JSON
        with open(self.output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(len(data['events']), 2)
        print(f"  Saved 2 events to temp file, verified JSON structure")


class TestAnalyzeCollectedData(unittest.TestCase):
    """Test 8: Analyzer processes collected data correctly"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='sentinel_test_')
        self.test_file = os.path.join(self.test_dir, 'test_events.json')

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_analyze_with_mixed_events(self):
        """Analyzer should handle mix of critical/error/warning events."""
        events = [
            build_test_event('Microsoft-Windows-Kernel-Power', 41, 1, 1, SAMPLE_XML_CRITICAL, 'SYSTEM_FAULT'),
            build_test_event('Service Control Manager', 7031, 2, 2, SAMPLE_XML_ERROR, 'SERVICE_ERROR'),
            build_test_event('Microsoft-Windows-Kernel-PnP', 219, 3, 3, SAMPLE_XML_WARNING, 'DRIVER_ISSUE'),
        ]
        data = build_test_data(events)
        with open(self.test_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        from analyzer import load_events, detect_errors
        loaded = load_events(self.test_file)
        self.assertEqual(len(loaded['events']), 3)

        errors = detect_errors(loaded['events'])
        self.assertEqual(len(errors), 3)

        levels = Counter(e['level'] for e in errors)
        self.assertEqual(levels[1], 1)  # 1 critical
        self.assertEqual(levels[2], 1)  # 1 error
        self.assertEqual(levels[3], 1)  # 1 warning
        print(f"  Analyzed 3 mixed events: {dict(levels)}")


class TestFaultDiagnosisOutput(unittest.TestCase):
    """Test 9: Fault diagnosis report generation"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='sentinel_test_')
        self.output_file = os.path.join(self.test_dir, 'test_summary.txt')

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_includes_diagnosis(self):
        """Exported summary should include fault diagnosis section."""
        events = [
            build_test_event('Microsoft-Windows-Kernel-Power', 41, 1, 1, SAMPLE_XML_CRITICAL, 'SYSTEM_FAULT'),
            build_test_event('Service Control Manager', 7031, 2, 2, SAMPLE_XML_ERROR, 'SERVICE_ERROR'),
        ]
        data = build_test_data(events)

        from analyzer import export_detailed_report
        export_detailed_report(data, self.output_file)

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('FAULT SUMMARY', content)
        self.assertIn('CRITICAL', content)
        self.assertIn('Unexpected Shutdown', content)
        self.assertIn('Crash', content)
        self.assertIn('Solutions', content)
        print("  Fault diagnosis report contains expected sections")

    def test_export_healthy_system(self):
        """Summary with no errors should report healthy system."""
        # All info-level events (level=4) — no errors
        events = [
            build_test_event('SomeProvider', 100, 4, 1),
        ]
        data = build_test_data(events)

        from analyzer import export_detailed_report
        export_detailed_report(data, self.output_file)

        with open(self.output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('No faults detected', content)
        print("  Healthy system message confirmed")


class TestMalformedDataHandling(unittest.TestCase):
    """Test 10: Resilience to malformed/corrupt data"""

    def test_handle_empty_events(self):
        """Should handle empty events list without crashing."""
        from analyzer import detect_errors, generate_resource_alerts
        errors = detect_errors([])
        alerts = generate_resource_alerts([])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alerts), 0)
        print("  Empty events handled gracefully")

    def test_handle_missing_fields(self):
        """Should handle events with missing fields."""
        from analyzer import detect_errors
        events = [
            {'level': 2},  # Minimal event
            {},  # Completely empty event
            {'provider_name': 'Test', 'event_id': 1},  # No level (defaults to 4)
        ]
        # Should not crash
        errors = detect_errors(events)
        # Only the first one has level=2, so it should be detected
        self.assertEqual(len(errors), 1)
        print(f"  Handled {len(events)} malformed events, detected {len(errors)} errors")

    def test_handle_none_values(self):
        """Should handle None values in event fields."""
        from analyzer import detect_errors
        events = [
            {
                'provider_name': None,
                'event_id': None,
                'level': 2,
                'event_record_id': None,
                'event_time': None,
            },
        ]
        errors = detect_errors(events)
        self.assertEqual(len(errors), 1)
        print("  None values handled gracefully")

    def test_xml_parsing_with_garbage(self):
        """XML parser should handle garbage input without crashing."""
        from collector import extract_event_metadata
        result = extract_event_metadata("not valid xml at all <><>")
        # The refactored parser returns None when no EventRecordID is found
        self.assertIsNone(result)
        print("  Garbage XML handled without crash")

    def test_xml_parsing_with_empty_string(self):
        """XML parser should handle empty string."""
        from collector import extract_event_metadata
        result = extract_event_metadata("")
        self.assertIsNone(result)
        print("  Empty XML handled without crash")


class TestGracefulDegradation(unittest.TestCase):
    """Test 11: Non-admin mode should work without crashing"""

    def test_collect_accessible_channels(self):
        """Should collect from channels that don't require admin."""
        from collector import collect_events_from_channel
        # System channel is typically accessible without admin
        events = collect_events_from_channel("System", 0)
        self.assertIsInstance(events, list)
        print(f"  System channel: {len(events)} events (non-admin)")

    def test_skip_inaccessible_channels(self):
        """Should return empty list for inaccessible channels."""
        from collector import collect_events_from_channel
        # Security log requires admin
        events = collect_events_from_channel("Security", 0)
        self.assertIsInstance(events, list)
        # Should not crash regardless of access
        print(f"  Security channel: {len(events)} events (graceful)")

    def test_provider_filtering(self):
        """Network providers should be filtered out."""
        from collector import should_exclude_provider
        # Should exclude
        self.assertTrue(should_exclude_provider("Microsoft-Windows-TCPIP"))
        self.assertTrue(should_exclude_provider("Microsoft-Windows-DNS-Client"))
        self.assertTrue(should_exclude_provider("Microsoft-Windows-Firewall"))
        # Should include
        self.assertFalse(should_exclude_provider("Microsoft-Windows-Kernel-Power"))
        self.assertFalse(should_exclude_provider("Service Control Manager"))
        print("  Provider filtering working correctly")


class TestDuplicateDetection(unittest.TestCase):
    """Test 12: SHA256 deduplication"""

    def test_same_event_same_hash(self):
        """Same event should produce same hash."""
        from collector import generate_event_hash
        xml = "<Event>Test</Event>"
        h1 = generate_event_hash(xml, "sys1", 100)
        h2 = generate_event_hash(xml, "sys1", 100)
        self.assertEqual(h1, h2)
        print(f"  Same inputs -> same hash: {h1[:16]}...")

    def test_different_events_different_hashes(self):
        """Different events should produce different hashes."""
        from collector import generate_event_hash
        h1 = generate_event_hash("<Event>A</Event>", "sys1", 100)
        h2 = generate_event_hash("<Event>B</Event>", "sys1", 100)
        h3 = generate_event_hash("<Event>A</Event>", "sys1", 101)
        self.assertNotEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        print("  Different inputs -> different hashes")

    def test_hash_is_valid_sha256(self):
        """Hash should be 64-char hex string."""
        from collector import generate_event_hash
        h = generate_event_hash("<Event/>", "sys", 1)
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in h))
        print(f"  Valid SHA256: {h}")


class TestResourceAlerts(unittest.TestCase):
    """Test 13: Resource alert detection"""

    def test_high_cpu_alert(self):
        """Should detect high CPU usage."""
        from analyzer import generate_resource_alerts
        events = [build_test_event('P', 1, 3, 1, cpu=95.0)]
        alerts = generate_resource_alerts(events)
        self.assertTrue(any(a['type'] == 'HIGH_CPU' for a in alerts))
        print("  HIGH_CPU alert detected")

    def test_high_memory_alert(self):
        """Should detect high memory usage."""
        from analyzer import generate_resource_alerts
        events = [build_test_event('P', 1, 3, 1, mem=95.0)]
        alerts = generate_resource_alerts(events)
        self.assertTrue(any(a['type'] == 'HIGH_MEMORY' for a in alerts))
        print("  HIGH_MEMORY alert detected")

    def test_low_disk_alert(self):
        """Should detect low disk space."""
        from analyzer import generate_resource_alerts
        events = [build_test_event('P', 1, 3, 1, disk=5.0)]
        alerts = generate_resource_alerts(events)
        self.assertTrue(any(a['type'] == 'LOW_DISK' for a in alerts))
        print("  LOW_DISK alert detected")

    def test_no_alerts_normal_resources(self):
        """Should not alert on normal resource usage."""
        from analyzer import generate_resource_alerts
        events = [build_test_event('P', 1, 3, 1, cpu=30.0, mem=50.0, disk=60.0)]
        alerts = generate_resource_alerts(events)
        self.assertEqual(len(alerts), 0)
        print("  No alerts for normal resources")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("SENTINELCORE E2E TEST SUITE")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Run tests with verbose output
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes in logical order
    test_classes = [
        TestAdminDetection,
        TestSystemMetadata,
        TestEventCollectionE2E,
        TestErrorDetection,
        TestCheckpointLifecycle,
        TestErrorClassification,
        TestLocalFileOutput,
        TestAnalyzeCollectedData,
        TestFaultDiagnosisOutput,
        TestMalformedDataHandling,
        TestGracefulDegradation,
        TestDuplicateDetection,
        TestResourceAlerts,
    ]

    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 80)
    print("E2E TEST SUMMARY")
    print("=" * 80)
    print(f"Tests Run:    {result.testsRun}")
    print(f"Passed:       {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures:     {len(result.failures)}")
    print(f"Errors:       {len(result.errors)}")
    print("=" * 80)

    sys.exit(0 if result.wasSuccessful() else 1)
