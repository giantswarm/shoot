"""
Collector configuration for the multi-agent Kubernetes debugging system.

This module provides:
- MCP server configurations for workload and management clusters
- AgentDefinitions for use with ClaudeSDKClient
- Pre-flight validation for configuration
"""

from typing import Any

from claude_agent_sdk import AgentDefinition

from config import get_settings, get_wc_collector_prompt, get_mc_collector_prompt


# =============================================================================
# MCP Server Configurations
# =============================================================================


def get_wc_mcp_config() -> dict[str, Any]:
    """
    Get MCP server configuration for workload cluster.

    Uses KUBECONFIG environment variable to connect to the workload cluster.
    """
    settings = get_settings()
    return {
        "command": settings.mcp_kubernetes_path,
        "args": ["serve", "--non-destructive"],
        "env": {"KUBECONFIG": settings.kubeconfig},
    }


def get_mc_mcp_config() -> dict[str, Any]:
    """
    Get MCP server configuration for management cluster.

    Uses MC_KUBECONFIG if set (local development),
    otherwise uses --in-cluster mode (production).
    """
    settings = get_settings()

    if settings.mc_kubeconfig:
        # Local development: use kubeconfig file
        return {
            "command": settings.mcp_kubernetes_path,
            "args": ["serve", "--non-destructive"],
            "env": {"KUBECONFIG": settings.mc_kubeconfig},
        }
    else:
        # Production: use in-cluster service account
        return {
            "command": settings.mcp_kubernetes_path,
            "args": ["serve", "--non-destructive", "--in-cluster"],
        }


# =============================================================================
# Agent Definitions
# =============================================================================

# MCP tool names for mcp-kubernetes server
# These are the read-only tools exposed by mcp-kubernetes in --non-destructive mode
# Tool naming convention: mcp__<server_name>__<tool_name>
WC_MCP_TOOLS = [
    "mcp__kubernetes_wc__get",
    "mcp__kubernetes_wc__list",
    "mcp__kubernetes_wc__describe",
    "mcp__kubernetes_wc__logs",
    "mcp__kubernetes_wc__events",
]

MC_MCP_TOOLS = [
    "mcp__kubernetes_mc__get",
    "mcp__kubernetes_mc__list",
    "mcp__kubernetes_mc__describe",
    "mcp__kubernetes_mc__logs",
    "mcp__kubernetes_mc__events",
]


def create_agent_definitions() -> dict[str, AgentDefinition]:
    """
    Create AgentDefinitions for the collector subagents.

    These are used with ClaudeSDKClient to define specialized subagents
    that the coordinator can delegate to via the Task tool.

    IMPORTANT: Each collector is restricted to only its own MCP server's tools
    to maintain strict isolation between workload and management clusters.
    """
    settings = get_settings()

    return {
        "wc_collector": AgentDefinition(
            description=(
                "Use this agent to collect runtime data from the WORKLOAD CLUSTER. "
                "The WC collector gathers information about Pods, Deployments, Services, "
                "ReplicaSets, events, logs, and other Kubernetes resources running in the "
                "workload cluster. Use this as your PRIMARY data source for debugging. "
                "This agent does NOT have access to management cluster resources."
            ),
            prompt=get_wc_collector_prompt(),
            tools=WC_MCP_TOOLS,  # Strict isolation: only WC MCP tools
            model=settings.collector_model,  # type: ignore[arg-type]
        ),
        "mc_collector": AgentDefinition(
            description=(
                "Use this agent to collect data from the MANAGEMENT CLUSTER. "
                "The MC collector gathers information about App/HelmRelease deployment status "
                "and CAPI/CAPA resources (Cluster, AWSCluster, Machine, MachinePool) for the "
                "workload cluster. Use this ONLY when you need to check deployment status or "
                "cluster infrastructure. This agent does NOT have access to workload cluster resources."
            ),
            prompt=get_mc_collector_prompt(),
            tools=MC_MCP_TOOLS,  # Strict isolation: only MC MCP tools
            model=settings.collector_model,  # type: ignore[arg-type]
        ),
    }


# =============================================================================
# Readiness Checks
# =============================================================================


def get_mcp_configs_valid() -> tuple[bool, bool]:
    """Check if MCP configurations are valid (configs can be created)."""
    try:
        wc_valid = get_wc_mcp_config() is not None
    except Exception:
        wc_valid = False

    try:
        mc_valid = get_mc_mcp_config() is not None
    except Exception:
        mc_valid = False

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
