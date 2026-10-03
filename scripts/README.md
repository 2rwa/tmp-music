# Analysis scripts

## Common CLI

Milestone 1 adds a common wrapper that owns track configuration, source-integrity checks, and shared `provenance.json` / `status.json` files while keeping the existing analyzers independently runnable.

Install the small CLI dependency:

    python -m pip install -r requirements-core.txt

Verify the immutable benchmark source before analysis:

    python scripts/cli.py verify --track whisper-ao
    python scripts/cli.py verify --track jugemu

Inspect the commands that `full` would run without starting the heavy analyzers:

    python scripts/cli.py full --track whisper-ao --dry-run
    python scripts/cli.py full --track jugemu --dry-run

Run one existing analyzer through the common wrapper:

    python scripts/cli.py metadata --track jugemu
    python scripts/cli.py acoustic --track jugemu
    python scripts/cli.py repetition --track jugemu
    python scripts/cli.py asr --track jugemu --model small

Common-wrapper outputs go below `analysis/<track>/measurements/`. Every executed stage gets:

- `provenance.json` with source SHA, analyzer/model parameters, Actions run identity when available, and tool versions;
- `status.json` with running/success/failed state and an explicit output list.

A stage that exits zero but produces no analyzer outputs is treated as failure.

Track-specific source paths, expected SHA-256 values, language, ASR modes, and repetition settings live in `config/tracks/*.yml`. The CLI rejects an unknown track, a SHA mismatch, or an unexpected source size before running analysis.

## Synthetic regression fixtures

The synthetic generators use only the Python standard library so they remain cheap in CI:

    python scripts/synthetic/generate_pitch_fixtures.py
    python scripts/synthetic/generate_rhythm_fixtures.py

Generated WAV files are written under `tests/fixtures/generated/` and are intentionally not committed. Pitch fixtures currently cover 440 Hz, +25 cent, glissando, 6 Hz vibrato, and a 19-EDO scale. Rhythm fixtures cover 100 BPM clicks, 100/200 BPM tactus/subdivision ambiguity, and tempo drift.

Run the cheap suite with:

    python -m unittest discover -s scripts/tests -p 'test_*.py' -v

## Acoustic analysis

Requires ffmpeg / ffprobe and the packages in requirements-analysis.txt.

    python -m pip install -r requirements-analysis.txt
    python scripts/analyze_audio.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao

For a cheap smoke test, add `--skip-pitch`. The full Actions run should normally include pYIN pitch analysis.

Automatic section boundaries are only candidates. To reproduce the listening-assisted comparison used during the initial investigation:

    python scripts/analyze_audio.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao --boundaries 21.7,77.5

Outputs include metadata.json, sections.json, spectral-features.csv, pitch-f0.csv, pitch-summary.json, waveform.png, spectrogram.png and embedded-lyrics-eng.txt.

## Repetition analysis

For repeated material such as Jugemu:

    python scripts/repetition_analysis.py samples/jugemu/source/jugemu.mp3 --out analysis/jugemu/repetition --template-start 12 --template-end 34

The common CLI reads those template values from `config/tracks/jugemu.yml`.

## Vocal separation

Install the Demucs dependency separately from the cheap core:

    python -m pip install -r requirements-separation.txt

Run source separation through the common CLI:

    python scripts/cli.py separate --track whisper-ao
    python scripts/cli.py separate --track jugemu

Outputs are written to `analysis/<track>/stems/demucs/`:

- `vocals.wav`
- `accompaniment.wav`
- `diagnostics.json`
- common `provenance.json` / `status.json`

The diagnostics validate duration, finite samples, RMS, clipping fraction, and source-vs-resummed-stems residual. A silent stem or a duration mismatch above the configured tolerance is not treated as success.

## Multi-estimator pitch and tuning

Install analysis dependencies plus torchcrepe:

    python -m pip install -r requirements-analysis.txt
    python -m pip install -r requirements-pitch-ml.txt

Run pYIN + CREPE on the original mix:

    python scripts/cli.py pitch --track jugemu --source mix
    python scripts/cli.py targets --track jugemu --source mix
    python scripts/cli.py tuning --track jugemu --source mix

After Demucs has produced a vocal stem, run the same pipeline on vocals:

    python scripts/cli.py pitch --track jugemu --source vocals
    python scripts/cli.py targets --track jugemu --source vocals
    python scripts/cli.py tuning --track jugemu --source vocals

Pitch outputs live under `analysis/<track>/measurements/pitch/<source>/`.

`consensus.csv` preserves both estimators and classifies agreement instead of silently averaging conflicting F0:

- strong: <= 25 cent
- weak: <= 50 cent
- disagreement: > 50 cent

Stable-target detection uses local linear slope plus detrended residual variation. This is intended to reject glissando while retaining moderate vibrato around a stable center.

`tuning-models.json` compares residuals against 12-, 19-, 24-, and 31-EDO after estimating a global offset. A lower residual is only a fit statistic; it is not by itself an identification of the intended scale or tuning system.

## ASR / embedded-lyrics comparison

Install the optional ASR dependency:

    python -m pip install -r requirements-asr.txt

Run automatic language detection and forced English:

    python scripts/asr_compare.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao/asr --model small --modes auto,en

The central section can be isolated with `--start` / `--end` after the boundaries are reviewed:

    python scripts/asr_compare.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao/asr-central --model small --modes auto,en --start 21.7 --end 77.5

The reference text comes from the MP3 `USLT::eng` frame. The script emits transcript JSON/text, alignment TSV, and token/character edit-error metrics.

## Interpretation rule

Keep measurement separate from cultural interpretation. FFT/F0 alone cannot identify a country, ethnicity, or folk tradition.
