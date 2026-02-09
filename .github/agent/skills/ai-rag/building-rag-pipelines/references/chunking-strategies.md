# Chunking Strategies for RAG

## Overview

Chunking is the process of splitting documents into smaller pieces for embedding and retrieval. The right strategy depends on document type, query patterns, and performance requirements.

## Core Strategies

### 1. Fixed-Size Chunking

Split by character/token count with overlap.

```python
def chunk_fixed_size(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks
```

**When to use:**
- Generic documents
- When speed is critical
- As a fallback strategy

**Tradeoffs:**
- Fast and predictable
- May split mid-sentence
- Works well with 200-500 token chunks

### 2. Semantic Chunking

Split by natural boundaries (paragraphs, sections).

```python
def chunk_semantic(text: str) -> list[str]:
    # Split on double newlines (paragraphs)
    paragraphs = text.split('\n\n')
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para_size = len(para)
        if current_size + para_size > MAX_CHUNK_SIZE and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = []
            current_size = 0
        current_chunk.append(para)
        current_size += para_size
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks
```

**When to use:**
- Structured documents (markdown, HTML)
- When semantic coherence matters
- For domain-specific content

### 3. Document-Type Specific Chunking

Different strategies for different file types:

```python
def chunk_by_type(content: str, source_type: str) -> list[str]:
    if source_type == 'log':
        # Group log entries by time window
        return chunk_log_entries(content, window_seconds=60)
    elif source_type == 'config':
        # Keep config sections together
        return chunk_config_sections(content)
    elif source_type == 'code':
        # Chunk by function/class
        return chunk_code_blocks(content)
    else:
        return chunk_fixed_size(content)
```

### 4. Log-Specific Chunking

For log files, preserve temporal context:

```python
def chunk_log_entries(content: str, max_lines: int = 50) -> list[str]:
    lines = content.split('\n')
    chunks = []
    current = []
    
    for line in lines:
        current.append(line)
        if len(current) >= max_lines:
            # Look for natural break (timestamp change, empty line)
            if is_log_boundary(line):
                chunks.append('\n'.join(current))
                current = []
    
    if current:
        chunks.append('\n'.join(current))
    return chunks
```

## Context Windows

Include surrounding chunks for better understanding:

```python
def get_context_window(chunk_id: str, window_size: int = 1) -> list[dict]:
    """Get chunk with N chunks before and after from same source."""
    center_chunk = get_chunk(chunk_id)
    source_file = center_chunk.source_file
    
    # Get all chunks from same file, ordered
    file_chunks = Chunk.query.filter_by(source_file=source_file).order_by(Chunk.id).all()
    
    # Find center position
    center_idx = next(i for i, c in enumerate(file_chunks) if c.chunk_id == chunk_id)
    
    # Get window
    start = max(0, center_idx - window_size)
    end = min(len(file_chunks), center_idx + window_size + 1)
    
    return [{"content": c.content, "is_center": c.chunk_id == chunk_id} 
            for c in file_chunks[start:end]]
```

## Optimal Chunk Sizes

| Document Type | Recommended Size | Overlap |
|--------------|------------------|---------|
| Generic text | 500-1000 tokens | 20% |
| Log files | 30-50 lines | 5 lines |
| Config files | By section | None |
| Code | By function | Context only |
| Markdown | By heading | None |

## Performance Tips

1. **Precompute token counts** - Cache during chunking, not query time
2. **Use hash-based chunk IDs** - Include session_id for uniqueness
3. **Batch database inserts** - Flush every 1000 chunks
4. **Skip duplicate content** - Check content_hash before inserting

```python
chunk_id = hashlib.sha256(f"{session_id}:{source_file}:{chunk_index}".encode()).hexdigest()[:16]
content_hash = hashlib.sha256(content.encode()).hexdigest()
```

## Anti-Patterns

❌ **Too small chunks** (< 100 tokens) - Lose context
❌ **Too large chunks** (> 2000 tokens) - Dilute relevance
❌ **No overlap** - Miss cross-boundary content
❌ **Ignoring structure** - Split configs mid-block
❌ **Same strategy everywhere** - Logs ≠ configs ≠ code
