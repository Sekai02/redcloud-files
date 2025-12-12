#!/bin/bash

SERVICE=$1

if [ -z "$SERVICE" ]; then
    echo "Tailing logs from all containers on dfs-network..."
    echo ""
    CONTAINERS=$(docker ps --filter "network=dfs-network" -q)
    
    if [ -z "$CONTAINERS" ]; then
        echo "No containers running on dfs-network"
        exit 1
    fi
    
    docker logs -f $CONTAINERS
else
    echo "Tailing logs from $SERVICE containers..."
    echo ""
    CONTAINERS=$(docker ps --filter "network=dfs-network" --filter "ancestor=redcloud-$SERVICE:latest" -q)
    
    if [ -z "$CONTAINERS" ]; then
        echo "No $SERVICE containers running on dfs-network"
        exit 1
    fi
    
    docker logs -f $CONTAINERS
fi
