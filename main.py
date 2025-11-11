import os
import logging
from string import Template
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from fastapi import FastAPI, HTTPException, Request


# Configure MCP server
kubernetes_wc = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['serve', '--non-destructive'], env=os.environ, tool_prefix='workload_cluster')
kubernetes_mc = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['serve', '--non-destructive', '--in-cluster'], env=os.environ, tool_prefix='management_cluster')

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
prompt_template = Template(open('prompt.md').read())
system_prompt = prompt_template.safe_substitute(
    WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
    ORG_NS=os.environ.get('ORG_NS', 'organization namespace'),
)
agent = Agent(
    model, 
    model_settings=settings, 
    toolsets=[kubernetes_wc, kubernetes_mc],
    system_prompt=system_prompt,
)

# Configure logging filter to suppress healthcheck endpoint logs
class HealthcheckLogFilter(logging.Filter):    
    def filter(self, record):
        message = record.getMessage()
        if "/health" in message or "/ready" in message:
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
        "kubernetes_wc": kubernetes_wc is not None,
        "kubernetes_mc": kubernetes_mc is not None,
        "model": model is not None,
        "agent": agent is not None,
    }
    
    # If any critical dependency is missing, return 503
    if not all([checks["kubernetes_wc"], checks["kubernetes_mc"], checks["model"], checks["agent"]]):
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
