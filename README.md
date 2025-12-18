# Shoot - Go Implementation with Claude Code

Go implementation of the Shoot Kubernetes troubleshooting service using Claude Code in headless mode with native subagents.

## Architecture

This is a simplified Go implementation that replaces the Python/pydantic-ai multi-agent system with:
- Single HTTP server in Go (standard library)
- Claude Code headless mode for AI orchestration
- Native subagent feature for MC collector delegation
- MCP server for Kubernetes management cluster access

```
HTTP Request → Go HTTP Server → Single `claude -p` invocation
                                ├─ Coordinator (main agent)
                                │   └─ Delegates to mc-collector subagent
                                │       └─ Subagent uses MCP kubernetes-mc tools
                                │       └─ Returns data to coordinator
                                └─ Coordinator synthesizes response
```

## Prerequisites

- Go 1.21+
- Claude CLI installed and in PATH ([installation instructions](https://code.claude.com))
- `mcp-kubernetes` binary at `/usr/local/bin/mcp-kubernetes`
- `ANTHROPIC_API_KEY` environment variable set

## Configuration

Environment variables:
- `PORT` - HTTP server port (default: `8000`)
- `WC_CLUSTER` - Name of workload cluster under investigation (default: `workload-cluster`)
- `ORG_NS` - Organization namespace in management cluster (default: `org-giantswarm`)
- `ANTHROPIC_API_KEY` - Claude API key (required)

## Running Locally

```bash
# Set up environment
export ANTHROPIC_API_KEY="your-api-key"
export WC_CLUSTER="golem"
export ORG_NS="org-giantswarm"

# Run the server
go run main.go
```

## API Endpoints

### Health Check (Liveness)
```bash
curl http://localhost:8000/health
```

### Readiness Check
```bash
curl http://localhost:8000/ready
```

### Query Endpoint
```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{"query": "Check status of cluster golem"}'
```

## Response Format

```json
{
  "result": "- **failure_signal**: ...\n- **summary**: ...",
  "session_id": "abc123",
  "total_cost_usd": 0.05,
  "duration_ms": 5000
}
```

## Project Structure

```
shoot-go/
├── main.go                        # HTTP server implementation
├── .claude/
│   ├── agents/
│   │   └── mc-collector.md        # MC collector subagent definition
│   └── mcp_config.json            # MCP server configuration
├── prompts/
│   └── coordinator_prompt.md      # Main coordinator system prompt
├── go.mod                         # Go module definition
├── Dockerfile                     # Container image definition
└── README.md                      # This file
```

## How It Works

1. **HTTP Request**: Server receives a query via POST to `/`
2. **Template Substitution**: Coordinator prompt has `${WC_CLUSTER}` and `${ORG_NS}` substituted
3. **Claude Execution**: Single `claude -p` command is executed with:
   - User query as main prompt
   - Coordinator prompt as system prompt
   - MCP config pointing to kubernetes-mc server
   - Agents directory containing mc-collector subagent
4. **Subagent Delegation**: Claude coordinator automatically invokes mc-collector subagent when needing management cluster data
5. **Response**: Structured diagnostic report returned to client

## Subagent Configuration

The MC collector subagent is defined in `.claude/agents/mc-collector.md` with:
- **Name**: `mc-collector`
- **Tools**: `mcp__kubernetes-mc` (from MCP config)
- **Model**: `sonnet`
- **Role**: Gather management cluster data without interpretation

The coordinator automatically delegates to this subagent when it needs management cluster information.

## MCP Server Configuration

The MCP server configuration in `.claude/mcp_config.json` defines the `kubernetes-mc` server:
- Command: `/usr/local/bin/mcp-kubernetes`
- Args: `["serve", "--non-destructive", "--in-cluster"]`
- Provides read-only access to management cluster Kubernetes API

## Building

```bash
go build -o shoot .
```

## Docker Build

```bash
# Note: Ensure mcp-kubernetes binary is available in build context
docker build -t shoot:latest .
```

## Differences from Python Version

| Aspect | Python Version | Go Version |
|--------|---------------|------------|
| HTTP Server | FastAPI | Go stdlib net/http |
| AI Orchestration | pydantic-ai | Claude Code headless |
| Multi-agent | Python functions | Native subagents |
| WC Collector | Included | Not included (MC-only) |
| Observability | OpenTelemetry | log/slog |
| Lines of Code | ~200+ | ~150-200 |

## Troubleshooting

### Claude CLI not found
Ensure `claude` is installed and in PATH:
```bash
which claude
claude --version
```

### MCP server errors
Check that `mcp-kubernetes` is available and has execute permissions:
```bash
ls -l /usr/local/bin/mcp-kubernetes
```

### Prompt not loading
Ensure `prompts/coordinator_prompt.md` exists and is readable from the working directory.

## Development

Run with verbose logging:
```bash
# The Go implementation uses slog for structured logging
# All logs are JSON formatted and sent to stdout
go run main.go 2>&1 | jq
```

Test the subagent directly:
```bash
cd shoot-go
claude -p "List Apps in org-giantswarm" \
  --agents .claude/agents/ \
  --mcp-config .claude/mcp_config.json
```

## References

- [Claude Code Headless Mode](https://code.claude.com/docs/en/headless)
- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents)
- [Model Context Protocol (MCP)](https://code.claude.com/docs/en/model-context-protocol)
