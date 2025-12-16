# ADK Integration Migration Guide

## Overview

This document describes the migration from a custom MCP implementation to Google's Agent Development Kit (ADK) for Go, enabling the use of OpenAI models with ADK's robust MCP toolset infrastructure.

## Architecture Before & After

### Before: Custom Implementation
```
┌─────────────────────┐
│   Custom Agents     │
│  (OpenAI SDK)       │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Custom MCP Client  │
│  (~300 lines)       │
│  - JSON-RPC 2.0     │
│  - stdio pipes      │
│  - Tool conversion  │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  mcp-kubernetes     │
│  binary             │
└─────────────────────┘
```

### After: ADK Integration
```
┌─────────────────────┐
│   ADK Agents        │
│  (llmagent)         │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  OpenAI Adapter     │
│  (model.LLM impl)   │
└─────────────────────┘
           
┌─────────────────────┐
│  ADK MCP Toolset    │
│  (built-in)         │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  mcp-kubernetes     │
│  binary             │
└─────────────────────┘
```

## Key Components

### 1. OpenAI Model Adapter

**File**: `internal/model/openai_simple.go`

Implements ADK's `model.LLM` interface to use OpenAI models with ADK agents.

```go
type SimpleOpenAIModel struct {
    client *openai.Client
    model  string
}

func (m *SimpleOpenAIModel) GenerateContent(ctx context.Context, req *model.LLMRequest, stream bool) iter.Seq2[*model.LLMResponse, error]
```

**Key Features**:
- Converts ADK's `genai.Content` ↔ OpenAI messages
- Handles function/tool calling
- Supports temperature and token limits
- Returns usage metadata

### 2. Collector Agents with MCP

**File**: `internal/agents/collectors_adk.go`

Uses ADK's `mcptoolset` instead of custom MCP client.

**Before**:
```go
// Custom MCP client
mcpClient, err := StartMCPServer(ctx, mcpCmd)
tools, err := mcpClient.ListTools(ctx)
// Manual tool conversion...
```

**After**:
```go
// ADK handles everything
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

### 3. Coordinator Agent with Function Tools

**File**: `internal/agents/coordinator_adk.go`

Uses ADK's `functiontool` to create custom tools that call collector agents.

```go
collectWCTool, err := functiontool.New(functiontool.Config{
    Name:        "collect_wc_data",
    Description: "Collect data from the workload cluster...",
}, func(ctx tool.Context, args CollectorArgs) (CollectorResult, error) {
    result, err := wcCollector.Run(ctx, args.Query)
    return CollectorResult{Result: result}, err
})
```

### 4. Runner Pattern

ADK uses a `runner.Runner` to execute agents with session management.

```go
runner, err := runner.New(runner.Config{
    Agent:           agent,
    SessionService:  session.InMemoryService(),
    ArtifactService: artifact.InMemoryService(),
})

