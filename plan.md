# Migration Plan: PydanticAI → Claude Agent Python SDK

## ✅ MIGRATION COMPLETED

This document describes the completed migration from PydanticAI + OpenAI to Claude Agent SDK + Anthropic Claude models.

## Overview

Migrated the Shoot Kubernetes debugging system while maintaining:
- Three-agent hierarchical architecture (coordinator + WC collector + MC collector)
- **Strict separation of concerns**:
  - Coordinator has NO MCP access (only `Task` tool for delegation)
  - WC collector has ONLY workload cluster MCP access
  - MC collector has ONLY management cluster MCP access
- OpenTelemetry observability
- FastAPI HTTP interface

## Model Mapping

| Current (OpenAI) | Target (Claude) | Purpose |
|------------------|-----------------|---------|
| Reasoning model | `claude-sonnet-4-5` | Coordinator - orchestration and synthesis |
| `gpt-4o-mini` | `claude-3-5-haiku-20241022` | Collectors - fast data gathering |

## Architecture

Following the pattern from [anthropics/claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos/blob/main/research-agent/research_agent/agent.py):

```
┌─────────────────────────────────────────────────────────────┐
│                     ClaudeSDKClient                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Coordinator (Sonnet)                    │    │
│  │         allowed_tools=["Task"]                       │    │
│  │              (No MCP access)                         │    │
│  └──────────────────┬──────────────────┬───────────────┘    │
│                     │ Task             │ Task               │
│  ┌──────────────────▼─────┐  ┌────────▼──────────────────┐ │
│  │   wc_collector (Haiku) │  │   mc_collector (Haiku)    │ │
│  │   AgentDefinition      │  │   AgentDefinition         │ │
│  │   tools=WC_MCP_TOOLS   │  │   tools=MC_MCP_TOOLS      │ │
│  └──────────────────┬─────┘  └────────┬──────────────────┘ │
│                     │                  │                    │
│  ┌──────────────────▼─────┐  ┌────────▼──────────────────┐ │
│  │    kubernetes_wc       │  │    kubernetes_mc          │ │
│  │    (MCP Server)        │  │    (MCP Server)           │ │
│  │    Workload Cluster    │  │    Management Cluster     │ │
│  └────────────────────────┘  └───────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

1. **ClaudeSDKClient** - Single client session for the entire investigation
2. **AgentDefinition** - Defines subagents that coordinator delegates to via `Task` tool
3. **Tool Isolation** - Each AgentDefinition.tools restricts which MCP tools subagent can use

### Implementation Pattern

```python
# collectors.py - Define subagents
agents = {
    "wc_collector": AgentDefinition(
        description="Collect data from WORKLOAD CLUSTER...",
        prompt=wc_system_prompt,
        tools=["mcp__kubernetes_wc__get", ...],  # Only WC MCP tools
        model="haiku"
    ),
    "mc_collector": AgentDefinition(
        description="Collect data from MANAGEMENT CLUSTER...",
        prompt=mc_system_prompt,
        tools=["mcp__kubernetes_mc__get", ...],  # Only MC MCP tools
        model="haiku"
    ),
}

# coordinator.py - Configure coordinator
options = ClaudeAgentOptions(
    system_prompt=coordinator_prompt,
    model="sonnet",
    mcp_servers={
        "kubernetes_wc": wc_config,
        "kubernetes_mc": mc_config,
    },
    allowed_tools=["Task"],  # Coordinator only delegates
    agents=agents,
    permission_mode="bypassPermissions",
)

# Run investigation
async with ClaudeSDKClient(options=options) as client:
    await client.query("Deployment not ready in namespace X")
    async for message in client.receive_response():
        # Process response...
```

## Files Modified

1. ✅ `/requirements.txt` - Updated dependencies
2. ✅ `/src/main.py` - FastAPI integration
3. ✅ `/src/coordinator.py` - ClaudeSDKClient with AgentDefinitions
4. ✅ `/src/collectors.py` - MCP configs and AgentDefinitions
5. ✅ `/helm/shoot/templates/deployment.yaml` - Anthropic env vars
6. ✅ `/helm/shoot/values.yaml` - Updated defaults
7. ✅ `/helm/shoot/values.schema.json` - Updated schema
8. ✅ `/Dockerfile` - Added Claude Code CLI
9. ✅ `/claude_settings/` - Created for future config

## Environment Variables

### Removed (OpenAI)
- `OPENAI_API_KEY`
- `OPENAI_COORDINATOR_MODEL`
- `OPENAI_COLLECTOR_MODEL`

### Added (Anthropic)
- `ANTHROPIC_API_KEY` - API key from secret
- `ANTHROPIC_COORDINATOR_MODEL` - Default: `claude-sonnet-4-5`
- `ANTHROPIC_COLLECTOR_MODEL` - Default: `claude-3-5-haiku-20241022`

### OpenTelemetry
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP endpoint URL
- `OTEL_TRACES_EXPORTER` - Set to "otlp"
- `OTEL_SERVICE_NAME` - Service name for traces

## MCP Tool Naming

Tools from MCP servers follow the pattern: `mcp__<server_name>__<tool_name>`

For `mcp-kubernetes` in non-destructive mode:
- `mcp__kubernetes_wc__get` - Get a resource
- `mcp__kubernetes_wc__list` - List resources
- `mcp__kubernetes_wc__describe` - Describe a resource
- `mcp__kubernetes_wc__logs` - Get pod logs
- `mcp__kubernetes_wc__events` - Get events

## Deployment

1. **Create Kubernetes secret**:
   ```bash
   kubectl create secret generic anthropic-api-key \
     --from-literal=ANTHROPIC_API_KEY=<your-key>
   ```

2. **Deploy with Helm**:
   ```bash
   helm upgrade --install shoot ./helm/shoot \
     --set clusterID=my-cluster
   ```

3. **Test**:
   ```bash
   curl -X POST http://shoot:8000/ \
     -H "Content-Type: application/json" \
     -d '{"query": "Deployment not ready in namespace default"}'
   ```

## Key Differences from Previous Implementation

| Feature | Previous (custom tools) | Current (AgentDefinition) |
|---------|------------------------|---------------------------|
| Session | Separate query() calls | Single ClaudeSDKClient |
| Delegation | @tool decorator | Task tool + AgentDefinition |
| Isolation | Separate sessions | Tool restrictions |
| Efficiency | Multiple CLI processes | Single session |
| Pattern | Custom | Standard SDK pattern |

## References

- [Claude Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Research Agent Demo](https://github.com/anthropics/claude-agent-sdk-demos/blob/main/research-agent/research_agent/agent.py)
