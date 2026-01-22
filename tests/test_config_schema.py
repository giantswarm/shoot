"""Tests for config_schema.py"""

import sys
from pathlib import Path

import pytest  # noqa: F401

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_schema import (  # noqa: E402
    ShootConfig,
    MCPServerConfig,
    SubagentConfig,
    AgentConfig,
    ResponseSchemaConfig,
    ResponseFormat,
    Defaults,
    validate_config_references,
    generate_tool_name,
    get_tools_for_mcp,
)


class TestResponseFormat:
    """Tests for ResponseFormat enum."""

    def test_human_format(self) -> None:
        assert ResponseFormat.HUMAN.value == "human"

    def test_json_format(self) -> None:
        assert ResponseFormat.JSON.value == "json"


class TestDefaults:
    """Tests for Defaults model."""

    def test_default_values(self) -> None:
        defaults = Defaults()
        assert defaults.models.orchestrator == "claude-sonnet-4-5-20250514"
        assert defaults.models.collector == "claude-3-5-haiku-20241022"
        assert defaults.timeouts.investigation == 300
        assert defaults.timeouts.subagent == 60
        assert defaults.max_turns.investigation == 15
        assert defaults.max_turns.subagent == 10
        assert defaults.response.format == ResponseFormat.HUMAN


class TestMCPServerConfig:
    """Tests for MCPServerConfig model."""

    def test_minimal_config(self) -> None:
        config = MCPServerConfig(command="/usr/bin/mcp")
        assert config.command == "/usr/bin/mcp"
        assert config.args == []
        assert config.env == {}
        assert config.tools == []

    def test_full_config(self) -> None:
        config = MCPServerConfig(
            command="/usr/bin/mcp",
            args=["serve", "--non-destructive"],
            env={"KUBECONFIG": "/path/to/config"},
            tools=["get", "list", "describe"],
        )
        assert config.command == "/usr/bin/mcp"
        assert config.args == ["serve", "--non-destructive"]
        assert config.env == {"KUBECONFIG": "/path/to/config"}
        assert config.tools == ["get", "list", "describe"]


class TestSubagentConfig:
    """Tests for SubagentConfig model."""

    def test_minimal_config(self) -> None:
        config = SubagentConfig(
            description="Test subagent",
            system_prompt_file="prompts/test.md",
        )
        assert config.description == "Test subagent"
        assert config.system_prompt_file == "prompts/test.md"
        assert config.model == ""
        assert config.mcp_servers == []
        assert config.allowed_tools == []
        assert config.prompt_variables == {}
        assert config.request_variables == []
        assert config.response_schema == ""

    def test_full_config(self) -> None:
        config = SubagentConfig(
            description="Test subagent",
            system_prompt_file="prompts/test.md",
            model="claude-3-5-haiku-20241022",
            mcp_servers=["kubernetes_wc"],
            allowed_tools=["mcp__kubernetes_wc__get", "mcp__kubernetes_wc__list"],
            prompt_variables={"CLUSTER_NAME": "test-cluster"},
            request_variables=["namespace"],
            response_schema="diagnostic_report",
        )
        assert config.mcp_servers == ["kubernetes_wc"]
        assert config.allowed_tools == [
            "mcp__kubernetes_wc__get",
            "mcp__kubernetes_wc__list",
        ]
        assert config.prompt_variables == {"CLUSTER_NAME": "test-cluster"}
        assert config.request_variables == ["namespace"]
        assert config.response_schema == "diagnostic_report"


class TestAgentConfig:
    """Tests for AgentConfig model."""

    def test_minimal_config(self) -> None:
        config = AgentConfig(
            description="Test agent",
            system_prompt_file="prompts/coordinator.md",
        )
        assert config.description == "Test agent"
        assert config.allowed_tools == ["Task"]
        assert config.subagents == []
        assert config.response_schema == ""

    def test_full_config(self) -> None:
        config = AgentConfig(
            description="Test agent",
            system_prompt_file="prompts/coordinator.md",
            model="claude-sonnet-4-5-20250514",
            allowed_tools=["Task"],
            subagents=["wc_collector", "mc_collector"],
            response_schema="diagnostic_report",
            timeout_seconds=300,
            max_turns=15,
            prompt_variables={"WC_CLUSTER": "test-cluster"},
            request_variables=["alertname", "namespace"],
        )
        assert config.subagents == ["wc_collector", "mc_collector"]
        assert config.response_schema == "diagnostic_report"
        assert config.prompt_variables == {"WC_CLUSTER": "test-cluster"}
        assert config.request_variables == ["alertname", "namespace"]


