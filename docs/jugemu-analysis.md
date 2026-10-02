# Jugemu analysis

Source: `samples/jugemu/source/jugemu.mp3`

## Integrity / embedded metadata

- size: **5,790,694 bytes**
- SHA-256: `e760ff46dcea8a1056a006a3373250da0a4f6f42616a74986b8182e8a33b31ab`
- container duration: **240.024 s**
- title: `じゅげむ`
- Suno creation timestamp: `2025-04-04T12:35:58.895021+00:00`
- Suno id: `15e4cb7f-49d2-43c4-bc0a-8a2b54af2569`

The MP3 contains a `lyrics-eng` ID3 field, but the actual text is Japanese hiragana. It is the reference lyric for ASR comparison.

## Preliminary local measurements

Cheap local analysis before Actions:

- active audio reaches the end of the 240 s file; no ~50 s trailing silence like Whisper AO
- beat tracker: about **98.68 BPM**, with **~197.37 BPM** as the obvious double-time interpretation
- mean spectral centroid: about **2.42 kHz**
- energy below 300 Hz: about **68.4%**
- 300–1000 Hz: about **15.8%**
- 1–4 kHz: about **13.1%**
- repeated-cycle template matching suggests vocal-cycle starts near:
  `12.00, 40.75, 69.50, 96.00, 127.25, 156.00, 184.75, 213.50 s`
- most cycle spacing is roughly **28.7–30 s**; the middle has a structural deviation.

These are preliminary measurements, not the final Actions output.

## Questions for Actions

1. Does Whisper identify the language as Japanese without forcing `ja`?
2. How different are automatic-language and forced-Japanese transcripts?
3. CER against the embedded correct Jugemu text.
4. Which syllables / mora-like sequences are systematically transformed?
5. Does pronunciation drift across the repeated cycles?
6. Is tempo / onset density stable while pronunciation changes?
7. Are pitch targets conventional 12-TET despite the unusual vocal articulation?
8. How similar are the repeated cycles acoustically, and where does the arrangement deviate?

## Japanese ASR metric note

The ASR comparison script now supports Japanese. Its token metric treats contiguous Japanese script spans as token units; the more useful precision metric is **CER**, computed after removing spaces and punctuation.
