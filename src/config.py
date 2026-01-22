"""
Centralized configuration for the Shoot agent system.

Uses Pydantic BaseSettings for validated, typed configuration with
environment variable support and sensible defaults.
"""

from functools import lru_cache

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
        description="Model for agent (reasoning/orchestration)",
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

    # Configuration file
    shoot_config: str = Field(
        default="",
        validation_alias="SHOOT_CONFIG",
        description="Path to YAML configuration file for multi-agent mode",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.

    Settings are loaded once and cached for the lifetime of the application.
    """
    return Settings()
