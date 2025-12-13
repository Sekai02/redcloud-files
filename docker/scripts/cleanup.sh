#!/bin/bash

set -e

echo "Cleaning up RedCloud Docker resources..."
echo ""

echo "Stopping containers on dfs-network..."
CONTAINERS=$(docker ps -a --filter "network=dfs-network" -q)
if [ -n "$CONTAINERS" ]; then
    docker stop $CONTAINERS 2>/dev/null || true
    docker rm $CONTAINERS 2>/dev/null || true
    echo "Containers removed"
else
    echo "No containers to remove"
fi

echo ""
read -p "Remove dfs-network? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if docker network ls | grep -q "dfs-network"; then
        docker network rm dfs-network
        echo "Network removed"
    else
        echo "Network does not exist"
    fi
fi

echo ""
read -p "Remove Docker images? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker rmi redcloud-controller:latest 2>/dev/null || true
    docker rmi redcloud-chunkserver:latest 2>/dev/null || true
    docker rmi redcloud-cli:latest 2>/dev/null || true
    echo "Images removed"
fi

echo ""
echo "Cleanup complete"
