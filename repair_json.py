"""
JSON Repair Script for SentinelCore
Fixes corrupted NDJSON files where JSON objects run together
"""

import json
import re
import sys

def repair_ndjson(input_file, output_file):
    """
    Repair NDJSON file by splitting concatenated JSON objects
    """
    print(f"Reading {input_file}...")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"File size: {len(content)} bytes")
    
    # Find all instances where "}{"  appears (two JSON objects without newline)
    corrupted_count = content.count('}{')
    print(f"Found {corrupted_count} corrupted line joins")
    
    # Split on "}{"  and rejoin with "}\n{"
    fixed_content = content.replace('}{', '}\n{')
    
    # Ensure file ends with newline
    if not fixed_content.endswith('\n'):
        fixed_content += '\n'
    
    # Write repaired file
    print(f"Writing to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(fixed_content)
    
    # Validate by counting lines
    lines = fixed_content.split('\n')
    valid_json_lines = [l for l in lines if l.strip()]
    
    print(f"\nValidation:")
    print(f"  Total lines: {len(valid_json_lines)}")
    
    # Try parsing first and last objects
    try:
        first_obj = json.loads(valid_json_lines[0])
        print(f"  First object: Valid JSON")
    except Exception as e:
        print(f"  First object: INVALID - {e}")
    
    try:
        last_obj = json.loads(valid_json_lines[-1])
        print(f"  Last object: Valid JSON")
    except Exception as e:
        print(f"  Last object: INVALID - {e}")
    
    print(f"\nRepair complete!")
    print(f"Original: {input_file}")
    print(f"Repaired: {output_file}")

if __name__ == "__main__":
    input_file = "events_20260215_181044.json"
    output_file = "events_20260215_181044_REPAIRED.json"
    
    repair_ndjson(input_file, output_file)
