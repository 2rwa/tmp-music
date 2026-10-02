# Analysis scripts

## Acoustic analysis

Requires ffmpeg / ffprobe and the packages in requirements-analysis.txt.

    python -m pip install -r requirements-analysis.txt
    python scripts/analyze_audio.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao

For a cheap smoke test, add --skip-pitch. The full Actions run should normally include pYIN pitch analysis.

Automatic section boundaries are only candidates. To reproduce the listening-assisted comparison used during the initial investigation:

    python scripts/analyze_audio.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao --boundaries 21.7,77.5

Outputs include metadata.json, sections.json, spectral-features.csv, pitch-f0.csv, pitch-summary.json, waveform.png, spectrogram.png and embedded-lyrics-eng.txt.

## ASR / embedded-lyrics comparison

Install the optional ASR dependency:

    python -m pip install -r requirements-asr.txt

Run automatic language detection and forced English:

    python scripts/asr_compare.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao/asr --model small --modes auto,en

The central section can be isolated with --start / --end after the boundaries are reviewed:

    python scripts/asr_compare.py samples/whisper-ao/source/whisper-ao.mp3 --out analysis/whisper-ao/asr-central --model small --modes auto,en --start 21.7 --end 77.5

The reference text comes from the MP3 USLT::eng ID3 frame. The script emits transcript JSON/text, word alignment TSV, and word/character edit-error metrics.

## Interpretation rule

Keep measurement separate from cultural interpretation. FFT/F0 alone cannot identify a country, ethnicity, or folk tradition.
