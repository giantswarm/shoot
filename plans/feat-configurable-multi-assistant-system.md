# feat: Configurable Multi-Assistant System

Transform Shoot from a single-purpose Kubernetes debugger into a generic, configurable multi-agent platform that can expose different assistants via YAML configuration files.

## Overview

This feature enables Shoot to support multiple assistant use cases (Kubernetes debugging, alert handling, E2E test failure investigation) through configuration files rather than hard-coded Python. Users can define:
- Orchestrator system prompts and behavior
- Multiple subagents with specific MCP access
- Shared MCP server definitions (referenced by name)
- Environment variable interpolation for secrets
- Runtime request parameters for dynamic behavior
- **Output response schemas** (JSON for machines, human-readable for operators)

## Problem Statement / Motivation

**Current limitations:**
- Single hard-coded use case (Kubernetes debugging)
- Agent definitions locked in Python code (`src/collectors.py:84-121`)
- MCP configurations hard-coded (`src/collectors.py:17-58`)
- No way to add new assistants without code changes
- Tool restrictions are static lists (`WC_MCP_TOOLS`, `MC_MCP_TOOLS`)
- Single output format (`DiagnosticReport`) - no support for machine-readable JSON or custom schemas

**Why this matters:**
- Operations teams want different assistants for different scenarios
- Adding new use cases requires Python development
- Configuration changes require redeployment instead of config updates
- Cannot share the same MCP across different assistant configurations

## Proposed Solution

### Configuration-Driven Architecture

```
config/
├── shoot.yaml                    # Main configuration
│   ├── defaults (models, timeouts)
│   ├── mcp_servers (shared MCP definitions)
│   │   ├── kubernetes_wc
│   │   ├── kubernetes_mc
│   │   └── prometheus (future)
│   ├── subagents (collector definitions)
│   │   ├── wc_collector
│   │   ├── mc_collector
│   │   └── alerts_collector (future)
│   └── assistants (orchestrator definitions)
│       ├── kubernetes_debugger
│       ├── alerts_handler
│       └── e2e_test_handler
└── schemas/                      # Response schemas (JSON Schema files)
    ├── diagnostic_report.json    # Human-friendly diagnostic output
    ├── e2e_test_result.json      # Machine-readable test results
    └── alert_analysis.json       # Structured alert analysis
```

### Example Configuration

