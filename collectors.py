import os
from string import Template
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.mcp import MCPServerStdio


# Initialize MCP servers
kubernetes_wc = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['serve', '--non-destructive'], env=os.environ, tool_prefix='workload_cluster')
kubernetes_mc = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['serve', '--non-destructive', '--in-cluster'], env=os.environ, tool_prefix='management_cluster')


def create_wc_collector() -> Agent:
    """Create the workload cluster collector agent."""
    # Use simpler model for collectors (cost and speed optimization)
    collector_model_name = os.environ.get('OPENAI_COLLECTOR_MODEL', 'gpt-4o-mini')
    collector_model = OpenAIResponsesModel(collector_model_name)
    
    # Load and substitute prompt template
    prompt_template = Template(open('prompts/wc_collector_prompt.md').read())
    system_prompt = prompt_template.safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
    )
    
    return Agent(
        collector_model,
        toolsets=[kubernetes_wc],
        system_prompt=system_prompt,
    )


def create_mc_collector() -> Agent:
    """Create the management cluster collector agent."""
    # Use simpler model for collectors (cost and speed optimization)
    collector_model_name = os.environ.get('OPENAI_COLLECTOR_MODEL', 'gpt-4o-mini')
    collector_model = OpenAIResponsesModel(collector_model_name)
    
    # Load and substitute prompt template
    prompt_template = Template(open('prompts/mc_collector_prompt.md').read())
    system_prompt = prompt_template.safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
        ORG_NS=os.environ.get('ORG_NS', 'organization namespace'),
    )
    
    return Agent(
        collector_model,
        toolsets=[kubernetes_mc],
        system_prompt=system_prompt,
    )

