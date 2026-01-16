"""
Structured output schemas for the Shoot agent system.

This module defines JSON schemas and Pydantic models for validating
agent outputs, ensuring consistent diagnostic report formats.
"""

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DiagnosticReport(BaseModel):
    """
    Structured diagnostic report from the coordinator agent.

    This schema enforces the output format defined in the coordinator prompt,
    ensuring consistent, actionable reports.
    """

    failure_signal: str = Field(
        ...,
        description="The original failure description from the user",
        min_length=1,
        max_length=500,
    )
    summary: list[str] = Field(
        ...,
        description="1-3 bullets describing the key findings",
        min_length=1,
        max_length=5,
    )
    likely_cause: list[str] = Field(
        ...,
        description="1-2 bullets with the most likely root cause(s)",
        min_length=1,
        max_length=3,
    )
    recommended_next_steps: list[str] = Field(
        ...,
        description="1-4 bullets with concrete, actionable steps",
        min_length=1,
        max_length=6,
    )

    @field_validator("summary", "likely_cause", "recommended_next_steps", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        """Ensure value is a list of strings."""
        if isinstance(v, str):
            return [v]
        return v


# JSON Schema for documentation and external validation
DIAGNOSTIC_REPORT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "DiagnosticReport",
    "description": "Structured diagnostic report from the Shoot coordinator agent",
    "type": "object",
    "properties": {
        "failure_signal": {
            "type": "string",
            "description": "The original failure description from the user",
            "minLength": 1,
            "maxLength": 500,
        },
        "summary": {
            "type": "array",
            "description": "1-3 bullets describing the key findings",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 5,
        },
        "likely_cause": {
            "type": "array",
            "description": "1-2 bullets with the most likely root cause(s)",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
        "recommended_next_steps": {
            "type": "array",
            "description": "1-4 bullets with concrete, actionable steps",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 6,
        },
    },
    "required": ["failure_signal", "summary", "likely_cause", "recommended_next_steps"],
    "additionalProperties": False,
}


def parse_markdown_report(text: str) -> DiagnosticReport | None:
    """
    Parse a markdown-formatted diagnostic report into a structured DiagnosticReport.

    Expected format:
    - **failure_signal**: `<text>`
    - **summary**:
      - `<bullet 1>`
      - `<bullet 2>`
    - **likely_cause**:
      - `<bullet>`
    - **recommended_next_steps**:
      - `<bullet 1>`
      - `<bullet 2>`

    Returns None if parsing fails.
    """
    try:
        result: dict[str, Any] = {}

        # Pattern for single-value fields (failure_signal)
        failure_match = re.search(
            r"\*\*failure_signal\*\*:\s*`?([^`\n]+)`?", text, re.IGNORECASE
        )
        if failure_match:
            result["failure_signal"] = failure_match.group(1).strip()

        # Pattern for list fields
        list_fields = ["summary", "likely_cause", "recommended_next_steps"]
        for field in list_fields:
            # Find the section
            pattern = rf"\*\*{field}\*\*:\s*\n((?:\s*-\s*`?[^`\n]+`?\n?)+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract bullets
                bullets_text = match.group(1)
                bullets = re.findall(r"-\s*`?([^`\n]+)`?", bullets_text)
                result[field] = [b.strip() for b in bullets if b.strip()]

        # Validate with Pydantic
        if all(
            k in result
            for k in [
                "failure_signal",
                "summary",
                "likely_cause",
                "recommended_next_steps",
            ]
        ):
            return DiagnosticReport(**result)

        return None
    except Exception:
        return None


def validate_report(report: DiagnosticReport) -> dict[str, Any]:
    """Convert a DiagnosticReport to a JSON-serializable dict."""
    return report.model_dump()
