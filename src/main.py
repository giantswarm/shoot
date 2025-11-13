import os
from string import Template

from fastapi import FastAPI, HTTPException, Request

from langchain.agents import create_agent
from deepagents.middleware.subagents import SubAgentMiddleware
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import StdioServerParameters
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def get_wc_mcp_tools():
    server_params = StdioServerParameters(
        command="/usr/local/bin/mcp-kubernetes",
        args=["serve", "--non-destructive"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await load_mcp_tools(session)

async def get_mc_mcp_tools():
    server_params = StdioServerParameters(
        command="/usr/local/bin/mcp-kubernetes",
        args=["serve", "--non-destructive", "--in-cluster"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await load_mcp_tools(session)

async def get_agent():
    wc_tools = await get_wc_mcp_tools()
    mc_tools = await get_mc_mcp_tools()
    coordinator_prompt = Template(open('prompts/coordinator_prompt.md').read()).safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
        ORG_NS=os.environ.get('ORG_NS', 'organization namespace'),
    )
    return create_agent(
        model=os.environ.get('OPENAI_COORDINATOR_MODEL', 'gpt-5'),
        system_prompt = coordinator_prompt,
        middleware=[
            SubAgentMiddleware(
                default_model=os.environ.get('OPENAI_COLLECTOR_MODEL', 'gpt-5-mini'),
                default_tools=wc_tools,
                subagents=[
                    {
                        "name": "workload_cluster",
                        "description": "This subagent can get data from the workload cluster.",
                        "system_prompt": "Use tools to get data from the workload cluster.",
                        "tools": wc_tools,
                        "model": os.environ.get('OPENAI_COLLECTOR_MODEL', 'gpt-5-mini')
                    },
                    {
                        "name": "management_cluster",
                        "description": "This subagent can get data from the management cluster.",
                        "system_prompt": "Use tools to get data from the management cluster.",
                        "tools": mc_tools,
                        "model": os.environ.get('OPENAI_COLLECTOR_MODEL', 'gpt-5-mini')
                    }
                ],
            )
        ],
    )


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
    return {"status": "ready"}

@app.post("/")
async def run(request: Request):
    try:
        data = await request.json()
        query = data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        agent = await get_agent()
        result = await agent.invoke({"messages": [{"role": "user", "content": query}]})
        return result.output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
