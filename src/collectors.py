"""
Collector configuration for the multi-agent Kubernetes debugging system.

This module provides:
- MCP server configurations for workload and management clusters
- System prompts for collector agents
- AgentDefinitions for use with ClaudeSDKClient
"""

import os
from string import Template
from typing import Any

from claude_agent_sdk import AgentDefinition


# =============================================================================
# MCP Server Configurations
# =============================================================================

def get_wc_mcp_config() -> dict[str, Any]:
    """
    Get MCP server configuration for workload cluster.
    
    Uses KUBECONFIG environment variable to connect to the workload cluster.
    """
    return {
        "command": "/usr/local/bin/mcp-kubernetes",
        "args": ["serve", "--non-destructive"],
        "env": {"KUBECONFIG": os.environ.get("KUBECONFIG", "")}
    }


def get_mc_mcp_config() -> dict[str, Any]:
    """
    Get MCP server configuration for management cluster.
    
    Uses --in-cluster mode to connect to the management cluster
    where this pod is running.
    """
    return {
        "command": "/usr/local/bin/mcp-kubernetes",
        "args": ["serve", "--non-destructive", "--in-cluster"]
    }


# =============================================================================
# System Prompts
# =============================================================================

def _get_wc_system_prompt() -> str:
    """Load and substitute the WC collector system prompt."""
    prompt_template = Template(open('prompts/wc_collector_prompt.md').read())
    return prompt_template.safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
    )


def _get_mc_system_prompt() -> str:
    """Load and substitute the MC collector system prompt."""
    prompt_template = Template(open('prompts/mc_collector_prompt.md').read())
    return prompt_template.safe_substitute(
        WC_CLUSTER=os.environ.get('WC_CLUSTER', 'workload cluster'),
        ORG_NS=os.environ.get('ORG_NS', 'organization namespace'),
    )


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
    collector_model = os.environ.get('ANTHROPIC_COLLECTOR_MODEL', 'claude-3-5-haiku-20241022')
    
    return {
        "wc_collector": AgentDefinition(
            description=(
                "Use this agent to collect runtime data from the WORKLOAD CLUSTER. "
                "The WC collector gathers information about Pods, Deployments, Services, "
                "ReplicaSets, events, logs, and other Kubernetes resources running in the "
                "workload cluster. Use this as your PRIMARY data source for debugging. "
                "This agent does NOT have access to management cluster resources."
            ),
            prompt=_get_wc_system_prompt(),
            tools=WC_MCP_TOOLS,  # Strict isolation: only WC MCP tools
            model=collector_model,
        ),
        "mc_collector": AgentDefinition(
            description=(
                "Use this agent to collect data from the MANAGEMENT CLUSTER. "
                "The MC collector gathers information about App/HelmRelease deployment status "
                "and CAPI/CAPA resources (Cluster, AWSCluster, Machine, MachinePool) for the "
                "workload cluster. Use this ONLY when you need to check deployment status or "
                "cluster infrastructure. This agent does NOT have access to workload cluster resources."
            ),
            prompt=_get_mc_system_prompt(),
            tools=MC_MCP_TOOLS,  # Strict isolation: only MC MCP tools
            model=collector_model,
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
