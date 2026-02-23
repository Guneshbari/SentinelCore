"""
Enhanced Log Analysis Tool for SentinelCore
Analyzes collected events with solutions and root cause analysis
"""

import json
import sys
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

# Known event patterns with solutions
EVENT_KNOWLEDGE_BASE = {
    # Kernel-PnP Event 219 - Driver issues
    ('Microsoft-Windows-Kernel-PnP', 219): {
        'title': 'Driver Start Timeout',
        'description': 'The driver failed to start within the allotted time.',
        'causes': [
            'Device driver is slow to initialize',
            'Hardware device not responding properly',
            'Driver compatibility issues with Windows version'
        ],
        'solutions': [
            'Update the device driver to the latest version',
            'Check Windows Update for driver updates',
            'Verify hardware is functioning correctly',
            'Consider disabling fast startup if issue persists'
        ]
    },
    
    # DistributedCOM warnings
    ('Microsoft-Windows-DistributedCOM', 10016): {
        'title': 'DCOM Permission Issues',
        'description': 'Application-specific permission settings do not grant Local Activation permission.',
        'causes': [
            'Default DCOM permissions prevent certain applications from starting COM servers',
            'Security hardening has removed necessary permissions',
            'Application attempting to use DCOM without proper configuration'
        ],
        'solutions': [
            'This is often a benign warning and can be safely ignored',
            'If problematic: Use Component Services (dcomcnfg) to adjust permissions',
            'Identify the CLSID/AppID in event details and grant appropriate permissions'
        ]
    },
    
    # Kernel-Processor-Power Event 37
    ('Microsoft-Windows-Kernel-Processor-Power', 37): {
        'title': 'Processor Power State Change',
        'description': 'The speed of processor has been limited by system firmware.',
        'causes': [
            'Thermal throttling due to high CPU temperature',
            'Power management settings limiting CPU performance',
            'BIOS/UEFI power limits being enforced',
            'Battery saving mode active on laptops'
        ],
        'solutions': [
            'Check CPU temperatures and improve cooling if needed',
            'Review power plan settings (High Performance vs Balanced)',
            'Update BIOS/UEFI to latest version',
            'Ensure adequate power supply for the system'
        ]
    },
    
    # Network driver (Netwtw14 - Intel WiFi)
    ('Netwtw14', 5002): {
        'title': 'Intel WiFi Driver Event',
        'description': 'Network adapter encountered an issue.',
        'causes': [
            'WiFi driver instability',
            'Network interference or weak signal',
            'Power management settings affecting WiFi adapter',
            'Driver compatibility issues'
        ],
        'solutions': [
            'Update Intel WiFi driver to latest version',
            'Disable WiFi adapter power management (Allow computer to turn off device)',
            'Check for Windows updates',
            'Consider using 5GHz band if on 2.4GHz'
        ]
    },
    
    # WindowsUpdateClient errors
    ('Microsoft-Windows-WindowsUpdateClient', 20): {
        'title': 'Windows Update Installation Failure',
        'description': 'Installation failure occurred during Windows Update.',
        'causes': [
            'Insufficient disk space for update',
            'Corrupted Windows Update components',
            'Third-party software interfering with updates',
            'System files corruption'
        ],
        'solutions': [
            'Run Windows Update Troubleshooter',
            'Execute: DISM /Online /Cleanup-Image /RestoreHealth',
            'Execute: sfc /scannow to repair system files',
            'Clear Windows Update cache (C:\\Windows\\SoftwareDistribution)',
            'Ensure sufficient free disk space (10GB+ recommended)'
        ]
    },
    
    # Volsnap errors
    ('Volsnap', 25): {
        'title': 'Volume Shadow Copy Service Error',
        'description': 'The shadow copies of volume were aborted due to insufficient resources.',
        'causes': [
            'Insufficient disk space for shadow storage',
            'VSS service configuration issues',
            'Corrupted shadow copy storage',
            'Disk I/O bottleneck during snapshot'
        ],
        'solutions': [
            'Free up disk space on the affected volume',
            'Resize shadow storage allocation: vssadmin resize shadowstorage',
            'Delete old shadow copies: vssadmin delete shadows',
            'Check disk health with chkdsk',
            'Restart Volume Shadow Copy service'
        ]
    },
    
    # Hyper-V Hypervisor
    ('Microsoft-Windows-Hyper-V-Hypervisor', 167): {
        'title': 'Hypervisor Launch Warning',
        'description': 'Hypervisor launch detected during boot.',
        'causes': [
            'Hyper-V or WSL2 enabled on the system',
            'Normal operation for virtualization-enabled systems',
            'Virtualization-based security features active'
        ],
        'solutions': [
            'This is informational - no action needed if virtualization is intentional',
            'If virtualization not needed: Disable Hyper-V via Windows Features',
            'For performance: Disable if not using VMs or WSL2'
        ]
    },
    
    # winsrvext Event 100
    ('winsrvext', 100): {
        'title': 'Windows Service Extension Event',
        'description': 'Service-related configuration or state change.',
        'causes': [
            'Service startup/shutdown events',
            'Service configuration changes',
            'Scheduled maintenance tasks'
        ],
        'solutions': [
            'Review event details for specific service information',
            'Generally informational - no action required unless recurring errors',
            'Check Services console (services.msc) for service status'
        ]
    },
    
    # Disk warnings
    ('disk', 153): {
        'title': 'Disk I/O Performance Warning',
        'description': 'The IO operation encountered a long delay.',
        'causes': [
            'Failing or degraded hard drive',
            'Insufficient disk performance (old HDD)',
            'Background processes causing disk contention',
            'Disk driver issues'
        ],
        'solutions': [
            'Run disk health check: chkdsk /f /r',
            'Check SMART status using CrystalDiskInfo or similar tool',
            'Consider upgrading to SSD if using HDD',
            'Update storage controller drivers',
            'Disable disk indexing on slow drives'
        ]
    }
}

