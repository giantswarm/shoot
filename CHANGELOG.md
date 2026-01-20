# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-01-20

### Added

- `MC_KUBECONFIG` environment variable for local development with management cluster kubeconfig
- `MCP_KUBERNETES_PATH` environment variable to configure mcp-kubernetes binary location
- `.env.example` template with all configuration options
- Makefile targets for local development (`docker-build`, `docker-run`, `local-setup`, `local-kubeconfig`, `local-mcp`, `local-deps`, `local-run`)
- Local development setup documentation in CLAUDE.md
- Centralized configuration with Pydantic BaseSettings (`config.py`)
- Prompt caching at module load time for faster response times
- Pre-flight configuration validation (`/ready?deep=true`) - checks kubeconfig, API key, MCP binary
- Request ID tracking for all API requests
- HTTP-level timeout handling with 504 response on timeout
- Structured error responses with request ID for debugging
- **Token usage and cost metrics in API responses** - all endpoints now return detailed usage information including:
  - Total tokens (input/output)
  - Cache read/creation tokens
  - Total cost in USD
  - Duration in milliseconds
  - Number of turns
  - **Per-agent breakdown** showing separate metrics for coordinator, wc_collector, and mc_collector

### Changed

- Improved `/ready` endpoint with optional deep configuration checks
- All configuration now loaded from centralized `Settings` class
- Prompts are now cached at startup instead of read on each request
- Better error messages with request ID for traceability
- `make local-query` now displays formatted metrics including token usage, cost, and per-agent breakdown
- Updated README.md with comprehensive local development instructions (Docker and native Python setup)

### Fixed

- Removed invalid `timeout_seconds` parameter from `ClaudeAgentOptions` initialization (not supported by Claude Agent SDK)
- Updated coordinator model from invalid `claude-sonnet-4-5-20250514` to valid `claude-sonnet-4-5-20250929`
- Fixed all mypy type checking errors:
  - Added type assertions with local variables for prompt templates in config.py
  - Added return type annotations for all API endpoints in main.py
  - Added type annotation for HealthcheckLogFilter.filter() method
  - Added type ignore comments for AgentDefinition model parameter (using full model IDs instead of short names)
  - Added type ignore comments for mcp_servers dict items (using dict instead of TypedDict)
  - Fixed response dict type to dict[str, Any] in main.py to allow structured output
- Fixed all flake8 linting errors:
  - Added noqa comments for intentionally unused span variables in context managers
  - Removed unused json import from schemas.py

### Dependencies

- Added `pydantic-settings` for configuration management

## [2.11.1] - 2025-12-15

### Fixed

- Add renovate config file.

## [2.11.0] - 2025-11-27

### Changed

- Use GS kubernetes MCP

## [2.10.1] - 2025-11-14

### Changed

- Rework prompts
- Remove tool prefix

## [2.10.0] - 2025-11-14

### Changed

- Use redhat kubernetes MCP

## [2.9.0] - 2025-11-14

### Changed

- Improve prompts

## [2.8.0] - 2025-11-13

### Changed

- Reorganize source files
- Log debug via uvicorn logger

## [2.6.0] - 2025-11-12

### Changed

- Fix collector model value.
- Add debug mode.

## [2.4.2] - 2025-11-12

### Changed

- Fix multiagent setup

## [2.4.1] - 2025-11-12

- Fix Dockerfile

## [2.4.0] - 2025-11-12

- Use a multiagent setup

## [2.3.0] - 2025-11-11

### Change

- Change endpoint to serve on / instead of /run

## [2.2.0] - 2025-11-11

### Change

- Change port of the service to 8000
- Improve prompt for single namespace permissions

## [2.1.0] - 2025-11-11

### Changed

- Change to only have org permissions, not cluster-wide permissions.

## [2.0.0] - 2025-11-11

### Changed

- Switch from Job to Deployment. FastAPI will serve an HTTP endpoint for AI debugging.

## [1.1.2] - 2025-10-24

### Changed

- Test release

## [1.1.1] - 2025-10-24

### Changed

- Tag latest when building from main.

## [1.1.0] - 2025-10-23

### Changed

- Use OpenTelemtry exporter directly, not logfire.

## [1.0.0] - 2025-10-23

### Changed

- First release using Pydantic AI and using a single MCP pointing to the


[Unreleased]: https://github.com/giantswarm/shoot/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/giantswarm/shoot/compare/v2.12.0...v3.0.0
[2.12.0]: https://github.com/giantswarm/shoot/compare/v2.11.1...v2.12.0
[2.11.1]: https://github.com/giantswarm/shoot/compare/v2.11.0...v2.11.1
[2.11.0]: https://github.com/giantswarm/shoot/compare/v2.10.1...v2.11.0
[2.10.1]: https://github.com/giantswarm/shoot/compare/v2.10.0...v2.10.1
[2.10.0]: https://github.com/giantswarm/shoot/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/giantswarm/shoot/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/giantswarm/shoot/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/giantswarm/shoot/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/giantswarm/shoot/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/giantswarm/shoot/compare/v2.4.2...v2.5.0
[2.4.2]: https://github.com/giantswarm/shoot/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/giantswarm/shoot/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/giantswarm/shoot/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/giantswarm/shoot/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/giantswarm/shoot/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/giantswarm/shoot/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/giantswarm/shoot/compare/v1.1.2...v2.0.0
[1.1.2]: https://github.com/giantswarm/shoot/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/giantswarm/shoot/compare/v1.1.1...v1.1.1
[1.1.1]: https://github.com/giantswarm/shoot/compare/v1.0.0...v1.1.1
[1.0.0]: https://github.com/giantswarm/shoot/compare/v0.0.0...v1.0.0
[1.1.0]: https://github.com/giantswarm/shoot/compare/v1.0.0...v1.1.0
