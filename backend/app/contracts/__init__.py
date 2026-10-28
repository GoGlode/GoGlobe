"""Рабочий контракт v0.3, общий для BFF и интеграций."""
import json
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker, validators
from rfc3339_validator import validate_rfc3339
from rfc3986_validator import validate_rfc3986

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time")
def valid_timestamp(value):
    return not isinstance(value, str) or validate_rfc3339(value.upper())


@FORMAT_CHECKER.checks("uri")
def valid_uri(value):
    if not isinstance(value, str):
        return True
    if validate_rfc3986(value, rule="URI") is None:
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"}:
            return bool(parsed.hostname) and (parsed.port is None or 0 < parsed.port <= 65535)
    except ValueError:
        return False
    return True

StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda checker, value: type(value) is int),
)


@lru_cache
def _document(name: str) -> dict:
    return json.loads(files(__package__).joinpath(name).read_text(encoding="utf-8"))


def specification() -> dict:
    return deepcopy(_document("openapi_v0.3.json"))


def examples() -> dict:
    return deepcopy(_document("examples_v0.3.json"))


@lru_cache
def validator(name: str) -> Draft202012Validator:
    return StrictValidator(
        {"components": specification()["components"], "$ref": f"#/components/schemas/{name}"},
        format_checker=FORMAT_CHECKER,
    )


def validate(name: str, value: Any) -> None:
    validator(name).validate(value)
