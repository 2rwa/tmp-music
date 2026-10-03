# 2026-10-04 — recovery workflow auto-trigger overwrote current analysis

## Symptom

After PR #17 updated the recovery workflow files, the merge commit triggered both recovery workflows because each workflow had a `push` trigger scoped to its own workflow file.

The recovery jobs downloaded fixed historical artifacts and wrote them back to `analysis/whisper-ao` and `analysis/jugemu`, advancing `main` with:

- `f9cfc95812d513293ac061cdbb5a54bce13275d3` — Recover Whisper AO analysis artifacts
- `5d0ced6df1ef5d1e58524d1a7f83fd91a79d2eba` — Recover Jugemu analysis artifacts

This was not a failure of the new safe write-back helper. The helper correctly serialized the concurrent pushes. The problem was that a recovery-only workflow was allowed to run automatically on a normal push.

## Root cause

Both recovery workflows included:

```yaml
on:
  push:
    branches: [main]
    paths:
      - ".github/workflows/recover-...yml"
  workflow_dispatch:
```

Changing the workflow definition therefore executed a historical recovery operation automatically.

## Fix

- make both recovery workflows `workflow_dispatch` only;
- restore `analysis/whisper-ao` and `analysis/jugemu` to the tree state from PR #17 merge commit `77d9d8102151a24f348639bee9ef22b3b202014a`;
- add a cheap regression test requiring recovery workflows to remain manual-only.

## Regression expectation

Future edits to recovery workflow YAML must not launch historical artifact recovery automatically. Recovery is an explicit operator action only.
