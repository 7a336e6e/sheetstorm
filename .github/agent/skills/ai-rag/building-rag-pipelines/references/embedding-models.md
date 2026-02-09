# Embedding Models for RAG

## Overview

Embedding models convert text into dense vectors for semantic similarity search. Model choice significantly impacts retrieval quality and performance.

## Model Categories

### 1. Sentence Transformers (Open Source)

Best for local deployment and privacy:

```python
from sentence_transformers import SentenceTransformer

# Good general purpose
model = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dims, fast
model = SentenceTransformer('all-mpnet-base-v2')  # 768 dims, accurate

# For asymmetric search (short query → long document)
model = SentenceTransformer('multi-qa-mpnet-base-dot-v1')

embeddings = model.encode(texts, show_progress_bar=True)
```

### 2. OpenAI Embeddings (API)

Best accuracy, requires API key:

```python
from openai import OpenAI

client = OpenAI()

response = client.embeddings.create(
    model="text-embedding-3-small",  # 1536 dims, cheap
    # model="text-embedding-3-large",  # 3072 dims, accurate
    input=texts
)

embeddings = [r.embedding for r in response.data]
```

### 3. Ollama Local Embeddings

For fully local deployments:

```python
import requests

def embed_ollama(texts: list[str], model: str = "nomic-embed-text"):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": model, "prompt": texts}
    )
    return response.json()["embedding"]
```

### 4. ChromaDB Built-in

Simplest option with ChromaDB:

```python
import chromadb

# Uses 'all-MiniLM-L6-v2' by default
client = chromadb.PersistentClient(path="./chroma")
collection = client.get_or_create_collection("chunks")

# Embedding happens automatically
collection.add(
    ids=["chunk1", "chunk2"],
    documents=["text 1", "text 2"]
)
```

## Model Comparison

| Model | Dimensions | Speed | Quality | Privacy | Cost |
|-------|------------|-------|---------|---------|------|
| all-MiniLM-L6-v2 | 384 | ⚡⚡⚡ | ★★★ | ✅ Local | Free |
| all-mpnet-base-v2 | 768 | ⚡⚡ | ★★★★ | ✅ Local | Free |
| text-embedding-3-small | 1536 | ⚡⚡ | ★★★★ | ❌ Cloud | $0.02/1M |
| text-embedding-3-large | 3072 | ⚡ | ★★★★★ | ❌ Cloud | $0.13/1M |
| nomic-embed-text | 768 | ⚡⚡ | ★★★★ | ✅ Local | Free |

## Best Practices

### Batch Processing

Always embed in batches for performance:

```python
BATCH_SIZE = 250  # ChromaDB handles this well

for i in range(0, len(texts), BATCH_SIZE):
    batch = texts[i:i + BATCH_SIZE]
    embeddings = model.encode(batch)
    collection.upsert(
        ids=[f"chunk_{i+j}" for j in range(len(batch))],
        embeddings=embeddings.tolist(),
        documents=batch
    )
```

### Caching

Cache embeddings to avoid recomputation:

```python
import hashlib
import json

def get_or_create_embedding(text: str, cache: dict) -> list[float]:
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    
    if text_hash in cache:
        return cache[text_hash]
    
    embedding = model.encode(text).tolist()
    cache[text_hash] = embedding
    return embedding
```

### Query vs Document Embeddings

Some models need different prefixes:

```python
# For asymmetric models, prefix queries differently
def embed_query(query: str) -> list[float]:
    return model.encode(f"query: {query}")

def embed_document(doc: str) -> list[float]:
    return model.encode(f"passage: {doc}")
```

## Cross-Encoder Reranking

First-stage retrieval is fast but noisy. Rerank for precision:

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank(query: str, chunks: list[dict], top_k: int = 10) -> list[dict]:
    pairs = [(query, c['text']) for c in chunks]
    scores = reranker.predict(pairs)
    
    for chunk, score in zip(chunks, scores):
        chunk['cross_encoder_score'] = float(score)
    
    return sorted(chunks, key=lambda x: x['cross_encoder_score'], reverse=True)[:top_k]
```

## Hybrid Search

Combine dense (vector) and sparse (BM25) for robustness:

```python
def hybrid_search(query: str, top_k: int = 10) -> list[dict]:
    # Dense: Semantic similarity
    vector_results = collection.query(query_texts=[query], n_results=top_k * 3)
    
    # Sparse: BM25 keyword matching  
    bm25_results = bm25.search(query, top_k * 3)
    
    # Fuse with Reciprocal Rank Fusion
    return reciprocal_rank_fusion(vector_results, bm25_results, k=60)

def reciprocal_rank_fusion(results_list: list, k: int = 60) -> list:
    scores = {}
    for results in results_list:
        for rank, doc in enumerate(results):
            doc_id = doc['id']
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

## Privacy Considerations

Mark embedding providers clearly:

```python
EMBEDDING_PROVIDERS = {
    "local-minilm": {
        "model": "all-MiniLM-L6-v2",
        "privacy_level": "local",
        "privacy_note": "Embeddings computed locally, no data sent"
    },
    "openai": {
        "model": "text-embedding-3-small", 
        "privacy_level": "cloud",
        "privacy_warning": "Text sent to OpenAI API for embedding"
    }
}
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Low recall | Model too small | Try mpnet or OpenAI |
| Slow queries | No batch processing | Embed in batches of 100-500 |
| OOM errors | Model too large | Use smaller model or GPU |
| Bad semantic match | Wrong model type | Use asymmetric model for Q&A |
