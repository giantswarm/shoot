"""
Shoot API - Kubernetes Debugging Agent Service

This FastAPI service provides an HTTP interface to the Shoot multi-agent
Kubernetes debugging system.

Architecture:
- Coordinator agent (Claude Sonnet) orchestrates investigation
- WC Collector subagent gathers workload cluster data
- MC Collector subagent gathers management cluster data
- Strict separation: each collector only accesses its own cluster
"""

import asyncio
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app_logging import logger
from collectors import get_mcp_configs_valid, run_preflight_checks
from config import get_settings
from coordinator import (
    run_coordinator,
    run_coordinator_streaming,
    is_coordinator_ready,
    get_structured_report,
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
    version="2.12.0"
)


@app.get("/health")
async def health():
    """Liveness probe - checks if the application is running."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready(deep: bool = False):
    """
    Readiness probe - checks if the application is ready to serve traffic.

    Args:
        deep: If True, performs actual connectivity checks to clusters.
              Default is False for faster health checks.
    """
    wc_valid, mc_valid = get_mcp_configs_valid()
    coordinator_ready = is_coordinator_ready()

    checks = {
        "status": "ready",
        "kubernetes_wc": wc_valid,
        "kubernetes_mc": mc_valid,
        "coordinator": coordinator_ready,
    }

    # Deep check: validate actual cluster connectivity
    if deep:
        preflight = run_preflight_checks()
        checks["preflight"] = preflight
        # Consider not ready if any preflight check fails
        all_preflight_valid = all(
            check["valid"] for check in preflight.values()
        )
        if not all_preflight_valid:
            checks["status"] = "not_ready"
            raise HTTPException(status_code=503, detail=checks)

    # If any critical dependency is missing, return 503
    if not all([checks["kubernetes_wc"], checks["kubernetes_mc"], checks["coordinator"]]):
        checks["status"] = "not_ready"
        raise HTTPException(status_code=503, detail=checks)

    return checks


@app.post("/")
async def run(request: Request):
    """
    Run the Shoot agent to investigate a Kubernetes issue.

    Request body:
        {
            "query": "Description of the issue, e.g., 'Deployment not ready'",
            "timeout_seconds": 300,  // optional, default 300
            "max_turns": 15,         // optional, default 15
            "structured": false      // optional, return structured JSON if parseable
        }

    Returns:
        {"result": "Diagnostic report with findings and recommendations",
         "request_id": "uuid"}

        If structured=true and output is parseable:
        {"result": "...", "structured": {...}, "request_id": "uuid"}
    """
    # Generate request ID for tracking
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

            # Optional parameters with defaults from config
            timeout_seconds = data.get("timeout_seconds") or settings.timeout_seconds
            max_turns = data.get("max_turns")
            want_structured = data.get("structured", False)

            span.set_attribute("query_length", len(query))
            span.set_attribute("timeout_seconds", timeout_seconds)

            logger.info(
                f"Starting investigation request_id={request_id} "
                f"query_length={len(query)} timeout={timeout_seconds}s"
            )

            # HTTP-level timeout with buffer for graceful shutdown
            http_timeout = timeout_seconds + 30
            try:
                async with asyncio.timeout(http_timeout):
                    result = await run_coordinator(
                        query,
                        timeout_seconds=timeout_seconds,
                        max_turns=max_turns,
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
                    }
                )

            response = {"result": result, "request_id": request_id}

            # Optionally include structured output
            if want_structured:
                structured = get_structured_report(result)
                if structured:
                    response["structured"] = structured.model_dump()

            logger.info(f"Investigation completed request_id={request_id}")
            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Investigation failed request_id={request_id}")
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise HTTPException(
                status_code=500,
                detail={"error": str(e), "request_id": request_id}
            )


@app.post("/stream")
async def run_stream(request: Request):
    """
    Run the Shoot agent with streaming response.

    Provides real-time feedback during long investigations by streaming
    text chunks as they are generated.

    Request body:
        {
            "query": "Description of the issue, e.g., 'Deployment not ready'",
            "timeout_seconds": 300,  // optional, default 300
            "max_turns": 15          // optional, default 15
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

        timeout_seconds = data.get("timeout_seconds") or settings.timeout_seconds
        max_turns = data.get("max_turns")

        logger.info(
            f"Starting streaming investigation request_id={request_id} "
            f"query_length={len(query)} timeout={timeout_seconds}s"
        )

        async def generate():
            try:
                async for chunk in run_coordinator_streaming(
                    query,
                    timeout_seconds=timeout_seconds,
                    max_turns=max_turns,
                ):
                    yield chunk
                logger.info(f"Streaming investigation completed request_id={request_id}")
            except Exception as e:
                logger.exception(f"Streaming investigation failed request_id={request_id}")
                yield f"\n\n[ERROR: {str(e)}]"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "X-Request-ID": request_id,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Streaming investigation failed request_id={request_id}")
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "request_id": request_id}
        )


@app.get("/schema")
async def get_schema():
    """
    Get the JSON schema for structured diagnostic reports.
    
    This schema describes the expected output format when the coordinator
    successfully generates a structured diagnostic report.
    """
    return DIAGNOSTIC_REPORT_SCHEMA
