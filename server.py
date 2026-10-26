import os
import sqlite3
import time

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

import voice  # Whisper + Piper (Sprache)
from ownRAG import BASE_DIR, LANGUAGE_MODEL, MODELS, NO_INFO, build_database, llm, retrieve, system_prompt

DB_PATH = os.getenv('DB_PATH', os.path.join(BASE_DIR, 'chats.db'))

app = FastAPI()


# ---------- Chat-Verlauf (SQLite) ----------
def db():
  con = sqlite3.connect(DB_PATH)
  con.row_factory = sqlite3.Row
  return con

with db() as con:
  con.executescript('''
    CREATE TABLE IF NOT EXISTS chats (
      id TEXT PRIMARY KEY, mode TEXT, title TEXT, updated REAL
    );
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      chat_id TEXT, role TEXT, content TEXT, ts REAL
    );
  ''')

def save_message(chat_id, mode, role, content):
  now = time.time()
  with db() as con:
    con.execute('INSERT INTO messages (chat_id, role, content, ts) VALUES (?, ?, ?, ?)',
                (chat_id, role, content, now))
    con.execute('INSERT OR IGNORE INTO chats (id, mode, title, updated) VALUES (?, ?, ?, ?)',
                (chat_id, mode, content[:60], now))
    con.execute('UPDATE chats SET updated = ? WHERE id = ?', (now, chat_id))

def history(chat_id):
  with db() as con:
    rows = con.execute('SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id', (chat_id,))
    return [{'role': r['role'], 'content': r['content']} for r in rows]

def drop_last_turn(chat_id):
  # Wenn die letzte Frage bearbeitet wird: sie und die Antwort danach löschen
  with db() as con:
    con.execute('''DELETE FROM messages WHERE chat_id = ? AND id >= (
                     SELECT MAX(id) FROM messages WHERE chat_id = ? AND role = 'user')''',
                (chat_id, chat_id))


# ---------- Chat-Liste (gleich für beide Modi) ----------
def chat_routes(prefix, mode):
  @app.get(prefix + '/chats')
  def list_chats():
    with db() as con:
      rows = con.execute('''
        SELECT c.id, c.title, c.updated,
          (SELECT content FROM messages m WHERE m.chat_id = c.id AND m.role = 'assistant'
           ORDER BY m.id DESC LIMIT 1) AS preview
        FROM chats c WHERE c.mode = ? ORDER BY c.updated DESC''', (mode,))
      return [{'id': r['id'], 'title': r['title'], 'preview': r['preview'] or '',
               'updated': int(r['updated'])} for r in rows]

  @app.get(prefix + '/chats/{chat_id}')
  def get_chat(chat_id: str):
    return history(chat_id)

  @app.patch(prefix + '/chats/{chat_id}')
  def rename_chat(chat_id: str, body: dict):
    with db() as con:
      con.execute('UPDATE chats SET title = ? WHERE id = ?', (body.get('title', ''), chat_id))
    return {'ok': True}

  @app.delete(prefix + '/chats/{chat_id}')
  def delete_chat(chat_id: str):
    with db() as con:
      con.execute('DELETE FROM messages WHERE chat_id = ?', (chat_id,))
      con.execute('DELETE FROM chats WHERE id = ?', (chat_id,))
    return {'ok': True}

chat_routes('/api', 'chat')
chat_routes('/api/rag', 'rag')


# ---------- Seite + Modelle ----------
@app.get('/')
def index():
  # no-cache: Browser lädt Änderungen an index.html sofort statt einer alten Kopie
  return FileResponse(os.path.join(BASE_DIR, 'index.html'), headers={'Cache-Control': 'no-cache'})

@app.get('/sioul-avatar.svg')
def avatar():
  return FileResponse(os.path.join(BASE_DIR, 'sioul-avatar.svg'), media_type='image/svg+xml')

# Modelle für die Auswahl, das Basismodell steht grau unter dem Namen
@app.get('/api/models')
def models():
  installed = {m.model.removesuffix(':latest'): m for m in llm.list().models}
  out = []
  for name, base in MODELS.items():
    m = installed.get(name)
    if m:
      out.append({'name': m.model, 'base': base, 'size': f'{m.size / 1e9:.1f} GB'})
  if not out:   # keins der s(i)oul-Modelle installiert: alle Chat-Modelle anzeigen
    out = [{'name': m.model, 'size': f'{m.size / 1e9:.1f} GB'}
           for m in installed.values() if 'embed' not in m.model]
  return out


