import json
from pathlib import Path
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "metricsagent-1.0.schema.json"

with SCHEMA_PATH.open("r", encoding="utf-8") as f:
    _SCHEMA = json.load(f)

VALIDATOR = Draft202012Validator(_SCHEMA)


class ValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


def validate_snapshot(payload: dict) -> None:
    errors = sorted(VALIDATOR.iter_errors(payload), key=lambda e: e.path)
    if errors:
        # Surface the first error for concise API responses.
        e = errors[0]
        loc = "/".join(str(p) for p in e.path)
        raise ValidationError(f"schema validation failed at '{loc}': {e.message}")
