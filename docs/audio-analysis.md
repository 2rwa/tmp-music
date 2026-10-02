# Audio analysis notes — Whisper AO

## Purpose

This repository is a disposable workspace for reproducible analysis of unusual vocal/rap generation.
The first sample is a Suno-generated track titled **Whisper AO**.

Target source path:

```text
samples/whisper-ao/source/whisper-ao.mp3
```

The binary is transferred through the private `2rwa/bridge` repository rather than written through the text-file API.

## Source integrity

Measured from the uploaded MP3 before transfer:

- file size: **4,992,093 bytes**
- SHA-256: `91f021f6906873c3e4ff4d72a82d2a3cc27faa1c312de98d6b7eee7352e9394b`
- container duration: **207.024 s**
- average container bitrate: about **192.9 kb/s**
- trailing silence detected with `ffmpeg silencedetect=noise=-50dB:d=1`:
  - silence start: **155.531563 s**
  - silence end: **206.999979 s**
  - silence duration: **51.468417 s**

The bridge writes a deterministic sidecar manifest next to the MP3. Use that manifest plus this SHA-256 when checking later Actions results.

## Embedded metadata

`ffprobe` / ID3 inspection found:

- title: `Whisper AO`
- Suno marker in the comment tag
- creation timestamp: `2025-03-11T00:53:09.298680+00:00`
- Suno id: `02502e60-67c4-44e1-8ff3-b9d458bc599c`
- an embedded English lyrics field (`lyrics-eng`)

The embedded lyrics are coherent English and are the best available reference text for ASR comparison. Do not treat an ASR transcript as the ground truth when this tag is present.

## Current working observations

The track is useful because it combines several separable phenomena:

1. non-lexical / vocable-like melodic singing at the beginning and end;
2. a central English rap-like section;
3. strong continuous pitch motion and ornament between stable pitch targets;
4. a pronounced change in spectral balance and rhythmic density during the rap section;
5. English source lyrics whose realized pronunciation can sound much less English-like than the written text.

A previous listening-only judgement over-interpreted the apparent pseudo-language. Reading the embedded lyrics showed that the source text is ordinary English. Future analysis must therefore distinguish **lexical content** from **realized phonetics**.

## Analysis pipeline

### 1. Integrity and container inspection

Cheap checks first:

```bash
sha256sum samples/whisper-ao/source/whisper-ao.mp3

ffprobe -v error \
  -show_entries format=duration,size,bit_rate:format_tags \
  -of json \
  samples/whisper-ao/source/whisper-ao.mp3

ffmpeg -hide_banner \
  -i samples/whisper-ao/source/whisper-ao.mp3 \
  -af silencedetect=noise=-50dB:d=1 \
  -f null -
```

Record the exact input SHA-256 in every generated report.

### 2. Decode once to an analysis waveform

Use one deterministic decode for downstream measurements:

```bash
ffmpeg -y -v error \
  -i samples/whisper-ao/source/whisper-ao.mp3 \
  -ac 1 -ar 24000 -c:a pcm_s16le \
  analysis/whisper-ao/mono-24k.wav
```

Keep the original MP3 unchanged.

### 3. Waveform, FFT and STFT

Generate:

- full-song waveform / RMS envelope;
- long-window FFT summaries for broad spectral balance;
- STFT spectrogram for time-localized harmonic and percussive structure;
- band-energy ratios, at minimum:
  - <300 Hz,
  - 300–1000 Hz,
  - 1–4 kHz,
  - >4 kHz;
- spectral centroid, bandwidth, rolloff and flatness.

Prefer STFT for comparisons between sections. A single FFT over the whole song hides the change from sparse vocal passages to the rap section.

Suggested Python stack:

- NumPy
- SciPy
- librosa
- soundfile
- matplotlib

### 4. Section / boundary detection

Compute short-time features in 20–50 ms frames:

- RMS;
- onset strength;
- spectral centroid;
- low-frequency energy ratio;
- zero-crossing rate;
- optional MFCC / chroma distance.

Use change-point detection or simple feature-distance peaks to propose section boundaries, then inspect them manually.

Expected broad structure to verify:

```text
opening non-lexical singing
        ↓
central English rap-like section
        ↓
return to non-lexical singing
        ↓
long trailing silence
```

Do not hard-code the currently estimated timestamps; let the Action recompute them from the audio.

### 5. Tempo and rhythmic density

Measure both global and section-local rhythm:

- onset autocorrelation;
- beat tracking;
- inter-onset interval histogram;
- onset count per second;
- syllable / word rate in the rap section after ASR alignment.

Report half-time / double-time alternatives instead of forcing a single BPM when the evidence is ambiguous.

### 6. Fundamental frequency and tuning

For voiced frames, extract F0 with one or more of:

- `librosa.pyin`;
- CREPE / torchcrepe;
- Praat / Parselmouth as a cross-check.

From F0:

1. convert Hz to MIDI / cents;
2. estimate the global tuning offset;
3. measure distance to the nearest 12-TET pitch center;
4. retain the continuous F0 trajectory rather than quantizing it away;
5. measure slide rate, vibrato range and rapid register jumps.