class ChatIn(BaseModel):
  sessionId: str
  message: str
  model: str | None = None
  replaceLast: bool = False


# ---------- Modus "Chat": freier Chat mit dem Modell, Wort für Wort ----------
@app.post('/api/chat')
def chat(body: ChatIn):
  message = body.message.strip()
  if not message:
    return JSONResponse({'error': 'Leere Nachricht'}, status_code=400)
  if body.replaceLast:
    drop_last_turn(body.sessionId)
  save_message(body.sessionId, 'chat', 'user', message)
  messages = history(body.sessionId)

  def generate():
    answer = ''
    try:
      stream = llm.chat(model=body.model or LANGUAGE_MODEL, messages=messages, stream=True, think=False)
      for part in stream:
        text = part['message']['content']
        answer += text
        yield text
    finally:
      if answer.strip():
        save_message(body.sessionId, 'chat', 'assistant', answer)

  return StreamingResponse(generate(), media_type='text/plain; charset=utf-8')


# ---------- Modus "RAG": Antworten aus den Dateien in data/ ----------
@app.post('/api/rag/chat')
def rag_chat(body: ChatIn):
  message = body.message.strip()
  if not message:
    return JSONResponse({'error': 'Leere Nachricht'}, status_code=400)
  if body.replaceLast:
    drop_last_turn(body.sessionId)
  save_message(body.sessionId, 'rag', 'user', message)

  hits = retrieve(message)
  if not hits:
    answer = NO_INFO
  else:
    response = llm.chat(
      model=body.model or LANGUAGE_MODEL,   # aus der Auswahl, sonst LANGUAGE_MODEL
      messages=[{'role': 'system', 'content': system_prompt(hits)}] + history(body.sessionId),
      think=False,
    )
    # "(Quelle: ...)" am Ende zeigt index.html als Quellenzeile an
    sources = ', '.join(dict.fromkeys(source for _, _, source in hits if source))
    answer = response['message']['content'].strip() + f'\n\n(Quelle: {sources})'

  save_message(body.sessionId, 'rag', 'assistant', answer)
  return {'answer': answer}


# ---------- Sprache: Whisper (Sprache -> Text) und Piper (Text -> Sprache) ----------
def voice_not_ready():
  # None, wenn bereit, sonst eine Fehlerantwort (nach einem Fehler wird neu gestartet)
  if voice.state['status'] == 'ready':
    return None
  if voice.state['status'] in ('error', 'off'):
    err = voice.state.get('error')
    voice.start()
    msg = 'Sprachfunktionen nicht verfügbar: ' + err if err else 'Sprachfunktionen werden gestartet ...'
  else:
    msg = 'Sprachmodelle werden noch geladen (beim ersten Start einmaliger Download) ...'
  return JSONResponse({'error': msg}, status_code=503)

@app.get('/api/voice')
def voice_status():
  return voice.state

@app.post('/api/stt')
async def stt(request: Request):
  data = await request.body()
  if (error := voice_not_ready()):
    return error
  if not data or len(data) > 30 * 1024 * 1024:
    return JSONResponse({'error': 'Keine oder zu große Aufnahme'}, status_code=400)
  ctype = request.headers.get('content-type', '').lower()
  suffix = '.mp4' if ('mp4' in ctype or 'm4a' in ctype or 'aac' in ctype) else \
           '.ogg' if 'ogg' in ctype else '.wav' if 'wav' in ctype else '.webm'
  try:
    return voice.transcribe(data, suffix)
  except Exception as e:
    return JSONResponse({'error': 'Spracherkennung fehlgeschlagen: ' + str(e)}, status_code=500)

class TtsIn(BaseModel):
  text: str
  lang: str | None = None

@app.post('/api/tts')
def tts(body: TtsIn):
  if (error := voice_not_ready()):
    return error
  text = body.text.strip()
  if not text:
    return JSONResponse({'error': 'Kein Text'}, status_code=400)
  try:
    audio, lang = voice.speak(text, body.lang)
  except Exception as e:
    return JSONResponse({'error': 'Vorlesen fehlgeschlagen: ' + str(e)}, status_code=500)
  return Response(audio, media_type='audio/wav', headers={'X-Voice-Lang': lang})


# Qdrant beim Start einmal befüllen (übersprungen, wenn schon Daten da sind)
build_database()
# Sprachmodelle im Hintergrund laden (beim ersten Start einmaliger Download)
voice.start()