# Coded RAG

Eigenes RAG-System mit Chat-Interface im s(i)oul.ai-Design.

## Starten & stoppen

```bash
./start.command   # startet Ollama, Qdrant und den Server, öffnet den Browser
./stop.command    # stoppt Server und Qdrant (Ollama läuft weiter)
```

Oder einfach im Finder doppelklicken.

Adresse: http://localhost:3001

## Zum Entwickeln (Änderungen sofort live)

```bash
docker compose up -d qdrant
python3.12 -m uvicorn server:app --port 3001 --reload
```

## Was läuft wo

| Teil | Wo | Aufgabe |
|---|---|---|
| Ollama | Mac | Modelle (nomic-embed-text, qwen3.5:4b, sioul …) |
| Qdrant | Docker | Katzenfakten als Vektoren |
| server.py + index.html | Mac | Interface und API |
| chats.db | Datei im Ordner | Chat-Verlauf (SQLite) |

## Dateien

- `ownRAG.py` – Einbetten, Suchen, Terminal-Chatbot (`python3.12 ownRAG.py`)
- `server.py` – API für die Webseite
- `index.html` – Interface
- `cat-facts.txt` – die Daten
- `server.log` – Ausgaben des Servers, wenn über start.command gestartet