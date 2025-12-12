#!/bin/bash

set -e

echo "Starting CLI container (interactive mode)..."
echo "Press Ctrl+D or type 'exit' to quit"
echo ""

docker run -it --rm \
    --network dfs-network \
    redcloud-cli:latest
