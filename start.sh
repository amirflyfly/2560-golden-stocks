#!/bin/bash
set -e

if [ "${APP_ENV:-development}" = "production" ] || [ "${APP_ENV:-development}" = "prod" ]; then
    echo "start.sh is a legacy docker-run helper without MySQL wiring. Use docker compose for production."
    exit 1
fi

echo "Building 2560 Strategy legacy Docker image..."
docker build -t 2560-strategy .

echo "Starting legacy container with local data volume..."
docker run -d --name 2560-runner -v "$(pwd)/data:/app/data" 2560-strategy
echo "Container started. Logs: docker logs -f 2560-runner"
echo "Stop command: docker stop 2560-runner"
