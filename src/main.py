"""
Shoot API - Kubernetes Debugging Agent Service

This FastAPI service provides an HTTP interface to the Shoot multi-agent
Kubernetes debugging system.

Architecture:
- Agent (Claude Sonnet) orchestrates investigation
- Subagents gather data from configured MCP servers
- Strict separation: each subagent only accesses its own MCP servers

Configuration:
- Set SHOOT_CONFIG to point to the configuration file (required)
- Different agents for different use cases (debugging, alerts, E2E tests)
- Each agent has its own prompts, subagents, and response schema
"""

import asyncio
import uuid
from contextvars import ContextVar
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app_logging import logger
from collectors import get_mcp_configs_valid, run_preflight_checks
from config import get_settings
from config_loader import get_config, get_config_base_dir
from config_schema import ResponseFormat
from coordinator import (
    run_coordinator,
    run_coordinator_streaming,
    is_coordinator_ready,
    get_structured_report,
    InvestigationResult,
)
from response_formatter import (
    get_schema_for_agent,
    parse_structured_response,
    validate_response,
)
from schemas import DIAGNOSTIC_REPORT_SCHEMA
from telemetry import get_tracer, trace_operation

# Initialize telemetry on module load
get_tracer()

# Request ID context variable for tracking
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# Configure HTTP endpoint
app = FastAPI(
    title="Shoot API",
    description="A Kubernetes debugging agent powered by Claude",
    version="3.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe - checks if the application is running."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready(deep: bool = False) -> dict[str, Any]:
    """
    Readiness probe - checks if the application is ready to serve traffic.

    Args:
        deep: If True, performs actual connectivity checks to clusters.
              Default is False for faster health checks.
    """
    wc_valid, mc_valid = get_mcp_configs_valid()
    coordinator_ready = is_coordinator_ready()

    config = get_config()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "error": "SHOOT_CONFIG not set - configuration file is required",
            },
        )

    checks: dict[str, Any] = {
        "status": "ready",
        "kubernetes_wc": wc_valid,
        "kubernetes_mc": mc_valid,
        "coordinator": coordinator_ready,
        "agents": list(config.agents.keys()),
    }

    # Deep check: validate actual cluster connectivity
    if deep:
        preflight = run_preflight_checks()
        checks["preflight"] = preflight
        # Consider not ready if any preflight check fails
        all_preflight_valid = all(check["valid"] for check in preflight.values())
        if not all_preflight_valid:
            checks["status"] = "not_ready"
            raise HTTPException(status_code=503, detail=checks)

    # If any critical dependency is missing, return 503
    if not all(
        [checks["kubernetes_wc"], checks["kubernetes_mc"], checks["coordinator"]]
    ):
        checks["status"] = "not_ready"
        raise HTTPException(status_code=503, detail=checks)

    return checks


@app.get("/agents")
async def list_agents() -> dict[str, Any]:
    """
    List available agents and their configurations.

    Returns:
        Dictionary with agent names and their descriptions
    """
    config = get_config()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="SHOOT_CONFIG not set - configuration file is required",
        )

    agents: dict[str, Any] = {}
    for name, agent in config.agents.items():
        agents[name] = {
            "description": agent.description,
            "subagents": agent.subagents,
            "response_schema": agent.response_schema or None,
            "request_variables": agent.request_variables,
        }

    return {"agents": agents}


@app.get("/agents/{agent_name}/schema")
async def get_agent_schema(agent_name: str) -> dict[str, Any]:
    """
    Get the JSON Schema for an agent's response format.

    Args:
        agent_name: Name of the agent

    Returns:
        JSON Schema for the agent's response format
    """
    config = get_config()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="SHOOT_CONFIG not set - configuration file is required",
        )

    if agent_name not in config.agents:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. "
            f"Available: {list(config.agents.keys())}",
        )

    config_base_dir = get_config_base_dir()
    if config_base_dir is None:
        raise HTTPException(status_code=500, detail="Config base directory not found")

    schema, schema_config = get_schema_for_agent(config, agent_name, config_base_dir)

    if schema is None:
        return {
            "agent": agent_name,
            "schema": None,
            "message": "No response schema configured for this agent",
        }

    return {
        "agent": agent_name,
        "schema": schema,
        "format": schema_config.format.value if schema_config else "human",
        "description": schema_config.description if schema_config else "",
    }


