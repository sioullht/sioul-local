"""
s(i)oul – Agent-Schleife, selbst gebaut (kein Framework).

Ablauf pro Frage:
  1. Verlauf + Tool-Schemas ans Modell schicken
  2. Antwortet das Modell mit Text -> fertig
  3. Antwortet es mit Tool-Calls -> Tools ausführen, Ergebnisse als
     Nachrichten mit role 'tool' anhängen, zurück zu 1.
MAX_STEPS ist die Notbremse, falls das Modell nie aufhört, Tools aufzurufen.

agent_steps() ist ein Generator und meldet jeden Schritt als Event:
  {'type': 'token', 'text': ...}                       Teil der Antwort (Streaming)
  {'type': 'tool_call', 'name': ..., 'args': ...}      Modell ruft ein Tool auf
  {'type': 'tool_result', 'name': ..., 'result': ...}  Ergebnis des Tools
  {'type': 'done', 'answer': ..., 'steps': n}          fertig
So kann das Web-Interface live streamen und die Evals alles mitprotokollieren.
"""
from ownRAG import llm
from tools import TOOL_SCHEMAS, run_tool

MAX_STEPS = 5
# Qwen statt Gemma: Gemma erzeugt mit System-Prompt + Tools kaputte Tool-Calls (Ollama/MLX)
AGENT_MODEL = 'sioul-mini'

# Ersetzt den SYSTEM-Teil aus dem Modelfile, darum steht die Persönlichkeit hier noch mal
SYSTEM_PROMPT = '''Du bist s(i)oul, ein KI-Assistent, entwickelt von Louis.
Du bist locker und hilfsbereit.
Antworte immer in der Sprache, in der die Frage gestellt wurde.

Du kannst Tools aufrufen. Wenn eine Frage s(i)oul.ai oder die Dokumente des Nutzers
betreffen könnte, suche zuerst mit search_documents, bevor du antwortest.
Stütze dich dann nur auf die gefundenen Abschnitte und nenne die Quelle.
Findet die Suche nichts Passendes, sag ehrlich, dass du dazu keine Informationen hast.
Bittet dich der Nutzer, eine App zu öffnen, nutze open_app.
Für allgemeine Fragen und Smalltalk brauchst du keine Tools.'''


def agent_steps(messages, model=None, think=False, options=None, max_steps=MAX_STEPS):
  messages = [{'role': 'system', 'content': SYSTEM_PROMPT}] + list(messages)
  model = model or AGENT_MODEL

  for step in range(1, max_steps + 1):
    # Im letzten Schritt keine Tools mehr anbieten, dann muss das Modell antworten
    tools = TOOL_SCHEMAS if step < max_steps else None
    content, tool_calls = '', []
    for part in llm.chat(model=model, messages=messages, tools=tools, stream=True, think=think, options=options):
      if part.message.content:
        content += part.message.content
        yield {'type': 'token', 'text': part.message.content}
      if part.message.tool_calls:
        tool_calls += part.message.tool_calls

    # Antwort des Modells (Text und/oder Tool-Calls) in den Verlauf
    messages.append({'role': 'assistant', 'content': content, 'tool_calls': tool_calls})
    if not tool_calls:
      yield {'type': 'done', 'answer': content.strip(), 'steps': step}
      return

    for call in tool_calls:
      name, args = call.function.name, dict(call.function.arguments or {})
      yield {'type': 'tool_call', 'name': name, 'args': args}
      result = run_tool(name, args)
      yield {'type': 'tool_result', 'name': name, 'result': result}
      messages.append({'role': 'tool', 'tool_name': name, 'content': result})


def run_agent(messages, **kwargs):
  # Für Evals und Tests: alle Events sammeln, Antwort + Protokoll zurückgeben
  trace = []
  for event in agent_steps(messages, **kwargs):
    if event['type'] == 'done':
      return event['answer'], trace
    if event['type'] != 'token':
      trace.append(event)


if __name__ == '__main__':
  # Agent im Terminal, zeigt jeden Tool-Aufruf an
  history = []
  while True:
    question = input('\nDu: ').strip()
    if question.lower() in ('exit', 'quit'):
      break
    if not question:
      continue
    history.append({'role': 'user', 'content': question})
    print('s(i)oul: ', end='', flush=True)
    for event in agent_steps(history):
      if event['type'] == 'token':
        print(event['text'], end='', flush=True)
      elif event['type'] == 'tool_call':
        print(f'\n  🔧 {event["name"]}({event["args"]})')
      elif event['type'] == 'tool_result':
        preview = event['result'].replace('\n', ' | ')[:150]
        print(f'  ↳ {preview}\ns(i)oul: ', end='', flush=True)
      elif event['type'] == 'done':
        history.append({'role': 'assistant', 'content': event['answer']})
    print()
