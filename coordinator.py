import os
from dataclasses import dataclass
from string import Template
import anyio
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

@dataclass
class CollectorAgents:
    """Dependencies for the coordinator agent."""
    wc_collector: Agent
    mc_collector: Agent


async def collect_wc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    """Collect data from the workload cluster."""
    # Run nested agent in a separate task group to avoid cancel scope conflicts
    # This isolates the nested agent's cancel scope from the parent agent's scope
    result_container = {}
    async def run_agent():
        result_container['result'] = await ctx.deps.wc_collector.run(query, usage=ctx.usage)
    
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_agent)
    # Task group waits for completion before exiting, ensuring result is available
    return result_container['result'].output


async def collect_mc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    """Collect data from the management cluster."""
    # Run nested agent in a separate task group to avoid cancel scope conflicts
    # This isolates the nested agent's cancel scope from the parent agent's scope
    result_container = {}
    async def run_agent():
        result_container['result'] = await ctx.deps.mc_collector.run(query, usage=ctx.usage)
    
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_agent)
    # Task group waits for completion before exiting, ensuring result is available
    return result_container['result'].output


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

