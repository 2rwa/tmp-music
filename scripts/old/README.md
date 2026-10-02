# Old / exploratory scripts

These files preserve disposable analysis code used during the initial 2026-10-02 investigation of `Whisper AO` before the reusable programs under `scripts/` were finalized.

They are kept as a research log, **not** as the supported interface. Use `scripts/analyze_audio.py` and `scripts/asr_compare.py` for new runs.

- `20261002-analyze-audio-exploratory.py` — first larger acoustic-analysis implementation. It was the memory-heavy version used before the later 16 kHz / active-section optimizations.
- `20261002-asr-compare-exploratory.py` — first larger faster-whisper / embedded-lyrics comparison implementation.
- `20261002-id3-dump.py` — file form of the inline Mutagen ID3 dump used to discover `USLT::eng` and the Suno metadata.
- `20261002-env-silence-check.sh` — file form of the dependency check and `ffmpeg silencedetect` command used to locate the long trailing silence.
- `20261002-analyze-audio-compact-intermediate.py` / `20261002-asr-compare-compact-intermediate.py` — snapshots of the compact intermediate versions that were smoke-tested immediately before being promoted to the supported scripts.

The two larger Python files were reconstructed from the executed scratch versions and include an archive note; they are not intended to replace the current scripts.

Some files are intentionally redundant or less polished. Preserve them to make the evolution of the analysis reproducible.
