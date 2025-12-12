#!/bin/bash

set -e

echo "Initializing Docker Swarm network for RedCloud Files..."

if ! docker info | grep -q "Swarm: active"; then
    echo "Initializing Docker Swarm..."
    docker swarm init
    echo "Docker Swarm initialized successfully"
else
    echo "Docker Swarm already active"
fi

if ! docker network ls | grep -q "dfs-network"; then
    echo "Creating overlay network: dfs-network"
    docker network create --driver overlay --attachable dfs-network
    echo "Network created successfully"
else
    echo "Network 'dfs-network' already exists"
fi

echo ""
echo "Setup complete!"
echo ""
echo "To add worker nodes to this swarm, run the following command on other machines:"
echo ""
docker swarm join-token worker