for event, err := range runner.Run(ctx, userID, sessionID, userMsg, agent.RunConfig{}) {
    // Handle events
}
```

## Migration Steps

### Step 1: Install Dependencies

```bash
go get google.golang.org/adk@v0.2.0
go get github.com/modelcontextprotocol/go-sdk/mcp@latest
go get google.golang.org/genai@latest
go mod tidy
```

### Step 2: Create OpenAI Model Adapter

Create `internal/model/openai_simple.go` implementing `model.LLM`:

```go
func NewSimpleOpenAIModel(apiKey, modelName string) (*SimpleOpenAIModel, error)
func (m *SimpleOpenAIModel) Name() string
func (m *SimpleOpenAIModel) GenerateContent(ctx, req, stream) iter.Seq2[*model.LLMResponse, error]
```

### Step 3: Replace Custom MCP Client with ADK Toolset

**Remove**: `internal/agents/mcp.go` (~300 lines)

**Add**: Use `mcptoolset.New()` with `mcp.CommandTransport`

### Step 4: Update Agent Creation

**Before**:
```go
type Collector struct {
    client    *openai.Client
    mcpClient *MCPClient
}
```

**After**:
```go
type CollectorAgent struct {
    runner *runner.Runner
    agent  agent.Agent
}
```

### Step 5: Update Agent Execution

**Before**:
```go
resp, err := client.Chat.Completions.New(ctx, params)
```

**After**:
```go
userMsg := genai.NewContentFromText(query, genai.RoleUser)
for event, err := range runner.Run(ctx, userID, sessionID, userMsg, agent.RunConfig{}) {
    if event.Text != "" {
        output += event.Text
    }
}
```

### Step 6: Update HTTP Handlers

Minimal changes needed - just pass queries to the new agent interface.

## Benefits Achieved

### 1. Code Reduction
- **Removed**: ~300 lines of custom MCP client code
- **Removed**: Manual JSON-RPC 2.0 implementation
- **Removed**: Tool conversion logic

### 2. Better MCP Support
- ✅ Multiple transport types (stdio, HTTP/SSE, in-memory)
- ✅ Automatic tool discovery
- ✅ Connection lifecycle management
- ✅ Error handling and retries
- ✅ Tool filtering support

### 3. Flexibility
- Easy to switch between OpenAI and Gemini models
- Easy to add more MCP servers
- Easy to add custom function tools
- Built-in session and artifact management

### 4. Production Ready
- Battle-tested by Google
- Proper resource management
- Observable and debuggable
- Well-documented API

## Configuration

### Environment Variables

Same as before:
```bash
OPENAI_API_KEY=your-key
OPENAI_COORDINATOR_MODEL=o1-2024-12-17
OPENAI_COLLECTOR_MODEL=gpt-4o-mini
WC_CLUSTER=my-cluster
ORG_NS=my-org
DEBUG=true
```

### Running

**Original Version**:
```bash
go run ./cmd/shoot/main.go
```

**ADK Version**:
```bash
go run ./cmd/shoot/main_adk.go
```

## Comparison Table

| Feature | Custom Implementation | ADK Integration |
|---------|----------------------|-----------------|
| MCP Support | Manual JSON-RPC | Built-in toolset |
| Code Lines (MCP) | ~300 | ~10 |
| Transport Types | stdio only | stdio, HTTP, SSE, memory |
| Tool Discovery | Manual | Automatic |
| Connection Management | Manual | Automatic |
| Error Handling | Basic | Robust |
| Model Support | OpenAI only | OpenAI + Gemini |
| Session Management | None | Built-in |
| Artifact Support | None | Built-in |
| Tool Filtering | No | Yes |
| Production Ready | Basic | Yes |

## Troubleshooting

### Issue: MCP Server Not Starting

```go
// Check transport configuration
mcpToolset, err := mcptoolset.New(mcptoolset.Config{
    Transport: &mcp.CommandTransport{
        Command: exec.Command("/usr/local/bin/mcp-kubernetes", "serve", "--non-destructive"),
    },
})
if err != nil {
    log.Fatalf("Failed to create MCP toolset: %v", err)
}
```

### Issue: Agent Not Calling Tools

Enable debug mode to see tool interactions:
```bash
DEBUG=true go run ./cmd/shoot/main_adk.go
```

### Issue: Type Conversion Errors

The OpenAI adapter handles basic text and function calls. For complex multi-modal content, you may need to enhance the adapter.

## Future Enhancements

### 1. Native ADK OpenAI Support
Contribute the OpenAI adapter back to the ADK project for official support.

### 2. Streaming Support
Implement streaming in the OpenAI adapter for real-time responses.

### 3. Multi-Modal Support
Enhance the adapter to handle images, audio, and other content types.

### 4. Remote MCP Servers
Deploy MCP servers as separate HTTP services for better scalability.

## References

- [ADK Documentation](https://google.github.io/adk-docs/)
- [ADK Go Package](https://pkg.go.dev/google.golang.org/adk)
- [MCP Specification](https://modelcontextprotocol.io/)
- [MCP Go SDK](https://github.com/modelcontextprotocol/go-sdk)

## Conclusion

The migration to ADK provides a more robust, maintainable, and feature-rich foundation for the agent system while maintaining compatibility with OpenAI models. The investment in creating the OpenAI adapter pays off with significantly reduced MCP client code and access to ADK's rich ecosystem of tools and features.