```yaml
# config/shoot.yaml
version: "1.0"

defaults:
  models:
    orchestrator: ${ANTHROPIC_COORDINATOR_MODEL:-claude-sonnet-4-5-20250514}
    collector: ${ANTHROPIC_COLLECTOR_MODEL:-claude-3-5-haiku-20241022}
  timeouts:
    investigation: ${SHOOT_TIMEOUT_SECONDS:-300}
    subagent: 60
  max_turns:
    investigation: ${SHOOT_MAX_TURNS:-15}
    subagent: 10
  response:
    format: human  # Default: human-readable text

# Response schemas (JSON Schema files, referenced by name)
# Stored in config/schemas/ directory alongside this file
response_schemas:
  diagnostic_report:
    file: schemas/diagnostic_report.json
    description: "Human-friendly diagnostic report with summary and recommendations"
    format: human  # Parsed to human-readable markdown

  e2e_test_result:
    file: schemas/e2e_test_result.json
    description: "Machine-readable E2E test failure analysis"
    format: json   # Raw JSON output for CI/CD pipelines

  alert_analysis:
    file: schemas/alert_analysis.json
    description: "Structured alert analysis for alerting systems"
    format: json   # Raw JSON for webhook responses

# Root-level MCP definitions (shared, referenced by name)
mcp_servers:
  kubernetes_wc:
    command: ${MCP_KUBERNETES_PATH:-/usr/local/bin/mcp-kubernetes}
    args: ["serve", "--non-destructive"]
    env:
      KUBECONFIG: ${KUBECONFIG}
    tools:
      - get
      - list
      - describe
      - logs
      - events

  kubernetes_mc:
    command: ${MCP_KUBERNETES_PATH:-/usr/local/bin/mcp-kubernetes}
    args: ["serve", "--non-destructive"]
    env:
      KUBECONFIG: ${MC_KUBECONFIG}
    in_cluster_fallback: true
    tools:
      - get
      - list
      - describe
      - logs
      - events

# Subagent definitions
subagents:
  wc_collector:
    description: |
      Use this agent to collect runtime data from the WORKLOAD CLUSTER.
      Gathers Pods, Deployments, Services, ReplicaSets, events, and logs.
    system_prompt_file: prompts/wc_collector.md
    model: ${defaults.models.collector}
    mcp_servers: [kubernetes_wc]
    timeout_seconds: ${defaults.timeouts.subagent}
    max_turns: ${defaults.max_turns.subagent}

  mc_collector:
    description: |
      Use this agent to collect data from the MANAGEMENT CLUSTER.
      Gathers App/HelmRelease status and CAPI/CAPA resources.
    system_prompt_file: prompts/mc_collector.md
    model: ${defaults.models.collector}
    mcp_servers: [kubernetes_mc]
    timeout_seconds: ${defaults.timeouts.subagent}
    max_turns: ${defaults.max_turns.subagent}

# Assistant definitions (orchestrators)
assistants:
  kubernetes_debugger:
    description: "General Kubernetes debugging assistant"
    system_prompt_file: prompts/coordinator.md
    model: ${defaults.models.orchestrator}
    allowed_tools: [Task]
    subagents: [wc_collector, mc_collector]
    timeout_seconds: ${defaults.timeouts.investigation}
    max_turns: ${defaults.max_turns.investigation}
    response_schema: diagnostic_report  # Human-readable output
    prompt_variables:
      WC_CLUSTER: ${WC_CLUSTER:-workload cluster}
      ORG_NS: ${ORG_NS:-organization namespace}

  alerts_handler:
    description: "Handles Prometheus/alerting webhook events"
    system_prompt_file: prompts/alerts_coordinator.md
    model: ${defaults.models.orchestrator}
    allowed_tools: [Task]
    subagents: [wc_collector, mc_collector]
    response_schema: alert_analysis     # JSON for alerting systems
    request_variables: [alertname, namespace, pod, cluster_name, severity]

  e2e_test_handler:
    description: "Investigates E2E test failures"
    system_prompt_file: prompts/e2e_coordinator.md
    model: ${defaults.models.orchestrator}
    allowed_tools: [Task]
    subagents: [wc_collector]
    response_schema: e2e_test_result    # JSON for CI/CD pipelines
    request_variables: [test_name, test_output, cluster_name]
```

### Example Response Schemas

**Human-readable schema** (`config/schemas/diagnostic_report.json`):
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DiagnosticReport",
  "description": "Human-friendly diagnostic report",
  "type": "object",
  "properties": {
    "failure_signal": {
      "type": "string",
      "description": "Original failure description",
      "maxLength": 500
    },
    "summary": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "maxItems": 5,
      "description": "Key findings as bullet points"
    },
    "likely_cause": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "maxItems": 3,
      "description": "Most likely root causes"
    },
    "recommended_next_steps": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "maxItems": 6,
      "description": "Actionable next steps"
    }
  },
  "required": ["failure_signal", "summary", "likely_cause", "recommended_next_steps"]
}
```

**Machine-readable schema** (`config/schemas/e2e_test_result.json`):
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "E2ETestResult",
  "description": "Machine-readable E2E test failure analysis for CI/CD",
  "type": "object",
  "properties": {
    "test_name": { "type": "string" },
    "status": { "type": "string", "enum": ["infrastructure_failure", "test_bug", "application_bug", "flaky", "unknown"] },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "root_cause": { "type": "string" },
    "affected_components": {
      "type": "array",
      "items": { "type": "string" }
    },
    "remediation": {
      "type": "object",
      "properties": {
        "action": { "type": "string", "enum": ["retry", "fix_infra", "fix_test", "fix_app", "investigate"] },
        "details": { "type": "string" }
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": { "type": "string" },
          "finding": { "type": "string" }
        }
      }
    }
  },
  "required": ["test_name", "status", "confidence", "root_cause"]
}
```

