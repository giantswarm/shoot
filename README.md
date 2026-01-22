# Shoot

A configurable multi-agent AI system built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk). Shoot enables you to define orchestrator agents that delegate tasks to specialized subagents, each with access to specific MCP (Model Context Protocol) servers.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              shoot.yaml                                     │
│                         (Configuration File)                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FastAPI Server                                   │
│                         POST / • POST /stream                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
┌─────────────────────────────────────────────────────────────────────────────┐|
│                              Agent                                          │|
│                   (Orchestrates investigation)                              │|
│                                                                             │|
│   • Receives queries from API                                               │|
│   • Plans investigation strategy                                            │|
│   • Delegates to subagents via Task tool                                    │|
│   • Synthesizes findings into reports                                       │┘
└─────────────────────────────────────────────────────────────────────────────┘
                          │                   │
              ┌───────────┘                   └───────────┐
              ▼                                           ▼
┌──────────────────────────────┐         ┌──────────────────────────────┐
│     Subagent: Collector A    │         │     Subagent: Collector B    │
│                              │         │                              │
│  • Gathers data from MCP     │         │  • Gathers data from MCP     │
│  • Returns findings          │         │  • Returns findings          │
└──────────────────────────────┘         └──────────────────────────────┘
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Agent** | Orchestrator that receives queries, plans investigations, and delegates to subagents |
| **Subagent** | Specialized collector that gathers data from specific MCP servers |
| **MCP Server** | External service providing tools (Kubernetes, Backstage, databases, etc.) |
| **Response Schema** | JSON Schema defining the structure of agent outputs |

## Configuration

All agents, subagents, and MCP servers are defined in a single YAML file:

```yaml
# shoot.yaml
version: "1.0"

# Default settings (can be overridden per agent)
defaults:
  models:
    orchestrator: claude-sonnet-4-5-20250514
    collector: claude-3-5-haiku-20241022
  timeouts:
    investigation: 300
    subagent: 60
  max_turns:
    investigation: 15
    subagent: 10

# MCP Servers - external services providing tools
mcp_servers:
  kubernetes_prod:
    command: /usr/local/bin/mcp-kubernetes
    args: ["serve", "--non-destructive"]
    env:
      KUBECONFIG: ${KUBECONFIG}
    tools: [get, list, describe, logs, events]

  kubernetes_staging:
    command: /usr/local/bin/mcp-kubernetes
    args: ["serve", "--non-destructive"]
    env:
      KUBECONFIG: ${STAGING_KUBECONFIG}
    tools: [get, list, describe, logs, events]

  # Remote HTTP MCP server
  backstage:
    url: https://backstage-mcp.internal.example.com
    tools: [search, get_component, get_api]

# Subagents - data collectors with access to specific MCP servers
subagents:
  prod_collector:
    description: |
      Collects runtime data from the PRODUCTION Kubernetes cluster.
      Use this for investigating production issues, pod status, logs, and events.
    system_prompt_file: prompts/prod_collector_prompt.md
    mcp_servers: [kubernetes_prod]

  staging_collector:
    description: |
      Collects data from the STAGING Kubernetes cluster.
      Use this for comparing staging vs production behavior.
    system_prompt_file: prompts/staging_collector_prompt.md
    mcp_servers: [kubernetes_staging]

  catalog_collector:
    description: |
      Queries the Backstage service catalog for component ownership,
      dependencies, and API documentation.
    system_prompt_file: prompts/catalog_collector_prompt.md
    mcp_servers: [backstage]

# Agents - orchestrators that delegate to subagents
agents:
  kubernetes-debugger:
    description: "Debug Kubernetes issues across environments"
    system_prompt_file: prompts/debugger/coordinator_prompt.md
    allowed_tools: [Task]
    subagents: [prod_collector, staging_collector, catalog_collector]
    response_schema: diagnostic_report
    prompt_variables:
      TEAM: ${TEAM_NAME:-platform}

# Response schemas for structured output
response_schemas:
  diagnostic_report:
    file: schemas/diagnostic_report.json
    description: "Diagnostic report with summary and recommendations"
    format: human
```

## Configuration Reference

