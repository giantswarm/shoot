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
    get_wc_mcp_config,
    get_mc_mcp_config,
    create_agent_definitions,
)
from config import get_settings, get_coordinator_prompt
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


def create_coordinator_options(
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
) -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions for the coordinator.

    Architecture:
    - Coordinator uses Task tool to delegate to subagents
    - Two MCP servers configured: kubernetes_wc and kubernetes_mc
    - Each subagent (via AgentDefinition) is restricted to its own MCP tools
    - Coordinator itself has NO MCP access (allowed_tools=["Task"] only)

    Args:
        timeout_seconds: Maximum time for investigation (used for HTTP timeouts
                        and logging, not passed to SDK)
        max_turns: Maximum conversation turns (default from config)
    """
    settings = get_settings()

    return ClaudeAgentOptions(
        system_prompt=get_coordinator_prompt(),
        model=settings.coordinator_model,
        # Configure both MCP servers with distinct names
        # Tool isolation is enforced via AgentDefinition.tools
        mcp_servers={
            "kubernetes_wc": get_wc_mcp_config(),  # type: ignore[dict-item]
            "kubernetes_mc": get_mc_mcp_config(),  # type: ignore[dict-item]
        },
        # Coordinator can ONLY delegate via Task tool
        # No direct MCP access - enforces hierarchical pattern
        allowed_tools=["Task"],
        # Define collector subagents
        agents=create_agent_definitions(),
        # Bypass permission prompts for automated execution
        permission_mode="bypassPermissions",
        # Turn limits to prevent runaway investigations
        max_turns=max_turns or settings.max_turns,
    )


async def run_coordinator(  # noqa: C901
    query_text: str,
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
) -> InvestigationResult:
    """
    Run the coordinator agent to investigate a Kubernetes issue.

    Uses ClaudeSDKClient for a single query/response cycle.
    The coordinator delegates to collector subagents via the Task tool.

    Args:
        query_text: High-level failure description (e.g., "Deployment not ready")
        timeout_seconds: Optional timeout override
        max_turns: Optional max turns override

    Returns:
        InvestigationResult with diagnostic report and usage metrics
    """
    settings = get_settings()

    with trace_operation(
        "coordinator.investigate",
        {
            "query": query_text[:200],
            "timeout_seconds": timeout_seconds or settings.timeout_seconds,
            "max_turns": max_turns or settings.max_turns,
        },
    ) as _span:  # noqa: F841
        options = create_coordinator_options(timeout_seconds, max_turns)

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
    timeout_seconds: int | None = None,
    max_turns: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    Run the coordinator agent with streaming response.

    Yields text chunks as they are received, providing real-time feedback
    during long investigations.

    Args:
        query_text: High-level failure description
        timeout_seconds: Optional timeout override
        max_turns: Optional max turns override

    Yields:
        Text chunks as they are generated
    """
    with trace_operation(
        "coordinator.investigate.streaming",
        {
            "query": query_text[:200],
            "streaming": True,
        },
    ) as _span:  # noqa: F841
        options = create_coordinator_options(timeout_seconds, max_turns)

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


def is_coordinator_ready() -> bool:
    """Check if the coordinator can be created."""
    try:
        create_coordinator_options()
        return True
    except Exception as e:
        logger.error(f"Coordinator not ready: {e}")
        return False
