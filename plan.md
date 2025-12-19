# Migration Plan: PydanticAI → Claude Agent Python SDK

## Overview

Migrate the Shoot Kubernetes debugging system from PydanticAI + OpenAI to Claude Agent SDK + Anthropic Claude models while maintaining:
- Three-agent hierarchical architecture (coordinator + WC collector + MC collector)
- **Strict separation of concerns**:
  - Coordinator has NO MCP access (only delegation tools)
  - WC collector has ONLY workload cluster MCP access
  - MC collector has ONLY management cluster MCP access
- Nested agent execution patterns
- OpenTelemetry observability
- FastAPI HTTP interface

## Model Mapping

| Current (OpenAI) | Target (Claude) | Purpose |
|------------------|-----------------|---------|
| Reasoning model (via `OPENAI_COORDINATOR_MODEL`) | `claude-sonnet-4-5` | Coordinator - high-level orchestration and synthesis |
| `gpt-4o-mini` (default collector) | `claude-3-5-haiku-20241022` | Collectors - fast, efficient data gathering |

**Rationale**: Claude Sonnet 4.5 provides strong reasoning for coordination. Haiku offers fast, cost-effective data collection.

## New Structure: Claude Settings Folder

Create `/Users/pau/workspace/shoot-main/claude_settings/` directory to house all Claude-specific configuration. This folder may be pulled from a shared company repo in the future for consistent Claude CLI usage across projects.

**Purpose**: Centralize Claude Agent SDK configuration, settings, and any company-specific Claude conventions.

## Critical Files to Modify

1. `/Users/pau/workspace/shoot-main/requirements.txt` - Update dependencies
2. `/Users/pau/workspace/shoot-main/src/main.py` - Update imports and instrumentation
3. `/Users/pau/workspace/shoot-main/src/coordinator.py` - Migrate coordinator agent
4. `/Users/pau/workspace/shoot-main/src/collectors.py` - Migrate collector agents
5. `/Users/pau/workspace/shoot-main/helm/shoot/templates/deployment.yaml` - Update environment variables
6. `/Users/pau/workspace/shoot-main/claude_settings/` - Create new folder for Claude configuration

## Step-by-Step Migration

### 1. Update Dependencies (`requirements.txt`)

**Remove**:
```
pydantic-ai-slim[mcp]
pydantic-ai-slim[openai]
```

**Add**:
```
claude-agent-sdk
anthropic
```

**Keep**:
```
opentelemetry-sdk
opentelemetry-exporter-otlp
fastapi
uvicorn
anyio
```

### 2. Migrate `src/collectors.py`

**Key Changes**:
- Replace `from pydantic_ai import Agent` with `from claude_agent_sdk import Agent`
- Replace `from pydantic_ai.models.openai import OpenAIResponsesModel` with `from anthropic import Anthropic`
- Replace `from pydantic_ai.mcp import MCPServerStdio` with Claude Agent SDK MCP equivalent
- Update agent creation to use Claude models
- Update MCP server initialization syntax

**CRITICAL - MCP Access Isolation**:
- WC collector agent gets ONLY `kubernetes_wc` MCP server (workload cluster)
- MC collector agent gets ONLY `kubernetes_mc` MCP server (management cluster)
- Each collector is isolated to its specific Kubernetes cluster
- This maintains security boundaries and prevents cross-cluster access

**MCP Integration**:
- Claude Agent SDK supports MCP via `mcp` module
- Syntax similar but may have different initialization patterns
- Need to verify exact API from Claude Agent SDK docs

**Agent Creation Pattern**:
```python
# OLD (PydanticAI)
collector_model = OpenAIResponsesModel(collector_model_name)
return Agent(
    collector_model,
    toolsets=[kubernetes_wc],
    system_prompt=system_prompt,
)

# NEW (Claude Agent SDK) - approximate structure
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
return Agent(
    client=client,
    model="claude-3-5-haiku-20241022",
    tools=[kubernetes_wc],  # or toolsets, depending on SDK
    system_prompt=system_prompt,
)
```

### 3. Migrate `src/coordinator.py`

**Key Changes**:
- Update imports: `pydantic_ai` → `claude_agent_sdk`
- Replace `OpenAIResponsesModel` and `OpenAIResponsesModelSettings` with Claude equivalents
- Update model configuration (remove OpenAI-specific settings like `openai_reasoning_effort`)
- Update `RunContext` import and usage
- Maintain `CollectorAgents` dataclass structure
- Keep tool functions (`collect_wc_data`, `collect_mc_data`) with updated context types