### Agent Configuration

```yaml
agents:
  my-agent:
    description: "Human-readable description"
    system_prompt_file: prompts/my_agent_prompt.md
    model: claude-sonnet-4-5-20250514      # optional, uses default
    allowed_tools: [Task]                   # tools the orchestrator can use
    mcp_servers: []                         # direct MCP access (optional)
    subagents: [collector_a, collector_b]   # subagents to delegate to
    response_schema: my_schema              # output schema (optional)
    timeout_seconds: 300                    # override default timeout
    max_turns: 15                           # override default max turns
    prompt_variables:                       # variables for prompt templating
      VAR_NAME: ${ENV_VAR:-default}
    request_variables: [dynamic_var]        # variables passed per-request
```

### Subagent Configuration

```yaml
subagents:
  my-collector:
    description: |
      Detailed description of when to use this subagent.
      This is shown to the coordinator to help it decide when to delegate.
    system_prompt_file: prompts/collector_prompt.md
    model: claude-3-5-haiku-20241022        # optional, uses default
    mcp_servers: [server_a, server_b]       # MCP servers this subagent can access
    allowed_tools: [server_a, server_b_list]
    prompt_variables:                       # variables for prompt templating
      VAR_NAME: ${ENV_VAR:-default}
```

### MCP Server Configuration

```yaml
mcp_servers:
  # Local command-based MCP server
  local_server:
    command: /path/to/mcp-server
    args: ["--flag", "value"]
    env:
      API_KEY: ${API_KEY}
    tools: [tool_a, tool_b, tool_c]      # use --in-cluster if env not set

  # Remote HTTP MCP server
  remote_server:
    url: https://mcp-server.example.com
    tools: [tool_x, tool_y]
```

### Environment Variable Expansion

Configuration values support environment variable expansion:

```yaml
env:
  SIMPLE: ${MY_VAR}              # Required variable
  WITH_DEFAULT: ${MY_VAR:-fallback}  # With default value
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | POST | Run an agent investigation |
| `/stream` | POST | Run with streaming response |
| `/agents` | GET | List available agents |
| `/agents/{name}/schema` | GET | Get agent's response schema |
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |

### Example Request

```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why is the payment-service deployment not ready?",
    "agent": "kubernetes-debugger",
    "timeout_seconds": 300,
    "variables": {
      "dynamic_var": "custom_value"
    }
  }'
```

### Example Response

```json
{
  "result": "## Investigation Summary\n\n...",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent": "kubernetes-debugger",
  "metrics": {
    "duration_ms": 45230,
    "num_turns": 8,
    "total_cost_usd": 0.0342,
    "usage": { ... }
  }
}
```

## Quick Start

1. **Install dependencies**
   ```bash
   uv sync
   ```

2. **Set environment variables**
   ```bash
   export ANTHROPIC_API_KEY="your-api-key"
   export SHOOT_CONFIG="/path/to/shoot.yaml"
   export KUBECONFIG="/path/to/kubeconfig"
   ```

3. **Run the server**
   ```bash
   uv run uvicorn src.main:app --reload --port 8000
   ```

4. **Send a query**
   ```bash
   curl -X POST http://localhost:8000/ \
     -H "Content-Type: application/json" \
     -d '{"query": "Check pod status", "agent": "kubernetes-debugger"}'
   ```

## Development

```bash
# Code formatting and linting
uv run pre-commit run --all-files

# Run tests
uv run pytest

# Type checking
uv run mypy src/
```

## Project Structure

```
shoot/
├── config/
│   ├── shoot.yaml              # Main configuration file
│   ├── prompts/                # System prompts for agents
│   │   ├── coordinator_prompt.md
│   │   └── collector_prompt.md
│   └── schemas/                # JSON schemas for responses
│       └── diagnostic_report.json
├── src/
│   ├── main.py                 # FastAPI application
│   ├── coordinator.py          # Orchestrator agent logic
│   ├── collectors.py           # Subagent builders
│   ├── config_schema.py        # Pydantic models for configuration
│   └── config_loader.py        # YAML loading and validation
└── tests/
```

## License

See [LICENSE](LICENSE) for details.
