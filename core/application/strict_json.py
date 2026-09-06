"""Reject ambiguous or non-standard JSON at the model trust boundary."""
import json
import math
from typing import Any


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def loads(payload: str | bytes) -> Any:
    return json.loads(payload, parse_constant=_reject_constant, parse_float=_finite_float, object_pairs_hook=_unique_object)
