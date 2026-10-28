"""
s(i)oul – Tools, die das Modell im Agent-Modus selbst aufrufen kann.

Jedes Tool besteht aus zwei Teilen:
- einer normalen Python-Funktion, die die Arbeit macht und einen Text zurückgibt
- einem Schema (JSON), das dem Modell sagt, wie das Tool heißt, was es tut
  und welche Argumente es erwartet

Das Modell sieht nur das Schema. Wenn es ein Tool aufrufen will, antwortet es
statt mit Text mit einem Tool-Call (Name + Argumente). Den führen wir hier aus.
"""
import os
import subprocess
import sys
from datetime import datetime

from ownRAG import DATA_DIR, retrieve

MAX_FILE_CHARS = 4000   # damit eine große Datei nicht den ganzen Kontext füllt

# Erlaubnisliste für open_app: Name, den das Modell sieht -> App-Name unter macOS.
# Nur harmlose Apps, bewusst NICHT: Passwörter, Systemeinstellungen, Terminal, VPN, Kurzbefehle
APPS = {
  'Rechner': 'Calculator',
  'Kalender': 'Calendar',
  'Notizen': 'Notes',
  'Erinnerungen': 'Reminders',
  'Musik': 'Music',
  'Fotos': 'Photos',
  'Karten': 'Maps',
  'Wetter': 'Weather',
  'Safari': 'Safari',
  'Google Chrome': 'Google Chrome',
  'Notion': 'Notion',
  'Goodnotes': 'Goodnotes',
  'Anki': 'Anki',
  'Zotero': 'Zotero',
  'Word': 'Microsoft Word',
  'Excel': 'Microsoft Excel',
  'PowerPoint': 'Microsoft PowerPoint',
  'Visual Studio Code': 'Visual Studio Code',
  'Discord': 'Discord',
  'Slack': 'Slack',
  'WhatsApp': 'WhatsApp',
  'Steam': 'Steam',
}


# ---------- Die Tools selbst ----------
def search_documents(query, top_n=3):
  hits = retrieve(query, top_n=int(top_n))
  if not hits:
    return 'Keine passenden Abschnitte gefunden.'
  return '\n'.join(f'[{source}, Ähnlichkeit {score:.2f}] {text}' for text, score, source in hits)

def list_files():
  files = sorted(f for f in os.listdir(DATA_DIR) if not f.startswith('.'))
  return '\n'.join(files) or 'Der Ordner data/ ist leer.'

def read_file(filename):
  # Nur Dateien direkt in data/ erlauben, kein "../" nach draußen
  path = os.path.realpath(os.path.join(DATA_DIR, filename))
  if os.path.dirname(path) != os.path.realpath(DATA_DIR) or not os.path.isfile(path):
    return f'Datei "{filename}" nicht gefunden. Verfügbare Dateien:\n{list_files()}'
  with open(path, 'r', encoding='utf-8', errors='replace') as file:
    text = file.read()
  if len(text) > MAX_FILE_CHARS:
    text = text[:MAX_FILE_CHARS] + f'\n[... gekürzt, Datei hat {len(text)} Zeichen]'
  return text

def current_datetime():
  return datetime.now().strftime('%A, %d.%m.%Y, %H:%M Uhr')

def open_app(app):
  # Groß-/Kleinschreibung egal, aber nur Namen aus der Erlaubnisliste
  name = next((n for n in APPS if n.lower() == str(app).strip().lower()), None)
  if not name:
    return f'"{app}" darf ich nicht öffnen. Erlaubt sind: {", ".join(APPS)}'
  if sys.platform != 'darwin':
    return 'Apps öffnen geht nur auf macOS.'
  # Liste statt Text-Befehl: kein Shell, also kann niemand Befehle einschleusen
  result = subprocess.run(['open', '-a', APPS[name]], check=False, capture_output=True, text=True, timeout=10)
  if result.returncode != 0:
    return f'{name} konnte nicht geöffnet werden: {result.stderr.strip()}'
  return f'{name} wurde geöffnet.'


# ---------- Schemas: das sieht das Modell ----------
def schema(name, description, properties=None, required=None):
  return {
    'type': 'function',
    'function': {
      'name': name,
      'description': description,
      'parameters': {'type': 'object', 'properties': properties or {}, 'required': required or []},
    },
  }

TOOLS = {
  'search_documents': (search_documents, schema(
    'search_documents',
    'Durchsucht die Dokumente des Nutzers (Ordner data/) semantisch und gibt die passendsten '
    'Abschnitte mit Quelle zurück. Nutze das bei jeder Frage zu s(i)oul.ai oder zu Inhalten, '
    'die in den Dokumenten stehen könnten.',
    {
      'query': {'type': 'string', 'description': 'Suchanfrage, am besten eine kurze, präzise Frage oder Stichworte'},
      'top_n': {'type': 'integer', 'description': 'Anzahl der Abschnitte (Standard 3)'},
    },
    ['query'],
  )),
  'list_files': (list_files, schema(
    'list_files',
    'Listet alle Dateien im Dokumente-Ordner data/ auf.',
  )),
  'read_file': (read_file, schema(
    'read_file',
    'Liest eine ganze Datei aus dem Ordner data/. Nur nutzen, wenn die Suche nicht reicht.',
    {'filename': {'type': 'string', 'description': 'Dateiname, z.B. sioul.txt'}},
    ['filename'],
  )),
  'current_datetime': (current_datetime, schema(
    'current_datetime',
    'Gibt das aktuelle Datum und die Uhrzeit zurück.',
  )),
  'open_app': (open_app, schema(
    'open_app',
    'Öffnet eine App auf dem Mac des Nutzers, z.B. wenn er sagt "öffne den Rechner". '
    'Nur die Apps aus der Liste sind möglich.',
    # enum: Das Modell kann nur Namen aus der Erlaubnisliste wählen
    {'app': {'type': 'string', 'enum': list(APPS), 'description': 'Name der App'}},
    ['app'],
  )),
}

TOOL_SCHEMAS = [s for _, s in TOOLS.values()]


def run_tool(name, args):
  # Fehler gehen als Text zurück ans Modell, dann kann es sich selbst korrigieren
  if name not in TOOLS:
    return f'Fehler: Tool "{name}" gibt es nicht. Verfügbar: {", ".join(TOOLS)}'
  function, _ = TOOLS[name]
  try:
    return str(function(**(args or {})))
  except TypeError as e:
    return f'Fehler: falsche Argumente für {name}: {e}'
  except Exception as e:
    return f'Fehler in {name}: {e}'