def extract_event_description(raw_xml):
    """Extract event description from raw XML"""
    try:
        # Parse XML
        root = ET.fromstring(raw_xml)
        
        # Try to find description in various locations
        # Check for RenderingInfo/Message
        ns = {'evt': 'http://schemas.microsoft.com/win/2004/08/events/event'}
        message = root.find('.//evt:RenderingInfo/evt:Message', ns)
        if message is not None and message.text:
            return message.text.strip()
        
        # Check EventData for descriptive text
        event_data = root.find('.//EventData', ns) or root.find('.//EventData')
        if event_data is not None:
            data_parts = []
            for data in event_data.findall('.//Data'):
                if data.text:
                    data_parts.append(data.text.strip())
            if data_parts:
                return ' | '.join(data_parts[:3])  # First 3 data elements
        
        return None
    except:
        return None

def get_event_knowledge(provider, event_id):
    """Get knowledge base entry for event"""
    # Try exact match
    key = (provider, event_id)
    if key in EVENT_KNOWLEDGE_BASE:
        return EVENT_KNOWLEDGE_BASE[key]
    
    # Try generic provider match (event_id 0 often means multiple sub-events)
    if event_id == 0:
        for kb_key in EVENT_KNOWLEDGE_BASE:
            if kb_key[0] == provider:
                return EVENT_KNOWLEDGE_BASE[kb_key]
    
    return None

def analyze_event_patterns(events):
    """Analyze patterns in events to provide insights"""
    insights = []
    
    # Count events by provider
    by_provider = Counter(e.get('provider_name') for e in events)
    
    # Check for repetitive warnings
    warning_events = [e for e in events if e.get('level') == 3]
    if len(warning_events) > 100:
        insights.append(f"Found {len(warning_events)} warning events - review patterns for recurring issues")
    
    # Check for DCOM spam
    dcom_count = sum(1 for e in events if 'DistributedCOM' in e.get('provider_name', ''))
    if dcom_count > 50:
        insights.append(f"High DCOM event count ({dcom_count}) - typically benign but can be reduced via permissions")
    
    # Check for driver issues
    pnp_count = sum(1 for e in events if 'Kernel-PnP' in e.get('provider_name', ''))
    if pnp_count > 20:
        insights.append(f"Multiple Plug-and-Play events ({pnp_count}) - consider updating device drivers")
    
    # Check for thermal throttling
    throttle_count = sum(1 for e in events if 'Processor-Power' in e.get('provider_name', '') and e.get('event_id') == 37)
    if throttle_count > 10:
        insights.append(f"CPU throttling detected ({throttle_count} events) - check cooling and power settings")
    
    # Check for WiFi issues
    wifi_count = sum(1 for e in events if 'Netwtw' in e.get('provider_name', ''))
    if wifi_count > 15:
        insights.append(f"WiFi driver events detected ({wifi_count}) - update Intel WiFi drivers")
    
    return insights