def _validate_agent(agent_name: str | None) -> None:
    """Validate that agent name is provided and exists in config."""
    if not agent_name:
        raise HTTPException(
            status_code=400,
            detail="Agent name is required. Use /agents to list available agents.",
        )

    config = get_config()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="SHOOT_CONFIG not set - configuration file is required",
        )
    if agent_name not in config.agents:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. "
            f"Available: {list(config.agents.keys())}",
        )


def _get_response_schema_info(
    agent_name: str | None,
) -> tuple[ResponseFormat, dict[str, Any] | None]:
    """Get response format and schema for an agent."""
    config = get_config()
    if config is None or not agent_name:
        return ResponseFormat.HUMAN, None

    config_base_dir = get_config_base_dir()
    if not config_base_dir:
        return ResponseFormat.HUMAN, None

    schema, schema_config = get_schema_for_agent(config, agent_name, config_base_dir)
    response_format = schema_config.format if schema_config else ResponseFormat.HUMAN
    return response_format, schema


def _add_structured_output(
    response: dict[str, Any],
    result_text: str,
    response_format: ResponseFormat,
    schema: dict[str, Any] | None,
    want_structured: bool,
) -> None:
    """Add structured output to response if applicable."""
    if response_format == ResponseFormat.JSON:
        parsed = parse_structured_response(result_text, schema)
        if parsed:
            if schema:
                is_valid, errors = validate_response(parsed, schema)
                if not is_valid:
                    logger.warning(f"Response validation errors: {errors}")
            response["structured"] = parsed
    elif want_structured:
        structured = get_structured_report(result_text)
        if structured:
            response["structured"] = structured.model_dump()


@app.post("/")
async def run(request: Request) -> Any:
    """
    Run the Shoot agent to investigate a Kubernetes issue.

    Request body:
        {
            "query": "Description of the issue, e.g., 'Deployment not ready'",
            "agent": "kubernetes_debugger",  // required, agent name
            "timeout_seconds": 300,  // optional, default 300
            "max_turns": 15,         // optional, default 15
            "structured": false,     // optional, return structured JSON if parseable
            "variables": {}          // optional, request variables for prompt injection
        }

    Returns:
        {
            "result": "Diagnostic report with findings and recommendations",
            "request_id": "uuid",
            "agent": "kubernetes_debugger",
            "metrics": {
                "duration_ms": 12345,
                "num_turns": 8,
                "total_cost_usd": 0.0245,
                "usage": {...}
            }
        }

        If structured=true and output is parseable:
        {"result": "...", "structured": {...}, "metrics": {...}, "request_id": "uuid"}

        For JSON-format agents, returns raw JSON response.
    """
    request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)
    settings = get_settings()

    with trace_operation("api.investigate") as span:
        span.set_attribute("request_id", request_id)

        try:
            data = await request.json()
            query = data.get("query")
            if not query:
                raise HTTPException(status_code=400, detail="Query is required")

            agent_name = data.get("agent")
            _validate_agent(agent_name)

            timeout_seconds = data.get("timeout_seconds") or settings.timeout_seconds
            max_turns = data.get("max_turns")
            want_structured = data.get("structured", False)
            request_variables = data.get("variables", {})

            span.set_attribute("query_length", len(query))
            span.set_attribute("timeout_seconds", timeout_seconds)
            span.set_attribute("agent", agent_name or "default")

            logger.info(
                f"Starting request_id={request_id} "
                f"agent={agent_name or 'default'} "
                f"query_length={len(query)} timeout={timeout_seconds}s"
            )

            http_timeout = timeout_seconds + 30
            try:
                async with asyncio.timeout(http_timeout):
                    investigation_result: InvestigationResult = await run_coordinator(
                        query,
                        agent_name=agent_name,
                        timeout_seconds=timeout_seconds,
                        max_turns=max_turns,
                        request_variables=request_variables,
                    )
            except asyncio.TimeoutError:
                logger.error(f"Investigation timed out request_id={request_id}")
                span.set_attribute("error", True)
                span.set_attribute("error.type", "timeout")
                raise HTTPException(
                    status_code=504,
                    detail={
                        "error": "Investigation timed out",
                        "request_id": request_id,
                        "timeout_seconds": http_timeout,
                    },
                )

            response_format, schema = _get_response_schema_info(agent_name)
            response: dict[str, Any] = {
                "result": investigation_result["result"],
                "request_id": request_id,
                "agent": agent_name,
                "metrics": {
                    "duration_ms": investigation_result["duration_ms"],
                    "num_turns": investigation_result["num_turns"],
                    "total_cost_usd": investigation_result["total_cost_usd"],
                    "usage": investigation_result["usage"],
                    "breakdown": investigation_result.get("breakdown"),
                },
            }

            _add_structured_output(
                response,
                investigation_result["result"],
                response_format,
                schema,
                want_structured,
            )

            logger.info(f"Investigation completed request_id={request_id}")
            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Investigation failed request_id={request_id}")
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise HTTPException(
                status_code=500, detail={"error": str(e), "request_id": request_id}
            )


