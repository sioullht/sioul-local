import os
import ollama
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Einstellungen
EMBEDDING_MODEL = 'nomic-embed-text:latest'
LANGUAGE_MODEL = 'gemma4:12b'
SIMILARITY_THRESHOLD = 0.6
COLLECTION_NAME = 'documents'
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# Verbindungen (über Umgebungsvariablen, damit es später auch im Container klappt)
QDRANT_URL = os.getenv('QDRANT_URL', 'http://localhost:6333')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')

qdrant = QdrantClient(url=QDRANT_URL)
llm = ollama.Client(host=OLLAMA_URL)

def embed(text):
  return llm.embed(model=EMBEDDING_MODEL, input=text)['embeddings'][0]

# Datenbank nur befüllen, wenn sie noch leer ist
def build_database():
  if qdrant.collection_exists(COLLECTION_NAME):
    count = qdrant.count(COLLECTION_NAME).count
    if count > 0:
      print(f'Collection "{COLLECTION_NAME}" already has {count} entries, skipping embedding.')
      return

  # Alle .txt-Dateien aus data/ einlesen, eine Zeile = ein Chunk
  dataset = []
  for filename in sorted(os.listdir(DATA_DIR)):
    if not filename.endswith('.txt'):
      continue
    with open(os.path.join(DATA_DIR, filename), 'r', encoding='utf-8') as file:
      dataset += [(line.strip(), filename) for line in file if line.strip()]
  print(f'Loaded {len(dataset)} entries')

  if not dataset:
    print(f'No .txt files found in {DATA_DIR}, skipping embedding.')
    return

  points = []
  for i, (chunk, source) in enumerate(dataset):
    vector = embed(chunk)
    points.append(PointStruct(id=i, vector=vector, payload={'text': chunk, 'source': source}))
    print(f'Embedded chunk {i+1}/{len(dataset)}')

  # Collection anlegen, Vektorgröße direkt aus dem ersten Embedding
  if not qdrant.collection_exists(COLLECTION_NAME):
    qdrant.create_collection(
      collection_name=COLLECTION_NAME,
      vectors_config=VectorParams(size=len(points[0].vector), distance=Distance.COSINE),
    )

  qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
  print(f'Stored {len(points)} chunks in Qdrant')

def retrieve(query, top_n=3):
  result = qdrant.query_points(
    collection_name=COLLECTION_NAME,
    query=embed(query),
    limit=top_n,
    score_threshold=SIMILARITY_THRESHOLD,
  )
  return [(point.payload['text'], point.score, point.payload.get('source')) for point in result.points]

if __name__ == "__main__":
  build_database()

  # Chatbot
  while True:
    input_query = input('Ask me a question: ')
    if input_query.strip().lower() in ['exit', 'quit']:
      print('Goodbye!')
      break
    if not input_query:
      print("Please enter a question or leave with 'exit' or 'quit'.")
      continue
    retrieved_knowledge = retrieve(input_query)

    if not retrieved_knowledge:
      print("Dazu habe ich leider keine Informationen.")
    else:
      print('Retrieved knowledge:')
      for chunk, similarity, source in retrieved_knowledge:
        print(f' - (similarity: {similarity:.2f}, {source}) {chunk}')

      context = '\n'.join(f' - {chunk}' for chunk, _, _ in retrieved_knowledge)
      instruction_prompt = f'''You are a helpful chatbot.
  Use only the following pieces of context to answer the question. Don't make up any new information:
  {context}
  '''

      stream = llm.chat(
        model=LANGUAGE_MODEL,
        messages=[
          {'role': 'system', 'content': instruction_prompt},
          {'role': 'user', 'content': input_query},
        ],
        stream=True,
        think=False,
      )

      print('Chatbot response:')
      for chunk in stream:
        print(chunk['message']['content'], end='', flush=True)
      print()