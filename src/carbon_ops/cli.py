"""Command-line utilities for carbon_ops."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tools.verify import verify_json


def _read_stdin() -> str | None:
    """Read JSON payload from stdin if available."""
    try:
        if sys.stdin and not sys.stdin.isatty():
            return sys.stdin.read()
    except IOError as e:
        print(f"Error reading stdin: {e}", file=sys.stderr)
    return None


def _load_json(path: str | None, stdin_payload: str | None) -> dict[str, object]:
    """Load JSON data from file or stdin."""
    if path:
        text = Path(path).read_text(encoding="utf-8")
        return _parse_json_dict(text)
    if stdin_payload:
        return _parse_json_dict(stdin_payload)
    raise ValueError("No input provided. Use --input or pipe JSON via stdin.")


def _parse_json_dict(payload: str) -> dict[str, object]:
    """Parse a JSON string and ensure the result is a dictionary."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object at the top level.")
    normalised: dict[str, object] = {str(key): value for key, value in data.items()}
    return normalised


def main(argv: list[str] | None = None) -> int:
    """Verify signed JSON."""
    parser = argparse.ArgumentParser(description="Verify signed JSON label.")
    parser.add_argument(
        "--input",
        "-i",
        help="Path to signed JSON file. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--public-key",
        "-k",
        help="Public key hex. If omitted, uses 'signing_key' embedded in the payload.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode: suppress output, just return exit code.",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # pragma: no cover - controlled via tests
        exit_code = int(exc.code) if isinstance(exc.code, int) else 1
        return 0 if exit_code == 0 else 1

    try:
        stdin_payload = _read_stdin()
        data = _load_json(args.input, stdin_payload)
        public_key_hex: str | None = args.public_key

        # If no key provided, attempt to use 'signing_key' embedded in payload
        if not public_key_hex:
            candidate = data.get("signing_key")
            if isinstance(candidate, str):
                public_key_hex = candidate

        if not public_key_hex:
            raise ValueError("Missing --public-key and no 'signing_key' in payload.")

        is_valid, original = verify_json(data, public_key_hex)

        if not args.quiet:
            print(
                json.dumps(
                    {
                        "valid": bool(is_valid),
                        "original": original if is_valid else None,
                    },
                    separators=(",", ":"),
                )
            )

        return 0 if is_valid else 1

    except Exception as exc:
        if not args.quiet:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
