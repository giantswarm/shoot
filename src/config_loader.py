"""
Configuration loader for the Shoot multi-assistant system.

This module handles:
- Loading YAML configuration files
- Environment variable expansion (${VAR} and ${VAR:-default})
- Configuration validation
- JSON Schema loading for response schemas
"""

import json
import os
import re
from pathlib import Path
from string import Template
from typing import Any

import yaml

from config_schema import (
    ShootConfig,
    validate_config_references,
)


class ConfigError(Exception):
    """Raised when configuration loading or validation fails."""

    pass


def expand_env_var(value: str, env: dict[str, str] | None = None) -> str:
    """
    Expand environment variables in a string.

    Supports:
    - ${VAR} - required variable
    - ${VAR:-default} - variable with default value

    Args:
        value: String containing ${VAR} patterns
        env: Optional dict of environment variables (defaults to os.environ)

    Returns:
        String with variables expanded
    """
    if env is None:
        env = dict(os.environ)

    # Pattern for ${VAR:-default} with optional default
    pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}"

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)

        if var_name in env:
            return env[var_name]
        elif default is not None:
            return default
        else:
            # Return the original pattern if no default and not in env
            # This allows for later expansion or detection of missing vars
            return match.group(0)

    return re.sub(pattern, replacer, value)


def expand_env_vars_recursive(obj: Any, env: dict[str, str] | None = None) -> Any:
    """
    Recursively expand environment variables in a data structure.

    Args:
        obj: Dict, list, or string to expand
        env: Optional dict of environment variables

    Returns:
        Data structure with all string values expanded
    """
    if isinstance(obj, str):
        return expand_env_var(obj, env)
    elif isinstance(obj, dict):
        return {k: expand_env_vars_recursive(v, env) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars_recursive(item, env) for item in obj]
    else:
        return obj


