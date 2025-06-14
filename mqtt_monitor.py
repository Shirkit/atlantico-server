#!/usr/bin/env python3
"""
MQTT Traffic Monitor - Listen to all topics to debug the federated learning communication
"""

import paho.mqtt.client as mqtt
import time
import json

BROKER_IP = "127.0.0.1"
BROKER_PORT = 1883

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT Monitor connected")
        # Subscribe to all topics with wildcard
        client.subscribe("#")
        print("📡 Monitoring ALL MQTT topics (#)")
        print("=" * 60)
    else:
        print(f"❌ Connection failed: {rc}")

def on_message(client, userdata, message):
    topic = message.topic
    timestamp = time.strftime("%H:%M:%S")
    
    # Try to decode as text first
    try:
        payload = message.payload.decode('utf-8')
        payload_type = "TEXT"
        preview = payload[:100] + "..." if len(payload) > 100 else payload
        
        # Try to parse as JSON for better formatting
        try:
            json_data = json.loads(payload)
            if len(str(json_data)) < 200:
                preview = str(json_data)
            else:
                preview = f"JSON object with {len(json_data)} fields"
        except:
            pass
            
    except UnicodeDecodeError:
        # Binary data
        payload_type = "BINARY"
        preview = f"{len(message.payload)} bytes - {message.payload[:16].hex()}"
    
    print(f"[{timestamp}] 📨 {topic}")
    print(f"         Type: {payload_type}")
    print(f"         Data: {preview}")
    print(f"         Size: {len(message.payload)} bytes")
    print("-" * 60)

def main():
    print("🔍 MQTT Traffic Monitor for Federated Learning")
    print("📡 This will show all MQTT messages on all topics")
    print("🔄 Press Ctrl+C to stop")
    print("=" * 60)
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="mqtt-monitor")
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER_IP, BROKER_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n👋 Stopping MQTT monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
