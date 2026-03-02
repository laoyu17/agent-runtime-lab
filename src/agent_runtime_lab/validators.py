"""Output validators: schema, keyword, constraint, and rule-based checks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationResult:
    """Validation result container."""

    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.passed = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: ValidationResult) -> ValidationResult:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self


class JSONSchemaValidator:
    """Minimal JSON-schema validator for common runtime checks."""

    def validate(self, payload: Any, schema: dict[str, Any]) -> ValidationResult:
        result = ValidationResult()
        self._validate_node(payload, schema, "$", result)
        return result

    def _validate_node(
        self,
        payload: Any,
        schema: dict[str, Any],
        path: str,
        result: ValidationResult,
    ) -> None:
        expected = schema.get("type")
        if expected and not self._matches_type(payload, expected):
            result.add_error(f"{path}: expected type {expected}")
            return

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and payload not in enum_values:
            result.add_error(f"{path}: value not in enum")

        if expected == "object" and isinstance(payload, dict):
            self._validate_object(payload, schema, path, result)
            return

        if expected == "array" and isinstance(payload, list):
            self._validate_array(payload, schema, path, result)
            return

        if expected == "string" and isinstance(payload, str):
            self._validate_string(payload, schema, path, result)
            return

        if expected in {"number", "integer"} and isinstance(payload, (int, float)):
            self._validate_number(payload, schema, path, result)

    def _validate_object(
        self,
        payload: dict[str, Any],
        schema: dict[str, Any],
        path: str,
        result: ValidationResult,
    ) -> None:
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in payload:
                    result.add_error(f"{path}: missing required key {key}")

        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, subschema in properties.items():
                if key in payload and isinstance(subschema, dict):
                    self._validate_node(
                        payload[key],
                        subschema,
                        f"{path}.{key}",
                        result,
                    )

    def _validate_array(
        self,
        payload: list[Any],
        schema: dict[str, Any],
        path: str,
        result: ValidationResult,
    ) -> None:
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(payload) < min_items:
            result.add_error(f"{path}: minItems={min_items}")

        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(payload) > max_items:
            result.add_error(f"{path}: maxItems={max_items}")

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(payload):
                self._validate_node(item, item_schema, f"{path}[{index}]", result)

    def _validate_string(
        self,
        payload: str,
        schema: dict[str, Any],
        path: str,
        result: ValidationResult,
    ) -> None:
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(payload) < min_length:
            result.add_error(f"{path}: minLength={min_length}")

        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(payload) > max_length:
            result.add_error(f"{path}: maxLength={max_length}")

        pattern = schema.get("pattern")
        if isinstance(pattern, str) and not re.search(pattern, payload):
            result.add_error(f"{path}: pattern mismatch")

    def _validate_number(
        self,
        payload: int | float,
        schema: dict[str, Any],
        path: str,
        result: ValidationResult,
    ) -> None:
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and payload < minimum:
            result.add_error(f"{path}: minimum={minimum}")

        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and payload > maximum:
            result.add_error(f"{path}: maximum={maximum}")

    def _matches_type(self, payload: Any, expected: str | list[str]) -> bool:
        expected_types = expected if isinstance(expected, list) else [expected]
        for item in expected_types:
            if item == "object" and isinstance(payload, dict):
                return True
            if item == "array" and isinstance(payload, list):
                return True
            if item == "string" and isinstance(payload, str):
                return True
            if (
                item == "integer"
                and isinstance(payload, int)
                and not isinstance(payload, bool)
            ):
                return True
            if (
                item == "number"
                and isinstance(payload, (int, float))
                and not isinstance(payload, bool)
            ):
                return True
            if item == "boolean" and isinstance(payload, bool):
                return True
            if item == "null" and payload is None:
                return True
        return False


class KeywordValidator:
    """Validate required and forbidden keywords."""

    def validate(
        self,
        text: str,
        *,
        required_keywords: list[str] | None = None,
        forbidden_keywords: list[str] | None = None,
    ) -> ValidationResult:
        result = ValidationResult()
        lowered = text.lower()

        for keyword in required_keywords or []:
            token = keyword.strip().lower()
            if token and token not in lowered:
                result.add_error(f"missing required keyword: {keyword}")

        for keyword in forbidden_keywords or []:
            token = keyword.strip().lower()
            if token and token in lowered:
                result.add_error(f"found forbidden keyword: {keyword}")

        return result


class ConstraintValidator:
    """Validate explicit constraints against response text."""

    _NETWORK_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
    _MUST_JSON_HINTS = (
        "must json",
        "must be json",
        "json only",
        "必须json",
        "必须 json",
        "必须是json",
        "必须是 json",
    )
    _NO_NETWORK_HINTS = (
        "no network",
        "must not use network",
        "offline only",
        "禁止联网",
        "不能联网",
    )

    def validate(
        self,
        text: str,
        constraints: list[str] | None = None,
    ) -> ValidationResult:
        result = ValidationResult()
        constraints = constraints or []

        for constraint in constraints:
            normalized = constraint.strip().lower()
            if not normalized:
                continue

            if self._requires_json(normalized) and not self._is_json(text):
                result.add_error("constraint violated: must json")

            if self._forbids_network(normalized) and self._NETWORK_PATTERN.search(text):
                result.add_error("constraint violated: no network")

        return result

    def has_no_network_constraint(self, constraints: list[str] | None) -> bool:
        for constraint in constraints or []:
            normalized = constraint.strip().lower()
            if normalized and self._forbids_network(normalized):
                return True
        return False

    def _requires_json(self, normalized: str) -> bool:
        return any(hint in normalized for hint in self._MUST_JSON_HINTS)

    def _forbids_network(self, normalized: str) -> bool:
        return any(hint in normalized for hint in self._NO_NETWORK_HINTS)

    @staticmethod
    def _is_json(text: str) -> bool:
        candidate = text.strip()
        if not candidate:
            return False
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, (dict, list))


RuleCallable = Callable[
    [Any, dict[str, Any]],
    ValidationResult | tuple[bool, str | None],
]


class RuleBasedValidator:
    """Evaluate additional custom rule callables."""

    def __init__(self, rules: list[RuleCallable] | None = None) -> None:
        self.rules = rules or []

    def add_rule(self, rule: RuleCallable) -> None:
        self.rules.append(rule)

    def validate(
        self,
        payload: Any,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        context = context or {}
        result = ValidationResult()

        for rule in self.rules:
            rule_result = rule(payload, context)
            if isinstance(rule_result, ValidationResult):
                result.merge(rule_result)
                continue

            if not isinstance(rule_result, tuple) or len(rule_result) != 2:
                result.add_error("rule violation")
                continue

            ok, message = rule_result
            if not ok:
                result.add_error(message or "rule violation")

        return result


class OutputValidator:
    """Composite validator for schema + keywords + constraints + rules."""

    def __init__(
        self,
        schema_validator: JSONSchemaValidator | None = None,
        keyword_validator: KeywordValidator | None = None,
        constraint_validator: ConstraintValidator | None = None,
        rule_validator: RuleBasedValidator | None = None,
    ) -> None:
        self.schema_validator = schema_validator or JSONSchemaValidator()
        self.keyword_validator = keyword_validator or KeywordValidator()
        self.constraint_validator = constraint_validator or ConstraintValidator()
        self.rule_validator = rule_validator or RuleBasedValidator()

    def validate(
        self,
        payload: Any,
        *,
        text: str,
        schema: dict[str, Any] | None = None,
        required_keywords: list[str] | None = None,
        forbidden_keywords: list[str] | None = None,
        constraints: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        result = ValidationResult()

        if schema is not None:
            result.merge(self.schema_validator.validate(payload, schema))

        result.merge(
            self.keyword_validator.validate(
                text,
                required_keywords=required_keywords,
                forbidden_keywords=forbidden_keywords,
            )
        )
        result.merge(self.constraint_validator.validate(text, constraints=constraints))
        result.merge(self.rule_validator.validate(payload, context=context))
        return result


__all__ = [
    "ConstraintValidator",
    "JSONSchemaValidator",
    "KeywordValidator",
    "OutputValidator",
    "RuleBasedValidator",
    "ValidationResult",
]
