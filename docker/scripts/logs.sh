#!/bin/bash

SERVICE=$1
TAIL_LINES=${2:-100}
FOLLOW=${3:-false}

show_usage() {
    echo "Usage: $0 [SERVICE] [LINES] [--follow]"
    echo ""
    echo "Arguments:"
    echo "  SERVICE    Component to view logs from: controller, chunkserver, cli, or 'all' (default: all)"
    echo "  LINES      Number of recent lines to show (default: 100)"
    echo "  --follow   Follow log output in real-time (use -f for short)"
    echo ""
    echo "Examples:"
    echo "  $0                          # Show last 100 lines from all containers"
    echo "  $0 controller               # Show last 100 lines from controller"
    echo "  $0 controller 50            # Show last 50 lines from controller"
    echo "  $0 controller 100 -f        # Follow controller logs"
    echo "  $0 all 200 --follow         # Follow all logs (last 200 lines)"
    exit 0
}

if [ "$SERVICE" = "-h" ] || [ "$SERVICE" = "--help" ]; then
    show_usage
fi

FOLLOW_FLAG=""
if [ "$TAIL_LINES" = "-f" ] || [ "$TAIL_LINES" = "--follow" ]; then
    FOLLOW_FLAG="-f"
    TAIL_LINES=100
elif [ "$FOLLOW" = "-f" ] || [ "$FOLLOW" = "--follow" ]; then
    FOLLOW_FLAG="-f"
fi

if [ -z "$SERVICE" ] || [ "$SERVICE" = "all" ]; then
    echo "Showing logs from all containers on dfs-network (last $TAIL_LINES lines)..."
    if [ -n "$FOLLOW_FLAG" ]; then
        echo "Following logs... (Press Ctrl+C to stop)"
    fi
    echo ""
    CONTAINERS=$(docker ps --filter "network=dfs-network" -q)
    
    if [ -z "$CONTAINERS" ]; then
        echo "No containers running on dfs-network"
        echo "Start the system with: ./docker/scripts/run-controller.sh && ./docker/scripts/run-chunkserver.sh"
        exit 1
    fi
    
    docker logs --tail "$TAIL_LINES" $FOLLOW_FLAG $CONTAINERS
else
    echo "Showing logs from $SERVICE containers (last $TAIL_LINES lines)..."
    if [ -n "$FOLLOW_FLAG" ]; then
        echo "Following logs... (Press Ctrl+C to stop)"
    fi
    echo ""
    CONTAINERS=$(docker ps --filter "network=dfs-network" --filter "ancestor=redcloud-$SERVICE:latest" -q)
    
    if [ -z "$CONTAINERS" ]; then
        echo "No $SERVICE containers running on dfs-network"
        echo "Available services: controller, chunkserver, cli"
        exit 1
    fi
    
    docker logs --tail "$TAIL_LINES" $FOLLOW_FLAG $CONTAINERS
fi
