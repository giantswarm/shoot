"""
Response formatting for the Shoot multi-agent system.

This module handles:
- Loading JSON Schema files for response validation
- Validating responses against schemas
- Formatting responses based on schema format (human/json)
"""

import json
from pathlib import Path
from typing import Any

from config_schema import ShootConfig, ResponseSchemaConfig, ResponseFormat
from config_loader import resolve_path, load_json_schema, ConfigError


def get_schema_for_agent(
    config: ShootConfig,
    agent_name: str,
    config_base_dir: Path,
) -> tuple[dict[str, Any] | None, ResponseSchemaConfig | None]:
    """
    Get the JSON Schema and config for an agent's response schema.

    Args:
        config: ShootConfig object
        agent_name: Name of the agent
        config_base_dir: Base directory for resolving schema file paths

    Returns:
        Tuple of (schema_dict, schema_config), both None if no schema configured
    """
    agent = config.get_agent(agent_name)

    if not agent.response_schema:
        return None, None

    schema_config = config.get_response_schema(agent.response_schema)
    if schema_config is None:
        return None, None

    schema_path = resolve_path(config_base_dir, schema_config.file)
    try:
        schema = load_json_schema(schema_path)
        return schema, schema_config
    except ConfigError:
        return None, schema_config


def validate_response(
    data: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Validate response data against a JSON Schema.

    Args:
        data: Response data to validate
        schema: JSON Schema to validate against

    Returns:
        Tuple of (is_valid, error_messages)
    """
    try:
        # Try to use jsonschema for validation if available
        import jsonschema

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))
        if errors:
            error_messages = [f"{e.path}: {e.message}" for e in errors]
            return False, error_messages
        return True, []
    except ImportError:
        # Fallback: basic validation without jsonschema
        return _basic_validate(data, schema)


def _basic_validate(
    data: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Basic validation without jsonschema library.

    Only validates:
    - Required fields are present
    - Field types match (basic type checking)
    """
    errors: list[str] = []

    # Check required fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Check field types
    properties = schema.get("properties", {})
    for field, value in data.items():
        if field in properties:
            expected_type = properties[field].get("type")
            if expected_type:
                if not _check_type(value, expected_type):
                    errors.append(
                        f"Field '{field}' expected type '{expected_type}', "
                        f"got '{type(value).__name__}'"
                    )

    return len(errors) == 0, errors


def _check_type(value: Any, expected_type: str) -> bool:
    """Check if a value matches an expected JSON Schema type."""
    type_map: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True  # Unknown type, assume valid
    return isinstance(value, expected)


def format_response(
    data: dict[str, Any],
    schema_config: ResponseSchemaConfig | None,
    schema: dict[str, Any] | None = None,
) -> str:
    """
    Format response data based on schema configuration.

    Args:
        data: Response data to format
        schema_config: Schema configuration (determines format)
        schema: Optional JSON Schema (for human formatting hints)

    Returns:
        Formatted response string
    """
    if schema_config is None:
        # Default to human format
        return format_human(data, schema)

    if schema_config.format == ResponseFormat.JSON:
        return format_json(data)
    else:
        return format_human(data, schema)


def format_json(data: dict[str, Any]) -> str:
    """
    Format response data as JSON.

    Args:
        data: Response data to format

    Returns:
        JSON string
    """
    return json.dumps(data, indent=2)


def format_human(
    data: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> str:
    """
    Format response data as human-readable markdown.

    Uses schema field descriptions if available, otherwise uses field names.

    Args:
        data: Response data to format
        schema: Optional JSON Schema for field descriptions

    Returns:
        Human-readable markdown string
    """
    lines: list[str] = []

    for field, value in data.items():
        # Format field name
        field_display = field.replace("_", " ").title()

        if isinstance(value, list):
            # List field: render as bullet points
            lines.append(f"**{field_display}**:")
            for item in value:
                if isinstance(item, dict):
                    # Nested object in list
                    lines.append(f"  - {json.dumps(item)}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(value, dict):
            # Nested object: render as sub-section
            lines.append(f"**{field_display}**:")
            for sub_key, sub_value in value.items():
                sub_display = sub_key.replace("_", " ").title()
                lines.append(f"  - {sub_display}: {sub_value}")
        else:
            # Simple field
            lines.append(f"**{field_display}**: {value}")

        lines.append("")  # Blank line between fields

    return "\n".join(lines).strip()


def get_content_type(schema_config: ResponseSchemaConfig | None) -> str:
    """
    Get the HTTP Content-Type for a response based on schema config.

    Args:
        schema_config: Schema configuration

    Returns:
        Content-Type string (application/json or text/plain)
    """
    if schema_config is None:
        return "text/plain; charset=utf-8"

    if schema_config.format == ResponseFormat.JSON:
        return "application/json"
    else:
        return "text/plain; charset=utf-8"


def parse_structured_response(
    text: str,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Attempt to parse a text response into structured data.

    Tries multiple parsing strategies:
    1. JSON block extraction (```json ... ```)
    2. Direct JSON parsing
    3. Markdown parsing (if schema provided with expected fields)

    Args:
        text: Raw text response
        schema: Optional JSON Schema for markdown parsing hints

    Returns:
        Parsed data dict, or None if parsing fails
    """
    # Try to extract JSON from code block
    import re

    json_block_match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if json_block_match:
        try:
            return json.loads(json_block_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try direct JSON parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try markdown parsing if schema has expected fields
    if schema:
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if required and properties:
            return _parse_markdown_to_schema(text, required, properties)

    return None


def _parse_markdown_to_schema(
    text: str,
    required_fields: list[str],
    properties: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Parse markdown text into a dict based on expected schema fields.

    Looks for patterns like:
    - **field_name**: value
    - **field_name**:
      - bullet 1
      - bullet 2
    """
    import re

    result: dict[str, Any] = {}

    for field in required_fields:
        field_type = properties.get(field, {}).get("type", "string")

        if field_type == "array":
            # Look for list pattern
            pattern = rf"\*\*{field}\*\*:\s*\n((?:\s*-\s*[^\n]+\n?)+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                bullets_text = match.group(1)
                bullets = re.findall(r"-\s*`?([^`\n]+)`?", bullets_text)
                result[field] = [b.strip() for b in bullets if b.strip()]
        else:
            # Look for single value pattern
            pattern = rf"\*\*{field}\*\*:\s*`?([^`\n]+)`?"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result[field] = match.group(1).strip()

    # Only return if we found all required fields
    if all(f in result for f in required_fields):
        return result

    return None
