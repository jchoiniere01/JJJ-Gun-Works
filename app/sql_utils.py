from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def quote_identifier(identifier: str) -> str:
    """Safely quote a PostgreSQL identifier that has already been whitelisted."""

    return '"' + identifier.replace('"', '""') + '"'


def qualify_table(schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


@dataclass(frozen=True)
class TableMapping:
    key: str
    schema: str
    table: str
    primary_key: str
    allowed_columns: tuple[str, ...]
    searchable_columns: tuple[str, ...] = ()
    default_order_by: str | None = None

    @property
    def qualified_name(self) -> str:
        return qualify_table(self.schema, self.table)

    def require_column(self, column: str) -> str:
        if column not in self.allowed_columns and column != self.primary_key:
            raise KeyError(f"Column '{column}' is not allowed for table '{self.key}'.")
        return quote_identifier(column)

    def allowed_payload(self, data: dict[str, Any], include_primary_key: bool = False) -> dict[str, Any]:
        allowed = set(self.allowed_columns)
        if include_primary_key:
            allowed.add(self.primary_key)
        return {key: value for key, value in data.items() if key in allowed}
