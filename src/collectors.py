"""
Collector configuration for the multi-agent Kubernetes debugging system.

This module provides:
- Config-driven MCP server configurations
- Config-driven AgentDefinitions for use with ClaudeSDKClient
- Pre-flight validation for configuration
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

from claude_agent_sdk import AgentDefinition

from config import get_settings

if TYPE_CHECKING:
    from config_schema import MCPServerConfig, ShootConfig


# =============================================================================
# Config-Driven Agent Creation
# =============================================================================


def build_mcp_config_from_schema(
    mcp_config: MCPServerConfig,
) -> dict[str, Any]:
    """
    Build an MCP server configuration dict from a schema config.

    Supports both local command-based and remote HTTP-based MCP servers.

    Args:
        mcp_config: MCPServerConfig from the config schema

    Returns:
        Dict suitable for ClaudeAgentOptions.mcp_servers
    """
    # Remote HTTP MCP server
    if mcp_config.url:
        return {"url": mcp_config.url}

    # Local command-based MCP server
    config: dict[str, Any] = {
        "command": mcp_config.command,
        "args": list(mcp_config.args),
    }

    # Add environment variables if any (filter out empty values)
    env = {k: v for k, v in mcp_config.env.items() if v}
    if env:
        config["env"] = env
    elif mcp_config.in_cluster_fallback:
        # No env vars set but in_cluster_fallback is True
        # Add --in-cluster to args if not already present
        if "--in-cluster" not in config["args"]:
            config["args"].append("--in-cluster")

    return config


def build_mcp_servers_from_config(
    config: ShootConfig,
    assistant_name: str,
) -> dict[str, dict[str, Any]]:
    """
    Build MCP server configurations for an assistant from config.

    Includes MCP servers used by the assistant directly and by its subagents.

    Args:
        config: ShootConfig object
        assistant_name: Name of the assistant

    Returns:
        Dict of MCP server name -> configuration
    """
    assistant = config.get_assistant(assistant_name)
    mcp_servers: dict[str, dict[str, Any]] = {}

    # Collect MCP servers used directly by the assistant
    for mcp_name in assistant.mcp_servers:
        if mcp_name not in mcp_servers:
            mcp_config = config.get_mcp_server(mcp_name)
            mcp_servers[mcp_name] = build_mcp_config_from_schema(mcp_config)

    # Collect MCP servers used by the assistant's subagents
    for subagent_name in assistant.subagents:
        subagent = config.get_subagent(subagent_name)
        for mcp_name in subagent.mcp_servers:
            if mcp_name not in mcp_servers:
                mcp_config = config.get_mcp_server(mcp_name)
                mcp_servers[mcp_name] = build_mcp_config_from_schema(mcp_config)

    return mcp_servers


def get_tools_for_subagent(
    config: ShootConfig,
    subagent_name: str,
) -> list[str]:
    """
    Get the list of tool names a subagent can access.

    Args:
        config: ShootConfig object
        subagent_name: Name of the subagent

    Returns:
        List of tool names (e.g., ["mcp__kubernetes_wc__get", ...])
    """
    from config_schema import get_tools_for_mcp

    subagent = config.get_subagent(subagent_name)
    tools: list[str] = []

    for mcp_name in subagent.mcp_servers:
        mcp_config = config.get_mcp_server(mcp_name)
        tools.extend(get_tools_for_mcp(mcp_name, mcp_config.tools))

    return tools


def get_tools_for_assistant(
    config: ShootConfig,
    assistant_name: str,
) -> list[str]:
    """
    Get the list of MCP tool names an assistant can access directly.

    Args:
        config: ShootConfig object
        assistant_name: Name of the assistant

    Returns:
        List of tool names (e.g., ["mcp__kubernetes_wc__get", ...])
    """
    from config_schema import get_tools_for_mcp

    assistant = config.get_assistant(assistant_name)
    tools: list[str] = []

    for mcp_name in assistant.mcp_servers:
        mcp_config = config.get_mcp_server(mcp_name)
        tools.extend(get_tools_for_mcp(mcp_name, mcp_config.tools))

    return tools


def build_agent_definitions_from_config(
    config: ShootConfig,
    assistant_name: str,
    config_base_dir: Path,
) -> dict[str, AgentDefinition]:
    """
    Build AgentDefinitions for an assistant's subagents from config.

    Args:
        config: ShootConfig object
        assistant_name: Name of the assistant
        config_base_dir: Base directory for resolving prompt file paths

    Returns:
        Dict of subagent name -> AgentDefinition
    """
    from config_loader import get_prompt_with_variables

    assistant = config.get_assistant(assistant_name)
    agents: dict[str, AgentDefinition] = {}

    for subagent_name in assistant.subagents:
        subagent = config.get_subagent(subagent_name)

        # Load and process the prompt
        prompt = get_prompt_with_variables(
            config=config,
            base_dir=config_base_dir,
            prompt_file=subagent.system_prompt_file,
            variables={},  # Subagents don't have prompt variables currently
        )

        # Get the tools this subagent can access
        tools = get_tools_for_subagent(config, subagent_name)

        # Resolve model
        model = config.resolve_model(subagent.model, is_orchestrator=False)

        agents[subagent_name] = AgentDefinition(
            description=subagent.description.strip(),
            prompt=prompt,
            tools=tools,
            model=model,  # type: ignore[arg-type]
        )

    return agents


# =============================================================================
# Readiness Checks
# =============================================================================


def get_mcp_configs_valid() -> tuple[bool, bool]:
    """
    Check if MCP configurations are valid.

    Uses the configuration file to validate MCP servers are defined.
    Returns (wc_valid, mc_valid) tuple.
    """
    from config_loader import get_config

    config = get_config()
    if config is None:
        return False, False

    wc_valid = "kubernetes_wc" in config.mcp_servers
    mc_valid = "kubernetes_mc" in config.mcp_servers

    return wc_valid, mc_valid


def validate_wc_config() -> tuple[bool, str]:
    """
    Validate workload cluster configuration.

    Checks that KUBECONFIG is set and the file exists.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    import os

    settings = get_settings()

    if not settings.kubeconfig:
        return False, "KUBECONFIG environment variable not set"

    if not os.path.isfile(settings.kubeconfig):
        return False, f"KUBECONFIG file not found: {settings.kubeconfig}"

    return True, ""


