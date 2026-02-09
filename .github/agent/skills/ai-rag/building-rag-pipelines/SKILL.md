---
name: building-rag-pipelines
description: Design and implement production-quality RAG (Retrieval-Augmented Generation) pipelines with hybrid search, reranking, agentic patterns, and continuous learning.
---

# Building RAG Pipelines

## Goal

Create a RAG system that achieves >90% retrieval precision, supports iterative reasoning via tools, learns from usage patterns, and respects user privacy preferences.

## When to Use

- Building an AI assistant that needs to answer questions from a document corpus
- Implementing a knowledge base with natural language query interface
- Adding AI-powered search to an existing application

## Instructions

### Step 1: Design the Storage Tiers

Implement tiered storage to optimize for different access patterns:

```python
# Tier 0: Cold - Raw files on disk (archives, uploads)
# Tier 1: Warm - Chunked text in SQLite with metadata
# Tier 2: Hot - Vector embeddings in ChromaDB
# Tier 3: Cache - LRU in-memory for frequent chunks

class Chunk(db.Model):
    chunk_id = db.Column(db.String(64), primary_key=True)
    content = db.Column(db.Text, nullable=False)
    source_file = db.Column(db.String(500), index=True)
    source_type = db.Column(db.String(50), index=True)  # log, config, etc.
    artifact_category = db.Column(db.String(50), index=True)
    token_count = db.Column(db.Integer)
```

### Step 2: Implement Hybrid Search

Combine dense (vector) and sparse (BM25) retrieval:

```python
def hybrid_search(query: str, top_k: int = 10) -> list[Chunk]:
    # Dense: Semantic similarity via embeddings
    vector_results = collection.query(query_texts=[query], n_results=top_k * 2)
    
    # Sparse: Keyword matching via BM25
    bm25_results = bm25_index.search(query, top_k * 2)
    
    # Score fusion with RRF (Reciprocal Rank Fusion)
    return reciprocal_rank_fusion(vector_results, bm25_results, k=60)
```

### Step 3: Add Cross-Encoder Reranking

Rerank candidates for precision:

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank_chunks(query: str, chunks: list, top_k: int = 10) -> list:
    pairs = [(query, chunk['text']) for chunk in chunks]
    scores = reranker.predict(pairs)
    
    for chunk, score in zip(chunks, scores):
        chunk['cross_encoder_score'] = float(score)
    
    return sorted(chunks, key=lambda x: x['cross_encoder_score'], reverse=True)[:top_k]
```

### Step 4: Implement Query Enhancement

Use LLM to expand queries for better recall:

```python
def rewrite_query(query: str) -> str:
    prompt = f"""Expand this search query with related terms:
    Query: {query}
    
    Add synonyms, related concepts, and domain-specific terminology.
    Return expanded query as space-separated terms."""
    
    return llm.generate(prompt)

def generate_hyde_document(query: str) -> str:
    """Generate hypothetical document that would answer the query."""
    prompt = f"""Generate a document excerpt that would answer: {query}
    
    Write as if you're quoting from the actual source material."""
    
    return llm.generate(prompt)
```

### Step 5: Extract and Index Entities

Enable entity-aware retrieval:

```python
import re

PATTERNS = {
    'ipv4': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    'filepath': re.compile(r'(?:/[\w.-]+)+'),
    'username': re.compile(r'user[=:\s]+(\w+)', re.IGNORECASE),
}

def extract_entities(text: str) -> list[Entity]:
    entities = []
    for entity_type, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            entities.append(Entity(
                entity_type=entity_type,
                value=match.group(),
                context=text[max(0, match.start()-50):match.end()+50]
            ))
    return entities
```

### Step 6: Build Agentic RAG

Let the LLM decide what to search:

```python
AGENT_TOOLS = [
    {"name": "search_chunks", "description": "Search documents"},
    {"name": "search_entity", "description": "Find by IP/user/file"},
    {"name": "traverse_graph", "description": "Explore relationships"},
    {"name": "final_answer", "description": "Provide final response"}
]

def agent_loop(query: str, max_iterations: int = 5):
    history = []
    for i in range(max_iterations):
        response = llm.generate(build_agent_prompt(query, history))
        tool, params = parse_tool_call(response)
        
        if tool == "final_answer":
            return params["answer"]
        
        result = execute_tool(tool, params)
        history.append({"action": tool, "result": result})
```

### Step 7: Add Relevance Feedback

Learn from LLM usage patterns:

```python
def record_usage(chunks: list, response: str, query: str):
    for chunk in chunks:
        # Detect if chunk was cited in response
        if chunk['source_file'] in response.lower():
            chunk_relevance.citation_count += 1
        # Detect content overlap
        elif phrase_overlap(chunk['text'], response) > 0.3:
            chunk_relevance.usage_count += 1
    
    # Update relevance score
    chunk_relevance.score = citations * 1.0 + usages * 0.5
```

## Constraints

### ✅ Do
- **DO**: Use hybrid search (vector + BM25) for robustness
- **DO**: Apply cross-encoder reranking for precision
- **DO**: Extract entities at ingestion time (fast, deterministic)
- **DO**: Stream LLM responses for better UX
- **DO**: Track which chunks are actually used (relevance feedback)
- **DO**: Provide privacy warnings for cloud LLM providers

### ❌ Don't
- **DON'T**: Skip reranking — first-stage retrieval is noisy
- **DON'T**: Use fixed top_k — adapt to query complexity
- **DON'T**: Call LLM during entity extraction — too slow
- **DON'T**: Build entity graphs at query time — do it at ingestion
- **DON'T**: Ignore privacy — mark local vs cloud providers clearly
- **DON'T**: Hardcode chunking — allow overlap and context windows

## Output Format

A complete RAG service should provide:
- `ingest(files)` → Chunk, embed, extract entities, build graph
- `query(text)` → Retrieve, rerank, generate response
- `query_agent(text)` → Iterative search with reasoning
- `get_entities(type)` → List extracted entities
- `get_relevance_stats()` → View learning progress

## Dependencies

- `../backend/scaffolding-flask/SKILL.md` — API structure
- `../database/designing-schemas/SKILL.md` — Model design

## References

| Reference | Description |
|-----------|-------------|
| [chunking-strategies.md](references/chunking-strategies.md) | Document chunking patterns, token budgets, and overlap strategies |
| [embedding-models.md](references/embedding-models.md) | Model comparison, hybrid search, and BM25 integration |
| [agentic-patterns.md](references/agentic-patterns.md) | ReAct agent loops, tool design, and iterative reasoning |
| [graph-rag.md](references/graph-rag.md) | Entity relationship graphs, traversal algorithms, kill chain analysis |
| [relevance-feedback.md](references/relevance-feedback.md) | Learning from usage patterns, citation detection, score boosting |
