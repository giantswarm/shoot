# CLAUDE.md

## Project Overview

Shoot is a multi-agent system built with Python and the Claude Agent SDK.

## Development Commands

**Important**: Use `Makefile.local.mk` for all common operations. This ensures consistent environment setup and configuration.

```bash
# Setup local development environment
make -f Makefile.local.mk local-setup      # Create local_config with templates
make -f Makefile.local.mk local-mcp        # Download mcp-kubernetes binary
make -f Makefile.local.mk local-kubeconfig MC=<cluster>  # Setup kubeconfigs

# Run the server
make -f Makefile.local.mk local-run        # Run FastAPI server locally

# Code quality
make -f Makefile.local.mk format           # Run all pre-commit hooks

# Testing
make -f Makefile.local.mk local-query Q="your query"  # Test query against local server

# Run tests
uv run pytest

# Docker
make -f Makefile.local.mk docker-build     # Build Docker image
make -f Makefile.local.mk docker-run       # Run in Docker
```
