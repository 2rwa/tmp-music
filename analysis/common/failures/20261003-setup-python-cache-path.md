# 2026-10-03 — setup-python pip cache path mismatch

## Symptom

Milestone 2 Demucs matrix jobs failed before dependency installation.

Both jobs stopped in `actions/setup-python@v5` with:

```text
No file ... matched to [**/requirements.txt or **/pyproject.toml]
```

Affected run:

- https://github.com/2rwa/tmp-music/actions/runs/37083721806

## Root cause

The workflow enabled:

```yaml
cache: pip
```

but this repository intentionally splits dependencies into files such as:

- `requirements-core.txt`
- `requirements-separation.txt`
- `requirements-analysis.txt`
- `requirements-pitch-ml.txt`

There is no conventional root `requirements.txt` or `pyproject.toml`, so setup-python's automatic pip-cache dependency discovery failed.

The Demucs executable/model was never reached in the failed run.

## Fix

Specify the dependency manifests explicitly:

```yaml
cache: pip
cache-dependency-path: |
  requirements-core.txt
  requirements-separation.txt
```

The pitch workflow similarly lists its three dependency manifests.

## Regression coverage

The next Demucs run reached `Install dependencies` successfully after `setup-python`, proving this preflight failure is fixed.

When adding future workflows that use `cache: pip`, always provide `cache-dependency-path` because this repository intentionally has split requirement files.
