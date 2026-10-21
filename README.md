# Coded RAG

Eigenes RAG-System mit Chat-Interface im s(i)oul.ai-Design.
Zwei Modi: **Chat** (freies Gespräch mit dem Modell) und **RAG** (Antworten nur aus `cat-facts.txt`).

## Voraussetzungen

- **macOS** (die `.command`-Skripte nutzen `open`)
- [Python 3.12](https://www.python.org/downloads/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (für Qdrant)
- [Ollama](https://ollama.com/download)

## Installation

```bash
git clone https://github.com/sioullht/Coded_RAG.git
cd Coded_RAG

# Python-Pakete
python3.12 -m pip install -r requirements.txt

# Modelle für Ollama
ollama pull gemma4:12b          # Sprachmodell
ollama pull nomic-embed-text    # Embeddings für die Suche
```

> **Hinweis:** In der Modellauswahl erscheinen bevorzugt die Modelle `sioul` und `sioul-mini`.
> Sie werden aus den Modelfiles im s(i)oul.ai-Projekt erstellt (`ollama create sioul -f Modelfile`).
> Fehlen sie, zeigt die Auswahl automatisch alle installierten Chat-Modelle an.

## Starten & stoppen

```bash
./start.command   # startet Ollama, Qdrant und den Server, öffnet den Browser
./stop.command    # stoppt Server und Qdrant (Ollama läuft weiter)
```

Oder einfach im Finder doppelklicken.

Adresse: http://localhost:3001

Beim ersten Start werden die Katzenfakten eingebettet und in Qdrant gespeichert (dauert ein paar Sekunden).
Danach wird dieser Schritt übersprungen.

## Zum Entwickeln (Änderungen sofort live)

```bash
docker compose up -d qdrant
python3.12 -m uvicorn server:app --port 3001 --reload
```

## Was läuft wo

| Teil | Wo | Aufgabe |
|---|---|---|
| Ollama | Mac | Modelle (nomic-embed-text, gemma4:12b, sioul …) |
| Qdrant | Docker | Katzenfakten als Vektoren |
| server.py + index.html | Mac | Interface und API |
| chats.db | Datei im Ordner | Chat-Verlauf (SQLite, wird automatisch angelegt) |

## Dateien

- `ownRAG.py` – Einbetten, Suchen, Terminal-Chatbot (`python3.12 ownRAG.py`)
- `server.py` – API für die Webseite
- `index.html` – Interface
- `cat-facts.txt` – Beispieldaten für den RAG-Modus
- `requirements.txt` – benötigte Python-Pakete
- `docker-compose.yml` – Qdrant-Container