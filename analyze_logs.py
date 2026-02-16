"""
Log Analysis Tool for SentinelCore
Analyzes collected events and generates summary reports
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime

def load_events(filename="collected_events.json"):
    """Load events from JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filename}': {e}", file=sys.stderr)
        sys.exit(1)

def analyze_events(data):
    """Generate statistics and analysis from events"""
    events = data.get('events', [])
    
    if not events:
        print("No events found in file")
        return
    
    # Basic counts
    total_events = len(events)
    
    # Group by log channel
    by_channel = Counter(e.get('log_channel') for e in events)
    
    # Group by event level
    by_level = Counter(e.get('level') for e in events)
    level_names = {1: 'Critical', 2: 'Error', 3: 'Warning', 4: 'Information', 5: 'Verbose'}
    
    # Group by provider
    by_provider = Counter(e.get('provider_name') for e in events)
    
    # Group by event ID
    by_event_id = Counter(e.get('event_id') for e in events)
    
    # Resource usage stats
    cpu_values = [e.get('cpu_usage_percent', 0) for e in events]
    mem_values = [e.get('memory_usage_percent', 0) for e in events]
    disk_values = [e.get('disk_free_percent', 0) for e in events]
    
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
        print(f"  {channel:60s} {count:5d} ({count/total_events*100:5.1f}%)")
    
    # Events by level
    print(f"\nEvents by Severity Level:")
    for level, count in sorted(by_level.items()):
        level_name = level_names.get(level, f'Unknown({level})')
        print(f"  {level_name:20s} {count:5d} ({count/total_events*100:5.1f}%)")
    
    # Top providers
    print(f"\nTop 10 Event Providers:")
    for provider, count in by_provider.most_common(10):
        print(f"  {provider:60s} {count:5d}")
    
    # Top event IDs
    print(f"\nTop 10 Event IDs:")
    for event_id, count in by_event_id.most_common(10):
        # Find provider name for this event ID
        example = next((e for e in events if e.get('event_id') == event_id), None)
        provider = example.get('provider_name', 'Unknown') if example else 'Unknown'
        print(f"  {event_id:6d} ({provider:45s}) {count:5d}")
    
    # Resource usage
    print(f"\nSYSTEM RESOURCE USAGE (during collection)")
    print("-" * 80)
    if cpu_values:
        print(f"CPU Usage:       Min={min(cpu_values):.1f}%  Max={max(cpu_values):.1f}%  Avg={sum(cpu_values)/len(cpu_values):.1f}%")
    if mem_values:
        print(f"Memory Usage:    Min={min(mem_values):.1f}%  Max={max(mem_values):.1f}%  Avg={sum(mem_values)/len(mem_values):.1f}%")
    if disk_values:
        print(f"Disk Free:       Min={min(disk_values):.1f}%  Max={max(disk_values):.1f}%  Avg={sum(disk_values)/len(disk_values):.1f}%")
    
    # Critical/Error events
    critical_errors = [e for e in events if e.get('level') in [1, 2]]
    if critical_errors:
        print(f"\nCRITICAL & ERROR EVENTS ({len(critical_errors)} total)")
        print("-" * 80)
        
        # Group by provider
        ce_by_provider = Counter(e.get('provider_name') for e in critical_errors)
        print(f"By Provider:")
        for provider, count in ce_by_provider.most_common(5):
            print(f"  {provider:60s} {count:5d}")
    
    print("\n" + "=" * 80)

def export_summary(data, output_file="event_summary.txt"):
    """Export summary to text file"""
    events = data.get('events', [])
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("SENTINELCORE EVENT SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total Events: {len(events)}\n\n")
        
        # List all events with key details
        f.write("EVENT DETAILS:\n")
        f.write("-" * 80 + "\n")
        
        for i, event in enumerate(events, 1):
            level = event.get('level', 0)
            level_names = {1: 'CRITICAL', 2: 'ERROR', 3: 'WARNING', 4: 'INFO', 5: 'VERBOSE'}
            level_str = level_names.get(level, f'LEVEL_{level}')
            
            f.write(f"{i:4d}. [{level_str:8s}] {event.get('provider_name', 'Unknown'):50s} "
                   f"EventID={event.get('event_id', 0):5d} RecordID={event.get('event_record_id', 0):8d}\n")
            f.write(f"      Time: {event.get('event_time', 'Unknown')}\n")
            f.write(f"      Channel: {event.get('log_channel', 'Unknown')}\n")
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
