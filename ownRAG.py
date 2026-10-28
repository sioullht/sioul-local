import atexit
import os

import ollama
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# Einstellungen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
EMBEDDING_MODEL = 'nomic-embed-text:latest'
SIMILARITY_THRESHOLD = 0.6
COLLECTION_NAME = 'documents'

# Modelle in der Auswahl und das Basismodell, auf dem sie jeweils aufbauen
MODELS = {
  'sioul': 'gemma4:12b',
  'sioul-mini': 'qwen3.5:4b',
}
LANGUAGE_MODEL = MODELS['sioul']   # Standard, wenn kein Modell gewählt ist

NO_INFO = 'Dazu habe ich leider keine Informationen.'

# Verbindungen (über Umgebungsvariablen, damit es später auch im Container klappt)
QDRANT_URL = os.getenv('QDRANT_URL', 'http://localhost:6333')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
# Ist QDRANT_PATH gesetzt, läuft Qdrant ohne Docker direkt in Python und speichert
# in diesem Ordner (für die Desktop-App). Dann darf nur ein Programm gleichzeitig zugreifen.
QDRANT_PATH = os.getenv('QDRANT_PATH')

qdrant = QdrantClient(path=QDRANT_PATH) if QDRANT_PATH else QdrantClient(url=QDRANT_URL)
if QDRANT_PATH:
  atexit.register(qdrant.close)   # Ordner beim Beenden sauber freigeben
llm = ollama.Client(host=OLLAMA_URL)

def embed(text):
  return llm.embed(model=EMBEDDING_MODEL, input=text)['embeddings'][0]

# Datenbank nur befüllen, wenn sie noch leer ist
def build_database():
  if qdrant.collection_exists(COLLECTION_NAME):
    count = qdrant.count(COLLECTION_NAME).count
    if count > 0:
      print(f'Collection "{COLLECTION_NAME}" hat schon {count} Einträge, Einbetten wird übersprungen.')
      return

  # Alle .txt-Dateien aus data/ einlesen, eine Zeile = ein Chunk
  dataset = []
  for filename in sorted(os.listdir(DATA_DIR)):
    if not filename.endswith('.txt'):
      continue
    with open(os.path.join(DATA_DIR, filename), 'r', encoding='utf-8') as file:
      dataset += [(line.strip(), filename) for line in file if line.strip()]
  print(f'{len(dataset)} Einträge geladen')

  if not dataset:
    print(f'Keine .txt-Dateien in {DATA_DIR} gefunden, Einbetten wird übersprungen.')
    return

  points = []
  for i, (chunk, source) in enumerate(dataset):
    vector = embed(chunk)
    points.append(PointStruct(id=i, vector=vector, payload={'text': chunk, 'source': source}))
    print(f'Chunk {i+1}/{len(dataset)} eingebettet')

  # Collection anlegen, Vektorgröße direkt aus dem ersten Embedding
  if not qdrant.collection_exists(COLLECTION_NAME):
    qdrant.create_collection(
      collection_name=COLLECTION_NAME,
      vectors_config=VectorParams(size=len(points[0].vector), distance=Distance.COSINE),
    )

  qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
  print(f'{len(points)} Chunks in Qdrant gespeichert')

def retrieve(query, top_n=3):
  result = qdrant.query_points(
    collection_name=COLLECTION_NAME,
    query=embed(query),
    limit=top_n,
    score_threshold=SIMILARITY_THRESHOLD,
  )
  return [(point.payload['text'], point.score, point.payload.get('source')) for point in result.points]

# System-Prompt für den RAG-Modus aus den gefundenen Abschnitten
def system_prompt(hits):
  context = '\n'.join(f' - {chunk}' for chunk, _, _ in hits)
  return f'''You are a helpful chatbot.
Use only the following pieces of context to answer the question. Don't make up any new information:
{context}
'''

if __name__ == "__main__":
  build_database()

  # Chatbot im Terminal
  while True:
    input_query = input('Deine Frage: ')
    if input_query.strip().lower() in ['exit', 'quit']:
      print('Tschüss!')
      break
    if not input_query:
      print("Bitte gib eine Frage ein oder beende mit 'exit' oder 'quit'.")
      continue
    retrieved_knowledge = retrieve(input_query)

    if not retrieved_knowledge:
      print(NO_INFO)
    else:
      print('Gefundene Abschnitte:')
      for chunk, similarity, source in retrieved_knowledge:
        print(f' - (Ähnlichkeit: {similarity:.2f}, {source}) {chunk}')

      stream = llm.chat(
        model=LANGUAGE_MODEL,
        messages=[
          {'role': 'system', 'content': system_prompt(retrieved_knowledge)},
          {'role': 'user', 'content': input_query},
        ],
        stream=True,
        think=False,
      )

      print('Antwort:')
      for chunk in stream:
        print(chunk['message']['content'], end='', flush=True)
      print()
