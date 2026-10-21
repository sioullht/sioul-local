#!/bin/bash
cd "$(dirname "$0")"

echo "Stoppe den Server ..."
pkill -f "uvicorn server:app"

echo "Stoppe Qdrant ..."
docker compose stop