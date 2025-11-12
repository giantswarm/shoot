import os
from dataclasses import dataclass
from string import Template
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from collectors import create_wc_collector, create_mc_collector


@dataclass
class CollectorAgents:
    """Dependencies for the coordinator agent."""
    wc_collector: Agent
    mc_collector: Agent


async def collect_wc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    """Collect data from the workload cluster."""
    result = await ctx.deps.wc_collector.run(query, usage=ctx.usage)
    return result.output


async def collect_mc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    """Collect data from the management cluster."""
    result = await ctx.deps.mc_collector.run(query, usage=ctx.usage)
    return result.output


def create_coordinator() -> Agent[CollectorAgents]:
    """Create the coordinator agent that orchestrates collectors."""
    # Use powerful model for coordinator (reasoning and synthesis)
    model = OpenAIResponsesModel(os.environ['OPENAI_COORDINATOR_MODEL'])
    settings = OpenAIResponsesModelSettings(
        openai_reasoning_effort='high',
        openai_reasoning_summary='detailed',
    )
    
    # Load and substitute prompt template
    prompt_template = Template(open('prompts/coordinator_prompt.md').read())
    system_prompt = prompt_template.safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
        ORG_NS=os.environ.get('ORG_NS', 'organization namespace'),
    )
    
    return Agent(
        model,
        model_settings=settings,
        system_prompt=system_prompt,
        tools=[collect_wc_data, collect_mc_data],
        deps_type=CollectorAgents,
    )

