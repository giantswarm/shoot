"""Tests for config_loader.py"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_loader import (  # noqa: E402
    expand_env_var,
    expand_env_vars_recursive,
    find_unexpanded_vars,
    load_yaml_file,
    load_json_schema,
    load_config,
    ConfigError,
    clear_config_cache,
)


class TestExpandEnvVar:
    """Tests for expand_env_var function."""

    def test_simple_expansion(self) -> None:
        env = {"MY_VAR": "my_value"}
        result = expand_env_var("prefix_${MY_VAR}_suffix", env)
        assert result == "prefix_my_value_suffix"

    def test_multiple_expansions(self) -> None:
        env = {"VAR1": "one", "VAR2": "two"}
        result = expand_env_var("${VAR1}_${VAR2}", env)
        assert result == "one_two"

    def test_default_value(self) -> None:
        env: dict[str, str] = {}
        result = expand_env_var("${MY_VAR:-default_value}", env)
        assert result == "default_value"

    def test_default_value_not_used(self) -> None:
        env = {"MY_VAR": "actual_value"}
        result = expand_env_var("${MY_VAR:-default_value}", env)
        assert result == "actual_value"

    def test_empty_default(self) -> None:
        env: dict[str, str] = {}
        result = expand_env_var("${MY_VAR:-}", env)
        assert result == ""

    def test_no_expansion_needed(self) -> None:
        env: dict[str, str] = {}
        result = expand_env_var("no_variables_here", env)
        assert result == "no_variables_here"

    def test_undefined_without_default(self) -> None:
        env: dict[str, str] = {}
        result = expand_env_var("${UNDEFINED_VAR}", env)
        # Returns original pattern if no default and not in env
        assert result == "${UNDEFINED_VAR}"

    def test_uses_os_environ_by_default(self) -> None:
        os.environ["TEST_CONFIG_VAR"] = "test_value"
        try:
            result = expand_env_var("${TEST_CONFIG_VAR}")
            assert result == "test_value"
        finally:
            del os.environ["TEST_CONFIG_VAR"]


class TestExpandEnvVarsRecursive:
    """Tests for expand_env_vars_recursive function."""

    def test_dict_expansion(self) -> None:
        env = {"VAR": "value"}
        obj = {"key": "${VAR}"}
        result = expand_env_vars_recursive(obj, env)
        assert result == {"key": "value"}

    def test_nested_dict_expansion(self) -> None:
        env = {"VAR": "value"}
        obj = {"outer": {"inner": "${VAR}"}}
        result = expand_env_vars_recursive(obj, env)
        assert result == {"outer": {"inner": "value"}}

    def test_list_expansion(self) -> None:
        env = {"VAR": "value"}
        obj = ["${VAR}", "static"]
        result = expand_env_vars_recursive(obj, env)
        assert result == ["value", "static"]

    def test_mixed_expansion(self) -> None:
        env = {"A": "1", "B": "2"}
        obj = {
            "items": ["${A}", "${B}"],
            "nested": {"value": "${A}"},
        }
        result = expand_env_vars_recursive(obj, env)
        assert result == {
            "items": ["1", "2"],
            "nested": {"value": "1"},
        }

    def test_non_string_passthrough(self) -> None:
        env: dict[str, str] = {}
        obj = {"number": 42, "boolean": True, "none": None}
        result = expand_env_vars_recursive(obj, env)
        assert result == {"number": 42, "boolean": True, "none": None}


class TestFindUnexpandedVars:
    """Tests for find_unexpanded_vars function."""

    def test_no_unexpanded(self) -> None:
        obj = {"key": "value"}
        errors = find_unexpanded_vars(obj)
        assert errors == []

    def test_unexpanded_in_string(self) -> None:
        obj = {"key": "${MISSING}"}
        errors = find_unexpanded_vars(obj)
        assert len(errors) == 1
        assert "MISSING" in errors[0]

    def test_unexpanded_in_nested(self) -> None:
        obj = {"outer": {"inner": "${MISSING}"}}
        errors = find_unexpanded_vars(obj)
        assert len(errors) == 1
        assert "outer.inner" in errors[0]

    def test_unexpanded_in_list(self) -> None:
        obj = {"items": ["${MISSING}"]}
        errors = find_unexpanded_vars(obj)
        assert len(errors) == 1
        assert "items[0]" in errors[0]

    def test_default_not_flagged(self) -> None:
        # Variables with defaults are already handled
        obj = {"key": "${VAR:-default}"}
        errors = find_unexpanded_vars(obj)
        # The pattern ${VAR:-default} won't match ${VAR} (no default pattern)
        assert errors == []


class TestLoadYamlFile:
    """Tests for load_yaml_file function."""

    def test_load_valid_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\nitems:\n  - one\n  - two\n")
            f.flush()
            try:
                result = load_yaml_file(Path(f.name))
                assert result == {"key": "value", "items": ["one", "two"]}
            finally:
                os.unlink(f.name)

    def test_load_empty_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            try:
                result = load_yaml_file(Path(f.name))
                assert result == {}
            finally:
                os.unlink(f.name)

    def test_file_not_found(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            load_yaml_file(Path("/nonexistent/file.yaml"))
        assert "not found" in str(exc_info.value)

    def test_invalid_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: :")
            f.flush()
            try:
                with pytest.raises(ConfigError) as exc_info:
                    load_yaml_file(Path(f.name))
                assert "Invalid YAML" in str(exc_info.value)
            finally:
                os.unlink(f.name)


class TestLoadJsonSchema:
    """Tests for load_json_schema function."""

    def test_load_valid_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"type": "object", "properties": {"name": {"type": "string"}}}')
            f.flush()
            try:
                result = load_json_schema(Path(f.name))
                assert result["type"] == "object"
                assert "properties" in result
            finally:
                os.unlink(f.name)

    def test_file_not_found(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            load_json_schema(Path("/nonexistent/schema.json"))
        assert "not found" in str(exc_info.value)

    def test_invalid_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json}")
            f.flush()
            try:
                with pytest.raises(ConfigError) as exc_info:
                    load_json_schema(Path(f.name))
                assert "Invalid JSON" in str(exc_info.value)
            finally:
                os.unlink(f.name)


class TestLoadConfig:
    """Tests for load_config function."""

    def setup_method(self) -> None:
        """Clear config cache before each test."""
        clear_config_cache()

    def test_load_minimal_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shoot.yaml"
            config_path.write_text("version: '1.0'\n")

            config = load_config(config_path)
            assert config.version == "1.0"

    def test_load_config_with_env_vars(self) -> None:
        env = {"MY_MODEL": "custom-model"}
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shoot.yaml"
            config_path.write_text(
                """
version: '1.0'
defaults:
  models:
    orchestrator: ${MY_MODEL}
"""
            )

            config = load_config(config_path, env=env)
            assert config.defaults.models.orchestrator == "custom-model"

    def test_strict_mode_fails_on_unexpanded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shoot.yaml"
            config_path.write_text(
                """
version: '1.0'
defaults:
  models:
    orchestrator: ${UNDEFINED_VAR}
"""
            )

            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path, strict=True)
            assert "unexpanded" in str(exc_info.value).lower()

    def test_invalid_references_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shoot.yaml"
            config_path.write_text(
                """
version: '1.0'
agents:
  test:
    description: Test
    system_prompt_file: prompt.md
    subagents: [nonexistent]
"""
            )

            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)
            assert "invalid references" in str(exc_info.value).lower()

    def test_missing_prompt_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shoot.yaml"
            config_path.write_text(
                """
version: '1.0'
agents:
  test:
    description: Test
    system_prompt_file: nonexistent.md
"""
            )

            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)
            assert "missing files" in str(exc_info.value).lower()
