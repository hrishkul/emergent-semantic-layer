"""Shared failures for artifacts the API validates before it stores them."""

import json

from pydantic import BaseModel


class SchemaError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def canonical_json(model: BaseModel) -> bytes:
    return json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
