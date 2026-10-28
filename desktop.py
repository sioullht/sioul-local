"""
s(i)oul – Desktop-App: derselbe Server wie die Web-Version, aber in einem
eigenen macOS-Fenster statt im Browser.

Unterschiede zur Web-Version (start.command):
- Qdrant läuft ohne Docker direkt in Python (Ordner qdrant_data/)
- eigener Port 3002, damit Web-Version und App sich nicht in die Quere kommen

Starten: python3.12 desktop.py
"""
import os
import subprocess
import sys
import threading
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 3002
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
BG = '#110f17'   # Hintergrundfarbe aus index.html, damit beim Laden nichts weiß aufblitzt
LOG_FILE = os.path.expanduser('~/Library/Logs/sioul.log')

# Aus dem Dock gestartet gibt es kein Terminal: Ausgaben und Fehler in eine Log-Datei
# (ansehen z.B. mit: tail -f ~/Library/Logs/sioul.log)
if not sys.stdout or not sys.stdout.isatty():
  # Kein 'with': die Datei soll offen bleiben, solange die App läuft
  sys.stdout = sys.stderr = open(LOG_FILE, 'a', encoding='utf-8', buffering=1)  # noqa: SIM115
  print(f'\n--- s(i)oul gestartet {time.strftime("%d.%m.%Y %H:%M:%S")} ---')

# Muss vor dem Import von server gesetzt sein: ownRAG.py verbindet Qdrant schon beim Import
os.environ.setdefault('QDRANT_PATH', os.path.join(BASE_DIR, 'qdrant_data'))

import uvicorn
import webview


def ollama_running():
  try:
    urllib.request.urlopen(OLLAMA_URL + '/api/version', timeout=2)
    return True
  except OSError:
    return False

def ensure_ollama(wait=30):
  # Ollama starten, falls es nicht läuft, und bis zu 30 Sekunden warten
  if ollama_running():
    return True
  subprocess.run(['open', '-a', 'Ollama'], check=False)
  for _ in range(wait):
    time.sleep(1)
    if ollama_running():
      return True
  return False

class Api:
  # Funktionen, die index.html über window.pywebview.api aufrufen kann
  def zoom(self, factor):
    # Echte Seitenvergrößerung wie in Safari (⌘+ / ⌘−). Fenster-Änderungen
    # müssen im Haupt-Thread passieren, pywebview ruft uns aber in einem anderen auf.
    from PyObjCTools import AppHelper
    view = webview.windows[0].native.contentView()   # das WKWebView im Fenster
    AppHelper.callAfter(view.setPageZoom_, float(factor))

def show_error(text):
  html = f'''<body style="background:{BG};color:#e8e4f0;font-family:-apple-system,sans-serif;
    display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center">
    <div><h2>s(i)oul kann nicht starten</h2><p style="color:#9a93ab">{text}</p></div></body>'''
  webview.create_window('s(i)oul', html=html, width=520, height=320, background_color=BG)
  webview.start()


def main():
  if not ensure_ollama():
    show_error('Ollama läuft nicht. Starte die Ollama-App und öffne s(i)oul dann erneut.')
    return

  # Erst jetzt importieren: Beim Import füllt server.py Qdrant, dafür muss Ollama laufen
  try:
    from server import app
  except RuntimeError as e:
    if 'already accessed' not in str(e):
      raise
    # Qdrant-Ordner ist gesperrt: s(i)oul läuft schon (oder ein anderes Programm nutzt ihn)
    show_error('s(i)oul läuft bereits in einem anderen Fenster.')
    return

  # Server im Hintergrund-Thread, das Fenster braucht den Haupt-Thread
  server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning'))
  thread = threading.Thread(target=server.run, daemon=True)
  thread.start()
  while not server.started and thread.is_alive():
    time.sleep(0.1)
  if not server.started:
    show_error(f'Port {PORT} ist belegt. Läuft s(i)oul schon in einem anderen Fenster?')
    return

  webview.create_window('s(i)oul', f'http://127.0.0.1:{PORT}', width=1200, height=820,
                        min_size=(380, 600), background_color=BG, js_api=Api())
  webview.start()          # blockiert, bis das Fenster geschlossen wird
  server.should_exit = True


if __name__ == '__main__':
  main()
