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

import os
from string import Template
from typing import Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
)
from app_logging import logger
from collectors import (
    get_wc_mcp_config,
    get_mc_mcp_config,
    create_agent_definitions,
)


def _get_coordinator_system_prompt() -> str:
    """Load and substitute the coordinator system prompt."""
    prompt_template = Template(open('prompts/coordinator_prompt.md').read())
    return prompt_template.safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
        ORG_NS=os.environ.get('ORG_NS', 'organization namespace'),
    )


def create_coordinator_options() -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions for the coordinator.
    
    Architecture:
    - Coordinator uses Task tool to delegate to subagents
    - Two MCP servers configured: kubernetes_wc and kubernetes_mc
    - Each subagent (via AgentDefinition) is restricted to its own MCP tools
    - Coordinator itself has NO MCP access (allowed_tools=["Task"] only)
    """
    coordinator_model = os.environ.get('ANTHROPIC_COORDINATOR_MODEL', 'claude-sonnet-4-5')
    
    return ClaudeAgentOptions(
        system_prompt=_get_coordinator_system_prompt(),
        model=coordinator_model,
        # Configure both MCP servers with distinct names
        # Tool isolation is enforced via AgentDefinition.tools
        mcp_servers={
            "kubernetes_wc": get_wc_mcp_config(),
            "kubernetes_mc": get_mc_mcp_config(),
        },
        # Coordinator can ONLY delegate via Task tool
        # No direct MCP access - enforces hierarchical pattern
        allowed_tools=["Task"],
        # Define collector subagents
        agents=create_agent_definitions(),
        # Bypass permission prompts for automated execution
        permission_mode="bypassPermissions",
    )


async def run_coordinator(query_text: str) -> str:
    """
    Run the coordinator agent to investigate a Kubernetes issue.
    
    Uses ClaudeSDKClient for a single query/response cycle.
    The coordinator delegates to collector subagents via the Task tool.
    
    Args:
        query_text: High-level failure description (e.g., "Deployment not ready")
        
    Returns:
        Diagnostic report as a string
    """
    options = create_coordinator_options()
    
    result_text = ""
    debug_messages: list[Any] = []
    
    logger.info(f"Starting investigation: {query_text[:100]}...")
    
    async with ClaudeSDKClient(options=options) as client:
        # Send the investigation query
        await client.query(query_text)
        
        # Process response messages
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
                debug_messages.append(message)
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    logger.error(f"Coordinator error: {message.result}")
                else:
                    logger.info(
                        f"Investigation completed in {message.duration_ms}ms, "
                        f"turns: {message.num_turns}, "
                        f"cost: ${message.total_cost_usd or 0:.4f}"
                    )
    
    # Debug mode: log all messages
    if os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"):
        logger.info("=== DEBUG MODE: Coordinator All Messages ===")
        for msg in debug_messages:
            logger.info(msg)
        logger.info("=== End Coordinator Debug Output ===")
    
    return result_text


def is_coordinator_ready() -> bool:
    """Check if the coordinator can be created."""
    try:
        create_coordinator_options()
        return True
    except Exception as e:
        logger.error(f"Coordinator not ready: {e}")
        return False
