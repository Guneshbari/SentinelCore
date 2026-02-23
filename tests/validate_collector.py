"""
SentinelCore Validation Script
Validates dependencies, event parsing, and system functions
"""

import sys
import re

def test_imports():
    """Test that all required modules can be imported"""
    print("\n=== Testing Imports ===")
    results = []
    
    try:
        import win32evtlog
        print("✓ win32evtlog imported successfully")
        results.append(True)
    except ImportError as e:
        print(f"✗ win32evtlog import failed: {e}")
        results.append(False)
    
    try:
        import pywintypes
        print("✓ pywintypes imported successfully")
        results.append(True)
    except ImportError as e:
        print(f"✗ pywintypes import failed: {e}")
        results.append(False)
    
    try:
        import psutil
        print("✓ psutil imported successfully")
        results.append(True)
    except ImportError as e:
        print(f"✗ psutil import failed: {e}")
        results.append(False)
    
    try:
        import requests
        print("✓ requests imported successfully")
        results.append(True)
    except ImportError as e:
        print(f"✗ requests import failed: {e}")
        results.append(False)
    
    return all(results)


def test_xml_parsing():
    """Test XML metadata extraction with sample event"""
    print("\n=== Testing XML Parsing ===")
    
    sample_xml = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'>
        <System>
            <Provider Name='Microsoft-Windows-Kernel-Power' Guid='{331C3B3A-2005-44C2-AC5E-77220C37D6B4}'/>
            <EventID>41</EventID>
            <Level>1</Level>
            <Task>63</Task>
            <Opcode>0</Opcode>
            <Keywords>0x8000400000000002</Keywords>
            <TimeCreated SystemTime='2026-02-16T17:59:58.000000Z'/>
            <EventRecordID>12345</EventRecordID>
            <Execution ProcessID='4' ThreadID='8'/>
        </System>
    </Event>"""
    
    try:
        # Test EventRecordID extraction
        match = re.search(r'EventRecordID["\']?>(\d+)<', sample_xml)
        event_record_id = int(match.group(1)) if match else None
        assert event_record_id == 12345, f"Expected 12345, got {event_record_id}"
        print(f"✓ EventRecordID extracted: {event_record_id}")
        
        # Test Provider Name extraction
        match = re.search(r'Provider.*?Name=["\']([^"\']+)["\']', sample_xml)
        provider_name = match.group(1) if match else None
        assert provider_name == "Microsoft-Windows-Kernel-Power", f"Expected Kernel-Power, got {provider_name}"
        print(f"✓ Provider Name extracted: {provider_name}")
        
        # Test Event ID extraction
        match = re.search(r'EventID["\']?>(\d+)<', sample_xml)
        event_id = int(match.group(1)) if match else None
        assert event_id == 41, f"Expected 41, got {event_id}"
        print(f"✓ Event ID extracted: {event_id}")
        
        # Test Level extraction
        match = re.search(r'Level["\']?>(\d+)<', sample_xml)
        level = int(match.group(1)) if match else None
        assert level == 1, f"Expected 1, got {level}"
        print(f"✓ Level extracted: {level}")
        
        # Test Process ID extraction
        match = re.search(r'ProcessID["\']?>(\d+)<', sample_xml)
        process_id = int(match.group(1)) if match else None
        assert process_id == 4, f"Expected 4, got {process_id}"
        print(f"✓ Process ID extracted: {process_id}")
        
        return True
    except AssertionError as e:
        print(f"✗ XML parsing test failed: {e}")
        return False
    except Exception as e:
        print(f"✗ XML parsing test error: {e}")
        return False


def test_sha256_hashing():
    """Test SHA256 event hash generation"""
    print("\n=== Testing SHA256 Hashing ===")
    
    try:
        import hashlib
        
        raw_xml = "<Event>Sample XML</Event>"
        system_id = "TEST-SYSTEM-ID"
        event_record_id = 12345
        
        content = f"{raw_xml}{system_id}{event_record_id}"
        event_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # Verify hash is 64 characters (SHA256 hex)
        assert len(event_hash) == 64, f"Expected 64 characters, got {len(event_hash)}"
        assert all(c in '0123456789abcdef' for c in event_hash), "Hash contains invalid characters"
        
        print(f"✓ SHA256 hash generated: {event_hash[:16]}...")
        print(f"✓ Hash length correct: {len(event_hash)} characters")
        
        return True
    except Exception as e:
        print(f"✗ SHA256 hashing test failed: {e}")
        return False


def test_provider_filtering():
    """Test provider name filtering logic"""
    print("\n=== Testing Provider Filtering ===")
    
    exclude_keywords = [
        "tcpip", "dns", "dhcp", "wlan", "smb", "network",
        "firewall", "winhttp", "wininet"
    ]
    
    def should_exclude(provider_name):
        provider_lower = provider_name.lower()
        for keyword in exclude_keywords:
            if keyword in provider_lower:
                return True
        return False
    
    test_cases = [
        ("Microsoft-Windows-Kernel-Power", False),
        ("Microsoft-Windows-TCPIP", True),
        ("Microsoft-Windows-DNS-Client", True),
        ("Microsoft-Windows-Firewall", True),
        ("Microsoft-Windows-DriverFrameworks", False),
        ("System", False),
        ("Microsoft-Windows-SMBServer", True),
    ]
    
    all_passed = True
    for provider, expected_exclude in test_cases:
        result = should_exclude(provider)
        if result == expected_exclude:
            action = "excluded" if result else "included"
            print(f"✓ {provider}: {action}")
        else:
            action = "excluded" if result else "included"
            expected_action = "excluded" if expected_exclude else "included"
            print(f"✗ {provider}: {action} (expected {expected_action})")
            all_passed = False
    
    return all_passed


def test_resource_monitoring():
    """Test system resource monitoring functions"""
    print("\n=== Testing Resource Monitoring ===")
    
    try:
        import psutil
        
        # Test CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        assert 0 <= cpu_percent <= 100, f"Invalid CPU percentage: {cpu_percent}"
        print(f"✓ CPU usage: {cpu_percent}%")
        
        # Test memory usage
        memory = psutil.virtual_memory()
        assert 0 <= memory.percent <= 100, f"Invalid memory percentage: {memory.percent}"
        print(f"✓ Memory usage: {memory.percent}%")
        
        # Test disk usage
        disk = psutil.disk_usage('/')
        disk_free_percent = 100.0 - disk.percent
        assert 0 <= disk_free_percent <= 100, f"Invalid disk free percentage: {disk_free_percent}"
        print(f"✓ Disk free: {disk_free_percent}%")
        
        # Test boot time
        boot_time = psutil.boot_time()
        assert boot_time > 0, f"Invalid boot time: {boot_time}"
        print(f"✓ Boot time: {boot_time}")
        
        return True
    except Exception as e:
        print(f"✗ Resource monitoring test failed: {e}")
        return False


def main():
    """Run all validation tests"""
    print("=" * 70)
    print("SentinelCore Validation Script v2.0.0")
    print("=" * 70)
    
    results = {
        "Imports": test_imports(),
        "XML Parsing": test_xml_parsing(),
        "SHA256 Hashing": test_sha256_hashing(),
        "Provider Filtering": test_provider_filtering(),
        "Resource Monitoring": test_resource_monitoring()
    }
    
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        symbol = "✓" if passed else "✗"
        print(f"{symbol} {test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("=" * 70)
    if all_passed:
        print("✓ All validation tests PASSED")
        print("\nCollector is ready to run. Start with:")
        print("  python src/collector.py")
        return 0
    else:
        print("✗ Some validation tests FAILED")
        print("\nPlease fix issues before running collector.")
        print("Install missing dependencies with:")
        print("  pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