The current hypothesis is not “a non-12-TET scale” but rather “mostly conventional pitch targets connected by unusually continuous pitch motion and timbral/register changes”. The analysis should test this instead of assuming it.

### 7. ASR: multiple decoding conditions

Run at least these conditions on the central vocal section and on the full track:

- automatic language detection;
- forced `en`;
- at least two Whisper model sizes if compute budget allows;
- with and without leading/trailing non-lexical sections.

Recommended implementation for Actions:

- `faster-whisper` for practical CPU/GPU inference;
- preserve timestamps and per-segment confidence;
- export JSON, SRT/VTT and plain text.

The key question is not merely “can it transcribe English?” but **how the unusual vocal realization changes recognition errors**.

### 8. Reference-text alignment

Extract `lyrics-eng` from the MP3 with Mutagen or ffprobe and keep it as the reference text.

Compare ASR output with the embedded lyrics using:

- WER (word error rate);
- CER (character error rate);
- insertion / deletion / substitution counts;
- time alignment where possible.

Because sung text can repeat or stretch words, WER alone is insufficient. Always inspect the aligned text.

### 9. Phonetic / phoneme-level analysis

To investigate why coherent English sounds foreign or pseudo-linguistic:

1. convert the reference lyrics to phonemes (ARPAbet or IPA);
2. force-align words/phonemes to the audio if practical;
3. inspect consonant clusters, diphthongs and word boundaries;
4. measure vowel duration and F1/F2 where reliable;
5. identify epenthetic-vowel-like events and consonant weakening.

Useful candidates:

- Montreal Forced Aligner, WhisperX or another alignment tool;
- phonemizer / eSpeak-ng;
- Parselmouth for formants and voice-quality measurements.

Treat forced-alignment failures as data: they can identify the most heavily transformed passages.

### 10. Vocal / accompaniment separation

Optional later stage:

- Demucs or equivalent stem separation;
- repeat F0, formant and ASR analysis on the vocal stem;
- compare with the original mix.

Do not make stem separation a prerequisite for the first Action. It is expensive and can introduce artifacts.

### 11. Voice-quality measurements

For the non-lexical singing passages consider:

- harmonic-to-noise ratio;
- spectral tilt;
- cepstral peak prominence;
- formant tracks;
- abrupt register transitions;
- glissando slope;
- vibrato rate and extent.

These features are more useful for comparing vocal technique than guessing a geographic origin from listening alone.

### 12. Folk-style comparison: caution

Do not infer ethnicity, country or tradition directly from FFT or pitch alone.

A safer comparison is feature-based:

- vocables / non-lexical syllables;
- cyclic short motifs;
- glissando and ornament density;
- register switching;
- monophonic vs polyphonic texture;
- drone / interval friction;
- rhythmic freedom vs metrical accompaniment.

Then compare those documented features with published descriptions / recordings of candidate traditions. Treat terms such as yoik, kulning, Balkan singing, Amami shima-uta, Ainu song, etc. as hypotheses to test, not labels to assign from one generated recording.

## Proposed Action outputs

A future analysis workflow should write under:

```text
analysis/whisper-ao/
  metadata.json
  integrity.txt
  sections.json
  waveform.png
  spectrogram.png
  spectral-features.csv
  pitch-f0.csv
  pitch-summary.json
  asr/
    auto.json
    en.json
    reference.txt
    alignment.txt
    metrics.json
  report.md
```

Artifacts may be uploaded by Actions first; only compact, useful results should be committed back to the repo.

## Reproducibility rule

For every Actions run:

1. verify source SHA-256;
2. record tool versions;
3. generate machine-readable outputs;
4. preserve raw measurements separately from interpretation;
5. only then write a human-readable conclusion.

This follows the workspace Build → Test → Fix rule: measure first, do cheap checks before expensive work, and keep diagnostics that can catch regressions.

## Saved implementation

The programs used to reproduce the current measurements are saved in:

- `scripts/analyze_audio.py` — ffprobe/ID3, silence/active-end detection, FFT/STFT-derived features, candidate section boundaries, reviewed-section summaries, pYIN F0 and 12-TET distance, diagnostic plots.
- `scripts/asr_compare.py` — faster-whisper in auto/forced-English modes, extraction of the embedded `USLT::eng` lyrics, word/character edit metrics, and alignment TSV.
- `requirements-analysis.txt` and `requirements-asr.txt` — dependencies.

See `scripts/README.md` for exact commands. A local smoke test against Whisper AO passed for the non-pitch path using reviewed boundaries `21.7,77.5`; full pYIN and ASR are intended for Actions because they are the slower stages.

## ASR compatibility note (2026-10-02)

PyAV 19 removed the `metadata_errors` argument from `av.open()`, while `faster-whisper 1.2.1` still passes it in `decode_audio`. The first Actions run therefore failed in both small and medium ASR jobs with:

`TypeError: open() got an unexpected keyword argument 'metadata_errors'`

`requirements-asr.txt` pins `av<19` until faster-whisper releases a compatible decoder path.
