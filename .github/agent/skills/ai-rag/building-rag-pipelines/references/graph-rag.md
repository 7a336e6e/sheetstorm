# Graph RAG and Entity Relationships

## Overview

Graph RAG builds a knowledge graph from extracted entities, enabling relationship-aware retrieval. Instead of just finding "documents about X", you can ask "how is X connected to Y" or "what did entity X affect".

## Entity Extraction

Extract entities at ingestion time (not query time):

```python
import re

ENTITY_PATTERNS = {
    'ipv4': re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'),
    'ipv6': re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'),
    'domain': re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+(?:com|net|org|edu|gov|io)\b'),
    'filepath': re.compile(r'(?:/[\w.-]+)+'),
    'username': re.compile(r'(?:user(?:name)?[=:\s]+)(\w+)', re.IGNORECASE),
    'command': re.compile(r'(?:^|\$\s*)((?:sudo\s+)?(?:wget|curl|ssh|chmod|rm|cat|grep|awk|sed|python|bash|sh)(?:\s+[^\n;|&]{1,100})?)', re.MULTILINE),
}

class Entity:
    def __init__(self, entity_type: str, value: str, chunk_id: str, context: str):
        self.entity_type = entity_type
        self.value = value
        self.normalized_value = value.lower()
        self.chunk_id = chunk_id
        self.context_snippet = context[:200]

def extract_entities(text: str, chunk_id: str) -> list[Entity]:
    entities = []
    for entity_type, pattern in ENTITY_PATTERNS.items():
        for match in pattern.finditer(text):
            # Get surrounding context
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            
            entities.append(Entity(
                entity_type=entity_type,
                value=match.group(),
                chunk_id=chunk_id,
                context=context
            ))
    return entities
```

## Relationship Inference

Infer relationships from entity co-occurrence in chunks:

```python
# (source_type, target_type) → relationship_type
RELATIONSHIP_RULES = {
    ("username", "command"): "executed",
    ("username", "ipv4"): "connected_from",
    ("username", "filepath"): "accessed",
    ("ipv4", "username"): "authenticated_as",
    ("ipv4", "port"): "connected_on",
    ("command", "filepath"): "accessed",
    ("command", "ipv4"): "contacted",
    ("command", "domain"): "contacted",
    ("filepath", "command"): "executed",
}

REVERSE_RELATIONSHIPS = {
    "executed": "executed_by",
    "connected_from": "connected_to",
    "accessed": "accessed_by",
    "authenticated_as": "authenticated",
    "contacted": "contacted_by",
}

def infer_relationship(source_type: str, target_type: str) -> str:
    key = (source_type, target_type)
    if key in RELATIONSHIP_RULES:
        return RELATIONSHIP_RULES[key]
    
    # Try reverse
    reverse_key = (target_type, source_type)
    if reverse_key in RELATIONSHIP_RULES:
        return REVERSE_RELATIONSHIPS.get(RELATIONSHIP_RULES[reverse_key], "related_to")
    
    return "co_occurs_with"
```

## Building the Graph

Create relationships from co-occurring entities:

```python
class EntityRelationship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, index=True)
    source_entity_id = db.Column(db.Integer, db.ForeignKey('entities.id'))
    target_entity_id = db.Column(db.Integer, db.ForeignKey('entities.id'))
    relationship_type = db.Column(db.String(50), index=True)
    confidence = db.Column(db.Float, default=1.0)
    evidence_chunk_id = db.Column(db.String(64))
    evidence_snippet = db.Column(db.String(300))

def build_relationships_for_chunk(chunk_id: str, session_id: int) -> list:
    entities = Entity.query.filter_by(chunk_id=chunk_id).all()
    if len(entities) < 2:
        return []
    
    relationships = []
    seen = set()
    
    for i, source in enumerate(entities):
        for target in entities[i+1:]:
            # Skip duplicates
            pair = (min(source.id, target.id), max(source.id, target.id))
            if pair in seen:
                continue
            seen.add(pair)
            
            rel_type = infer_relationship(source.entity_type, target.entity_type)
            
            relationships.append(EntityRelationship(
                session_id=session_id,
                source_entity_id=source.id,
                target_entity_id=target.id,
                relationship_type=rel_type,
                evidence_chunk_id=chunk_id
            ))
    
    return relationships
```

## Graph Traversal

### BFS Neighbor Discovery

```python
from collections import defaultdict

def get_entity_neighbors(session_id: str, entity_value: str, max_depth: int = 1) -> dict:
    # Build in-memory graph (cached per session)
    graph = build_graph_for_session(session_id)
    
    # Find starting entity
    start_id = find_entity_by_value(graph, entity_value)
    if not start_id:
        return {"error": "Entity not found"}
    
    visited = {start_id}
    current_level = {start_id}
    neighbors = []
    
    for depth in range(max_depth):
        next_level = set()
        
        for entity_id in current_level:
            # Forward edges
            for edge in graph["edges"].get(entity_id, []):
                target_id = edge["target_id"]
                if target_id not in visited:
                    visited.add(target_id)
                    next_level.add(target_id)
                    neighbors.append({
                        "entity_id": target_id,
                        "entity_value": graph["nodes"][target_id]["value"],
                        "relationship": edge["relationship_type"],
                        "depth": depth + 1,
                        "direction": "outgoing"
                    })
            
            # Reverse edges (for bidirectional traversal)
            for edge in graph["reverse_edges"].get(entity_id, []):
                target_id = edge["target_id"]
                if target_id not in visited:
                    visited.add(target_id)
                    next_level.add(target_id)
                    neighbors.append({
                        "entity_id": target_id,
                        "entity_value": graph["nodes"][target_id]["value"],
                        "relationship": edge["relationship_type"],
                        "depth": depth + 1,
                        "direction": "incoming"
                    })
        
        current_level = next_level
    
    return {
        "start_entity": entity_value,
        "total_neighbors": len(neighbors),
        "neighbors": neighbors
    }
```

