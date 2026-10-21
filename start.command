#!/bin/bash
cd "$(dirname "$0")"

echo "Starte Ollama ..."
open -a Ollama
echo "Starte Docker ..."
docker compose up -d

echo "Öffne den Browser ..."
(sleep 3 && open http://127.0.0.1:3001) &

echo "Starte den Server ..."
python3.12 -m uvicorn server:app --port 3001 --reload