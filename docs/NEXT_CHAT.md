# NEXT CHAT — tmp-music handoff

この文書は、新しいChatGPT会話で `tmp-music` の作業を1行プロンプトだけで再開するための handoff である。

## 最初にやること

1. GitHub Connector でこのrepo `2rwa/tmp-music` を読む。**gh CLIは使わない。**
2. 開発作業を始める前に `2rwa/chatgpt-workspace/docs/build-test-fix.md` を読む。
3. 次の順で背景資料を読む。
   - `docs/audio-analysis-implementation-plan.md` — 実装計画、最優先
   - `docs/audio-analysis-research-survey.md` — 論文・技術調査
   - `docs/audio-analysis.md` — 現行解析手順
   - `docs/jugemu-analysis.md` — じゅげむ固有メモ
4. 現在の `main` HEAD と最新Actions状態を確認してから変更する。

## プロジェクトの目的

AI生成音楽、とくに異常・民俗的・rap的な歌唱を、聴感だけでなく再現可能な測定として解析する。

主な研究対象:

- 歌唱F0 / 連続ピッチ / 12-TETとの関係
- voice register / 裏返り / glissando / vibrato
- ASRが壊れる発音変形
- 日本語rapのモーラ・flow
- 反復ごとの発音/リズム変化
- source separation後のvocal-only解析
- 民俗歌唱との類似性を「国当て」にせず多次元で比較する

## 現在の基準曲

### Whisper AO

Source:

`samples/whisper-ao/source/whisper-ao.mp3`

- bridge経由でrepo保存済み
- size: 4,992,093 bytes
- SHA-256: `91f021f6906873c3e4ff4d72a82d2a3cc27faa1c312de98d6b7eee7352e9394b`
- 約207秒、実音は約155.7秒、末尾約51秒無音
- 埋め込み英語歌詞は正常な英語
- unusual vocal realizationによりWhisper ASRが大きく崩れる
- small autoでは英語以外の言語候補が上位になった実績あり
- whole-mix F0だけで非12TETとは断定しない

Results:

`analysis/whisper-ao/`

主なディレクトリ:

- `acoustic-auto/`
- `acoustic-reviewed/`
- `asr-small-full/`
- `asr-medium-full/`

### じゅげむ

Source:

`samples/jugemu/source/jugemu.mp3`

- bridge経由でrepo保存済み
- size: 5,790,694 bytes
- SHA-256: `e760ff46dcea8a1056a006a3373250da0a4f6f42616a74986b8182e8a33b31ab`
- 240秒
- 埋め込み歌詞は日本語の寿限無
- tempo候補: 約98.68 BPM / double-time 約197.37 BPM
- 反復周期中央値: 約28.75秒
- whole-track ASRは反復を大量削除するため、whole-track CERだけでは発音評価不可
- pYIN whole-mixでは推定tuning offset約+1 cent、nearest-12TET偏差中央値約10 cent

Results:

`analysis/jugemu/`

主なディレクトリ:

- `acoustic/`
- `repetition/`
- `asr-small/`
- `asr-medium/`

## 現在の実装

`scripts/analyze_audio.py`

- ffprobe / ID3
- active audio / silence
- STFT特徴
- section候補
- pYIN
- waveform / spectrogram

`scripts/asr_compare.py`

- faster-whisper
- auto / forced language
- embedded lyrics reference
- token edit / CER
- 日本語文字列対応済み

`scripts/repetition_analysis.py`

- MFCC template similarity
- cycle候補
- tempo候補

`scripts/old/`

- 調査中に使った一発スクリプト・途中版
- 削除しない

## 既知のActionsトラブルと対策

### PyAV 19 / faster-whisper

`faster-whisper 1.2.1` と PyAV 19 の互換性問題で:

`TypeError: open() got an unexpected keyword argument 'metadata_errors'`

が発生した。

対策:

`requirements-asr.txt` で `av<19`。

### artifact write-back漏れ

過去に:

- artifactを `analysis/` へ展開
- `git add analysis/<track>`

としてしまい、repoへ `ACTION_RUN.md` しか入らない事故があった。

現在は修正済み。write-back順は必ず:

`pull/rebase → artifact/result生成 → validation → add → commit → push`

artifact展開先と `git add` 対象を一致させる。

### バイナリ

大きめのバイナリをChatGPT側から直接repoへ入れる場合は、既存の private `2rwa/bridge` + Dropbox + Core2 self-hosted runner の経路を使う。

bridge側README/ドキュメントを先に確認する。

## 調査書

`docs/audio-analysis-research-survey.md`

以下を論文ベースで整理済み:

- STFT / CQT
- pYIN / CREPE / SPICE
- predominant melody extraction
- Demucs / Open-Unmix / Mel-RoFormer
- Whisper / WhisperX / lyrics alignment / MFA
- Japanese CER / mora
- rap tactus / beat / flow
- self-similarity / novelty / DTW
- CPPS / HNR / spectral tilt / formants
- MERT / CLAP
- computational ethnomusicology
- cross-cultural music similarity

## 実装計画

`docs/audio-analysis-implementation-plan.md`

Milestone 1〜7、TODO約50件を記載。

### 次に着手する最優先実装

**Milestone 1: Analyzer foundation**