def find_unexpanded_vars(obj: Any, path: str = "") -> list[str]:
    """
    Find any unexpanded environment variables in a data structure.

    Args:
        obj: Data structure to check
        path: Current path for error messages

    Returns:
        List of error messages for unexpanded variables
    """
    errors: list[str] = []

    if isinstance(obj, str):
        # Only report variables without defaults
        no_default_pattern = r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}"
        matches = re.findall(no_default_pattern, obj)
        for var in matches:
            errors.append(f"Unexpanded environment variable ${{{var}}} at {path}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            errors.extend(find_unexpanded_vars(v, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            errors.extend(find_unexpanded_vars(item, f"{path}[{i}]"))

    return errors


def load_yaml_file(path: Path) -> dict[str, Any]:
    """
    Load a YAML file and return its contents as a dict.

    Args:
        path: Path to YAML file

    Returns:
        Parsed YAML content

    Raises:
        ConfigError: If file not found or invalid YAML
    """
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with open(path) as f:
            content = yaml.safe_load(f)
            if content is None:
                return {}
            if not isinstance(content, dict):
                raise ConfigError(
                    f"Configuration file must contain a YAML mapping: {path}"
                )
            return content
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e


def load_json_schema(path: Path) -> dict[str, Any]:
    """
    Load a JSON Schema file.

    Args:
        path: Path to JSON Schema file

    Returns:
        Parsed JSON Schema

    Raises:
        ConfigError: If file not found or invalid JSON
    """
    if not path.exists():
        raise ConfigError(f"JSON Schema file not found: {path}")

    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e


def load_prompt_file(path: Path) -> str:
    """
    Load a prompt file.

    Args:
        path: Path to prompt file

    Returns:
        Prompt content as string

    Raises:
        ConfigError: If file not found
    """
    if not path.exists():
        raise ConfigError(f"Prompt file not found: {path}")

    return path.read_text()


def resolve_path(base_dir: Path, relative_path: str) -> Path:
    """
    Resolve a relative path against a base directory.

    Args:
        base_dir: Base directory (typically config file's parent)
        relative_path: Relative path from config

    Returns:
        Resolved absolute path
    """
    return (base_dir / relative_path).resolve()


def load_config(
    config_path: Path | str,
    env: dict[str, str] | None = None,
    strict: bool = False,
) -> ShootConfig:
    """
    Load and validate a Shoot configuration file.

    Args:
        config_path: Path to YAML configuration file
        env: Optional dict of environment variables (defaults to os.environ)
        strict: If True, fail on unexpanded environment variables

    Returns:
        Validated ShootConfig object

    Raises:
        ConfigError: If loading or validation fails
    """
    config_path = Path(config_path)
    base_dir = config_path.parent

    # Load raw YAML
    raw_config = load_yaml_file(config_path)

    # Expand environment variables
    expanded_config = expand_env_vars_recursive(raw_config, env)

    # Check for unexpanded variables in strict mode
    if strict:
        unexpanded = find_unexpanded_vars(expanded_config)
        if unexpanded:
            raise ConfigError(
                "Configuration has unexpanded variables:\n" + "\n".join(unexpanded)
            )

    # Parse with Pydantic
    try:
        config = ShootConfig.model_validate(expanded_config)
    except Exception as e:
        raise ConfigError(f"Configuration validation failed: {e}") from e

    # Validate references
    ref_errors = validate_config_references(config)
    if ref_errors:
        raise ConfigError(
            "Configuration has invalid references:\n" + "\n".join(ref_errors)
        )

    # Validate that referenced files exist
    file_errors = validate_file_references(config, base_dir)
    if file_errors:
        raise ConfigError(
            "Configuration references missing files:\n" + "\n".join(file_errors)
        )

    return config


def validate_file_references(config: ShootConfig, base_dir: Path) -> list[str]:
    """
    Validate that all file references in the config exist.

    Args:
        config: Validated ShootConfig
        base_dir: Base directory for resolving relative paths

    Returns:
        List of error messages for missing files
    """
    errors: list[str] = []

    # Check response schema files
    for name, schema_config in config.response_schemas.items():
        path = resolve_path(base_dir, schema_config.file)
        if not path.exists():
            errors.append(f"Response schema '{name}' file not found: {path}")

    # Check assistant prompt files
    for name, assistant in config.assistants.items():
        path = resolve_path(base_dir, assistant.system_prompt_file)
        if not path.exists():
            errors.append(f"Assistant '{name}' prompt file not found: {path}")

    # Check subagent prompt files
    for name, subagent in config.subagents.items():
        path = resolve_path(base_dir, subagent.system_prompt_file)
        if not path.exists():
            errors.append(f"Subagent '{name}' prompt file not found: {path}")

    return errors


def get_prompt_with_variables(
    config: ShootConfig,
    base_dir: Path,
    prompt_file: str,
    variables: dict[str, str],
    env: dict[str, str] | None = None,
) -> str:
    """
    Load a prompt file and substitute variables.

    Args:
        config: ShootConfig for defaults
        base_dir: Base directory for resolving paths
        prompt_file: Relative path to prompt file
        variables: Dict of variables to substitute
        env: Optional environment variables for ${VAR} expansion

    Returns:
        Prompt with variables substituted
    """
    path = resolve_path(base_dir, prompt_file)
    prompt = load_prompt_file(path)

    # First expand environment variables
    prompt = expand_env_var(prompt, env)

    # Then substitute template variables using safe_substitute
    template = Template(prompt)
    return template.safe_substitute(variables)


# Global config cache
_config_cache: ShootConfig | None = None
_config_path_cache: Path | None = None


def get_config(
    config_path: Path | str | None = None,
    env: dict[str, str] | None = None,
    force_reload: bool = False,
) -> ShootConfig | None:
    """
    Get the global configuration, loading it if necessary.

    Args:
        config_path: Optional path to config file (uses SHOOT_CONFIG env var if not provided)
        env: Optional environment variables
        force_reload: If True, reload even if cached

    Returns:
        ShootConfig if config file exists, None if not configured
    """
    global _config_cache, _config_path_cache

    # Determine config path
    if config_path is None:
        config_path_str = os.environ.get("SHOOT_CONFIG", "")
        if not config_path_str:
            return None
        config_path = Path(config_path_str)
    else:
        config_path = Path(config_path)

    # Check cache
    if (
        not force_reload
        and _config_cache is not None
        and _config_path_cache == config_path
    ):
        return _config_cache

    # Load config
    try:
        config = load_config(config_path, env)
        _config_cache = config
        _config_path_cache = config_path
        return config
    except ConfigError:
        raise


def clear_config_cache() -> None:
    """Clear the global configuration cache."""
    global _config_cache, _config_path_cache
    _config_cache = None
    _config_path_cache = None


def get_config_base_dir(config_path: Path | str | None = None) -> Path | None:
    """
    Get the base directory for a config file.

    Args:
        config_path: Optional path to config file

    Returns:
        Parent directory of config file, or None if not configured
    """
    if config_path is None:
        config_path_str = os.environ.get("SHOOT_CONFIG", "")
        if not config_path_str:
            return None
        config_path = Path(config_path_str)
    else:
        config_path = Path(config_path)

    return config_path.parent
