# tmp-music 音楽・歌唱解析 実装計画書

作成日: 2026-10-03  
対象リポジトリ: `2rwa/tmp-music`  
参照調査: `docs/audio-analysis-research-survey.md`  
実装原則: `chatgpt-workspace/docs/build-test-fix.md`  
現状スナップショット: `docs/STATUS_20261003.md`

> 進捗更新: 2026-10-03。M1〜M6は完了。M7はHOLDし、次目標はM6実測結果をレビューして決める。

---

## 0. 目的

tmp-music を、単発の音響実験置き場から、

- 生成音楽の歌唱法
- ラップのフロウ
- 発音変形
- 反復ごとの差
- 音高・調律
- 声質
- 民俗歌唱との類似性

を**再現可能・比較可能・検証可能**に解析できる実験基盤へ拡張する。

最初の基準曲は以下の2曲。

- `samples/whisper-ao/source/whisper-ao.mp3`
- `samples/jugemu/source/jugemu.mp3`

この2曲を回帰テスト兼ベンチマークとして使う。

---

## 1. 現状

### 1.1 既存実装

現在の主要スクリプト:

- `scripts/analyze_audio.py`
  - ffprobe / ID3
  - active-end / trailing silence
  - STFT由来特徴
  - section boundary候補
  - pYIN F0
  - 12-TET最近傍cent差
  - waveform / spectrogram

- `scripts/asr_compare.py`
  - faster-whisper
  - auto language / forced language
  - 埋め込み歌詞参照
  - token edit distance
  - CER
  - alignment TSV

- `scripts/repetition_analysis.py`
  - MFCC template similarity
  - 反復候補
  - beat tempo候補
  - cycle gap

- `scripts/old/`
  - 調査中の使い捨て・中間版

既存workflow:

- `.github/workflows/analyze-whisper-ao.yml`
- `.github/workflows/analyze-jugemu.yml`
- 復旧用workflow 2本

### 1.2 現状で確認できたこと

#### Whisper AO

- 正常な英語歌詞がID3に埋め込まれている。
- free ASRでは別言語判定や大きな誤認識が起きる。
- 非語彙歌唱 → rap → 非語彙歌唱の構造差がスペクトルにも出る。
- whole-mix pYINだけでは非12TET判定はできない。
- vocal-only解析が必要。

#### じゅげむ

- 正常な日本語歌詞がID3に埋め込まれている。
- 約29秒周期で同じ句が繰り返される。
- whole-track ASRは反復を大量削除する。
- whole-track CERだけでは発音品質を評価できない。
- cycle単位のalignmentが必要。
- F0はWhisper AOより12-TET付近へ強く集中する。

---

## 2. 実装方針

### 2.1 最重要原則

**測定と解釈を分離する。**

例:

- 測定: 「stable F0 target の中央値が12-TETから+17 cent」
- 解釈: 「微分音を意図した可能性がある」

を同じJSONへ書かない。

推奨:

    analysis/<track>/
      measurements/
      interpretation/

### 2.2 解析は層で分ける

    source
      ↓
    metadata / integrity
      ↓
    structure / beat
      ↓
    source separation
      ↓
    vocal F0 / voice quality
      ↓
    ASR / lyrics alignment
      ↓
    cycle comparison
      ↓
    embeddings / reference comparison
      ↓
    interpretation

上流の出力を再利用し、重いモデルを何度も回さない。

### 2.3 原音を絶対に加工保存しない

`samples/**/source/` は immutable と扱う。

- 原音
- bridge manifest
- source SHA-256

のみ。

派生WAV/stem/CSVは必ず `analysis/` 以下へ置く。

---

## 3. 目標ディレクトリ構造

