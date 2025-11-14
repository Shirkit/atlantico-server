#!/bin/bash
# Helper script to start multiple device containers with different data directories

set -e

# Check if number of devices is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <number_of_devices>"
    echo "Example: $0 5  # Start 5 devices (0-4)"
    echo "         $0 200  # Start 200 devices (0-199)"
    exit 1
fi

NUM_DEVICES=$1

# First, start the base services (mosquitto and server)
echo "Starting base services (mosquitto and server)..."
docker-compose up -d

# Wait a bit for services to be ready
sleep 2

# Build the image once if it doesn't exist
echo "Building device image..."
docker-compose build atlantico-raspberry

# Now start each device with its own DEVICE_ID
echo "Starting $NUM_DEVICES device(s)..."
for i in $(seq 0 $((NUM_DEVICES - 1))); do
    echo "Starting device $i..."
    DEVICE_ID=$i docker-compose run -d --name atlantico-raspberry-$i atlantico-raspberry
done

echo ""
echo "Started $NUM_DEVICES device(s)"
echo "To view logs: docker logs -f atlantico-raspberry-0"
echo "To stop all devices: docker stop \$(docker ps -q --filter name=atlantico-raspberry-)"
echo "To remove all devices: docker rm \$(docker ps -aq --filter name=atlantico-raspberry-)"
echo "To stop all services: docker-compose down"
