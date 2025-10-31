import os
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
model = OpenAIResponsesModel('gpt-5')
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

# Configure HTTP endpoint
app = FastAPI(
    title="Shoot API",
    description="A simple API serving the Giantswarm Shoot agent",
    version="1.0.0"
)

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
