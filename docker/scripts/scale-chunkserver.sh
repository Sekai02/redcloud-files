#!/bin/bash

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <number_of_chunkservers>"
    echo "Example: $0 3"
    exit 1
fi

COUNT=$1

if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [ "$COUNT" -lt 1 ]; then
    echo "Error: Please provide a valid number >= 1"
    exit 1
fi

echo "Starting $COUNT chunkserver container(s)..."
echo ""

for i in $(seq 1 $COUNT); do
    CONTAINER_ID=$(docker run -d \
        --network dfs-network \
        --network-alias chunkserver \
        redcloud-chunkserver:latest)
    
    echo "Chunkserver $i started: $CONTAINER_ID"
done

echo ""
echo "All $COUNT chunkserver(s) started successfully!"
echo "Network alias: chunkserver (load-balanced across all instances)"
