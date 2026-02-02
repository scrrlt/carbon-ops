"""Export the carbon-ops audit record JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

from carbon_ops.schemas import AuditRecord, CURRENT_AUDIT_SCHEMA_VERSION


def main() -> None:
    """Write the JSON Schema for :class:`AuditRecord` to the repository root."""

    schema = AuditRecord.model_json_schema()
    output_path = Path(__file__).resolve().parent.parent / (
        f"audit_schema_v{CURRENT_AUDIT_SCHEMA_VERSION}.json"
    )
    output_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
