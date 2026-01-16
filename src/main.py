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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from coordinator import (
    run_coordinator,
    run_coordinator_streaming,
    is_coordinator_ready,
    get_structured_report,
)
from collectors import get_mcp_configs_valid
from schemas import DIAGNOSTIC_REPORT_SCHEMA
from telemetry import get_tracer, trace_operation

# Initialize telemetry on module load
get_tracer()

# Configure HTTP endpoint
app = FastAPI(
    title="Shoot API",
    description="A Kubernetes debugging agent powered by Claude",
    version="2.0.0"
)


@app.get("/health")
async def health():
    """Liveness probe - checks if the application is running."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness probe - checks if the application is ready to serve traffic."""
    wc_valid, mc_valid = get_mcp_configs_valid()
    coordinator_ready = is_coordinator_ready()
    
    checks = {
        "status": "ready",
        "kubernetes_wc": wc_valid,
        "kubernetes_mc": mc_valid,
        "coordinator": coordinator_ready,
    }
    
    # If any critical dependency is missing, return 503
    if not all([checks["kubernetes_wc"], checks["kubernetes_mc"], checks["coordinator"]]):
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
        {"result": "Diagnostic report with findings and recommendations"}
        
        If structured=true and output is parseable:
        {"result": "...", "structured": {...}}
    """
    with trace_operation("api.investigate") as span:
        try:
            data = await request.json()
            query = data.get("query")
            if not query:
                raise HTTPException(status_code=400, detail="Query is required")
            
            # Optional parameters
            timeout_seconds = data.get("timeout_seconds")
            max_turns = data.get("max_turns")
            want_structured = data.get("structured", False)
            
            span.set_attribute("query_length", len(query))
            
            result = await run_coordinator(
                query,
                timeout_seconds=timeout_seconds,
                max_turns=max_turns,
            )
            
            response = {"result": result}
            
            # Optionally include structured output
            if want_structured:
                structured = get_structured_report(result)
                if structured:
                    response["structured"] = structured.model_dump()
            
            return response
        except HTTPException:
            raise
        except Exception as e:
            span.set_attribute("error", True)
            raise HTTPException(status_code=500, detail=str(e))


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
    try:
        data = await request.json()
        query = data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        timeout_seconds = data.get("timeout_seconds")
        max_turns = data.get("max_turns")
        
        async def generate():
            async for chunk in run_coordinator_streaming(
                query,
                timeout_seconds=timeout_seconds,
                max_turns=max_turns,
            ):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schema")
async def get_schema():
    """
    Get the JSON schema for structured diagnostic reports.
    
    This schema describes the expected output format when the coordinator
    successfully generates a structured diagnostic report.
    """
    return DIAGNOSTIC_REPORT_SCHEMA