def validate_mc_config() -> tuple[bool, str]:
    """
    Validate management cluster configuration.

    Checks either MC_KUBECONFIG file exists (local) or
    service account token is mounted (in-cluster).

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    import os

    settings = get_settings()

    # Local mode: check kubeconfig file
    if settings.mc_kubeconfig:
        if not os.path.isfile(settings.mc_kubeconfig):
            return False, f"MC_KUBECONFIG file not found: {settings.mc_kubeconfig}"
        return True, ""

    # Production mode: check for in-cluster token
    sa_token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # nosec B105
    if os.path.isfile(sa_token_path):
        return True, ""

    return (
        True,
        "Not running in-cluster (service account token not found), MC_KUBECONFIG not set",
    )


def validate_anthropic_api_key() -> tuple[bool, str]:
    """
    Validate that the Anthropic API key is configured.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        return False, "ANTHROPIC_API_KEY environment variable not set"

    # Basic format validation (API keys start with "sk-ant-")
    if not settings.anthropic_api_key.startswith("sk-ant-"):
        return (
            False,
            "ANTHROPIC_API_KEY does not appear to be a valid Anthropic API key",
        )

    return True, ""


def validate_mcp_binary() -> tuple[bool, str]:
    """
    Validate that the MCP kubernetes binary exists.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    import os

    settings = get_settings()
    mcp_path = settings.mcp_kubernetes_path
    if os.path.isfile(mcp_path) and os.access(mcp_path, os.X_OK):
        return True, ""

    return False, f"MCP kubernetes binary not found or not executable: {mcp_path}"


def run_preflight_checks() -> dict[str, dict[str, Any]]:
    """
    Run all pre-flight validation checks.

    Returns a dictionary with check results:
    {
        "wc_config": {"valid": bool, "error": str},
        "mc_config": {"valid": bool, "error": str},
        "anthropic_api": {"valid": bool, "error": str},
        "mcp_binary": {"valid": bool, "error": str},
    }
    """
    wc_valid, wc_error = validate_wc_config()
    mc_valid, mc_error = validate_mc_config()
    api_valid, api_error = validate_anthropic_api_key()
    mcp_valid, mcp_error = validate_mcp_binary()

    return {
        "wc_config": {"valid": wc_valid, "error": wc_error},
        "mc_config": {"valid": mc_valid, "error": mc_error},
        "anthropic_api": {"valid": api_valid, "error": api_error},
        "mcp_binary": {"valid": mcp_valid, "error": mcp_error},
    }