class TestResponseSchemaConfig:
    """Tests for ResponseSchemaConfig model."""

    def test_human_format(self) -> None:
        config = ResponseSchemaConfig(
            file="schemas/diagnostic_report.json",
            description="Human-friendly report",
            format=ResponseFormat.HUMAN,
        )
        assert config.format == ResponseFormat.HUMAN

    def test_json_format(self) -> None:
        config = ResponseSchemaConfig(
            file="schemas/e2e_result.json",
            description="Machine-readable result",
            format=ResponseFormat.JSON,
        )
        assert config.format == ResponseFormat.JSON


class TestShootConfig:
    """Tests for ShootConfig model."""

    def test_minimal_config(self) -> None:
        config = ShootConfig()
        assert config.version == "1.0"
        assert config.mcp_servers == {}
        assert config.subagents == {}
        assert config.agents == {}

    def test_full_config(self) -> None:
        config = ShootConfig(
            version="1.0",
            mcp_servers={
                "kubernetes_wc": MCPServerConfig(
                    command="/usr/bin/mcp",
                    tools=["get", "list"],
                ),
            },
            subagents={
                "wc_collector": SubagentConfig(
                    description="WC collector",
                    system_prompt_file="prompts/wc.md",
                    mcp_servers=["kubernetes_wc"],
                ),
            },
            agents={
                "kubernetes_debugger": AgentConfig(
                    description="K8s debugger",
                    system_prompt_file="prompts/coord.md",
                    subagents=["wc_collector"],
                ),
            },
        )
        assert "kubernetes_wc" in config.mcp_servers
        assert "wc_collector" in config.subagents
        assert "kubernetes_debugger" in config.agents

    def test_get_agent(self) -> None:
        config = ShootConfig(
            agents={
                "test": AgentConfig(
                    description="Test",
                    system_prompt_file="test.md",
                ),
            },
        )
        agent = config.get_agent("test")
        assert agent.description == "Test"

    def test_get_agent_not_found(self) -> None:
        config = ShootConfig()
        with pytest.raises(KeyError):
            config.get_agent("nonexistent")

    def test_resolve_model_default(self) -> None:
        config = ShootConfig()
        assert (
            config.resolve_model("", is_orchestrator=True)
            == "claude-sonnet-4-5-20250514"
        )
        assert (
            config.resolve_model("", is_orchestrator=False)
            == "claude-3-5-haiku-20241022"
        )

    def test_resolve_model_custom(self) -> None:
        config = ShootConfig()
        assert (
            config.resolve_model("custom-model", is_orchestrator=True) == "custom-model"
        )

    def test_resolve_timeout_default(self) -> None:
        config = ShootConfig()
        assert config.resolve_timeout(0, is_investigation=True) == 300
        assert config.resolve_timeout(0, is_investigation=False) == 60

    def test_resolve_timeout_custom(self) -> None:
        config = ShootConfig()
        assert config.resolve_timeout(120, is_investigation=True) == 120


class TestValidateConfigReferences:
    """Tests for validate_config_references function."""

    def test_valid_references(self) -> None:
        config = ShootConfig(
            mcp_servers={
                "kubernetes_wc": MCPServerConfig(command="/usr/bin/mcp"),
            },
            subagents={
                "wc_collector": SubagentConfig(
                    description="WC",
                    system_prompt_file="wc.md",
                    mcp_servers=["kubernetes_wc"],
                ),
            },
            agents={
                "debugger": AgentConfig(
                    description="Debug",
                    system_prompt_file="coord.md",
                    subagents=["wc_collector"],
                ),
            },
        )
        errors = validate_config_references(config)
        assert errors == []

    def test_invalid_subagent_reference(self) -> None:
        config = ShootConfig(
            agents={
                "debugger": AgentConfig(
                    description="Debug",
                    system_prompt_file="coord.md",
                    subagents=["nonexistent"],
                ),
            },
        )
        errors = validate_config_references(config)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_invalid_mcp_reference(self) -> None:
        config = ShootConfig(
            subagents={
                "wc_collector": SubagentConfig(
                    description="WC",
                    system_prompt_file="wc.md",
                    mcp_servers=["nonexistent"],
                ),
            },
        )
        errors = validate_config_references(config)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]


class TestToolNameGeneration:
    """Tests for tool name generation functions."""

    def test_generate_tool_name(self) -> None:
        assert generate_tool_name("kubernetes_wc", "get") == "mcp__kubernetes_wc__get"
        assert generate_tool_name("prometheus", "query") == "mcp__prometheus__query"

    def test_get_tools_for_mcp(self) -> None:
        tools = get_tools_for_mcp("kubernetes_wc", ["get", "list", "describe"])
        assert tools == [
            "mcp__kubernetes_wc__get",
            "mcp__kubernetes_wc__list",
            "mcp__kubernetes_wc__describe",
        ]

    def test_get_tools_for_mcp_empty(self) -> None:
        tools = get_tools_for_mcp("test", [])
        assert tools == []
