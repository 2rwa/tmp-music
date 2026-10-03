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


## Reproducible measurements — 2026-10-03

The initial local observations have now been followed by the common pipeline and Actions measurements.

### Vocal separation and pitch

Validated runs:

- Demucs: `37085412905`
- mix pitch: `37085412917`
- vocal pitch: `37085675663`
- mix-vocal comparison: `37087024191`

Whole mix:

- pYIN voiced fraction: **0.7193**
- CREPE reliable fraction: **0.0**
- strict pYIN/CREPE consensus coverage: **0.0**
- selected F0 coverage: **0.00208**
- stable target count: **0**

Demucs vocal stem:

- pYIN voiced fraction: **0.8286**
- CREPE reliable fraction: **0.5134**
- strict consensus coverage: **0.4039**
- selected F0 coverage: **0.5274**
- stable targets: **22**
- stable-target duration: **5.90 s**

Vocal stable-target EDO residuals:

| Model | weighted RMSE |
| --- | ---: |
| 12-EDO | 5.535 cent |
| 19-EDO | 8.488 cent |
| 24-EDO | 5.535 cent |
| 31-EDO | 7.227 cent |

12-EDO and 24-EDO are tied under this residual definition. Do not identify a tuning system from the lowest residual alone.

The important result is methodological: **the Jugemu mix is a poor input for CREPE pitch measurement, while the separated vocal stem supplies substantial reliable/consensus F0 coverage.**

### Multi-view recurrence and cycle alignment

Validated structure run: `37086468933`.

Strongest combined recurrence candidate:

- **28.75 s**

Template-aligned cycle starts:

`12.00, 40.75, 69.50, 98.50, 127.25, 156.00, 184.75, 213.50 s`

This supersedes the preliminary middle-cycle estimate of 96.00 s. The recurrence period and local alignment are stored separately so local timing drift does not redefine the global period.

### Tempo regression note

Jules added explicit primary/half/double tempo candidates, which is the correct representation for metrical ambiguity, but the first implementation reused the coarse 0.25 s structure grid.

That produced:

- 120 BPM
- 60 BPM
- 240 BPM

with artificially perfect beat regularity.

This conflicts with the earlier higher-resolution onset result of approximately **98.68 / 197.37 BPM**. The Jules tempo values are therefore not accepted as the final tempo measurement. Tempo analysis must be rerun with a finer independent hop.

### Cycle-level Japanese ASR

The first cycle-ASR workflow (`37086549657`) completed successfully, proving the aligned-cycle → Whisper → mora-metric pipeline works.

However, that first run compared each short cycle transcript against the whole embedded lyric. Jules subsequently added a **cycle-specific contiguous reference partition**:

- canonical cycle line count: 10
- expected eight-cycle line counts: `10, 10, 10, 10, 10, 9, 9, 9`

The revised reference logic passes cheap CI (`37087076630`). Real-audio E2E revalidation is still pending because the upstream structure workflow currently fails on the separate tempo regression.

Until that rerun completes, do not report the old cycle CER/MER values as final pronunciation measurements.
