#!/usr/bin/env python3
"""Build reproducibility metadata for analyzer stages."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping

from common.schema import SCHEMA_VERSION, validate_provenance, validate_status, write_json


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _command_version(command: str) -> str | None:
    if shutil.which(command) is None:
        return None
    try:
        result = subprocess.run(
            [command, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first = (result.stdout or result.stderr).splitlines()
    return first[0].strip() if first else None


def collect_tool_versions(packages: Iterable[str] = ()) -> dict[str, str | None]:
    versions: dict[str, str | None] = {
        "python": platform.python_version(),
        "ffmpeg": _command_version("ffmpeg"),
        "ffprobe": _command_version("ffprobe"),
    }
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def actions_run_url() -> str | None:
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if repository and run_id:
        return f"https://github.com/{repository}/actions/runs/{run_id}"
    return None


def build_provenance(
    *,
    source_path: str,
    source_sha256: str,
    analyzer: str,
    parameters: Mapping[str, Any] | None = None,
    models: Mapping[str, Any] | None = None,
    tool_versions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "source_path": source_path,
        "git_commit": os.getenv("GITHUB_SHA"),
        "actions_run": actions_run_url(),
        "analyzer": analyzer,
        "analyzer_version": "1",
        "parameters": dict(parameters or {}),
        "models": dict(models or {}),
        "tool_versions": dict(tool_versions or {}),
    }
    validate_provenance(payload)
    return payload


def write_stage_state(
    out_dir: Path,
    *,
    provenance: Mapping[str, Any],
    status: str,
    warnings: list[str] | None = None,
    started_from: str = "source",
    outputs: list[str] | None = None,
    return_code: int | None = None,
) -> None:
    validate_provenance(provenance)
    status_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "warnings": list(warnings or []),
        "started_from": started_from,
        "outputs": list(outputs or []),
    }
    if return_code is not None:
        status_payload["return_code"] = return_code
    validate_status(status_payload)
    write_json(out_dir / "provenance.json", provenance)
    write_json(out_dir / "status.json", status_payload)