最終形:

    tmp-music/
      samples/
        whisper-ao/
          source/
        jugemu/
          source/

      scripts/
        cli.py
        common/
          audio_io.py
          metadata.py
          schema.py
          provenance.py
          plotting.py
          text_normalize.py
          japanese.py
        analyze_audio.py
        separate_vocals.py
        analyze_pitch.py
        analyze_structure.py
        analyze_asr.py
        align_lyrics.py
        analyze_repetition.py
        analyze_voice.py
        analyze_embeddings.py
        compare_cycles.py
        compare_reference_corpus.py
        synthetic/
          generate_pitch_fixtures.py
          generate_rhythm_fixtures.py
          generate_structure_fixtures.py
          generate_asr_fixtures.py
        tests/
          test_metadata.py
          test_pitch.py
          test_tuning.py
          test_structure.py
          test_japanese_normalize.py
          test_artifact_layout.py
        old/

      config/
        tracks/
          whisper-ao.yml
          jugemu.yml
        models.yml
        analysis-defaults.yml

      analysis/
        whisper-ao/
        jugemu/

      docs/
        audio-analysis.md
        audio-analysis-research-survey.md
        audio-analysis-implementation-plan.md
        jugemu-analysis.md

      .github/
        workflows/
          analysis-ci.yml
          analyze-track.yml
          analyze-whisper-ao.yml
          analyze-jugemu.yml

---

## 4. 共通出力スキーマを最初に固定する

現状は各スクリプトが独立して出力しているため、後段で再利用しづらい。

### 4.1 provenance.json

全解析ディレクトリに共通で保存:

```json
{
  "source_sha256": "...",
  "source_path": "...",
  "git_commit": "...",
  "actions_run": "...",
  "analyzer": "pitch",
  "analyzer_version": "1",
  "parameters": {},
  "models": {},
  "tool_versions": {}
}
```

### 4.2 status.json

各stage:

```json
{
  "status": "success",
  "warnings": [],
  "started_from": "source",
  "outputs": []
}
```

失敗時も可能ならstatusを書き、後段が「ファイル無し」を成功扱いしない。

### 4.3 measurements JSON

数値結果には必ず:

- unit
- method
- scope
- confidence / coverage
- missing reason

を持たせる。

例:

```json
{
  "estimated_tuning_offset": {
    "value": 1.0,
    "unit": "cent",
    "method": "librosa.estimate_tuning",
    "scope": "whole_mix"
  }
}
```

---

# Phase 0 — 基盤整理

## P0-1. 共通CLI

新規:

- `scripts/cli.py`

想定:

    python scripts/cli.py metadata --track jugemu
    python scripts/cli.py structure --track jugemu
    python scripts/cli.py separate --track jugemu --model demucs
    python scripts/cli.py pitch --track jugemu --source vocals
    python scripts/cli.py asr --track jugemu --language ja
    python scripts/cli.py full --track jugemu

目的:

- workflowから直接個別Pythonを呼ばない
- path / config / provenanceを一元化
- track追加時にworkflowをコピーしない

### 完了条件

- 既存2曲をconfigだけで選択可能
- source SHA確認をCLIが自動実行
- unknown trackで明確に失敗
- `--dry-run` で実行予定stageを表示

---

## P0-2. Track config

`config/tracks/jugemu.yml` 例:

```yaml
id: jugemu
source: samples/jugemu/source/jugemu.mp3
language: ja
embedded_lyrics: true
expected_sha256: e760ff...
analysis:
  repetitions: true
  reference_lyrics: embedded
```

`whisper-ao.yml`:

- language: en
- nonlexical_vocal_sectionsを許容
- trailing silenceあり

### 完了条件

- source pathをコード内へhard-codeしない
- expected SHA mismatchで解析中止

---

## P0-3. requirements分割

推奨:

- `requirements-core.txt`
- `requirements-asr.txt`
- `requirements-separation.txt`
- `requirements-pitch-ml.txt`
- `requirements-voice.txt`
- `requirements-embeddings.txt`

重いTorch系をcoreへ入れない。

---

## P0-4. CI cheap tests

`.github/workflows/analysis-ci.yml`

pushで毎回やる:

- Python compile
- unit tests
- synthetic fixture生成
- cheap analyzer
- schema validation

**モデルダウンロードを伴う処理はCIに入れない。**

---

# Phase A — 実測精度を上げる

Phase Aが最優先。

---

## A1. Vocal source separation

### 新規

- `scripts/separate_vocals.py`

最初の実装:

1. Demucs系
2. 将来RoFormer系

### 入力

- original mix

### 出力

    analysis/<track>/stems/demucs/
      vocals.wav
      accompaniment.wav
      provenance.json
      status.json
      diagnostics.json

### diagnostics

- stem duration
- RMS
- clipping
- silence fraction
- re-sum residual
- vocal/accompaniment leakage proxy

### テスト

synthetic fixture:

