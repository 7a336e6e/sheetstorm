# Relevance Feedback and Learning

## Overview

Relevance feedback is a technique for improving retrieval quality over time by learning which chunks are actually useful. Instead of treating all retrieved chunks equally, the system tracks which ones get cited or used in LLM responses and boosts them in future queries.

## Types of Feedback

### 1. Implicit Feedback (Automatic)

Inferred from LLM behavior without user action:

- **Citation Detection**: LLM mentions a file name in response
- **Content Usage**: Chunk content appears in response (phrase overlap)
- **Retrieval Without Use**: Chunk retrieved but not referenced

### 2. Explicit Feedback (User Action)

Requires user interaction:

- **Response Rating**: Thumbs up/down on answers
- **Chunk Marking**: User marks chunks as relevant/irrelevant
- **Query Correction**: User rephrases after bad results

## Implementation

### Data Model

```python
class ChunkRelevance(db.Model):
    """Track relevance metrics for each chunk."""
    id = db.Column(db.Integer, primary_key=True)
    chunk_id = db.Column(db.String(64), unique=True, index=True)
    session_id = db.Column(db.Integer, index=True)
    
    # Metrics
    citation_count = db.Column(db.Integer, default=0)   # Explicitly cited
    usage_count = db.Column(db.Integer, default=0)      # Content used
    retrieval_count = db.Column(db.Integer, default=0)  # Retrieved but unused
    
    # Computed score
    relevance_score = db.Column(db.Float, default=0.0, index=True)
    
    # Topic associations
    useful_for_topics = db.Column(db.Text)  # JSON array
    
    def update_score(self):
        """Recalculate score from metrics."""
        raw_score = (
            self.citation_count * 1.0 +
            self.usage_count * 0.5 +
            self.retrieval_count * 0.1
        )
        # Normalize to 0-1 with sigmoid
        import math
        self.relevance_score = 1 - (1 / (1 + raw_score))
```

### Citation Detection

Find when LLM explicitly references a source:

```python
import re

def detect_citation(source_file: str, response_text: str) -> bool:
    """Check if source file was cited in response."""
    response_lower = response_text.lower()
    
    # Get filename
    filename = source_file.split("/")[-1].lower()
    
    # Direct mention
    if filename in response_lower:
        return True
    
    # Citation patterns
    name_parts = filename.replace(".", " ").replace("-", " ").split()
    for part in name_parts:
        if len(part) > 3 and part in response_lower:
            patterns = [
                rf"in\s+.*?{re.escape(part)}",
                rf"from\s+.*?{re.escape(part)}",
                rf"according\s+to\s+.*?{re.escape(part)}",
                rf"{re.escape(part)}\s+shows",
                rf"{re.escape(part)}\s+contains",
            ]
            if any(re.search(p, response_lower) for p in patterns):
                return True
    
    return False
```

### Content Usage Detection

Detect when chunk content appears in response:

```python
def detect_content_usage(chunk_content: str, response_text: str) -> bool:
    """Check if chunk content was used via n-gram overlap."""
    OVERLAP_THRESHOLD = 0.3
    
    chunk_phrases = extract_phrases(chunk_content)
    if not chunk_phrases:
        return False
    
    response_lower = response_text.lower()
    matches = sum(1 for phrase in chunk_phrases if phrase in response_lower)
    overlap_ratio = matches / len(chunk_phrases)
    
    return overlap_ratio >= OVERLAP_THRESHOLD

def extract_phrases(text: str, min_words: int = 3, max_words: int = 5) -> set:
    """Extract significant multi-word phrases."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    phrases = set()
    
    for n in range(min_words, min(max_words + 1, len(words) + 1)):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            if not is_common_phrase(phrase):
                phrases.add(phrase)
    
    return set(list(phrases)[:20])  # Limit for performance
```

### Recording Feedback

After each query response:

