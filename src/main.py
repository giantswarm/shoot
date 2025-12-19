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

from coordinator import run_coordinator, is_coordinator_ready
from collectors import get_mcp_configs_valid

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
        {"query": "Description of the issue, e.g., 'Deployment not ready'"}
    
    Returns:
        {"result": "Diagnostic report with findings and recommendations"}
    """
    try:
        data = await request.json()
        query = data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        result = await run_coordinator(query)
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
