import os
from string import Template
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from collectors import create_wc_collector, create_mc_collector


class CollectorQuery(BaseModel):
    """Query for a collector agent."""
    query: str


async def collect_wc_data(ctx: RunContext[CollectorQuery]) -> str:
    """Collect data from the workload cluster."""
    # Get the WC collector agent from context
    wc_collector = ctx.deps['wc_collector']
    query = ctx.data.query
    
    result = await wc_collector.run(query)
    return result.output


async def collect_mc_data(ctx: RunContext[CollectorQuery]) -> str:
    """Collect data from the management cluster."""
    # Get the MC collector agent from context
    mc_collector = ctx.deps['mc_collector']
    query = ctx.data.query
    
    result = await mc_collector.run(query)
    return result.output


def create_coordinator() -> Agent:
    """Create the coordinator agent that orchestrates collectors."""
    # Use powerful model for coordinator (reasoning and synthesis)
    model = OpenAIResponsesModel(os.environ['OPENAI_COORDINATOR_MODEL'])
    settings = OpenAIResponsesModelSettings(
        openai_reasoning_effort='high',
        openai_reasoning_summary='detailed',
    )
    
    # Create collector agents
    wc_collector = create_wc_collector()
    mc_collector = create_mc_collector()
    
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
        deps={'wc_collector': wc_collector, 'mc_collector': mc_collector},
    )

