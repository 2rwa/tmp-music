#!/usr/bin/env bash
# Exploratory one-off: verify analysis libraries, then inspect trailing silence.
# Archived from the inline commands used while investigating Whisper AO.
set -euo pipefail
AUDIO="${1:-samples/whisper-ao/source/whisper-ao.mp3}"

python - <<'PY'
mods=['numpy','scipy','librosa','soundfile','mutagen']
for m in mods:
    try:
        mod=__import__(m)
        print(m,'OK',getattr(mod,'__version__',''))
    except Exception as e:
        print(m,'NO',repr(e))
PY

ffmpeg -hide_banner -i "$AUDIO" \
  -af silencedetect=noise=-50dB:d=1 -f null - 2>&1 \
  | grep -E 'silence_(start|end)' | tail -20
