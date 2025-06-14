#!/usr/bin/env python3
"""
Test MQTT binary transmission
"""

import sys
import os
import paho.mqtt.client as mqtt
import time

# Configuration
BROKER_IP = "127.0.0.1"
BROKER_PORT = 1883

def test_binary_transmission():
    """Test if binary files can be transmitted via MQTT"""
    
    # Create a test client to listen for binary messages
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ Test listener connected")
            # Subscribe to all binary topics
            client.subscribe("esp32/fl/model/rawpush/+")
            print("📡 Subscribed to: esp32/fl/model/rawpush/+")
        else:
            print(f"❌ Connection failed: {rc}")
    
    def on_message(client, userdata, message):
        topic = message.topic
        payload_size = len(message.payload)
        print(f"📨 Received binary message:")
        print(f"   Topic: {topic}")
        print(f"   Size: {payload_size} bytes")
        print(f"   First 16 bytes: {message.payload[:16].hex()}")
        
        # Extract client name from topic
        client_name = topic.split('/')[-1]
        filename = f"received_{client_name}.nn"
        
        # Save received binary
        with open(filename, 'wb') as f:
            f.write(message.payload)
        print(f"💾 Saved as: {filename}")
    
    # Create listener client
    listener = mqtt.Client(client_id="test-listener", clean_session=True)
    listener.on_connect = on_connect
    listener.on_message = on_message
    
    print("🔍 Starting binary transmission test...")
    
    try:
        listener.connect(BROKER_IP, BROKER_PORT, 60)
        listener.loop_start()
        
        # Wait for connection
        time.sleep(2)
        
        # Now send a binary file
        sender = mqtt.Client(client_id="test-sender", clean_session=True)
        sender.connect(BROKER_IP, BROKER_PORT, 60)
        
        # Check if dummy1.nn exists and send it
        if os.path.exists("dummy1.nn"):
            with open("dummy1.nn", 'rb') as f:
                binary_data = f.read()
            
            topic = "esp32/fl/model/rawpush/esp20"
            print(f"📤 Sending binary file...")
            print(f"   Topic: {topic}")
            print(f"   Size: {len(binary_data)} bytes")
            
            result = sender.publish(topic, binary_data)
            print(f"📡 Publish result: {result.rc}")
            
        else:
            print("❌ dummy1.nn not found")
        
        # Wait for message to be received
        print("⏳ Waiting for message...")
        time.sleep(3)
        
        sender.disconnect()
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        listener.loop_stop()
        listener.disconnect()

if __name__ == "__main__":
    os.chdir("/home/shirkit/Projects/Github/atlantico-server")
    test_binary_transmission()