- sine vocal + drum-like noise
- mixture = vocal + accompaniment
- output duration一致
- NaN無し
- silent output禁止

### 完了条件

- Whisper AO / じゅげむ両方でstem作成
- vocal stemをffprobe可能
- downstream F0が実行可能
- whole-mix F0との差をレポート

---

## A2. Multi-estimator F0

### 新規

- `scripts/analyze_pitch.py`

実装:

- pYIN
- CREPE/torchcrepe
- consensus

### 出力

    pitch/
      mix/
        pyin.csv
        crepe.csv
      vocals-demucs/
        pyin.csv
        crepe.csv
        consensus.csv
      summary.json

CSV:

- time_s
- f0_hz
- midi
- cents
- voiced probability/confidence
- source estimator

### consensus

両者が一定cent以内なら合意。

例:

- <= 25 cent: strong agreement
- <= 50 cent: weak agreement
- >50 cent: disagreement

閾値はconfig化する。

### テストfixture

- 440 Hz
- +25 cent
- 12-TET ascending scale
- linear glissando
- 6 Hz vibrato
- octave jump

### 完了条件

既知fixtureで:

- stable sine誤差が十分小さい
- glissandoが階段状に量子化されない
- octave jumpを検出
- estimator disagreementが保存される

---

## A3. Stable pitch target detector

### 新規

- `scripts/detect_pitch_targets.py`

目的:

「移動中のF0」と「音符として滞在しているF0」を分離。

### 特徴

- slope cents/s
- duration
- local variance
- confidence
- vibrato compensation

### 出力

`stable-notes.csv`

- start/end
- median F0
- median cents
- dwell
- vibrato extent
- confidence

---

## A4. Tuning model comparison

### 新規

- `scripts/analyze_tuning.py`

候補:

- 12-TET
- 19-EDO
- 24-EDO
- 31-EDO

初期版ではjust intonation自動同定は後回し。

### 方法

1. global offset除去
2. stable targetのみ使用
3. duration/confidence weighted residual
4. 各モデルへfit
5. score比較

### 出力

`tuning-models.json`

重要:

**best modelを「曲の音階」と断定しない。**

出力は:

- fit error
- coverage
- number of targets
- ambiguity

### 回帰目標

#### Whisper AO

whole-mixとvocal stemで結論差を記録。

#### じゅげむ

12-TET fitが現状値と矛盾しないこと。

---

# Phase A5 — 構造解析を強化

## A5-1. Multi-view SSM

新規:

- `scripts/analyze_structure.py`

features:

- MFCC
- chroma/CQT
- onset
- tempogram
- optional F0

出力:

    structure/
      ssm-mfcc.npy
      ssm-mfcc.png
      ssm-chroma.npy
      ssm-onset.npy
      novelty.json
      boundaries.json

### 完了条件

じゅげむの約29秒反復がMFCC以外でも確認可能。

---

## A5-2. Beat-sync / tempo ambiguity

出力:

`tempo.json`

- primary tempo
- half
- double
- confidence
- beat timestamps

**単一BPMを確定値として出さない。**

じゅげむ:

- ~98.7
- ~197.4

を候補として保持する。

---

# Phase A6 — Cycle analyzer

じゅげむで最優先。

### 新規

- `scripts/compare_cycles.py`

### 手順

1. cycle startを構造解析から取得
2. cycleごとに切り出し
3. beat-sync
4. DTW alignment
5. feature差分

比較:

- duration
- onset density
- F0
- voice quality later
- ASR later
- embedding later

### 出力

    cycles/
      cycle-01/
      ...
      cycle-08/
      cycle-boundaries.json
      cycle-distance.csv
      cycle-dtw.json

### 完了条件

現在の候補:

- 12.0
- 40.75
- 69.5
- 96.0
- 127.25
- 156.0
- 184.75
- 213.5

付近に合理的対応が得られる。

ただしこの時刻をtest expectedへhard-codeしすぎない。
許容幅を持つ。

---

# Phase A7 — Cycle-level ASR

### 既存

`scripts/asr_compare.py`

を分割:

- `scripts/analyze_asr.py`
- `scripts/text_normalize.py`
- `scripts/japanese.py`

### 各cycleで実行

- auto
- forced ja
- small
- medium

全曲mediumは診断価値が低い場合、cycle解析を優先。

