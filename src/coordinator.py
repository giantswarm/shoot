"""
Coordinator agent for the multi-agent Kubernetes debugging system.

This module implements the coordinator following the pattern from:
https://github.com/anthropics/claude-agent-sdk-demos/blob/main/research-agent/

The coordinator:
1. Receives high-level failure descriptions
2. Plans the investigation
3. Delegates to collector subagents via the Task tool
4. Synthesizes findings into diagnostic reports

IMPORTANT: The coordinator has NO direct MCP/Kubernetes access.
It can only delegate to collectors via allowed_tools=["Task"].
"""

from pathlib import Path
from typing import Any, AsyncGenerator, TypedDict

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
    ToolUseBlock,
    ToolResultBlock,
)

from app_logging import logger
from collectors import (
    build_mcp_servers_from_config,
    build_agent_definitions_from_config,
)
from config import get_settings
from config_schema import ShootConfig
from config_loader import get_config, get_config_base_dir, get_prompt_with_variables
from telemetry import trace_operation, add_event, set_span_attribute
from schemas import parse_markdown_report, DiagnosticReport


class InvestigationResult(TypedDict):
    """Result from a coordinator investigation including usage metrics."""

    result: str
    duration_ms: int
    num_turns: int
    total_cost_usd: float | None
    usage: dict[str, Any] | None
    breakdown: dict[str, dict[str, Any]] | None