1. `scripts/cli.py`
2. `config/tracks/whisper-ao.yml`
3. `config/tracks/jugemu.yml`
4. common provenance/status schema
5. synthetic pitch/rhythm fixtures
6. cheap CI
7. 現行3 analyzerを共通CLIから実行

その後:

**Milestone 2**

- Demucs vocal separation
- CREPE
- pYIN/CREPE consensus
- stable pitch target
- tuning model comparison
- mix vs vocal comparison

**Milestone 3〜4**

- multi-view SSM / DTW
- じゅげむ cycle分割
- cycle-level ASR
- kana/mora normalization
- MER

## 実装時のルール

- measurement と interpretation を分離
- source audioはimmutable
- source SHAを毎回検証
- tool/model versionを記録
- cheap test → heavy Actions
- synthetic known-answer testを優先
- heavy処理は120分timeoutを基本
- Actionsが30秒程度で終わらなければ、run URL/IDと状態を報告して会話ターンを返す
- 成功はexit codeだけで判断せず成果物を検証
- GitHub操作はGitHub Connectorを使う
- commitはGit Data API blob → tree → commit → update_ref が使用可能
- mainの並行writer競合を前提に `force=false`
- 民俗音楽の類似を一つのFFTやembeddingだけで国・民族へ断定しない

## 推奨する次の一手

新しい会話で特に追加指示がなければ、`docs/audio-analysis-implementation-plan.md` の **Milestone 1** から実装を開始する。

まず共通CLI + track config + provenance/status schema + synthetic fixture + cheap CIを作り、Whisper AOとじゅげむの既存解析を新CLI経由で再現する。

長い処理はActionsへ投げ、軽いテストは先に実行する。

## このhandoffの更新

大きな設計変更、Milestone完了、新しい基準曲追加、重要な既知バグ修正のたびにこのファイルを更新する。

一行継続プロンプトから復帰できることを壊さない。


## 2026-10-03 Milestone 1/2 progress

### Milestone 1 — complete

Analyzer foundation is implemented and validated.

Implemented:

- `scripts/cli.py`
- `config/tracks/whisper-ao.yml`
- `config/tracks/jugemu.yml`
- common provenance/status schema
- synthetic pitch/rhythm fixtures
- cheap CI
- existing acoustic/repetition/ASR analyzers routed through the common CLI

Validation:

- cheap CI success: Actions run `37083242829`
- real-audio foundation smoke success: Actions run `37083316389`
- both benchmark source SHA checks passed
- both tracks were exercised through the common CLI
- Whisper AO tiny-ASR, Jugemu repetition, and metadata stages produced validated outputs

### Milestone 2 — in progress

Implemented in main:

- `scripts/separate_vocals.py`
  - Demucs two-stem vocal/accompaniment separation
  - duration/RMS/finite/clipping/re-sum diagnostics
  - silent stem is treated as failure
- `scripts/analyze_pitch.py`
  - pYIN
  - torchcrepe
  - estimator agreement/consensus
- `scripts/detect_pitch_targets.py`
  - local slope + detrended variation
  - glissando rejection
  - moderate-vibrato retention
- `scripts/analyze_tuning.py`
  - 12/19/24/31 EDO residual comparison
  - global offset removal
  - interpretation warning
- `scripts/common/separation.py`
- `scripts/common/pitch.py`
- `requirements-separation.txt`
- `requirements-pitch-ml.txt`
- unit/regression tests for separation diagnostics, CREPE/pYIN consensus, stable targets, and 19-EDO fixture

Current validation runs:

- Demucs separation: `37084031007`
  - Whisper AO and Jugemu run in parallel
  - dependency install succeeded
  - both are currently in the separation step
- mix pYIN+CREPE: `37084031038`
  - Whisper AO and Jugemu run in parallel
  - Whisper AO reached pitch analysis
  - Jugemu is installing pitch dependencies
- cheap CI for this Milestone 2 code: `37084031010` — success

A previous Demucs run `37083721806` failed before installing dependencies because `actions/setup-python` had `cache: pip` without `cache-dependency-path`. This is fixed and recorded at:

`analysis/common/failures/20261003-setup-python-cache-path.md`

### Vocal-only dependency chain

`.github/workflows/milestone2-pitch-vocals.yml` is configured to trigger after successful completion of the Demucs workflow.

It:

1. receives the completed Demucs run ID and head SHA,
2. downloads `demucs-<track>` artifacts from that exact run,
3. runs pYIN + CREPE on `vocals.wav`,
4. runs stable-target detection,
5. runs EDO residual comparison,
6. uploads compact vocal-pitch artifacts.

This avoids re-running Demucs merely to analyze the vocal stem.

### Next checks

When resuming:

1. check run `37084031007` (Demucs)
2. check run `37084031038` (mix pitch)
3. if Demucs succeeded, find the automatically triggered vocal-pitch workflow run and check both matrix jobs
4. inspect actual `diagnostics.json`, `summary.json`, stable-note counts, and tuning residuals before declaring Milestone 2 complete
5. only after mix + vocal results both exist, add the explicit mix-vs-vocal comparison report

Do not declare Milestone 2 complete based only on process exit status; verify artifacts and measurement contents.