### 出力

    lyrics/asr/cycle-01/
      auto.json
      ja.json
      metrics.json

### 指標

- raw CER
- normalized CER
- deletion
- insertion
- substitution
- recognized duration
- no-speech probability

### 完了条件

whole-track CERとcycle CERを別表示。

「反復省略」と「発音誤認識」を分離する。

---

# Phase A8 — 日本語モーラ解析

### 新規

- `scripts/common/japanese.py`

処理:

    original
      ↓
    Unicode normalize
      ↓
    kana
      ↓
    mora units

最低限対応:

- 長音
- 促音
- 撥音
- 拗音
- カタカナ/ひらがな統一

例:

- じゅ → 1 mora
- げ → 1
- む → 1

### 出力

- reference-mora.txt
- hypothesis-mora.txt
- mora-alignment.tsv
- MER

### 完了条件

「じゅげむ」「しゅうりんがん」等を期待どおり分割。

---

# Phase B — 発音と声質

Phase Aでvocal stemとalignmentが安定してから進む。

---

## B1. Known-lyrics forced alignment

優先順位:

1. WhisperX系を試す
2. MFAを比較
3. singing-specific alignmentの導入可否を評価

### 新規

- `scripts/align_lyrics.py`

### 英語

Whisper AO:

- word
- phoneme

### 日本語

じゅげむ:

- phrase
- mora
- phoneme

### 出力

- alignment.json
- alignment.tsv
- failed-spans.json
- timing error / confidence

### 重要

forced alignment failureを削除しない。

「標準発音モデルから外れた候補」として保存する。

---

## B2. Phonetic distortion

### 新規

- `scripts/analyze_pronunciation.py`

Whisper AO:

- consonant cluster breaking
- diphthong変形
- vowel insertion
- word-boundary shift

じゅげむ:

- mora deletion
- consonant weakening
- vowel change
- long vowel
- palatalized mora

### 出力

`pronunciation-events.csv`

---

## B3. Voice quality

### 新規

- `scripts/analyze_voice.py`

Praat/Parselmouth候補。

測定:

- CPPS
- HNR
- spectral tilt
- F1/F2/F3
- intensity
- register transitions
- vibrato
- glissando

### 区間選択

全frameへ無理に適用しない。

対象:

- stable voiced
- vowel-dominant
- F0 confidence high

### 出力

    voice/
      frames.csv
      stable-segments.csv
      register-breaks.csv
      summary.json

---

## B4. Register transition detector

目的:

元ちとせ的な「裏返り」やAI生成の声区切替を定量化する。

候補特徴:

- F0 jump
- spectral tilt jump
- CPPS jump
- formant continuity
- energy redistribution

出力:

- start/end
- before/after F0
- before/after source features
- confidence

---

# Phase C — Learned embeddings と文化的比較

このPhaseは**分類器を作ることが目的ではない**。

---

## C1. MERT embeddings

新規:

- `scripts/analyze_embeddings.py`

まず:

- full section
- vocal section
- cycle

でembeddingを保存。

### 出力

- embeddings.npy
- windows.csv
- model metadata

---

## C2. CLAP exploratory labels

用途:

- chant-like
- rap
- folk vocal
- vocalise
- spoken
- melodic

などの粗い探索。

民族名をfinal labelとして使わない。

---

## C3. Reference corpus manifest

新規:

`reference-corpus/manifest.csv`

列:

- id
- tradition
- region
- country
- performer
- recording date
- source URL
- license
- notes
- reliability

**音源ライセンスを確認できない場合はURL/metadataのみ保存。**

---

## C4. Cross-cultural comparison

新規:

- `scripts/compare_reference_corpus.py`

比較軸:

- melody
- rhythm
- timbre
- voice quality
- articulation
- embedding

出力例:

```json
{
  "reference_id": "...",
  "similarity": {
    "melody": 0.0,
    "rhythm": 0.0,
    "timbre": 0.0,
    "voice_quality": 0.0,
    "embedding": 0.0
  }
}
```

総合「国判定」は作らない。

---

# Phase D — レポート自動生成

### 新規

- `scripts/build_report.py`

出力:

    analysis/<track>/report/
      measurements.md
      interpretation.md
      provenance.json

### measurements.md

自動生成のみ。

- source
- integrity
- structure
- tempo
- pitch
- tuning
- ASR
- cycles
- voice quality