def create_coordinator_options_from_config(
    config: ShootConfig,
    assistant_name: str,
    config_base_dir: Path,
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
    request_variables: dict[str, str] | None = None,
) -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions for a configured assistant.

    Args:
        config: ShootConfig object
        assistant_name: Name of the assistant to use
        config_base_dir: Base directory for resolving paths
        timeout_seconds: Optional timeout override
        max_turns: Optional max turns override
        request_variables: Variables from the request for prompt injection

    Returns:
        ClaudeAgentOptions configured for the specified assistant
    """
    assistant = config.get_assistant(assistant_name)

    # Build prompt variables from config + request
    prompt_vars: dict[str, str] = {}
    for key, value in assistant.prompt_variables.items():
        prompt_vars[key] = value
    if request_variables:
        # Only include allowed request variables
        for key in assistant.request_variables:
            if key in request_variables:
                prompt_vars[key] = request_variables[key]

    # Load system prompt
    system_prompt = get_prompt_with_variables(
        config=config,
        base_dir=config_base_dir,
        prompt_file=assistant.system_prompt_file,
        variables=prompt_vars,
    )

    # Build MCP servers
    mcp_servers = build_mcp_servers_from_config(config, assistant_name)

    # Build agent definitions
    agents = build_agent_definitions_from_config(
        config, assistant_name, config_base_dir
    )

    # Resolve model and limits
    model = config.resolve_model(assistant.model, is_orchestrator=True)
    resolved_max_turns = max_turns or config.resolve_max_turns(
        assistant.max_turns, is_investigation=True
    )

    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        mcp_servers=mcp_servers,  # type: ignore[arg-type]
        allowed_tools=assistant.allowed_tools,
        agents=agents,
        permission_mode="bypassPermissions",
        max_turns=resolved_max_turns,
    )


def get_coordinator_options(
    assistant_name: str | None = None,
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
    request_variables: dict[str, str] | None = None,
) -> ClaudeAgentOptions:
    """
    Get ClaudeAgentOptions from the configuration file.

    Args:
        assistant_name: Name of assistant to use (uses first available if None)
        timeout_seconds: Optional timeout override
        max_turns: Optional max turns override
        request_variables: Variables from the request for prompt injection

    Returns:
        ClaudeAgentOptions for the coordinator

    Raises:
        ValueError: If SHOOT_CONFIG is not set or config is invalid
    """
    config = get_config()

    if config is None:
        raise ValueError(
            "SHOOT_CONFIG environment variable not set. "
            "Configuration file is required to run Shoot."
        )

    if not assistant_name:
        # Use first available assistant as default
        available = list(config.assistants.keys())
        if not available:
            raise ValueError("No assistants defined in configuration")
        assistant_name = available[0]
        logger.info(f"No assistant specified, using default: {assistant_name}")

    config_base_dir = get_config_base_dir()
    if config_base_dir is None:
        raise ValueError("Config base directory not found")

    return create_coordinator_options_from_config(
        config=config,
        assistant_name=assistant_name,
        config_base_dir=config_base_dir,
        timeout_seconds=timeout_seconds,
        max_turns=max_turns,
        request_variables=request_variables,
    )


async def run_coordinator(  # noqa: C901
    query_text: str,
    assistant_name: str | None = None,
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
    request_variables: dict[str, str] | None = None,
) -> InvestigationResult:
    """
    Run the coordinator agent to investigate a Kubernetes issue.

    Uses ClaudeSDKClient for a single query/response cycle.
    The coordinator delegates to collector subagents via the Task tool.

    Args:
        query_text: High-level failure description (e.g., "Deployment not ready")
        assistant_name: Name of assistant to use (None = default/legacy)
        timeout_seconds: Optional timeout override
        max_turns: Optional max turns override
        request_variables: Variables from the request for prompt injection

    Returns:
        InvestigationResult with diagnostic report and usage metrics
    """
    settings = get_settings()

    with trace_operation(
        "coordinator.investigate",
        {
            "query": query_text[:200],
            "assistant": assistant_name or "default",
            "timeout_seconds": timeout_seconds or settings.timeout_seconds,
            "max_turns": max_turns or settings.max_turns,
        },
    ) as _span:  # noqa: F841
        options = get_coordinator_options(
            assistant_name=assistant_name,
            timeout_seconds=timeout_seconds,
            max_turns=max_turns,
            request_variables=request_variables,
        )

        result_text = ""
        debug_messages: list[Any] = []
        # Capture metrics from ResultMessage
        metrics: dict[str, Any] = {
            "duration_ms": 0,
            "num_turns": 0,
            "total_cost_usd": None,
            "usage": None,
        }
        # Track subagent metrics separately
        subagent_breakdown: dict[str, dict[str, Any]] = {}
        # Map tool_use_id to subagent type for Task calls
        task_tool_uses: dict[str, str] = {}

        logger.info(f"Starting investigation: {query_text[:100]}...")
        add_event("investigation_started", {"query_length": len(query_text)})

        async with ClaudeSDKClient(options=options) as client:
            # Send the investigation query
            await client.query(query_text)

            # Process response messages
            turn_count = 0
            async for message in client.receive_response():
                # Log all message types to debug
                logger.info(f"Received message type: {type(message).__name__}")

                if isinstance(message, AssistantMessage):
                    turn_count += 1
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            # Track Task tool uses to capture subagent metrics
                            if block.name == "Task":
                                subagent_type = block.input.get(
                                    "subagent_type", "unknown"
                                )
                                task_tool_uses[block.id] = subagent_type
                                logger.info(
                                    f"Tracking Task call for subagent: {subagent_type}, id: {block.id}"
                                )
                        elif isinstance(block, ToolResultBlock):
                            # Capture subagent metrics from Task results
                            logger.info(
                                f"Got ToolResultBlock: tool_use_id={block.tool_use_id}, is_error={block.is_error}"
                            )
                            if block.tool_use_id in task_tool_uses:
                                subagent_type = task_tool_uses[block.tool_use_id]
                                logger.info(f"Found Task result for {subagent_type}")
                                # The content should be the Task tool output
                                # According to SDK docs, Task returns: result, usage, total_cost_usd, duration_ms
                                # But the actual content might be just the text result
                                # Let's log what we actually get
                                logger.info(
                                    f"ToolResultBlock content type: {type(block.content)}"
                                )
                                logger.info(
                                    f"ToolResultBlock content: {str(block.content)[:500]}"
                                )
                    debug_messages.append(message)
                    add_event("assistant_message", {"turn": turn_count})
                elif isinstance(message, ResultMessage):
                    # Capture metrics
                    metrics["duration_ms"] = message.duration_ms
                    metrics["num_turns"] = message.num_turns
                    metrics["total_cost_usd"] = message.total_cost_usd
                    metrics["usage"] = message.usage

                    if message.is_error:
                        logger.error(f"Coordinator error: {message.result}")
                        set_span_attribute("error", True)
                        set_span_attribute("error.message", str(message.result))
                    else:
                        logger.info(
                            f"Investigation completed in {message.duration_ms}ms, "
                            f"turns: {message.num_turns}, "
                            f"cost: ${message.total_cost_usd or 0:.4f}"
                        )
                        # Record metrics as span attributes
                        set_span_attribute("duration_ms", message.duration_ms)
                        set_span_attribute("num_turns", message.num_turns)
                        set_span_attribute("cost_usd", message.total_cost_usd or 0)
                        if message.usage:
                            set_span_attribute("usage", str(message.usage))

        # Debug mode: log all messages
        if settings.debug:
            logger.info("=== DEBUG MODE: Coordinator All Messages ===")
            for msg in debug_messages:
                logger.info(msg)
            logger.info("=== End Coordinator Debug Output ===")

        # Try to parse structured output
        parsed_report = parse_markdown_report(result_text)
        if parsed_report:
            set_span_attribute("output.structured", True)
            set_span_attribute("output.summary_items", len(parsed_report.summary))
        else:
            set_span_attribute("output.structured", False)

        return InvestigationResult(
            result=result_text,
            duration_ms=metrics["duration_ms"],
            num_turns=metrics["num_turns"],
            total_cost_usd=metrics["total_cost_usd"],
            usage=metrics["usage"],
            breakdown=subagent_breakdown if subagent_breakdown else None,
        )


async def run_coordinator_streaming(
    query_text: str,
    assistant_name: str | None = None,
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
    request_variables: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Run the coordinator agent with streaming response.

    Yields text chunks as they are received, providing real-time feedback
    during long investigations.

    Args:
        query_text: High-level failure description
        assistant_name: Name of assistant to use (None = default/legacy)
        timeout_seconds: Optional timeout override
        max_turns: Optional max turns override
        request_variables: Variables from the request for prompt injection

    Yields:
        Text chunks as they are generated
    """
    with trace_operation(
        "coordinator.investigate.streaming",
        {
            "query": query_text[:200],
            "assistant": assistant_name or "default",
            "streaming": True,
        },
    ) as _span:  # noqa: F841
        options = get_coordinator_options(
            assistant_name=assistant_name,
            timeout_seconds=timeout_seconds,
            max_turns=max_turns,
            request_variables=request_variables,
        )

        logger.info(f"Starting streaming investigation: {query_text[:100]}...")
        add_event(
            "investigation_started",
            {"query_length": len(query_text), "streaming": True},
        )

        async with ClaudeSDKClient(options=options) as client:
            await client.query(query_text)

            turn_count = 0
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    turn_count += 1
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            yield block.text
                    add_event("assistant_message", {"turn": turn_count})
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        logger.error(f"Coordinator error: {message.result}")
                        set_span_attribute("error", True)
                    else:
                        logger.info(
                            f"Streaming investigation completed in {message.duration_ms}ms, "
                            f"turns: {message.num_turns}, "
                            f"cost: ${message.total_cost_usd or 0:.4f}"
                        )
                        set_span_attribute("duration_ms", message.duration_ms)
                        set_span_attribute("num_turns", message.num_turns)
                        set_span_attribute("cost_usd", message.total_cost_usd or 0)


def get_structured_report(result_text: str) -> DiagnosticReport | None:
    """
    Attempt to parse the coordinator's text output into a structured report.

    Returns None if the output doesn't match the expected format.
    """
    return parse_markdown_report(result_text)


def is_coordinator_ready(assistant_name: str | None = None) -> bool:
    """
    Check if the coordinator can be created.

    Args:
        assistant_name: Optional assistant name to check (None = default)
    """
    try:
        get_coordinator_options(assistant_name=assistant_name)
        return True
    except Exception as e:
        logger.error(f"Coordinator not ready: {e}")
        return False


def get_available_assistants() -> list[str]:
    """
    Get list of available assistant names from configuration.

    Returns:
        List of assistant names defined in the configuration

    Raises:
        ValueError: If SHOOT_CONFIG is not set
    """
    config = get_config()
    if config is None:
        raise ValueError("SHOOT_CONFIG environment variable not set")
    return list(config.assistants.keys())