@app.post("/stream")
async def run_stream(request: Request) -> StreamingResponse:
    """
    Run the Shoot agent with streaming response.

    Provides real-time feedback during long investigations by streaming
    text chunks as they are generated.

    Request body:
        {
            "query": "Description of the issue, e.g., 'Deployment not ready'",
            "agent": "kubernetes_debugger",  // required, agent name
            "timeout_seconds": 300,  // optional, default 300
            "max_turns": 15,         // optional, default 15
            "variables": {}          // optional, request variables
        }

    Returns:
        text/event-stream with diagnostic report chunks
    """
    # Generate request ID for tracking
    request_id = str(uuid.uuid4())
    request_id_ctx.set(request_id)
    settings = get_settings()

    try:
        data = await request.json()
        query = data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        agent_name = data.get("agent")
        _validate_agent(agent_name)

        timeout_seconds = data.get("timeout_seconds") or settings.timeout_seconds
        max_turns = data.get("max_turns")
        request_variables = data.get("variables", {})

        logger.info(
            f"Starting streaming investigation request_id={request_id} "
            f"agent={agent_name} "
            f"query_length={len(query)} timeout={timeout_seconds}s"
        )

        async def generate() -> AsyncGenerator[str, None]:
            try:
                async for chunk in run_coordinator_streaming(
                    query,
                    agent_name=agent_name,
                    timeout_seconds=timeout_seconds,
                    max_turns=max_turns,
                    request_variables=request_variables,
                ):
                    yield chunk
                logger.info(
                    f"Streaming investigation completed request_id={request_id}"
                )
            except Exception as e:
                logger.exception(
                    f"Streaming investigation failed request_id={request_id}"
                )
                yield f"\n\n[ERROR: {str(e)}]"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "X-Request-ID": request_id,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Streaming investigation failed request_id={request_id}")
        raise HTTPException(
            status_code=500, detail={"error": str(e), "request_id": request_id}
        )


@app.get("/schema")
async def get_schema() -> dict[str, Any]:
    """
    Get the JSON schema for structured diagnostic reports.

    This schema describes the expected output format when the coordinator
    successfully generates a structured diagnostic report.

    Note: Use /agents/{name}/schema for agent-specific schemas.
    """
    return DIAGNOSTIC_REPORT_SCHEMA
