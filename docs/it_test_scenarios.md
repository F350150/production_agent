# Integration Testing (IT) Scenarios

This document provides comprehensive integration test scenarios for the enhanced MCP and Skill functionality.

---

## Table of Contents
1. [MCP HTTP/FastMCP Integration Tests](#1-mcp-httpfastmcp-integration-tests)
2. [MCP YAML Configuration Tests](#2-mcp-yaml-configuration-tests)
3. [Skill Execution Tests](#3-skill-execution-tests)
4. [Enhanced RAG Tests](#4-enhanced-rag-tests)
5. [End-to-End Workflow Tests](#5-end-to-end-workflow-tests)

---

## 1. MCP HTTP/FastMCP Integration Tests

### Test Scenario 1.1: HTTP MCP Client Connection

**Objective**: Verify HttpMCPClient can connect to a FastMCP server

**Prerequisites**:
- FastMCP server running on `http://localhost:8000/mcp`
- Server exposes at least one tool

**Steps**:
```bash
# Start a mock FastMCP server (example using FastMCP)
# npx fastmcp dev examples/server.py --port 8000

# Or use the built-in test server
cd tests/fixtures
python mock_fastmcp_server.py
```

**Expected Results**:
- [ ] Client successfully sends `initialize` handshake
- [ ] Client receives and parses capabilities
- [ ] `notifications/initialized` is sent
- [ ] `list_tools()` returns correct tool list
- [ ] `call_tool()` executes remote tool and returns result

**Test Code**:
```python
from tools.mcp_client import HttpMCPClient

client = HttpMCPClient(name="test", url="http://localhost:8000/mcp")
tools = client.list_tools()
assert len(tools) > 0

result = client.call_tool("echo", {"message": "hello"})
assert "hello" in result
```

---

### Test Scenario 1.2: Multiple Transport Types

**Objective**: Verify mixed MCP transport configuration works

**Prerequisites**:
- Stdio MCP server (filesystem)
- HTTP MCP server running

**Steps**:
```yaml
# config/mcp_servers.yaml
mcp_servers:
  - name: filesystem
    transport: stdio
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "./"]

  - name: api_server
    transport: http
    url: http://localhost:8000/mcp
```

**Expected Results**:
- [ ] Both servers connect successfully
- [ ] All tools available with correct namespace prefix
- [ ] `mcp__filesystem__read_file` works
- [ ] `mcp__api_server__some_tool` works

---

### Test Scenario 1.3: HTTP Transport Error Handling

**Objective**: Verify graceful handling of connection failures

**Steps**:
1. Configure HTTP client pointing to non-existent server
2. Call `list_tools()`

**Expected Results**:
- [ ] Returns error message (not exception)
- [ ] Connection timeout after configured `timeout` value
- [ ] Error message includes server name

---

## 2. MCP YAML Configuration Tests

### Test Scenario 2.1: YAML Config Loading

**Objective**: Verify MCP servers load from YAML config

**Prerequisites**:
- `config/mcp_servers.yaml` exists with valid configuration

**Steps**:
```bash
# Unset MCP_SERVERS environment variable
unset MCP_SERVERS

# Initialize registry
python -c "from tools.mcp_registry import mcp_registry; mcp_registry.initialize()"
```

**Expected Results**:
- [ ] Servers from YAML are loaded
- [ ] Tools are registered with correct schema
- [ ] `get_mcp_tools_schema()` returns non-empty list

---

### Test Scenario 2.2: Environment Variable Priority

**Objective**: Verify MCP_SERVERS env var takes precedence over YAML

**Steps**:
```bash
export MCP_SERVERS='[{"name":"env_server","transport":"stdio","command":["echo","test"]}]'
python -c "from tools.mcp_registry import mcp_registry; mcp_registry.initialize(); print(mcp_registry.get_mcp_tools_schema())"
```

**Expected Results**:
- [ ] Only `env_server` is loaded
- [ ] YAML servers are ignored

---

### Test Scenario 2.3: Invalid YAML Handling

**Objective**: Verify graceful handling of malformed YAML

**Steps**:
1. Create `config/mcp_servers.yaml` with invalid YAML
2. Initialize registry with no MCP_SERVERS env var

**Expected Results**:
- [ ] Error logged but no crash
- [ ] Empty tool list returned
- [ ] Agent continues to function

---

## 3. Skill Execution Tests

### Test Scenario 3.1: DebugExplainSkill - Real Error Analysis

**Objective**: Test skill on actual Python errors

**Prerequisites**:
- Python file with known error

**Steps**:
```python
# Create test file with error
echo 'import non_existent_module' > /tmp/test_error.py

# Execute through agent
use_skill(skill_name="debug_explain", parameters={
    "error_traceback": open("/tmp/test_error.py").read(),
    "language": "en"
})
```

**Expected Results**:
- [ ] Identifies `ModuleNotFoundError`
- [ ] Suggests `pip install non_existent_module`
- [ ] Provides actionable fix

---

### Test Scenario 3.2: GenerateTestSkill - Pytest Generation

**Objective**: Verify test generation produces valid pytest code

**Prerequisites**:
- Python module with functions

**Steps**:
```python
use_skill(skill_name="generate_test", parameters={
    "target": "src/utils.py",
    "function_name": "calculate_total",
    "test_framework": "pytest",
    "write_to_file": False
})
```

**Expected Results**:
- [ ] Returns test code with `test_calculate_total` function
- [ ] Includes `assert` statements
- [ ] Has proper pytest markers if async

---

### Test Scenario 3.3: ApiDesignReviewSkill - Design Score

**Objective**: Verify API review produces meaningful scores

**Steps**:
```python
use_skill(skill_name="api_design_review", parameters={
    "target": "src/api/endpoints.py",
    "check_naming": True,
    "check_types": True,
    "check_docs": True
})
```

**Expected Results**:
- [ ] Returns score out of 100
- [ ] Lists critical issues first
- [ ] Provides recommendations

---

### Test Scenario 3.4: DependencyAnalysisSkill - Import Graph

**Objective**: Verify dependency analysis works on real code

**Steps**:
```python
use_skill(skill_name="dependency_analysis", parameters={
    "target": "src/main.py",
    "max_depth": 3,
    "detect_cycles": True
})
```

**Expected Results**:
- [ ] Lists all imports (stdlib, third-party, local)
- [ ] Shows function call graph
- [ ] Detects circular dependencies if present

---

### Test Scenario 3.5: CodeMigrationSkill - Flask to FastAPI

**Objective**: Verify migration produces valid FastAPI code

**Prerequisites**:
- Flask application file

**Steps**:
```python
# Create Flask app
cat > /tmp/flask_app.py << 'EOF'
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route('/users/<int:user_id>')
def get_user(user_id):
    return jsonify({'id': user_id})
EOF

# Run migration
use_skill(skill_name="code_migration", parameters={
    "target": "/tmp/flask_app.py",
    "migration_type": "flask_to_fastapi",
    "apply_changes": False
})
```

**Expected Results**:
- [ ] `Flask` → `FastAPI`
- [ ] `@app.route()` → `@app.get()`
- [ ] `request.json()` → `request.json()`
- [ ] `jsonify()` → `json()`

---

### Test Scenario 3.6: Skill Registry Auto-Discovery

**Objective**: Verify all skills are discovered on startup

**Steps**:
```python
from skills.skill_registry import skill_registry

skill_registry.initialize()
names = skill_registry.get_skill_names()

expected = [
    "web_research",
    "code_review",
    "narcissistic_numbers",
    "debug_explain",
    "generate_test",
    "api_design_review",
    "dependency_analysis",
    "code_migration"
]

for name in expected:
    assert name in names, f"Missing skill: {name}"
```

**Expected Results**:
- [ ] All 8 skills are registered
- [ ] Schema includes all skill names
- [ ] `use_skill` tool has correct enum

---

## 4. Enhanced RAG Tests

### Test Scenario 4.1: Semantic Chunking with AST

**Objective**: Verify functions/classes are chunked correctly

**Prerequisites**:
- Python project with multiple functions/classes

**Steps**:
```python
from tools.rag_tools import RAGTools

# Index with semantic mode
result = RAGTools.index_codebase(
    path="src",
    workdir=Path("."),
    chunk_mode="semantic"
)

# Check stats
stats = RAGTools.get_index_stats()
assert stats["total_chunks"] > 0
```

**Expected Results**:
- [ ] Functions are separate chunks
- [ ] Classes with methods are chunked together
- [ ] Metadata includes `entity_type` and `entity_name`

---

### Test Scenario 4.2: Hybrid Search Quality

**Objective**: Verify hybrid search outperforms pure vector search

**Prerequisites**:
- Indexed codebase
- Query with specific keywords

**Steps**:
```python
# Pure vector search
vector_results = RAGTools.semantic_search_code(
    "authentication user login",
    n_results=5,
    use_hybrid=False
)

# Hybrid search
hybrid_results = RAGTools.semantic_search_code(
    "authentication user login",
    n_results=5,
    use_hybrid=True
)
```

**Expected Results**:
- [ ] Hybrid results include both semantic and keyword matches
- [ ] BM25 index is built (`_bm25_index` is not empty)
- [ ] Results show "vector + BM25 hybrid" indicator

---

### Test Scenario 4.3: Line Chunking Fallback

**Objective**: Verify non-Python files use line chunking

**Steps**:
```python
from tools.rag_tools import RAGTools

# Create JavaScript file
Path("/tmp/test.js").write_text("// " + "\n".join([f"line {i}" for i in range(150)]))

chunks = RAGTools._semantic_chunk(
    Path("/tmp/test.js").read_text(),
    Path("/tmp/test.js"),
    Path("/tmp")
)

# All chunks should be line-based
for chunk in chunks:
    assert chunk['metadata']['chunk_type'] == 'line'
```

---

### Test Scenario 4.4: RAG Index Persistence

**Objective**: Verify index persists across restarts

**Steps**:
1. Index a codebase
2. Restart Python interpreter
3. Query without re-indexing

**Expected Results**:
- [ ] ChromaDB persists to `.team/chroma_db`
- [ ] Subsequent queries return results
- [ ] BM25 index rebuilds from documents

---

### Test Scenario 4.5: Clear Index

**Objective**: Verify index clearing works

**Steps**:
```python
from tools.rag_tools import RAGTools

RAGTools.clear_index()
stats = RAGTools.get_index_stats()

assert stats["total_chunks"] == 0
```

---

## 5. End-to-End Workflow Tests

### Test Scenario 5.1: Complete Debug Workflow

**Objective**: Full workflow from error to fix

**Steps**:
1. User encounters error in code
2. Calls `debug_explain` skill
3. Analyzes the explanation
4. Uses `generate_test` to add regression test

**Expected Flow**:
```
User: "My code throws ModuleNotFoundError: No module named 'requests'"

Agent: use_skill(skill_name="debug_explain", parameters={
    "error_traceback": "...",
    "language": "en"
})

→ Skill returns: Explanation + pip install suggestion + prevention tips

Agent: use_skill(skill_name="generate_test", parameters={
    "target": "src/api_client.py",
    "function_name": "fetch_data",
    "write_to_file": True
})
```

---

### Test Scenario 5.2: Code Review to Migration Workflow

**Objective**: Review code, identify issues, then modernize

**Steps**:
1. Run `api_design_review` on legacy Flask app
2. Run `dependency_analysis` to understand structure
3. Run `code_migration` to convert to FastAPI

---

### Test Scenario 5.3: Knowledge Base Search Workflow

**Objective**: Build knowledge base and search effectively

**Steps**:
```python
# 1. Index codebase with semantic chunking
RAGTools.index_codebase(".", Path("."), chunk_mode="semantic")

# 2. Search with natural language
results = RAGTools.semantic_search_code(
    "How is user authentication implemented?",
    n_results=10,
    use_hybrid=True
)

# 3. Use in agent context
Agent: Answer user question about authentication
        using RAG search results
```

---

### Test Scenario 5.4: Multi-Skill Orchestration

**Objective**: Verify skills work together in complex scenarios

**Example Scenario**: Legacy API modernization

```python
# Step 1: Analyze current state
dependency_result = use_skill(skill_name="dependency_analysis", parameters={
    "target": "legacy/api.py",
    "detect_cycles": True
})

# Step 2: Review design quality
design_result = use_skill(skill_name="api_design_review", parameters={
    "target": "legacy/api.py"
})

# Step 3: Generate tests for critical functions
test_result = use_skill(skill_name="generate_test", parameters={
    "target": "legacy/api.py",
    "function_name": "process_payment",
    "write_to_file": True
})

# Step 4: Migrate to new framework
migration_result = use_skill(skill_name="code_migration", parameters={
    "target": "legacy/api.py",
    "migration_type": "flask_to_fastapi",
    "apply_changes": False  # Preview first
})
```

---

## Running the Tests

### Unit Tests
```bash
cd /path/to/production_agent
pytest tests/ -v
```

### Specific Test Files
```bash
pytest tests/test_http_mcp_client.py -v
pytest tests/test_skills.py -v
pytest tests/test_rag_enhanced.py -v
```

### Integration Tests (Manual)
```bash
# Start required services
docker-compose up -d  # If using Docker

# Run specific integration scenario
python tests/integration/test_mcp_http.py

# Run all integration tests
pytest tests/integration/ -v
```

---

## Test Environment Setup

```bash
# Create test environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/ -v --tb=short
```

---

## Troubleshooting

### FastMCP Server Not Starting
```bash
# Check Node.js version (requires v18+)
node --version

# Install FastMCP globally
npm install -g @modelcontextprotocol/server-filesystem
```

### ChromaDB Issues
```bash
# Clear existing index
rm -rf .team/chroma_db

# Reinstall if needed
pip install chromadb sentence-transformers --force-reinstall
```

### Skill Discovery Issues
```bash
# Check skills directory
ls -la skills/builtin/

# Verify Python path
python -c "import sys; print(sys.path)"
```
