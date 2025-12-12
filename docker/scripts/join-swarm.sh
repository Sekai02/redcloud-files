#!/bin/bash

echo "Docker Swarm Join Script"
echo ""

if [ -z "$1" ]; then
    echo "Error: Manager IP address required"
    echo ""
    echo "Usage: $0 <manager-ip> <join-token>"
    echo ""
    echo "To get the join token, run this on the manager node:"
    echo "  docker swarm join-token worker"
    echo ""
    exit 1
fi

MANAGER_IP=$1
JOIN_TOKEN=$2

if [ -z "$JOIN_TOKEN" ]; then
    echo "Error: Join token required"
    echo ""
    echo "Get the join token from the manager node:"
    echo "  docker swarm join-token worker"
    echo ""
    exit 1
fi

echo "Joining swarm at $MANAGER_IP..."
docker swarm join --token $JOIN_TOKEN $MANAGER_IP:2377

echo ""
echo "Successfully joined swarm!"
echo ""
echo "You can now run containers on this node that will connect to dfs-network"
