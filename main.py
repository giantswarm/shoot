import asyncio
import os
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
import logfire

# Ensure KUBECONFIG is set and passed to the subprocess
os.environ['KUBECONFIG'] = os.environ.get('KUBECONFIG', '/app/kubeconfig.yaml')

# Configure MCP server
kubernetes_server = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['--kubeconfig', os.environ['KUBECONFIG'], '--read-only'], env=os.environ, tool_prefix='workload_cluster')

# Configure OTEL for logging
os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')  
os.environ['OTEL_RESOURCE_ATTRIBUTES'] = os.environ.get('OTEL_RESOURCE_ATTRIBUTES', 'service.name=shoot')
logfire.configure(send_to_logfire=False)  
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)


# Configure logging
import logging
from logging import ERROR, basicConfig
logfire.configure()
logfire_handler = logfire.LogfireLoggingHandler()
urllib3_filter = logging.Filter('urllib3')
logfire_handler.fallback.addFilter(lambda record: not urllib3_filter.filter(record))
basicConfig(handlers=[logfire_handler], level=ERROR)

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

# Main function
async def main():
    # Run agent
    result = await agent.run(os.getenv("QUERY"))
    # Print result
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
