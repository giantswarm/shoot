# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shoot is a multi-agent Kubernetes debugging system built with Python and the Claude Agent SDK. It coordinates multiple AI agents to investigate Kubernetes issues across workload and management clusters.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server locally
uvicorn src.main:app --reload --port 8000

# Code quality (pre-commit hooks)
pre-commit run --all-files

# Individual linting/formatting
black src/                    # Format code
flake8 src/                   # Lint
mypy src/                     # Type checking
bandit -c .bandit src/        # Security scan
```

## Architecture

The system uses a three-agent architecture with strict tool isolation:

```
User Query → FastAPI (/stream or /)
    ↓
Coordinator Agent (Claude Sonnet)
├── Only has Task tool (NO direct MCP access)
├── Orchestrates investigation
└── Synthesizes findings into DiagnosticReport
    ↓
┌─────────────────────────┬─────────────────────────┐
↓                         ↓
WC Collector (Haiku)      MC Collector (Haiku)
├── kubernetes_wc MCP     ├── kubernetes_mc MCP
└── Workload cluster data └── Management cluster data
```

**Key design principle**: The Coordinator cannot access Kubernetes directly—it must delegate all data gathering to collector subagents. This enforces separation of concerns and cost optimization.

## Key Files

- `src/main.py` - FastAPI app, endpoints (`/`, `/stream`, `/health`, `/ready`, `/schema`)
- `src/coordinator.py` - `ClaudeSDKClient`, agent orchestration, streaming/blocking modes
- `src/collectors.py` - MCP server configs, `AgentDefinition` for WC/MC collectors
- `src/config.py` - `Settings` class (Pydantic), environment variables, prompt loading
- `src/schemas.py` - `DiagnosticReport` Pydantic model, JSON schema generation
- `src/telemetry.py` - OpenTelemetry setup, tracing decorators
- `src/prompts/*.md` - System prompts for each agent

## Configuration

Required environment variables:
- `ANTHROPIC_API_KEY` - Anthropic API key
- `KUBECONFIG` - Path to workload cluster kubeconfig

Optional:
- `ANTHROPIC_COORDINATOR_MODEL` (default: `claude-sonnet-4-5-20250514`)
- `ANTHROPIC_COLLECTOR_MODEL` (default: `claude-3-5-haiku-20241022`)
- `SHOOT_TIMEOUT_SECONDS` (default: 300, range: 30-600)
- `SHOOT_MAX_TURNS` (default: 15, range: 5-50)
- `OTEL_EXPORTER_OTLP_ENDPOINT` - For telemetry
- `WC_CLUSTER`, `ORG_NS` - Cluster context for prompts

## Code Style

- MyPy strict mode: `disallow_untyped_defs`, `disallow_incomplete_defs`
- Flake8: max line length 120, max complexity 10
- Black for formatting
- All functions require type annotations

## Changelog

Always update `CHANGELOG.md` when making changes. Add entries only under the `[Unreleased]` section using the appropriate category (`### Added`, `### Changed`, `### Fixed`, `### Dependencies`). Never modify released version sections.