```python
def record_usage(session_id: str, retrieved_chunks: list, 
                 response_text: str, query_text: str) -> dict:
    """Analyze response and update relevance scores."""
    stats = {"cited": 0, "used": 0, "unused": 0}
    query_keywords = extract_keywords(query_text)
    
    for chunk in retrieved_chunks:
        chunk_id = chunk["chunk_id"]
        
        # Get or create relevance record
        relevance = ChunkRelevance.query.filter_by(chunk_id=chunk_id).first()
        if not relevance:
            relevance = ChunkRelevance(chunk_id=chunk_id, session_id=session.id)
            db.session.add(relevance)
        
        # Check for citation
        is_cited = detect_citation(chunk["source_file"], response_text)
        
        # Check for content usage
        is_used = detect_content_usage(chunk["content"], response_text)
        
        if is_cited:
            relevance.citation_count += 1
            stats["cited"] += 1
        elif is_used:
            relevance.usage_count += 1
            stats["used"] += 1
        else:
            stats["unused"] += 1
        
        # Track topics this chunk is useful for
        if is_cited or is_used:
            update_topics(relevance, query_keywords)
        
        relevance.update_score()
    
    db.session.commit()
    return stats
```

### Applying Boost

During retrieval, boost chunks with high relevance:

```python
def apply_relevance_boost(chunks: list, session_id: str, 
                          boost_weight: float = 0.2) -> list:
    """Re-rank chunks with learned relevance boost."""
    
    # Get relevance scores
    chunk_ids = [c["chunk_id"] for c in chunks]
    relevances = ChunkRelevance.query.filter(
        ChunkRelevance.chunk_id.in_(chunk_ids)
    ).all()
    boosts = {r.chunk_id: r.relevance_score for r in relevances}
    
    # Apply boost
    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        if chunk_id in boosts:
            original = chunk["relevance_score"]
            boost = boosts[chunk_id]
            
            # Weighted combination
            chunk["relevance_score"] = (
                original * (1 - boost_weight) +
                (original + boost * 0.3) * boost_weight
            )
            chunk["relevance_boosted"] = True
    
    # Re-sort
    chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
    return chunks
```

## Integration Points

### In Query Pipeline

```python
def query_stream(session_id: str, query: str):
    # ... retrieval ...
    
    # Apply relevance boost before final ranking
    final_chunks = apply_relevance_boost(final_chunks, session_id)
    
    # ... LLM generation ...
    
    # Record which chunks were used
    record_usage(session_id, top_chunks, response_text, query)
```

### API Endpoint

```python
@app.route("/api/analyze/relevance/stats")
def get_relevance_stats():
    session_id = request.args.get("session_id")
    
    relevances = ChunkRelevance.query.filter_by(session_id=session.id).all()
    
    return jsonify({
        "total_tracked": len(relevances),
        "total_citations": sum(r.citation_count for r in relevances),
        "avg_relevance": sum(r.relevance_score for r in relevances) / len(relevances),
        "top_chunks": [
            {
                "source_file": get_chunk(r.chunk_id).source_file,
                "relevance_score": r.relevance_score,
                "citation_count": r.citation_count
            }
            for r in sorted(relevances, key=lambda x: x.relevance_score, reverse=True)[:10]
        ]
    })
```

## Topic Association

Track which topics each chunk is useful for:

```python
def update_topics(relevance: ChunkRelevance, keywords: set):
    """Associate chunk with query topics it helped with."""
    existing = set(json.loads(relevance.useful_for_topics or "[]"))
    updated = existing | keywords
    
    # Keep most recent 50 topics
    if len(updated) > 50:
        updated = set(list(updated)[-50:])
    
    relevance.useful_for_topics = json.dumps(list(updated))
```

This enables future enhancements:
- Topic-aware boost (if query matches topics, boost more)
- User preference learning
- Personalized retrieval

## Scoring Formula

```
relevance_score = normalize(
    citation_count * 1.0 +   # Strong signal
    usage_count * 0.5 +      # Medium signal  
    retrieval_count * 0.1    # Weak signal (retrieved but not used)
)
```

The sigmoid normalization keeps scores in 0-1 range:
```python
def normalize(score):
    return 1 - (1 / (1 + score))
```

Example:
- 0 interactions → score = 0.0
- 1 citation → score = 0.5
- 2 citations → score = 0.67
- 5 citations + 3 usages → score = 0.87

## Best Practices

### ✅ Do
- **DO**: Record feedback after every query (incremental learning)
- **DO**: Use async/background for feedback recording (don't block response)
- **DO**: Cap topic associations (prevent unbounded growth)
- **DO**: Provide feedback stats API for debugging
- **DO**: Weight citations higher than usage (more explicit signal)

### ❌ Don't
- **DON'T**: Boost too aggressively (new chunks need chance to prove useful)
- **DON'T**: Ignore retrieved-but-unused (weak negative signal)
- **DON'T**: Forget to normalize scores (keep in 0-1 range)
- **DON'T**: Update scores synchronously (adds latency)
