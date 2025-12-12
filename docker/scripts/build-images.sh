#!/bin/bash

set -e

cd "$(dirname "$0")/../.."

echo "Building Docker images for RedCloud Files..."

echo ""
echo "Building controller image..."
docker build -f docker/Dockerfile.controller -t redcloud-controller:latest .

echo ""
echo "Building chunkserver image..."
docker build -f docker/Dockerfile.chunkserver -t redcloud-chunkserver:latest .

echo ""
echo "Building CLI image..."
docker build -f docker/Dockerfile.cli -t redcloud-cli:latest .

echo ""
echo "All images built successfully!"
echo ""
docker images | grep redcloud
