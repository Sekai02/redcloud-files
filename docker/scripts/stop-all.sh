#!/bin/bash

set -e

echo "Stopping all RedCloud containers on dfs-network..."
echo ""

CONTAINERS=$(docker ps --filter "network=dfs-network" -q)

if [ -z "$CONTAINERS" ]; then
    echo "No containers running on dfs-network"
    exit 0
fi

echo "Found containers:"
docker ps --filter "network=dfs-network" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
echo ""

docker stop $CONTAINERS

echo ""
echo "All containers stopped successfully"
