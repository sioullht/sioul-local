import os
import sqlite3
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from ownRAG import build_database, retrieve, llm, LANGUAGE_MODEL

DB_PATH = os.getenv('DB_PATH', 'chats.db')
NO_INFO = 'Dazu habe ich leider keine Informationen.'

app = FastAPI()


# ---------- Chat history (SQLite) ----------
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
  # Used when the user edits their last question: remove it and the answer after it
  with db() as con:
    con.execute('''DELETE FROM messages WHERE chat_id = ? AND id >= (
                     SELECT MAX(id) FROM messages WHERE chat_id = ? AND role = 'user')''',
                (chat_id, chat_id))


# ---------- Chat list endpoints (same for both modes) ----------
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


# ---------- Page + models ----------
@app.get('/')
def index():
  return FileResponse('index.html')

@app.get('/sioul-avatar.svg')
def avatar():
  return FileResponse('sioul-avatar.svg', media_type='image/svg+xml')

# Which models appear in the picker, and which base model each one is built on
# (shown in grey below the name, like in s(i)oul.ai)
MODELS = {
  'sioul': 'gemma4:12b',
  'sioul-mini': 'qwen3.5:4b',
}

@app.get('/api/models')
def models():
  installed = {m.model.removesuffix(':latest'): m for m in llm.list().models}
  out = []
  for name, base in MODELS.items():
    m = installed.get(name)
    if m:
      out.append({'name': m.model, 'base': base, 'size': f'{m.size / 1e9:.1f} GB'})
  if not out:   # none of the s(i)oul models found: show every chat model instead
    out = [{'name': m.model, 'size': f'{m.size / 1e9:.1f} GB'}
           for m in installed.values() if 'embed' not in m.model]
  return out


class ChatIn(BaseModel):
  sessionId: str
  message: str
  model: str | None = None
  replaceLast: bool = False


# ---------- Mode "Chat": free chat with the model, streamed ----------
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


# ---------- Mode "RAG": answers from the files in data/ ----------
@app.post('/api/rag/chat')
def rag_chat(body: ChatIn):
  message = body.message.strip()
  if not message:
    return JSONResponse({'error': 'Leere Nachricht'}, status_code=400)
  save_message(body.sessionId, 'rag', 'user', message)

  hits = retrieve(message)
  if not hits:
    answer = NO_INFO
  else:
    context = '\n'.join(f' - {chunk}' for chunk, _, _ in hits)
    system = f'''You are a helpful chatbot.
Use only the following pieces of context to answer the question. Don't make up any new information:
{context}
'''
    response = llm.chat(
      model=body.model or LANGUAGE_MODEL,   # chosen in the picker, LANGUAGE_MODEL as fallback
      messages=[{'role': 'system', 'content': system}] + history(body.sessionId),
      think=False,
    )
    # "(Quelle: ...)" at the end is shown as a source line by your index.html
    sources = ', '.join(dict.fromkeys(source for _, _, source in hits if source))
    answer = response['message']['content'].strip() + f'\n\n(Quelle: {sources})'

  save_message(body.sessionId, 'rag', 'assistant', answer)
  return {'answer': answer}


# Fill Qdrant once at startup (skipped if it already has data)
build_database()