## Technical Approach

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Configuration Layer                        │
├──────────────────────────────────────────────────────────────┤
│  config/shoot.yaml                                           │
│  ├── response_schemas: Dict[str, SchemaConfig]              │
│  ├── mcp_servers: Dict[str, MCPServerConfig]                │
│  ├── subagents: Dict[str, SubagentConfig]                   │
│  └── assistants: Dict[str, AssistantConfig]                 │
│                                                              │
│  config/schemas/*.json  (JSON Schema files)                 │
│  ├── diagnostic_report.json (format: human)                 │
│  ├── e2e_test_result.json (format: json)                    │
│  └── alert_analysis.json (format: json)                     │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    Config Loader (New)                        │
├──────────────────────────────────────────────────────────────┤
│  src/config_loader.py                                        │
│  ├── load_config(path) → ShootConfig                        │
│  ├── expand_env_vars(config) → config with values           │
│  ├── validate_references() → check MCP/subagent refs        │
│  └── validate_tools() → verify tool availability            │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    Agent Factory (Modified)                   │
├──────────────────────────────────────────────────────────────┤
│  src/collectors.py (refactored)                              │
│  ├── build_mcp_servers(config) → dict[str, MCPConfig]       │
│  ├── build_subagents(config) → dict[str, AgentDefinition]   │
│  └── build_coordinator_options(assistant, config)           │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    Response Formatter (New)                   │
├──────────────────────────────────────────────────────────────┤
│  src/response_formatter.py                                   │
│  ├── load_schema(schema_name) → JSON Schema                 │
│  ├── validate_response(data, schema) → bool                 │
│  ├── format_human(data, schema) → markdown string           │
│  └── format_json(data, schema) → JSON string                │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    API Layer (Modified)                       │
├──────────────────────────────────────────────────────────────┤
│  src/main.py                                                 │
│  ├── GET /assistants → list available assistants            │
│  ├── POST / {assistant: "name", query: "..."} → run         │
│  ├── GET /assistants/{name}/schema → output schema          │
│  └── Response formatted based on schema format (human/json) │
└──────────────────────────────────────────────────────────────┘
```

### Implementation Phases

#### Phase 1: Configuration Schema & Loader

**Tasks:**
- [ ] Create `src/config_schema.py` with Pydantic models
  - `MCPServerConfig`: command, args, env, tools, in_cluster_fallback
  - `SubagentConfig`: description, system_prompt_file, model, mcp_servers, timeout, max_turns
  - `ResponseSchemaConfig`: file, description, format (human|json)
  - `AssistantConfig`: description, system_prompt_file, model, allowed_tools, subagents, response_schema, prompt_variables, request_variables
  - `ShootConfig`: version, defaults, response_schemas, mcp_servers, subagents, assistants
- [ ] Create `src/config_loader.py` with loading/validation logic
  - `load_config(path: Path) -> ShootConfig`
  - `expand_env_vars(value: str, env: dict) -> str` - supports `${VAR}` and `${VAR:-default}`
  - `validate_config(config: ShootConfig) -> list[str]` - returns validation errors
  - `load_json_schema(schema_path: Path) -> dict` - loads and validates JSON Schema files
- [ ] Add `SHOOT_CONFIG` environment variable support to `src/config.py`
- [ ] Create default config file `config/shoot.yaml`
- [ ] Create default response schema `config/schemas/diagnostic_report.json`

**Files to create:**
- `src/config_schema.py`
- `src/config_loader.py`
- `config/shoot.yaml`
- `config/schemas/diagnostic_report.json`

**Files to modify:**
- `src/config.py` - add `shoot_config_path` setting

#### Phase 2: Refactor Agent Creation

**Tasks:**
- [ ] Refactor `src/collectors.py` to use config-driven creation
  - `build_mcp_servers(config: ShootConfig, assistant_name: str) -> dict`
  - `build_subagents(config: ShootConfig, assistant_name: str) -> dict[str, AgentDefinition]`
  - `get_tool_list(mcp_name: str, tools: list[str]) -> list[str]` - generates `mcp__name__tool` format
- [ ] Refactor `src/coordinator.py` to accept config
  - `create_coordinator_options(config: ShootConfig, assistant_name: str) -> ClaudeAgentOptions`
- [ ] Update prompt loading to support config-specified paths
- [ ] Maintain backwards compatibility: if no config, use hard-coded defaults

**Files to modify:**
- `src/collectors.py` - refactor to config-driven
- `src/coordinator.py` - accept config parameter

#### Phase 3: Response Schema & Formatting

**Tasks:**
- [ ] Create `src/response_formatter.py` for response shaping
  - `load_schema(config: ShootConfig, schema_name: str) -> dict` - load JSON Schema
  - `validate_response(data: dict, schema: dict) -> tuple[bool, list[str]]` - validate against schema
  - `format_response(data: dict, schema_config: ResponseSchemaConfig) -> str` - format based on config
  - `format_human(data: dict, schema: dict) -> str` - render as human-readable markdown
  - `format_json(data: dict) -> str` - render as raw JSON
- [ ] Update coordinator to include response schema in system prompt
- [ ] Update response parsing to validate against configured schema
- [ ] Handle format-specific content types (text/plain vs application/json)

**Files to create:**
- `src/response_formatter.py`

**Files to modify:**
- `src/coordinator.py` - inject schema instructions into prompt
- `src/schemas.py` - dynamic schema loading

#### Phase 4: API Updates

**Tasks:**
- [ ] Add `assistant` parameter to request schema
- [ ] Add `GET /assistants` endpoint to list available assistants
- [ ] Add `GET /assistants/{name}/schema` endpoint for output schemas (returns JSON Schema)
- [ ] Support request variables injection into prompts
- [ ] Update `/ready?deep=true` to validate all configured assistants
- [ ] Set response Content-Type based on schema format (human=text/plain, json=application/json)

**Files to modify:**
- `src/main.py` - new endpoints, assistant parameter, content types
- `src/schemas.py` - request schema updates

#### Phase 5: Testing & Documentation

**Tasks:**
- [ ] Unit tests for config loading and validation
- [ ] Unit tests for response formatting (human and JSON)
- [ ] Integration tests for config-driven agent creation
- [ ] Edge case tests (missing files, invalid refs, env var expansion)
- [ ] Schema validation tests (valid/invalid responses)
- [ ] Backwards compatibility tests
- [ ] Update CLAUDE.md with new configuration documentation
- [ ] Create example configs for alerts_handler and e2e_test_handler
- [ ] Create example schemas for each use case

**Files to create:**
- `tests/test_config_loader.py`
- `tests/test_config_schema.py`
- `tests/test_response_formatter.py`
- `config/schemas/e2e_test_result.json`
- `config/schemas/alert_analysis.json`

## Acceptance Criteria

### Functional Requirements

- [ ] Configuration file loads successfully at startup
- [ ] Environment variables expand correctly (`${VAR}` and `${VAR:-default}`)
- [ ] MCPs defined at root level are shared across subagents
- [ ] Subagents only have access to their configured MCP tools
- [ ] Multiple assistants can be defined in config
- [ ] Request can specify which assistant to use
- [ ] Request variables are injected into prompts at runtime
- [ ] Backwards compatible: works without config file using defaults
- [ ] Response schemas load from JSON Schema files
- [ ] Responses validate against configured schema
- [ ] Human format renders as readable markdown text
- [ ] JSON format returns raw JSON (for machine consumption)
- [ ] API returns correct Content-Type based on format (text/plain vs application/json)

### Non-Functional Requirements

- [ ] Config loading completes in < 500ms
- [ ] Clear error messages for validation failures
- [ ] No inline secrets in config files (only env var refs)
- [ ] Config file changes require restart (no hot-reload initially)

### Quality Gates

- [ ] All existing tests pass
- [ ] New unit tests for config_loader.py and config_schema.py
- [ ] New unit tests for response_formatter.py
- [ ] Integration test with real config file
- [ ] Schema validation tests for each response format
- [ ] Pre-commit hooks pass
- [ ] Type annotations complete (mypy strict)

## Dependencies & Prerequisites

- Claude Agent SDK (already installed)
- PyYAML for YAML parsing
- Pydantic v2 for schema validation (already installed)

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing deployments | High | Critical | Backwards compatibility: no config = hard-coded defaults |
| Invalid config not caught | Medium | High | Comprehensive startup validation |
| Environment variable leakage | Medium | High | Never log expanded values; only refs |
| Tool name mismatches | Medium | Medium | Preflight validation against MCP tools |
| Circular agent references | Low | High | DAG validation at config load |

## References & Research

### Internal References

- Current coordinator setup: `src/coordinator.py:51-89`
- Current collector definitions: `src/collectors.py:84-121`
- Current MCP configs: `src/collectors.py:17-58`
- Current config module: `src/config.py:16-108`
- Current prompt loading: `src/config.py:120-195`
- Current DiagnosticReport schema: `src/schemas.py:14-54` (to be migrated to JSON Schema)
- Current markdown parser: `src/schemas.py:96-149` (format: human pattern)

### External References

- [Claude Agent SDK - Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [CrewAI YAML Configuration](https://docs.crewai.com/en/quickstart) - industry pattern
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [MCP Server Configuration](https://modelcontextprotocol.io/quickstart/client)

### Related Work

- PR #39: Use Claude Agent SDK (foundation for this work)
- PR #41: Release v3.0.0 (current state)
