#!/bin/bash

set -e

echo "Starting chunkserver container..."

CONTAINER_ID=$(docker run -d \
    --network dfs-network \
    --network-alias chunkserver \
    redcloud-chunkserver:latest)

echo "Chunkserver started successfully!"
echo "Container ID: $CONTAINER_ID"
echo "Network alias: chunkserver"
echo "Internal port: 50051"
echo "Internal access: chunkserver:50051"
