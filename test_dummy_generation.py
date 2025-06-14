#!/usr/bin/env python3
"""
Test script to verify dummy file generation without needing MQTT server
"""

import sys
import os

# Add the current directory to Python path
sys.path.append('/home/shirkit/Projects/Github/atlantico-server')

# Import the mock client
from dummy2 import MockESP32Client

def test_dummy_file_generation():
    """Test the dummy file generation functions"""
    print("🧪 Testing dummy file generation...")
    
    # Create a mock client instance
    client = MockESP32Client()
    
    # Test JSON generation
    print("\n📄 Testing JSON generation...")
    try:
        client._create_and_send_dummy_json()
        print("✅ JSON generation completed")
    except Exception as e:
        print(f"❌ JSON generation failed: {e}")
    
    # Test binary generation  
    print("\n📦 Testing binary generation...")
    try:
        client._create_and_send_dummy_nn()
        print("✅ Binary generation completed")
    except Exception as e:
        print(f"❌ Binary generation failed: {e}")
    
    # Check if files were created
    print("\n📁 Checking created files...")
    
    json_file = "dummy1.json"
    nn_file = "dummy1.nn"
    
    if os.path.exists(json_file):
        size = os.path.getsize(json_file)
        print(f"✅ {json_file} created ({size} bytes)")
        
        # Show first few lines of JSON
        with open(json_file, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            print(f"📄 JSON preview (first 10 lines):")
            for i, line in enumerate(lines[:10]):
                print(f"   {i+1}: {line}")
            if len(lines) > 10:
                print(f"   ... ({len(lines)-10} more lines)")
    else:
        print(f"❌ {json_file} not found")
    
    if os.path.exists(nn_file):
        size = os.path.getsize(nn_file)
        print(f"✅ {nn_file} created ({size} bytes)")
        
        # Show binary file info
        with open(nn_file, 'rb') as f:
            first_16_bytes = f.read(16)
            hex_preview = ' '.join(f'{b:02x}' for b in first_16_bytes)
            print(f"📦 Binary preview (first 16 bytes): {hex_preview}")
    else:
        print(f"❌ {nn_file} not found")

if __name__ == "__main__":
    test_dummy_file_generation()
