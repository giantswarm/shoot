import asyncio
import os
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

# Ensure KUBECONFIG is set and passed to the subprocess
env = os.environ.copy()
env['KUBECONFIG'] = env.get('KUBECONFIG', '/app/kubeconfig.yaml')

kubernetes_server = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['serve'], env=env, tool_prefix='workload_cluster_')

model = OpenAIResponsesModel('gpt-5')
settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='high',
    openai_reasoning_summary='detailed',
)
agent = Agent(
    model, 
    model_settings=settings, 
    toolsets=[kubernetes_server],
    system_prompt=(
        open('prompt.md').read()
    ),
)

async def main():
    result = await agent.run(os.getenv("QUERY"))
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
