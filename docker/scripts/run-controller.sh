#!/bin/bash

set -e

echo "Starting controller container..."

CONTAINER_ID=$(docker run -d \
    --network dfs-network \
    --network-alias controller \
    redcloud-controller:latest)

echo "Controller started successfully!"
echo "Container ID: $CONTAINER_ID"
echo "Network alias: controller"
echo "Internal access: http://controller:8000"
