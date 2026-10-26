# s(i)oul.local

Ein vollständig lokaler KI-Chat mit eigenem Interface. S(i)oul nutzt ein
Open-Weight-Modell, das direkt auf deinem Rechner läuft. Über RAG
(Retrieval-Augmented Generation) beantwortet es Fragen auf Basis eigener
Dokumente. Es braucht keine Internetverbindung und keinen API-Key, und
deine Daten verlassen nie dein Gerät.

## Features
- 💬 Selbstgebautes Chat-Interface
- 📚 RAG über eigene Textdateien im Ordner `data/`, mit Quellenangabe
- 🔒 100 % lokal und offline nutzbar
- ⚖️ Zwei Modellgrößen zur Auswahl

Getestet auf einem MacBook Air M2 mit 16 GB RAM. Beide Modelle laufen dort
problemlos.

Impressionen sind im Folder 'Einblicke' zu finden. 

## Voraussetzungen

- [Python 3.12](https://www.python.org/downloads/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (für Qdrant)
- [Ollama](https://ollama.com/download)

Getestet auf macOS. Die `.command`-Skripte zum Starten per Doppelklick
funktionieren nur auf macOS. Unter Linux und Windows startest du das Projekt
manuell (siehe [Zum Entwickeln](#zum-entwickeln-änderungen-sofort-live)).

## Installation

```bash
git clone https://github.com/sioullht/sioul-local.git
cd sioul-local

# Python-Pakete
python3.12 -m pip install -r requirements.txt

# Modelle für Ollama
ollama pull gemma4:12b          # größeres Sprachmodell -> 'sioul'
ollama pull qwen3.5:4b          # kleineres Sprachmodell -> 'sioul-mini'
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

Beim ersten Start werden alle `.txt`-Dateien aus `data/` eingebettet und in Qdrant gespeichert (dauert ein paar Sekunden).
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
| Qdrant | Docker | Dokumente aus `data/` als Vektoren |
| server.py + index.html | Mac | Interface und API |
| chats.db | Datei im Ordner | Chat-Verlauf (SQLite, wird automatisch angelegt) |

## Dateien

- `ownRAG.py` – Einbetten, Suchen, Terminal-Chatbot (`python3.12 ownRAG.py`)
- `server.py` – API für die Webseite
- `index.html` – Interface
- `data/` – Textdateien für den RAG-Modus (Beispiel: `sioul.txt`)
- `requirements.txt` – benötigte Python-Pakete
- `docker-compose.yml` – Qdrant-Container

## RAG: eigene Dokumente verwenden

Der Ordner `data/` lässt sich beliebig um eigene `.txt`-Dateien erweitern,
sodass das RAG auf weitere Daten zugreifen kann. Jede Zeile wird ein eigener
Abschnitt, also am besten eine Aussage pro Zeile. Als Beispiel liegt
`data/sioul.txt` bei, mit Fakten über dieses Projekt.

Ist Qdrant schon befüllt, leere die Collection einmal, damit die neuen Dateien
beim nächsten Start eingelesen werden:

```bash
curl -X DELETE http://localhost:6333/collections/documents
```