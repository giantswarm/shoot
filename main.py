import logging
from pydantic_ai import Agent
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from fastapi import FastAPI, HTTPException, Request
from coordinator import create_coordinator
from collectors import kubernetes_wc, kubernetes_mc

# Configure OTEL for logging
exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(exporter)
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(span_processor)
set_tracer_provider(tracer_provider)
Agent.instrument_all()

# Create coordinator agent (which manages collector agents)
coordinator = create_coordinator()

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
        "coordinator": coordinator is not None,
    }
    
    # If any critical dependency is missing, return 503
    if not all([checks["kubernetes_wc"], checks["kubernetes_mc"], checks["coordinator"]]):
        raise HTTPException(status_code=503, detail=checks)
    
    return checks


@app.post("/")
async def run(request: Request):
    try:
        data = await request.json()
        query = data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        result = await coordinator.run(query)
        return result.output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
