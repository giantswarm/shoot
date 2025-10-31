import os
import logging
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from fastapi import FastAPI, HTTPException, Request


# Configure MCP server
kubernetes_server = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['--kubeconfig', os.environ['KUBECONFIG'], '--read-only'], env=os.environ, tool_prefix='workload_cluster')

# Configure OTEL for logging
exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(exporter)
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(span_processor)
set_tracer_provider(tracer_provider)
Agent.instrument_all()

# Configure model
model = OpenAIResponsesModel(os.environ['OPENAI_MODEL'])
settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='high',
    openai_reasoning_summary='detailed',
)

# Configure agent
agent = Agent(
    model, 
    model_settings=settings, 
    toolsets=[kubernetes_server],
    system_prompt=(
        open('prompt.md').read()
    ),
)

# Configure logging filter to suppress healthcheck endpoint logs
class HealthcheckLogFilter(logging.Filter):
    """Filter to prevent logging access to healthcheck endpoints."""
    
    def filter(self, record):
        # Filter out access logs for /health and /ready endpoints
        # uvicorn access logs can have various formats, so we check the message content
        message = record.getMessage()
        # Check for common patterns: "/health" or "/ready" in the log message
        # This covers formats like: "GET /health HTTP/1.1" 200, "/health", etc.
        if "/health" in message or "/ready" in message:
            # Double-check it's an access log (not an error or other log)
            # Access logs typically contain HTTP methods or status codes
            if any(x in message for x in ["GET", "POST", "PUT", "DELETE", "PATCH", " HTTP/", " 200", " 503", " 404"]):
                return False
        return True

# Apply the filter to uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthcheckLogFilter())

# Configure HTTP endpoint
app = FastAPI(
    title="Shoot API",
    description="A simple API serving the Giantswarm Shoot agent",
    version="1.0.0"
)

@app.get("/health")
async def health():
    """Liveness probe - checks if the application is running."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness probe - checks if the application is ready to serve traffic."""
    # Check if critical dependencies are available
    checks = {
        "status": "ready",
        "kubernetes_server": kubernetes_server is not None,
        "model": model is not None,
        "agent": agent is not None,
    }
    
    # If any critical dependency is missing, return 503
    if not all([checks["kubernetes_server"], checks["model"], checks["agent"]]):
        raise HTTPException(status_code=503, detail=checks)
    
    return checks


@app.post("/run")
async def run(request: Request):
    try:
        data = await request.json()
        query = data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        result = await agent.run(query)
        return {"result": result.output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