**CRITICAL - No MCP Access for Coordinator**:
- Coordinator agent has NO MCP toolsets
- Coordinator only has two delegation tools: `collect_wc_data` and `collect_mc_data`
- All Kubernetes access must go through the collector agents
- This enforces the hierarchical pattern: coordinator orchestrates, collectors execute

**Model Configuration**:
- Remove OpenAI-specific settings (`openai_reasoning_effort`, `openai_reasoning_summary`)
- Add Claude-specific settings if available (thinking budget, etc.)
- For Sonnet 4.5, extended thinking is automatic

**Tool Function Signature**:
```python
# Need to update RunContext to Claude Agent SDK equivalent
async def collect_wc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    # Keep nested agent execution pattern with anyio.create_task_group()
    # Update ctx.deps and ctx.usage to Claude SDK equivalents
```

### 4. Migrate `src/main.py`

**Key Changes**:
- Update imports: `from pydantic_ai import Agent` → `from claude_agent_sdk import Agent`
- Remove `Agent.instrument_all()` - Claude Agent SDK handles OTEL automatically via environment variables
- Keep FastAPI structure unchanged
- Update agent instantiation calls
- Maintain readiness check logic

**OpenTelemetry**:
- Claude Agent SDK automatically instruments agents when OTEL environment variables are set
- No manual instrumentation needed - remove the explicit `Agent.instrument_all()` call
- Keep existing OTEL exporter configuration (lines 11-16) or simplify if not needed

### 5. Update Environment Variables

**In Helm deployment** (`helm/shoot/templates/deployment.yaml`):

**Remove**:
- `OPENAI_API_KEY`
- `OPENAI_COORDINATOR_MODEL`
- `OPENAI_COLLECTOR_MODEL`

**Add**:
- `ANTHROPIC_API_KEY` (from secret)
- `ANTHROPIC_COORDINATOR_MODEL` (default: `claude-sonnet-4-5`)
- `ANTHROPIC_COLLECTOR_MODEL` (default: `claude-3-5-haiku-20241022`)

**Keep**:
- `WC_CLUSTER`
- `ORG_NS`
- `DEBUG`
- `KUBECONFIG`

**OpenTelemetry Variables** (per https://code.claude.com/docs/en/monitoring-usage):
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP endpoint URL
- `OTEL_EXPORTER_OTLP_HEADERS` - Optional headers for authentication
- `OTEL_SERVICE_NAME` - Service name for traces (e.g., "shoot-agent")
- `OTEL_TRACES_EXPORTER` - Set to "otlp" to enable tracing

## Key API Differences to Address

### 1. Agent Execution
**PydanticAI**: `result = await agent.run(query, deps=deps)`
**Claude SDK**: Need to verify exact syntax - likely similar but may return different result object

### 2. Result Object
**PydanticAI**: `result.output`, `result.all_messages()`, `result.usage`
**Claude SDK**: Need to identify equivalent properties for:
- Output extraction
- Debug message logging
- Usage tracking

### 3. Usage Tracking Across Agents
**PydanticAI**: `await ctx.deps.wc_collector.run(query, usage=ctx.usage)`
**Claude SDK**: Need to verify if usage can be shared across nested agent calls

### 4. MCP Server Initialization
**PydanticAI**: `MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=[...], env=os.environ)`
**Claude SDK**: Need to check exact MCP integration API

### 5. Dependencies Injection
**PydanticAI**: `deps_type=CollectorAgents` parameter in Agent constructor
**Claude SDK**: Need to verify how to pass dependencies to tools

## Migration Risks

1. **API Differences**: Claude Agent SDK may have different APIs for RunContext, usage tracking, or MCP integration
2. **MCP Support**: Need to verify MCP support is stable in Claude Agent SDK
3. **Nested Agent Execution**: Cancel scope isolation pattern may work differently
4. **Model Behavior**: Claude models may produce different output formats - prompts may need adjustment
5. **Cost**: Need to monitor costs with new models (though Haiku should be cost-effective)

## Implementation Order

1. Create `claude_settings/` folder for Claude-specific configuration
2. Update `requirements.txt`
3. Migrate `collectors.py` (simpler, no nested agents)
4. Migrate `coordinator.py` (depends on collectors working)
5. Update `main.py` (integration layer)
6. Update Helm deployment environment variables (including OTEL vars)

## Research Needed Before Implementation

Since this plan was created without access to Claude Agent SDK documentation, we need to research:
1. Exact Agent class API and initialization
2. MCP integration API (MCPServer equivalent)
3. Tool definition and context access patterns
4. Result object structure and properties
5. Usage tracking across nested agents
6. OpenTelemetry instrumentation support