### Path Finding (BFS)

```python
from collections import deque

def find_path(session_id: str, source_value: str, target_value: str) -> dict:
    graph = build_graph_for_session(session_id)
    
    source_id = find_entity_by_value(graph, source_value)
    target_id = find_entity_by_value(graph, target_value)
    
    if not source_id or not target_id:
        return {"error": "Entity not found"}
    
    queue = deque([(source_id, [source_id], [])])
    visited = {source_id}
    
    while queue:
        current, path, relationships = queue.popleft()
        
        if len(path) > 5:  # Max path length
            continue
        
        for edge in graph["edges"].get(current, []) + graph["reverse_edges"].get(current, []):
            next_id = edge["target_id"]
            
            if next_id == target_id:
                # Found!
                final_path = path + [next_id]
                return format_path(graph, final_path, relationships + [edge])
            
            if next_id not in visited:
                visited.add(next_id)
                queue.append((next_id, path + [next_id], relationships + [edge]))
    
    return {"error": "No path found"}

def format_path(graph: dict, path: list[int], relationships: list) -> dict:
    readable = " → ".join([graph["nodes"][id]["value"] for id in path])
    return {
        "found": True,
        "path_length": len(path),
        "readable_path": readable,
        "path": [{"entity_id": id, "value": graph["nodes"][id]["value"]} for id in path],
        "relationships": relationships
    }
```

## Kill Chain Analysis

Classify entities into attack stages:

```python
def get_kill_chain(session_id: str) -> dict:
    graph = build_graph_for_session(session_id)
    
    kill_chain = {
        "initial_access": [],    # External IPs with auth
        "execution": [],         # Commands, scripts
        "persistence": [],       # Cron, systemd
        "privilege_escalation": [],  # sudo, passwd
        "data_access": [],       # Sensitive files
        "exfiltration": []       # Outbound connections
    }
    
    for entity_id, info in graph["nodes"].items():
        entity_type = info["type"]
        value = info["value"].lower()
        
        if entity_type in ("ipv4", "ipv6"):
            # Check if IP authenticated
            relationships = graph["edges"].get(entity_id, [])
            if any(r["relationship_type"] == "authenticated_as" for r in relationships):
                kill_chain["initial_access"].append(info)
        
        elif entity_type == "command":
            if any(x in value for x in ["wget", "curl", "nc", "python"]):
                kill_chain["execution"].append(info)
            if any(x in value for x in ["crontab", "systemctl"]):
                kill_chain["persistence"].append(info)
            if any(x in value for x in ["sudo", "passwd", "su "]):
                kill_chain["privilege_escalation"].append(info)
        
        elif entity_type == "filepath":
            if any(x in value for x in ["/etc/passwd", "/etc/shadow", ".ssh"]):
                kill_chain["data_access"].append(info)
    
    return {
        "stages_detected": sum(1 for v in kill_chain.values() if v),
        "kill_chain": {k: v for k, v in kill_chain.items() if v},
        "summary": " → ".join([f"{k.replace('_', ' ').title()}" 
                               for k, v in kill_chain.items() if v])
    }
```

## Performance Optimization

### Graph Caching

```python
class GraphRAGService:
    def __init__(self):
        self._graph_cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 300  # 5 minutes
    
    def build_graph_for_session(self, session_id: str) -> dict:
        # Check cache
        if session_id in self._graph_cache:
            if (datetime.now() - self._cache_timestamps[session_id]).seconds < self._cache_ttl:
                return self._graph_cache[session_id]
        
        # Build graph
        graph = self._build_graph_from_db(session_id)
        
        # Cache it
        self._graph_cache[session_id] = graph
        self._cache_timestamps[session_id] = datetime.now()
        
        return graph
```

### Efficient Indices

```python
# Add these indices to the EntityRelationship model
__table_args__ = (
    db.Index("idx_rel_session_source", "session_id", "source_entity_id"),
    db.Index("idx_rel_session_target", "session_id", "target_entity_id"),
    db.Index("idx_rel_type_source", "relationship_type", "source_entity_id"),
)
```

## Integration with Agentic RAG

Expose graph operations as agent tools:

```python
AGENT_TOOLS.extend([
    {
        "name": "traverse_graph",
        "description": "Explore relationships from an entity",
        "parameters": {
            "entity_value": "Starting entity",
            "depth": "Hops to traverse (1-3)"
        }
    },
    {
        "name": "find_path",
        "description": "Find connection between two entities",
        "parameters": {
            "source_entity": "Starting entity",
            "target_entity": "Target entity"
        }
    },
    {
        "name": "get_kill_chain",
        "description": "Analyze attack stages from entity graph",
        "parameters": {}
    }
])
```

The agent can now:
1. Discover entities via `list_entities`
2. Explore relationships via `traverse_graph`
3. Find connections via `find_path`
4. Summarize attacks via `get_kill_chain`