### interpretation.md

人間/LLMが読む用。

自動数値と推測を明確に分離。

---

# 5. Actions 設計

現行の曲別workflowは残しつつ、最終的には共通化する。

---

## 5.1 analyze-track.yml

`workflow_dispatch`

inputs:

- track
- stages
- separation model
- asr model
- heavy embeddings on/off

### Job graph

    preflight
       ↓
    core
     ├── structure
     ├── separation
     └── raw-asr
           ↓
      pitch-vocal
           ↓
       alignment
        ↙     ↘
     voice   cycles
        ↘     ↙
         report

### artifact

各jobが必ずartifactを出す。

後段はartifactを明示的に取得。

---

## 5.2 repo write-back

最終job:

1. checkout
2. pull/rebase
3. artifact download
4. validation
5. git add
6. commit
7. push

既知の回帰:

- artifactを `analysis/` へ展開したのに `analysis/<track>` だけaddし、成果物がrepoへ入らなかった。

### 回帰テスト

最終jobで必須:

    test -s analysis/<track>/.../metadata.json
    test -s analysis/<track>/.../metrics.json

さらに:

    git diff --cached --name-only

をログに出す。

---

## 5.3 parallel writer 対策

同一track:

`concurrency.group = analyze-${track}`

別trackは並列可。

結果書き戻しでmainが進んだ場合:

- pull --rebase before result generation/download
- push failure時は自動forceしない
- conflictならartifactを残して失敗

---

# 6. Synthetic regression suite

最優先で作る。

`tests/fixtures/generated/` は生成物なのでgit管理せず、fixture generatorを管理する。

---

## 6.1 Pitch

### fixture P1
440 Hz sine

expected:
- ~440 Hz
- ~A4
- tuning ~0 cent

### P2
A4 +25 cent

expected:
- stable target +25 cent

### P3
linear glissando

expected:
- stable target detectorが全区間をnote扱いしない

### P4
6 Hz vibrato

expected:
- center pitchを維持
- vibrato rate近傍

### P5
19-EDO scale

expected:
- 12-TET fitより19-EDO fitが改善

---

## 6.2 Rhythm

### R1
100 BPM clicks

### R2
100 BPM + eighth notes

expected:
- 100/200 ambiguityを保存

### R3
tempo drift

expected:
- global BPMだけでなくlocal tempogram差

---

## 6.3 Structure

### S1
A-A-A-A

expected:
- 4 repeats

### S2
A-B-A-B

expected:
- recurrence pattern

### S3
time-stretched A repeats

expected:
- raw similarityよりDTW後 similarity改善

---

## 6.4 Japanese

unit tests:

- じゅげむ
- しゅうりんがん
- ちょうきゅうめい
- きゃ / きゅ / きょ
- っ
- ん
- ー

---

# 7. ベンチマーク曲の回帰条件

---

## 7.1 Whisper AO

hard invariant:

- source SHAが既知値
- ID3 lyrics取得可能
- trailing silenceを検出
- ASR auto/forced-enを両方保存
- vocal stem解析可能

soft regression:

- auto languageが英語固定とは限らない
- ASR errorが高い
- central rap sectionの低域/onsetが前後と異なる

soft regressionは閾値を広くする。
モデル更新で値が変わり得るため。

---

## 7.2 じゅげむ

hard invariant:

- source SHAが既知値
- 240 s
- Japanese lyrics取得可能
- repetition analyzerが複数cycleを出す

soft regression:

- cycle gapが約29秒
- tempo候補が約99/197 BPM
- whole-track ASRはdeletion多め
- pitch targetがWhisper AOより12-TET近傍へ集中する傾向

---

# 8. 成果物のgit管理方針

Gitへ入れる:

- JSON
- CSV
- TSV
- Markdown
- diagnostic PNG
- 小さいembedding summary

artifactのみ:

- large WAV
- separated stems
- large model output
- huge numpy arrays
- model checkpoints

必要に応じてbridge/Dropboxを利用。

---

# 9. 失敗を記録する

`analysis/<track>/failures/`

例:

- PyAV 19 / faster-whisper compatibility
- artifact write-back path mismatch
- F0 timeout / OOM
- alignment failure

形式:

    YYYYMMDD-short-name.md

内容:

- symptom
- log excerpt
- root cause
- fix
- regression test

