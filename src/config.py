"""
Centralized configuration for the Shoot agent system.

Uses Pydantic BaseSettings for validated, typed configuration with
environment variable support and sensible defaults.
"""

from functools import lru_cache
from pathlib import Path
from string import Template

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All configuration is centralized here for easier management
    and validation at startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic API
    anthropic_api_key: str = Field(
        default="",
        validation_alias="ANTHROPIC_API_KEY",
        description="Anthropic API key for Claude models",
    )
    coordinator_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        validation_alias="ANTHROPIC_COORDINATOR_MODEL",
        description="Model for coordinator agent (reasoning/orchestration)",
    )
    collector_model: str = Field(
        default="claude-3-5-haiku-20241022",
        validation_alias="ANTHROPIC_COLLECTOR_MODEL",
        description="Model for collector agents (data gathering)",
    )

    # Kubernetes
    kubeconfig: str = Field(
        default="",
        validation_alias="KUBECONFIG",
        description="Path to workload cluster kubeconfig",
    )
    mc_kubeconfig: str = Field(
        default="",
        validation_alias="MC_KUBECONFIG",
        description="Path to management cluster kubeconfig (optional, uses in-cluster if not set)",
    )
    mcp_kubernetes_path: str = Field(
        default="/usr/local/bin/mcp-kubernetes",
        validation_alias="MCP_KUBERNETES_PATH",
        description="Path to mcp-kubernetes binary",
    )
    wc_cluster: str = Field(
        default="workload cluster",
        validation_alias="WC_CLUSTER",
        description="Workload cluster name for prompt substitution",
    )
    org_ns: str = Field(
        default="organization namespace",
        validation_alias="ORG_NS",
        description="Organization namespace for prompt substitution",
    )

    # Investigation defaults
    timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=600,
        validation_alias="SHOOT_TIMEOUT_SECONDS",
        description="Default timeout for investigations (seconds)",
    )
    max_turns: int = Field(
        default=15,
        ge=5,
        le=50,
        validation_alias="SHOOT_MAX_TURNS",
        description="Maximum conversation turns per investigation",
    )

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = Field(
        default="",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
        description="OTLP endpoint for telemetry export",
    )
    otel_service_name: str = Field(
        default="shoot",
        validation_alias="OTEL_SERVICE_NAME",
        description="Service name for telemetry",
    )

    # Development
    debug: bool = Field(
        default=False,
        validation_alias="DEBUG",
        description="Enable debug mode for verbose logging",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.

    Settings are loaded once and cached for the lifetime of the application.
    """
    return Settings()


# =============================================================================
# Prompt Caching
# =============================================================================

# Prompts are loaded once at module import time and cached
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load a prompt file from the prompts directory."""
    return (_PROMPTS_DIR / filename).read_text()


# Cache prompt templates at module load
_COORDINATOR_PROMPT_TEMPLATE: str | None = None
_WC_COLLECTOR_PROMPT_TEMPLATE: str | None = None
_MC_COLLECTOR_PROMPT_TEMPLATE: str | None = None


def _ensure_prompts_loaded() -> None:
    """Load prompt templates if not already loaded."""
    global _COORDINATOR_PROMPT_TEMPLATE, _WC_COLLECTOR_PROMPT_TEMPLATE, _MC_COLLECTOR_PROMPT_TEMPLATE

    if _COORDINATOR_PROMPT_TEMPLATE is None:
        _COORDINATOR_PROMPT_TEMPLATE = _load_prompt("coordinator_prompt.md")
    if _WC_COLLECTOR_PROMPT_TEMPLATE is None:
        _WC_COLLECTOR_PROMPT_TEMPLATE = _load_prompt("wc_collector_prompt.md")
    if _MC_COLLECTOR_PROMPT_TEMPLATE is None:
        _MC_COLLECTOR_PROMPT_TEMPLATE = _load_prompt("mc_collector_prompt.md")


def get_coordinator_prompt() -> str:
    """Get the coordinator system prompt with variable substitution."""
    _ensure_prompts_loaded()
    prompt_template = _COORDINATOR_PROMPT_TEMPLATE
    assert prompt_template is not None
    settings = get_settings()
    template = Template(prompt_template)
    return template.safe_substitute(
        WC_CLUSTER=settings.wc_cluster,
        ORG_NS=settings.org_ns,
    )


def get_wc_collector_prompt() -> str:
    """Get the WC collector system prompt with variable substitution."""
    _ensure_prompts_loaded()
    prompt_template = _WC_COLLECTOR_PROMPT_TEMPLATE
    assert prompt_template is not None
    settings = get_settings()
    template = Template(prompt_template)
    return template.safe_substitute(
        WC_CLUSTER=settings.wc_cluster,
    )


def get_mc_collector_prompt() -> str:
    """Get the MC collector system prompt with variable substitution."""
    _ensure_prompts_loaded()
    prompt_template = _MC_COLLECTOR_PROMPT_TEMPLATE
    assert prompt_template is not None
    settings = get_settings()
    template = Template(prompt_template)
    return template.safe_substitute(
        WC_CLUSTER=settings.wc_cluster,
        ORG_NS=settings.org_ns,
    )


# Eagerly load prompts at import time
try:
    _ensure_prompts_loaded()
except FileNotFoundError:
    # Allow import to succeed even if prompts don't exist (for testing)
    pass
