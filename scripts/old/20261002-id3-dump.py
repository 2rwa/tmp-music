#!/usr/bin/env python3
"""Exploratory one-off: dump ID3 frames from an MP3.

Archived from the inline command used while investigating Whisper AO.
"""
from mutagen.id3 import ID3
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "samples/whisper-ao/source/whisper-ao.mp3"
t = ID3(p)
for k, v in t.items():
    print(k, type(v).__name__, repr(str(v))[:800])