「直したら消す」のではなく、再発防止資産として残す。

---

# 10. 実装順序

依存関係込みの順序。

## Milestone 1 — Analyzer foundation — COMPLETE

- [x] P0-1 common CLI
- [x] P0-2 track config
- [x] P0-3 common provenance/status schema
- [x] P0-4 cheap CI
- [x] synthetic pitch/rhythm fixtures
- [x] existing analyzersをCLI経由で実行

### 完了条件

2曲の既存解析結果を新CLIから再生成できる。

**Validation:** cheap CI `37083242829`、real-audio smoke `37083316389` とも success。

---

## Milestone 2 — Vocal/pitch — COMPLETE

- [x] A1 Demucs separation
- [x] A2 CREPE
- [x] pYIN/CREPE consensus
- [x] stable target
- [x] tuning model comparison
- [x] mix vs vocal比較

### 完了条件

Whisper AO / じゅげむで:

- mix
- vocal

両方のF0比較レポートが出る。

**Validation:** Demucs `37085412905`、mix pitch `37085412917`、vocal pitch `37085675663`、mix-vocal comparison `37087024191` は両曲 success。

---

## Milestone 3 — Structure/cycles — COMPLETE

- [x] multi-view SSM
- [x] tempo candidates — structure gridから独立した高時間分解能onset envelopeで98.68/197.37 BPM候補を実測
- [x] cycle boundaries
- [x] DTW
- [x] cycle-distance

### 完了条件

じゅげむの全主要反復をcycle単位に分割できる。

**Current measurement:** selected period 28.75 s、aligned starts `12.00, 40.75, 69.50, 98.50, 127.25, 156.00, 184.75, 213.50` s。structure/cycle本体はrun `37086468933` で success。Jules追加tempo validationはrun `37086741133`, `37087024183` で regression を検出。

---

## Milestone 4 — Japanese lyrics — COMPLETE

- [x] Japanese normalization
- [x] mora tokenizer
- [x] cycle-level Whisper
- [x] CER/MER
- [x] cycle-to-cycle ASR comparison

### 完了条件

じゅげむで各周回ごとの:

- CER
- MER
- deletion
- substitution

を比較できる。

旧reference方式のcycle-ASRはrun `37086549657` で success。cycle-specific contiguous reference partitionへ改善後、実音源run `37089898445` も success。8 cycleすべてでCER/MER/deletion/substitutionを保存し、M4完了。

---

## Milestone 5 — Forced alignment — COMPLETE

- [x] English alignment — Whisper AO 0.0–77.5 s、117 words / 407 phones
- [x] Japanese alignment — Jugemu 8/8 cycles、396 words / 1956 phones
- [x] failed-span保存 — `failed-spans.json`
- [x] phoneme/mora timestamps — 969 mora。phone support無しwordはfailed spanとして保持

### 完了条件

Whisper AOで元歌詞のword/phoneを、Jugemuで各cycleのword/phone/moraを時刻付きで保存できる。

**Validation:** `37095819243`, `37096648316` は両曲 success。最新のWhisper AO単独failure `37097371836` はMFA model downloadの `ModelsConnectionError` であり、alignment実装回帰ではない。

---

## Milestone 6 — Voice quality — COMPLETE

- [x] calibrated CPPS — Praat 6.4.49、stable vocal区間で実音源測定
- [x] Praat HNR(cc)
- [x] autocorrelation HNR
- [x] spectral tilt
- [x] F1/F2/F3 Burg formants
- [x] vibrato — M2 stable-target情報をM6へ統合
- [x] glissando — M2 consensus由来のpitch-movement候補を統合
- [x] register transitions — multi-feature候補検出

### candidate semantics

pitch-movementはglissandoの**候補**であり、意図的glissandoとは断定しない。

既定条件:

- window 0.30 s
- |slope| >= 200 cent/s
- total change >= 60 cent
- linear-fit R² >= 0.80
- window結合後にも同じ条件を再確認

register transition候補は:

- F0 discontinuity
- calibrated CPPS / Praat HNR / autocorrelation HNR / spectral tilt のうち2種類以上の独立変化

を必須とする。

F1/F2/F3・intensity・vibratoはbefore/afterの補助contextとして保持するが、phoneme差だけでregister候補にならないよう成立条件には使わない。

