#!/usr/bin/env python3
"""Resolve this installed skill's API origin and origin-scoped token path.

Only the non-secret origin is stored beside the skill. Token contents are never
read or printed by this helper.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

SKILL_DIR = Path(__file__).resolve().parents[1]
PRODUCTION = "https://passmarkedu.com"


def normalize_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("origin must be an HTTP(S) URL with a host and no path, query, or credentials")
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError("origin has an invalid port") from exc
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = f":{parsed_port}" if parsed_port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port}"


def resolve_origin() -> str:
    configured = SKILL_DIR / "origin.txt"
    if configured.exists():
        return normalize_origin(configured.read_text(encoding="utf-8"))
    for name in ("PASSMARKEDU_BASE_URL", "PASSMARK_BASE_URL"):
        if value := os.environ.get(name):
            return normalize_origin(value)
    return PRODUCTION


def token_path(origin: str, home: Path, cwd: Path) -> Path:
    if origin == PRODUCTION:
        names = (
            home / ".passmarkedu" / "marking-kit-token",
            cwd / ".passmarkedu-marking-token",
            home / ".passmark" / "marking-kit-token",
            cwd / ".passmark-marking-token",
        )
    else:
        digest = hashlib.sha256(origin.encode("utf-8")).hexdigest()[:16]
        names = (
            home / ".passmarkedu" / f"marking-kit-token-{digest}",
            cwd / f".passmarkedu-marking-token-{digest}",
        )
    for path in names:
        if path.is_file():
            return path
    if os.access(home, os.W_OK):
        return names[0]
    return names[1]


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "set-origin":
            origin = normalize_origin(sys.argv[2])
            (SKILL_DIR / "origin.txt").write_text(origin + "\n", encoding="utf-8")
            print("Origin configured.")
            return 0
        if len(sys.argv) == 2 and sys.argv[1] == "resolve":
            origin = resolve_origin()
            path = token_path(origin, Path.home(), Path.cwd())
            print(json.dumps({
                "base": origin,
                "api_base": f"{origin}/api/v1/marking-kit",
                "token_path": str(path),
                "token_exists": path.is_file(),
            }))
            return 0
        print("Usage: config.py set-origin URL | resolve", file=sys.stderr)
    except (OSError, ValueError) as exc:
        print(f"Skill configuration error: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
