import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from deepagents import create_deep_agent
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@asynccontextmanager
async def wc_tools_context():
    """Yield WC tools while keeping the MCP session open."""
    params = StdioServerParameters(
        command="/usr/local/bin/mcp-kubernetes",
        args=["serve", "--non-destructive"],
        env={"KUBECONFIG": os.environ.get("KUBECONFIG", "/k8s/kubeconfig.yaml")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            yield tools


@asynccontextmanager
async def mc_tools_context():
    """Yield MC tools while keeping the MCP session open."""
    params = StdioServerParameters(
        command="/usr/local/bin/mcp-kubernetes",
        args=["serve", "--non-destructive", "--in-cluster"],
        env={
            "KUBERNETES_SERVICE_HOST": os.environ.get("KUBERNETES_SERVICE_HOST"),
            "KUBERNETES_SERVICE_PORT": os.environ.get("KUBERNETES_SERVICE_PORT"),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            yield tools


def build_agent(wc_tools, mc_tools):
    """Create the coordinator agent using provided tool sets."""
    wc_subagent = {
        "name": "workload_cluster",
        "description": "This subagent can get data from the workload cluster.",
        "system_prompt": "Use tools to get data from the workload cluster. Return only the relevant data.",
        "tools": wc_tools,
        "model": os.environ.get("OPENAI_COLLECTOR_MODEL", "gpt-5-mini"),
    }
    mc_subagent = {
        "name": "management_cluster",
        "description": "This subagent can get data from the management cluster.",
        "system_prompt": "Use tools to get data from the management cluster. Return only the relevant data. You only have access to the namespace ${ORG_NS}, you cannot access other namespaces.",
        "tools": mc_tools,
        "model": os.environ.get("OPENAI_COLLECTOR_MODEL", "gpt-5-mini"),
    }
    
    subagents = [wc_subagent, mc_subagent]

    return create_deep_agent(
        model=os.environ.get("OPENAI_COORDINATOR_MODEL", "gpt-5"),
        system_prompt="""
        You are an expert Kubernetes diagnostic agent. Your task is to investigate the issue described by the user and generate a clear, actionable diagnostic report.

        You have two subagents available:
        - The workload_cluster subagent collects data from the workload cluster.
        - The management_cluster subagent collects data from the management cluster.

        Reason step-by-step, use the subagents to gather evidence, and synthesize a concise summary of your findings.
        """,
        debug=os.environ.get("DEBUG", "false") == "true",
        subagents=subagents,
    )


# Configure HTTP endpoint
app = FastAPI(
    title="Shoot API",
    description="A simple API serving the Giantswarm Shoot agent",
    version="1.0.0",
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
        # Keep both MCP sessions alive with minimal nesting
        async with wc_tools_context() as wc_tools, mc_tools_context() as mc_tools:
            agent = build_agent(wc_tools, mc_tools)
            result = await agent.ainvoke({"messages": [{"role": "user", "content": query}]})
        return result.messages[-1].content
    except Exception as e:
        import traceback
        detail = str(e)
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail={"error": detail, "traceback": tb})
