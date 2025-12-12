#!/bin/bash

set -e

echo "Starting CLI container (interactive mode)..."
echo "Press Ctrl+D or type 'exit' to quit"
echo ""
echo "Volume mounts:"
echo "  - Current directory -> /uploads (for file uploads)"
echo "  - ./downloads -> /downloads (for file downloads)"
echo ""

mkdir -p downloads

docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest
