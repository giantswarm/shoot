# Agent Development Kit (ADK) Architecture

## Overview

This application uses Google's Agent Development Kit (ADK) for Go to create a multi-agent system that debugs Kubernetes clusters. The system integrates OpenAI models with ADK's infrastructure through a custom model adapter.

## Architecture

```
User Query → HTTP Server → Coordinator Agent (OpenAI)
                                    ↓
                          Function Tools
                           /            \
                          /              \
                   WC Collector      MC Collector
                   (OpenAI)          (OpenAI)
                         ↓                ↓
                   MCP Toolset      MCP Toolset
                   (ADK)            (ADK)
                         ↓                ↓
                   mcp-kubernetes   mcp-kubernetes
                   (--non-destructive)  (--in-cluster)
```

## Key Components

### 1. OpenAI Model Adapter

**File**: `internal/model/openai_simple.go`

Implements ADK's `model.LLM` interface to enable OpenAI models:

```go
type SimpleOpenAIModel struct {
    client *openai.Client
    model  string
}

func (m *SimpleOpenAIModel) GenerateContent(ctx context.Context, req *model.LLMRequest, stream bool) iter.Seq2[*model.LLMResponse, error]
```

**Key Responsibilities**:
- Converts ADK's `genai.Content` to OpenAI messages format
- Handles tool/function calling
- Returns usage metadata (token counts)
- Manages finish reasons and error codes

### 2. Collector Agents

**File**: `internal/agents/collectors.go`

Two collector agents gather diagnostic data from clusters:

- **WC Collector**: Connects to workload cluster via MCP
- **MC Collector**: Connects to management cluster via MCP (in-cluster mode)

**ADK Integration**:
```go
mcpToolset, err := mcptoolset.New(mcptoolset.Config{
    Transport: &mcp.CommandTransport{
        Command: exec.Command("/usr/local/bin/mcp-kubernetes", "serve", "--non-destructive"),
    },
})

agent, err := llmagent.New(llmagent.Config{
    Model:    openaiModel,
    Toolsets: []tool.Toolset{mcpToolset},
})
```

### 3. Coordinator Agent

**File**: `internal/agents/coordinator.go`

Orchestrates investigation by calling collector agents as function tools.

**Function Tools**:
```go
collectWCTool, err := functiontool.New(functiontool.Config{
    Name:        "collect_wc_data",
    Description: "Collect data from the workload cluster...",
}, func(ctx tool.Context, args CollectorArgs) (CollectorResult, error) {
    return wcCollector.Run(ctx, args.Query, debug)
})
```

### 4. Runner Pattern

ADK uses a `runner.Runner` for proper agent execution:

```go
runner, err := runner.New(runner.Config{
    Agent:           agent,
    SessionService:  session.InMemoryService(),
    ArtifactService: artifact.InMemoryService(),
})

for event, err := range runner.Run(ctx, userID, sessionID, userMsg, agent.RunConfig{}) {
    // Extract text from event.Content.Parts
}
```

## MCP Integration

### What is MCP?

Model Context Protocol (MCP) is an open standard for connecting AI models to external tools and data sources. This application uses MCP to connect agents to Kubernetes clusters.

### MCP Toolset Benefits

Using ADK's `mcptoolset` instead of a custom MCP client provides:

- ✅ Multiple transport types (stdio, HTTP/SSE, in-memory)
- ✅ Automatic tool discovery
- ✅ Connection lifecycle management
- ✅ Error handling and retries
- ✅ Tool filtering capabilities
- ✅ Zero maintenance burden

### MCP Server Configuration

The application spawns two MCP server processes:

1. **Workload Cluster**: `/usr/local/bin/mcp-kubernetes serve --non-destructive`
2. **Management Cluster**: `/usr/local/bin/mcp-kubernetes serve --non-destructive --in-cluster`

ADK's `CommandTransport` manages these processes automatically.

## Data Flow

1. **User sends query** via HTTP POST to `/`
2. **Coordinator agent** receives query and plans investigation
3. **Coordinator calls function tools** (`collect_wc_data`, `collect_mc_data`)
4. **Collector agents** execute with their MCP toolsets
5. **MCP servers** interact with Kubernetes API
6. **Results flow back** through collector → coordinator → HTTP response

## Session Management

ADK provides built-in session management:

```go
sessionResp, err := sessionService.Create(ctx, &session.CreateRequest{
    AppName: "shoot",
    UserID:  "system",
})

// Each query runs in its own session
runner.Run(ctx, userID, sessionResp.Session.ID(), userMsg, agent.RunConfig{})
```

## Prompt Templates

Agent system prompts are stored in the `prompts/` directory at the project root:

- **`prompts/coordinator_prompt.md`** - Coordinator agent instructions
- **`prompts/wc_collector_prompt.md`** - Workload cluster collector instructions  
- **`prompts/mc_collector_prompt.md`** - Management cluster collector instructions

These prompts support variable substitution (e.g., `${WC_CLUSTER}`, `${ORG_NS}`).

## Configuration

### Environment Variables

- `OPENAI_API_KEY` - OpenAI API key (required)
- `OPENAI_COORDINATOR_MODEL` - Model for coordinator (e.g., `o1-2024-12-17`)
- `OPENAI_COLLECTOR_MODEL` - Model for collectors (default: `gpt-4o-mini`)
- `WC_CLUSTER` - Workload cluster name
- `ORG_NS` - Organization namespace
- `DEBUG` - Enable debug logging (`true`, `1`, `yes`)
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OpenTelemetry endpoint (optional)

### Prompt Templates

Agent instructions are loaded from markdown files in `prompts/`:

- `coordinator_prompt.md` - Coordinator agent system prompt
- `wc_collector_prompt.md` - WC collector agent system prompt
- `mc_collector_prompt.md` - MC collector agent system prompt

Templates support variable substitution (e.g., `${WC_CLUSTER}`, `${ORG_NS}`).

## OpenTelemetry Integration

The application includes OpenTelemetry tracing:

```go
exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpoint(cfg.OTELEndpoint))
tp := sdktrace.NewTracerProvider(
    sdktrace.WithBatcher(exporter),
    sdktrace.WithResource(res),
)
otel.SetTracerProvider(tp)
```

Traces are automatically generated for HTTP requests and can be extended for agent execution.

## Dependencies

Key Go modules:

- `google.golang.org/adk` - Agent Development Kit
- `github.com/modelcontextprotocol/go-sdk/mcp` - MCP protocol
- `google.golang.org/genai` - Google AI types
- `github.com/openai/openai-go` - OpenAI SDK
- `go.opentelemetry.io/otel` - OpenTelemetry

## Extension Points

### Adding New Models

To add Gemini support, simply pass a Gemini model to `llmagent.New`:

```go
model, err := gemini.NewModel(ctx, "gemini-2.5-flash", &genai.ClientConfig{
    APIKey: os.Getenv("GOOGLE_API_KEY"),
})
```

### Adding New MCP Servers

Add more MCP toolsets to any agent:

```go
newMCPToolset, err := mcptoolset.New(mcptoolset.Config{
    Transport: &mcp.CommandTransport{
        Command: exec.Command("/path/to/mcp-server"),
    },
})

agent, err := llmagent.New(llmagent.Config{
    Toolsets: []tool.Toolset{mcpToolset, newMCPToolset},
})
```

### Adding Function Tools

Create custom tools for any agent:

```go
myTool, err := functiontool.New(functiontool.Config{
    Name:        "my_tool",
    Description: "Does something useful",
}, func(ctx tool.Context, args MyArgs) (MyResult, error) {
    // Implementation
})
```

## Troubleshooting

### MCP Server Issues

If MCP servers fail to start:
- Verify `/usr/local/bin/mcp-kubernetes` exists
- Check it's executable: `chmod +x /usr/local/bin/mcp-kubernetes`
- Test manually: `/usr/local/bin/mcp-kubernetes serve --non-destructive`

### Agent Not Calling Tools

Enable debug mode to see tool interactions:
```bash
DEBUG=true go run ./cmd/shoot
```

### OpenAI API Errors

- Verify `OPENAI_API_KEY` is set correctly
- Check model names match OpenAI's current offerings
- Monitor rate limits in OpenAI dashboard

## References

- [ADK Documentation](https://google.github.io/adk-docs/)
- [ADK Go Package](https://pkg.go.dev/google.golang.org/adk)
- [MCP Specification](https://modelcontextprotocol.io/)
- [OpenAI Go SDK](https://github.com/openai/openai-go)