def export_enhanced_summary(data, output_file="event_summary.txt"):
    """Export enhanced summary with solutions"""
    events = data.get('events', [])
    
    # Analyze patterns
    insights = analyze_event_patterns(events)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("SENTINELCORE EVENT SUMMARY - ENHANCED ANALYSIS\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total Events: {len(events)}\n\n")
        
        # Key insights
        if insights:
            f.write("KEY INSIGHTS:\n")
            f.write("-" * 80 + "\n")
            for insight in insights:
                f.write(f"• {insight}\n")
            f.write("\n")
        
        # Event severity breakdown
        level_counts = Counter(e.get('level') for e in events)
        level_names = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}
        f.write("EVENT SEVERITY BREAKDOWN:\n")
        f.write("-" * 80 + "\n")
        for level in sorted(level_counts.keys()):
            count = level_counts[level]
            name = level_names.get(level, f'LEVEL_{level}')
            f.write(f"{name:12s}: {count:5d} events ({count/len(events)*100:5.1f}%)\n")
        f.write("\n")
        
        # List all events with enhanced details
        f.write("EVENT DETAILS WITH ANALYSIS:\n")
        f.write("=" * 80 + "\n\n")
        
        for i, event in enumerate(events, 1):
            level = event.get('level', 0)
            level_names = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}
            level_str = level_names.get(level, f'LEVEL_{level}')
            provider = event.get('provider_name', 'Unknown')
            event_id = event.get('event_id', 0)
            
            # Basic event info
            f.write(f"{i:4d}. [{level_str:8s}] {provider:50s} "
                   f"EventID={event_id:5d} RecordID={event.get('event_record_id', 0):8d}\n")
            f.write(f"      Time: {event.get('event_time', 'Unknown')}\n")
            f.write(f"      Channel: {event.get('log_channel', 'Unknown')}\n")
            f.write(f"      Resources: CPU={event.get('cpu_usage_percent', 0):.1f}% "
                   f"MEM={event.get('memory_usage_percent', 0):.1f}% "
                   f"DISK={event.get('disk_free_percent', 0):.1f}%\n")
            
            # Extract description from raw XML
            raw_xml = event.get('raw_xml', '')
            if raw_xml:
                desc = extract_event_description(raw_xml)
                if desc:
                    f.write(f"      Description: {desc[:200]}\n")
            
            # Add knowledge base info for errors and warnings
            if level in [1, 2, 3]:  # Critical, Error, Warning
                kb_entry = get_event_knowledge(provider, event_id)
                if kb_entry:
                    f.write(f"\n      ┌─ ANALYSIS: {kb_entry['title']}\n")
                    f.write(f"      │\n")
                    f.write(f"      │ Description: {kb_entry['description']}\n")
                    f.write(f"      │\n")
                    if kb_entry.get('causes'):
                        f.write(f"      │ Possible Causes:\n")
                        for cause in kb_entry['causes']:
                            f.write(f"      │   • {cause}\n")
                        f.write(f"      │\n")
                    if kb_entry.get('solutions'):
                        f.write(f"      │ Recommended Solutions:\n")
                        for solution in kb_entry['solutions']:
                            f.write(f"      │   ✓ {solution}\n")
                    f.write(f"      └────────────────────────────────────────────────────\n")
            
            f.write("\n")
    
    print(f"\nEnhanced summary exported to: {output_file}")

def main():
    """Main function"""
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = "collected_events.json"
    
    print(f"Loading events from: {filename}\n")
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filename}': {e}", file=sys.stderr)
        sys.exit(1)
    
    events = data.get('events', [])
    print(f"Loaded {len(events)} events\n")
    
    print("Generating enhanced analysis with solutions...")
    export_enhanced_summary(data)
    print("\nDone! Review event_summary.txt for detailed analysis and solutions.")

if __name__ == "__main__":
    main()
