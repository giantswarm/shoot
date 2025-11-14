import os
from dataclasses import dataclass
from string import Template
import anyio
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from app_logging import logger


@dataclass
class CollectorAgents:
    """Dependencies for the coordinator agent."""
    wc_collector: Agent
    mc_collector: Agent


class CollectorError(Exception):
    """Error raised when a collector agent fails.

    The message is structured so that the coordinator can inspect:
    - which collector failed (source)
    - which query was used (query)
    - what underlying error occurred (type and message)
    """

    def __init__(self, source: str, query: str, original_exc: Exception):
        self.source = source
        self.query = query
        self.original_exc = original_exc
        message = (
            f"CollectorError[source={source}] "
            f"query={query!r} "
            f"type={type(original_exc).__name__} "
            f"message={original_exc}"
        )
        super().__init__(message)


async def collect_wc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    """Collect data from the workload cluster."""
    # Run nested agent in a separate task group to avoid cancel scope conflicts
    # This isolates the nested agent's cancel scope from the parent agent's scope
    result_container = {}

    async def run_agent():
        result_container["result"] = await ctx.deps.wc_collector.run(query, usage=ctx.usage)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(run_agent)
        # Task group waits for completion before exiting, ensuring result is available

        # Debug mode: print all messages before returning output
        if os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"):
            logger.info("=== DEBUG MODE: WC Collector All Messages ===")
            logger.info(result_container["result"].all_messages())
            logger.info("=== End WC Collector Debug Output ===")

        return result_container["result"].output
    except Exception as e:
        # Log with full traceback for operators, raise structured error for the coordinator.
        logger.exception("WC collector failed for query %r", query)
        raise CollectorError("workload_cluster", query, e) from e


async def collect_mc_data(ctx: RunContext[CollectorAgents], query: str) -> str:
    """Collect data from the management cluster."""
    # Run nested agent in a separate task group to avoid cancel scope conflicts
    # This isolates the nested agent's cancel scope from the parent agent's scope
    result_container = {}

    async def run_agent():
        result_container["result"] = await ctx.deps.mc_collector.run(query, usage=ctx.usage)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(run_agent)
        # Task group waits for completion before exiting, ensuring result is available

        # Debug mode: print all messages before returning output
        if os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"):
            logger.info("=== DEBUG MODE: MC Collector All Messages ===")
            logger.info(result_container["result"].all_messages())
            logger.info("=== End MC Collector Debug Output ===")

        return result_container["result"].output
    except Exception as e:
        logger.exception("MC collector failed for query %r", query)
        raise CollectorError("management_cluster", query, e) from e


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

