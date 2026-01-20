"""Tests for response_formatter.py"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from response_formatter import (  # noqa: E402
    validate_response,
    format_json,
    format_human,
    format_response,
    get_content_type,
    parse_structured_response,
    _basic_validate,
    _check_type,
)
from config_schema import ResponseSchemaConfig, ResponseFormat  # noqa: E402


class TestValidateResponse:
    """Tests for validate_response function."""

    def test_valid_response(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name"],
        }
        data = {"name": "test", "count": 42}
        is_valid, errors = validate_response(data, schema)
        assert is_valid
        assert errors == []

    def test_missing_required_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        data: dict = {}
        is_valid, errors = validate_response(data, schema)
        assert not is_valid
        assert len(errors) > 0


class TestBasicValidate:
    """Tests for _basic_validate function."""

    def test_valid_with_required(self) -> None:
        schema = {
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        data = {"name": "test"}
        is_valid, errors = _basic_validate(data, schema)
        assert is_valid
        assert errors == []

    def test_missing_required(self) -> None:
        schema = {
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        data: dict = {}
        is_valid, errors = _basic_validate(data, schema)
        assert not is_valid
        assert "name" in errors[0]

    def test_wrong_type(self) -> None:
        schema = {
            "properties": {"count": {"type": "integer"}},
            "required": [],
        }
        data = {"count": "not_an_int"}
        is_valid, errors = _basic_validate(data, schema)
        assert not is_valid
        assert "count" in errors[0]


class TestCheckType:
    """Tests for _check_type function."""

    def test_string_type(self) -> None:
        assert _check_type("hello", "string") is True
        assert _check_type(123, "string") is False

    def test_number_type(self) -> None:
        assert _check_type(123, "number") is True
        assert _check_type(123.45, "number") is True
        assert _check_type("123", "number") is False

    def test_integer_type(self) -> None:
        assert _check_type(123, "integer") is True
        assert _check_type(123.45, "integer") is False

    def test_boolean_type(self) -> None:
        assert _check_type(True, "boolean") is True
        assert _check_type(False, "boolean") is True
        assert _check_type(1, "boolean") is False

    def test_array_type(self) -> None:
        assert _check_type([1, 2, 3], "array") is True
        assert _check_type("not_array", "array") is False

    def test_object_type(self) -> None:
        assert _check_type({"key": "value"}, "object") is True
        assert _check_type([1, 2], "object") is False

    def test_null_type(self) -> None:
        assert _check_type(None, "null") is True
        assert _check_type("", "null") is False

    def test_unknown_type(self) -> None:
        # Unknown types return True
        assert _check_type("anything", "unknown_type") is True


class TestFormatJson:
    """Tests for format_json function."""

    def test_simple_object(self) -> None:
        data = {"name": "test", "count": 42}
        result = format_json(data)
        assert '"name": "test"' in result
        assert '"count": 42' in result

    def test_nested_object(self) -> None:
        data = {"outer": {"inner": "value"}}
        result = format_json(data)
        assert "inner" in result

    def test_array(self) -> None:
        data = {"items": [1, 2, 3]}
        result = format_json(data)
        assert "[" in result
        assert "1" in result


class TestFormatHuman:
    """Tests for format_human function."""

    def test_simple_fields(self) -> None:
        data = {"failure_signal": "Test failure", "status": "error"}
        result = format_human(data)
        assert "**Failure Signal**:" in result
        assert "Test failure" in result
        assert "**Status**:" in result

    def test_list_field(self) -> None:
        data = {"summary": ["Point 1", "Point 2"]}
        result = format_human(data)
        assert "**Summary**:" in result
        assert "- Point 1" in result
        assert "- Point 2" in result

    def test_nested_object(self) -> None:
        data = {"details": {"action": "retry", "reason": "timeout"}}
        result = format_human(data)
        assert "**Details**:" in result
        assert "Action:" in result
        assert "retry" in result


class TestFormatResponse:
    """Tests for format_response function."""

    def test_json_format(self) -> None:
        data = {"key": "value"}
        schema_config = ResponseSchemaConfig(
            file="test.json",
            format=ResponseFormat.JSON,
        )
        result = format_response(data, schema_config)
        assert '"key"' in result
        assert '"value"' in result

    def test_human_format(self) -> None:
        data = {"key": "value"}
        schema_config = ResponseSchemaConfig(
            file="test.json",
            format=ResponseFormat.HUMAN,
        )
        result = format_response(data, schema_config)
        assert "**Key**:" in result

    def test_none_schema_config(self) -> None:
        data = {"key": "value"}
        result = format_response(data, None)
        # Defaults to human format
        assert "**Key**:" in result


class TestGetContentType:
    """Tests for get_content_type function."""

    def test_json_format(self) -> None:
        schema_config = ResponseSchemaConfig(
            file="test.json",
            format=ResponseFormat.JSON,
        )
        assert get_content_type(schema_config) == "application/json"

    def test_human_format(self) -> None:
        schema_config = ResponseSchemaConfig(
            file="test.json",
            format=ResponseFormat.HUMAN,
        )
        assert get_content_type(schema_config) == "text/plain; charset=utf-8"

    def test_none_schema_config(self) -> None:
        assert get_content_type(None) == "text/plain; charset=utf-8"


class TestParseStructuredResponse:
    """Tests for parse_structured_response function."""

    def test_json_block_extraction(self) -> None:
        text = """
Here is the result:
```json
{"name": "test", "value": 42}
```
"""
        result = parse_structured_response(text)
        assert result is not None
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_direct_json(self) -> None:
        text = '{"name": "test"}'
        result = parse_structured_response(text)
        assert result is not None
        assert result["name"] == "test"

    def test_markdown_parsing(self) -> None:
        schema = {
            "properties": {
                "failure_signal": {"type": "string"},
                "summary": {"type": "array"},
            },
            "required": ["failure_signal", "summary"],
        }
        text = """
**failure_signal**: Test failure

**summary**:
- Point 1
- Point 2
"""
        result = parse_structured_response(text, schema)
        assert result is not None
        assert result["failure_signal"] == "Test failure"
        assert "Point 1" in result["summary"]

    def test_unparseable_text(self) -> None:
        text = "Just some random text without structure"
        result = parse_structured_response(text)
        assert result is None
