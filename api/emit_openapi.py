"""Emit the OpenAPI schema as JSON.

Usage (run from api/):
    python emit_openapi.py              # writes ../frontend/openapi.json
    python emit_openapi.py --out path   # writes to the given path
    python emit_openapi.py --stdout     # writes to stdout
"""
import argparse
import json
import sys
from pathlib import Path

from main import app


def default_out_path() -> Path:
    # api/emit_openapi.py -> ../frontend/openapi.json
    return Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None, help="Output path (default: frontend/openapi.json)")
    parser.add_argument("--stdout", action="store_true", help="Write to stdout instead of a file")
    args = parser.parse_args()

    payload = json.dumps(app.openapi(), indent=2)

    if args.stdout:
        sys.stdout.write(payload)
        return

    out = args.out or default_out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(f"Wrote OpenAPI schema to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