### 最終validation

- cheap CI `37101306895` — success
- Praat known-answer smoke `37101306899` — success
- M6 real-audio E2E `37101306889` — Whisper AO / Jugemu とも success
- artifact:
  - Whisper AO `11266196721`
  - Jugemu `11266885749`
- `provenance.json` の `tool_versions.praat` に Praat 6.4.49 を保存していることをartifact展開後に確認

### 完了条件

CPPS / 2系統HNR / tilt / formants / M2 F0系特徴をstable vocal区間で取得し、register transition候補を複数特徴のbefore/afterとしてmachine-readableに保存できる。Whisper AO / Jugemu両方でE2E successし、cheap CI・known-answer smoke・provenance・artifactまで確認済み。

---

## Milestone 7 — Cultural comparison — HOLD / NOT STARTED

M6は完了したが、M7へ自動的には進まない。次の目標はM6実測結果をレビューした上でユーザーと決める。


- [ ] reference corpus manifest
- [ ] MERT
- [ ] CLAP
- [ ] dimension-level similarity
- [ ] human-audition shortlist

### 完了条件

「○○民謡」と即断せず、

- 旋律は近い
- リズムは遠い
- 声質は近い
- embeddingでは候補Xが近い

のように説明できる。

---

# 11. 実装時に後回しにするもの

初期段階ではやらない:

- 独自ニューラルモデル学習
- 国籍/民族分類器
- 大規模スクレイピング
- GPU必須前提
- just intonationの完全自動同定
- end-to-end万能モデル
- UI/dashboard

先に測定基盤を固める。

---

# 12. 最初に着手すべき具体的PR相当

次の実装単位はこれが最も効率的。

## Implementation 1

**Analyzer foundation + synthetic tests**

追加:

- `scripts/cli.py`
- `scripts/common/schema.py`
- `scripts/common/provenance.py`
- `config/tracks/*.yml`
- `scripts/synthetic/generate_pitch_fixtures.py`
- `scripts/tests/test_pitch.py`
- `.github/workflows/analysis-ci.yml`

既存:

- analyze_audio.py
- asr_compare.py
- repetition_analysis.py

は内部関数化を最小限にし、CLIから呼べるようにする。

## Implementation 2

**Demucs + vocal pitch**

追加:

- separate_vocals.py
- analyze_pitch.py
- consensus
- stable targets

## Implementation 3

**Jugemu cycle + mora**

追加:

- cycle segmentation
- Japanese normalization
- mora alignment
- cycle-level ASR

この3単位まで実装すれば、今回の2曲に対して、現在よりかなり強い結論を出せる。

---

# 13. Definition of Done

機能単位の「完了」は次を全部満たすこと。

- [ ] source SHAを記録
- [ ] parametersを記録
- [ ] tool/model versionを記録
- [ ] machine-readable outputあり
- [ ] cheap synthetic testあり
- [ ] 実曲2曲の少なくとも片方で実測
- [ ] failure時にnon-zero
- [ ] empty resultをsuccess扱いしない
- [ ] Actions artifactあり
- [ ] repo write-backの必要ファイルを確認
- [ ] docs更新
- [ ] interpretationとmeasurementを分離

---

# 14. 成功指標

このプロジェクトの成功は「モデルを多く使った」ことではなく、次で測る。

1. 同じ入力・同じcommitで同じ解析を再現できる。
2. whole-mix由来の誤推論をvocal-onlyで検証できる。
3. 非12TETとglissandoを混同しない。
4. free ASR失敗と実際の発音変形を区別できる。
5. 反復曲でwhole-track CERに依存しない。
6. 「どこの民謡か」を単一特徴で断定しない。
7. 解析失敗が次回の回帰テストになる。
8. 新しい曲をtrack config追加だけで解析できる。

---

## 15. 関連ドキュメント

- `docs/audio-analysis.md` — 現行解析手順
- `docs/audio-analysis-research-survey.md` — 文献調査と技術選定根拠
- `docs/jugemu-analysis.md` — じゅげむ固有の観測
- `docs/STATUS_20261003.md` — 現在の実装・実測・既知課題
- `scripts/README.md` — 現行スクリプト実行方法

この計画書は、調査書の「何が有効か」を、tmp-music上で「何をどの順に作り、どう検証するか」へ変換したものとして扱う。
