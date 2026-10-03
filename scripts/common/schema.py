#!/usr/bin/env python3
"""Small JSON schema helpers shared by analysis stages.

This intentionally avoids a JSON-schema dependency so the cheap CI path stays small.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
STATUS_VALUES = {"running", "success", "failed", "skipped"}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_provenance(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "source_sha256",
        "source_path",
        "git_commit",
        "actions_run",
        "analyzer",
        "analyzer_version",
        "parameters",
        "models",
        "tool_versions",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"provenance missing keys: {', '.join(missing)}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported provenance schema_version: {payload['schema_version']}")
    sha = str(payload["source_sha256"])
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower()):
        raise ValueError("source_sha256 must be a 64-character hex digest")
    if not str(payload["analyzer"]).strip():
        raise ValueError("analyzer must be non-empty")
    for key in ("parameters", "models", "tool_versions"):
        if not isinstance(payload[key], Mapping):
            raise ValueError(f"{key} must be an object")


def validate_status(payload: Mapping[str, Any]) -> None:
    required = {"schema_version", "status", "warnings", "started_from", "outputs"}
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"status missing keys: {', '.join(missing)}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported status schema_version: {payload['schema_version']}")
    if payload["status"] not in STATUS_VALUES:
        raise ValueError(f"invalid status: {payload['status']}")
    if not isinstance(payload["warnings"], list):
        raise ValueError("warnings must be a list")
    if not isinstance(payload["outputs"], list):
        raise ValueError("outputs must be a list")
    if payload["status"] == "success" and not payload["outputs"]:
        raise ValueError("successful stages must list at least one output")
