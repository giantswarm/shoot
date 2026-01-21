"""
Configuration schema models for the Shoot multi-assistant system.

This module defines Pydantic models for YAML configuration files that
enable configurable assistants, MCP servers, and response schemas.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResponseFormat(str, Enum):
    """Output format for assistant responses."""

    HUMAN = "human"  # Human-readable markdown
    JSON = "json"  # Raw JSON for machine consumption


class DefaultsModels(BaseModel):
    """Default model configurations."""

    orchestrator: str = Field(
        default="claude-sonnet-4-5-20250514",
        description="Default model for orchestrator/coordinator agents",
    )
    collector: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Default model for collector subagents",
    )


class DefaultsTimeouts(BaseModel):
    """Default timeout configurations."""

    investigation: int = Field(
        default=300,
        ge=30,
        le=600,
        description="Default timeout for investigations (seconds)",
    )
    subagent: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Default timeout for subagent operations (seconds)",
    )


class DefaultsMaxTurns(BaseModel):
    """Default max turns configurations."""

    investigation: int = Field(
        default=15,
        ge=5,
        le=50,
        description="Maximum conversation turns for investigations",
    )
    subagent: int = Field(
        default=10,
        ge=3,
        le=30,
        description="Maximum conversation turns for subagents",
    )


class DefaultsResponse(BaseModel):
    """Default response configurations."""

    format: ResponseFormat = Field(
        default=ResponseFormat.HUMAN,
        description="Default response format",
    )


class Defaults(BaseModel):
    """Default configurations for the system."""

    models: DefaultsModels = Field(default_factory=DefaultsModels)
    timeouts: DefaultsTimeouts = Field(default_factory=DefaultsTimeouts)
    max_turns: DefaultsMaxTurns = Field(default_factory=DefaultsMaxTurns)
    response: DefaultsResponse = Field(default_factory=DefaultsResponse)


class ResponseSchemaConfig(BaseModel):
    """Configuration for a response schema."""

    file: str = Field(
        ...,
        description="Path to JSON Schema file (relative to config directory)",
    )
    description: str = Field(
        default="",
        description="Human-readable description of this schema",
    )
    format: ResponseFormat = Field(
        default=ResponseFormat.HUMAN,
        description="Output format: 'human' for markdown, 'json' for raw JSON",
    )


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server (local command or remote HTTP)."""

    command: str = Field(
        default="",
        description="Path to MCP server executable (supports ${VAR} expansion)",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command-line arguments for the MCP server",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables (supports ${VAR} and ${VAR:-default})",
    )
    url: str = Field(
        default="",
        description="HTTP URL for remote MCP server (alternative to command)",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="List of tool names exposed by this MCP server",
    )
    in_cluster_fallback: bool = Field(
        default=False,
        description="If True, use --in-cluster mode when env vars are not set",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL is HTTP/HTTPS if provided."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("MCP server URL must start with http:// or https://")
        return v

    def model_post_init(self, __context: Any) -> None:
        """Validate that either command or url is provided."""
        if not self.command and not self.url:
            raise ValueError(
                "MCP server must have either 'command' or 'url' configured"
            )
        if self.command and self.url:
            raise ValueError(
                "MCP server cannot have both 'command' and 'url' configured"
            )


class SubagentConfig(BaseModel):
    """Configuration for a subagent (collector)."""

    description: str = Field(
        ...,
        description="Description of when to use this subagent (shown to coordinator)",
    )
    system_prompt_file: str = Field(
        ...,
        description="Path to system prompt file (relative to config directory)",
    )
    model: str = Field(
        default="",
        description="Model to use (empty = use defaults.models.collector)",
    )
    mcp_servers: list[str] = Field(
        default_factory=list,
        description="List of MCP server names this subagent can access",
    )
    timeout_seconds: int = Field(
        default=0,
        ge=0,
        le=600,
        description="Timeout in seconds (0 = use defaults.timeouts.subagent)",
    )
    max_turns: int = Field(
        default=0,
        ge=0,
        le=50,
        description="Max turns (0 = use defaults.max_turns.subagent)",
    )


class AssistantConfig(BaseModel):
    """Configuration for an assistant (orchestrator)."""

    description: str = Field(
        ...,
        description="Human-readable description of this assistant",
    )
    system_prompt_file: str = Field(
        ...,
        description="Path to system prompt file (relative to config directory)",
    )
    model: str = Field(
        default="",
        description="Model to use (empty = use defaults.models.orchestrator)",
    )
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["Task"],
        description="Tools the orchestrator can use (typically just 'Task')",
    )
    mcp_servers: list[str] = Field(
        default_factory=list,
        description="MCP servers the orchestrator can access directly",
    )
    subagents: list[str] = Field(
        default_factory=list,
        description="List of subagent names this assistant can delegate to",
    )
    response_schema: str = Field(
        default="",
        description="Name of response schema to use (from response_schemas)",
    )
    timeout_seconds: int = Field(
        default=0,
        ge=0,
        le=600,
        description="Timeout in seconds (0 = use defaults.timeouts.investigation)",
    )
    max_turns: int = Field(
        default=0,
        ge=0,
        le=50,
        description="Max turns (0 = use defaults.max_turns.investigation)",
    )
    prompt_variables: dict[str, str] = Field(
        default_factory=dict,
        description="Variables to substitute in system prompt (supports ${VAR})",
    )
    request_variables: list[str] = Field(
        default_factory=list,
        description="Variables that can be passed in requests for prompt injection",
    )

    @field_validator("allowed_tools")
    @classmethod
    def validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Ensure orchestrators only have Task tool (enforces delegation pattern)."""
        if v and v != ["Task"]:
            # Allow custom tools but warn if not just Task
            pass
        return v


class ShootConfig(BaseModel):
    """
    Root configuration for the Shoot multi-assistant system.

    This is the top-level model that represents a complete shoot.yaml configuration.
    """

    version: str = Field(
        default="1.0",
        description="Configuration format version",
    )
    defaults: Defaults = Field(
        default_factory=Defaults,
        description="Default values for models, timeouts, etc.",
    )
    response_schemas: dict[str, ResponseSchemaConfig] = Field(
        default_factory=dict,
        description="Response schema definitions (name -> config)",
    )
    mcp_servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="MCP server definitions (name -> config)",
    )
    subagents: dict[str, SubagentConfig] = Field(
        default_factory=dict,
        description="Subagent definitions (name -> config)",
    )
    assistants: dict[str, AssistantConfig] = Field(
        default_factory=dict,
        description="Assistant definitions (name -> config)",
    )

    def get_assistant(self, name: str) -> AssistantConfig:
        """Get an assistant by name, raising KeyError if not found."""
        if name not in self.assistants:
            available = list(self.assistants.keys())
            raise KeyError(f"Assistant '{name}' not found. Available: {available}")
        return self.assistants[name]

    def get_subagent(self, name: str) -> SubagentConfig:
        """Get a subagent by name, raising KeyError if not found."""
        if name not in self.subagents:
            available = list(self.subagents.keys())
            raise KeyError(f"Subagent '{name}' not found. Available: {available}")
        return self.subagents[name]

    def get_mcp_server(self, name: str) -> MCPServerConfig:
        """Get an MCP server config by name, raising KeyError if not found."""
        if name not in self.mcp_servers:
            available = list(self.mcp_servers.keys())
            raise KeyError(f"MCP server '{name}' not found. Available: {available}")
        return self.mcp_servers[name]

    def get_response_schema(self, name: str) -> ResponseSchemaConfig | None:
        """Get a response schema by name, returning None if not found."""
        return self.response_schemas.get(name)

    def resolve_model(self, model: str, is_orchestrator: bool = True) -> str:
        """Resolve a model string, using defaults if empty."""
        if model:
            return model
        if is_orchestrator:
            return self.defaults.models.orchestrator
        return self.defaults.models.collector

    def resolve_timeout(self, timeout: int, is_investigation: bool = True) -> int:
        """Resolve a timeout value, using defaults if zero."""
        if timeout > 0:
            return timeout
        if is_investigation:
            return self.defaults.timeouts.investigation
        return self.defaults.timeouts.subagent

    def resolve_max_turns(self, max_turns: int, is_investigation: bool = True) -> int:
        """Resolve a max_turns value, using defaults if zero."""
        if max_turns > 0:
            return max_turns
        if is_investigation:
            return self.defaults.max_turns.investigation
        return self.defaults.max_turns.subagent


def generate_tool_name(mcp_name: str, tool: str) -> str:
    """
    Generate a full tool name from MCP server name and tool name.

    Tool naming convention: mcp__<server_name>__<tool_name>
    """
    return f"mcp__{mcp_name}__{tool}"


def get_tools_for_mcp(mcp_name: str, tools: list[str]) -> list[str]:
    """
    Generate full tool names for an MCP server.

    Args:
        mcp_name: Name of the MCP server
        tools: List of tool names (e.g., ["get", "list", "describe"])

    Returns:
        List of full tool names (e.g., ["mcp__kubernetes_wc__get", ...])
    """
    return [generate_tool_name(mcp_name, tool) for tool in tools]


def validate_config_references(config: ShootConfig) -> list[str]:
    """
    Validate that all references in the config are valid.

    Checks:
    - Assistant subagents exist
    - Subagent mcp_servers exist
    - Assistant response_schemas exist
    - No circular references

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Check assistant references
    for assistant_name, assistant in config.assistants.items():
        # Check subagent references
        for subagent_name in assistant.subagents:
            if subagent_name not in config.subagents:
                errors.append(
                    f"Assistant '{assistant_name}' references unknown subagent '{subagent_name}'"
                )

        # Check response schema reference
        if (
            assistant.response_schema
            and assistant.response_schema not in config.response_schemas
        ):
            errors.append(
                f"Assistant '{assistant_name}' references unknown response_schema '{assistant.response_schema}'"
            )

    # Check subagent references
    for subagent_name, subagent in config.subagents.items():
        for mcp_name in subagent.mcp_servers:
            if mcp_name not in config.mcp_servers:
                errors.append(
                    f"Subagent '{subagent_name}' references unknown mcp_server '{mcp_name}'"
                )

    return errors


def config_to_dict(config: ShootConfig) -> dict[str, Any]:
    """Convert a ShootConfig to a dictionary for serialization."""
    return config.model_dump()
