# NEXT CHAT — tmp-music handoff

この文書は、新しいChatGPT会話で `2rwa/tmp-music` の作業を1行プロンプトから再開するための handoff である。

## 最初に読む

1. `2rwa/chatgpt-workspace/docs/build-test-fix.md`
2. `docs/STATUS_20261003.md` — 現在の実装・実測・既知課題
3. `docs/audio-analysis-implementation-plan.md` — Milestone 1〜7
4. `docs/audio-analysis-research-survey.md` — 技術・論文調査
5. `scripts/README.md` — 現行コマンド

GitHub操作は GitHub Connector を使い、**gh CLI は使わない**。  
変更前に現在の `main` HEAD と最新Actions状態を確認する。

---

## プロジェクト目的

AI生成音楽、とくに unusual / rap / nonlexical / folk-like vocal を、聴感だけでなく再現可能な測定として解析する。

主要テーマ:

- 歌唱F0 / stable pitch / tuning
- glissando / vibrato / register
- source separation後の vocal-only解析
- ASR failure と発音変形
- 日本語mora / flow
- 反復ごとの差
- multi-view structure / cycle
- forced alignment
- voice quality
- cultural comparisonを単一ラベルへ潰さず多次元で扱う

---

## ベンチマーク音源

### Whisper AO

`samples/whisper-ao/source/whisper-ao.mp3`

- size: 4,992,093 bytes
- SHA-256: `91f021f6906873c3e4ff4d72a82d2a3cc27faa1c312de98d6b7eee7352e9394b`
- 約207秒
- 末尾約51秒無音
- embedded English lyrics
- unusual vocal realizationでWhisperが大きく崩れる

### Jugemu

`samples/jugemu/source/jugemu.mp3`

- size: 5,790,694 bytes
- SHA-256: `e760ff46dcea8a1056a006a3373250da0a4f6f42616a74986b8182e8a33b31ab`
- 240秒
- embedded Japanese lyrics
- recurrence period: 約28.75秒
- 従来tempo候補: 約98.68 / 197.37 BPM
- whole-track CERは反復削除のため発音評価に不適切

---

## 現在のMilestone

### M1 Analyzer foundation — COMPLETE

実装・実測済み:

- common CLI
- track config
- source SHA verification
- provenance / status
- cheap CI
- synthetic pitch / rhythm / structure fixtures
- existing analyzers integration

主要run:

- `37083242829` cheap CI success
- `37083316389` real-audio foundation smoke success

### M2 Vocal / pitch — COMPLETE

実装済み:

- Demucs
- pYIN + torchcrepe
- estimator agreement / confidence-aware fallback
- stable target
- 12/19/24/31 EDO fit
- mix vs vocal comparison

主要run:

- Demucs: `37085412905`
- mix pitch: `37085412917`
- vocal pitch: `37085675663`
- mix-vocal compare: `37087024191`

すべて両曲 success。

重要実測:

- Jugemu mix: CREPE reliable 0%, stable targets 0
- Jugemu vocals: CREPE reliable 51.3%, consensus 40.4%, stable targets 22
- Whisper AO: vocal stemで stable targets 69 → 104

whole-mixだけから歌唱pitchを結論しない。

### M3 Structure / cycles — COMPLETE

run `37089824512` success。Jugemu primary/half/double = 98.6842 / 49.3421 / 197.3684 BPM。tempo hop 512 samples = 0.032 s。recurrence 28.75 s。

### M4 Japanese lyrics — COMPLETE

run `37089898445` success。cycle-specific referenceで8 cycleのCER/MER/substitution/deletion/insertionを保存。free ASR deletionが支配的なので発音差と直結させない。

### M5 Forced alignment — COMPLETE

MFA 3.4.2ベースの既知歌詞alignmentを実音源で検証済み。

- final run `37095819243` — Whisper AO / Jugemu とも success
- Whisper AO:
  - 0.0–77.5 s の既知歌詞区間へ限定
  - beam / retry beam = 100 / 400
  - 117 words / 407 phones
  - failed spans 0
- Jugemu:
  - M3 aligned cycles 8本を既知歌詞chunkへ対応
  - Japanese tokenizer依存 `spacy sudachipy sudachidict-core` をActionsへ追加
  - beam / retry beam = 100 / 400
  - 396 words / 1956 phones / 969 mora
  - 8/8 cycle aligned
  - partial failed span 1件: cycle-07 `ぽん` 201.85–212.49 s はword intervalにphone supportが無いため、架空の長大moraを生成せず `failed-spans.json` に保持
  - mora最大長は品質修正後 0.60 s
- Japanese mora時刻は、MFA phoneが実際に重なるword span内での明示的equal projection。phoneそのものの境界と同一ではない。

MFA failure時は `mfa.log` をartifactだけでなくActions stderrにも出す。

### M6 Voice quality — PARTIAL

M2内に:

- stable pitch
- vibrato retention
- glissando rejection

はある。

未実装:

- CPPS
- HNR
- spectral tilt
- formants
- register transition detector

### M7 Cultural comparison — NOT STARTED

調査・設計のみ。

---

## 次にやること

最優先:

1. M6 voice-quality analyzer の最小実装
2. stable voiced / vocal stem を対象に CPPS・HNR・spectral tilt を機械可読で保存
3. synthetic known-answer / sanity test と cheap CI を追加
4. 実音源Actionsで Whisper AO / Jugemu の少なくとも片方を測定
5. formants と register transition detector を追加し、F0だけではない声区変化へ拡張

M5のJapanese moraはphone-supported spanへ制約済み。厳密なphone→mora音韻対応は、M6を止めてまで先行実装せず、必要になった時点で独立改善する。

---

## 実装ルール

- measurement / interpretation を分離
- source audioはimmutable
- source SHAを毎回検証
- tool/model versionを記録
- cheap test → heavy Actions
- synthetic known-answerを優先
- heavy処理は原則120分timeout
- Actionsが長時間ならrun IDと状態を残して会話を返す
- exit codeだけで成功判定しない
- empty resultをsuccess扱いしない
- failureは記録してregression test化
- main更新は並行writerを前提にforceしない
- 民俗・文化的類似を単一特徴から断定しない

---

## 既知failure

- `analysis/common/failures/20261003-setup-python-cache-path.md`
- `analysis/common/failures/20261003-jugemu-crepe-confidence.md`
- `analysis/common/failures/20261003-structure-tempo-quantization.md`
- `analysis/common/failures/20261003-mfa-seaborn-pip-check.md`

---

## 一行再開プロンプト

`GitHubの 2rwa/tmp-music の docs/NEXT_CHAT.md と docs/STATUS_20261003.md を読み、記載された最優先作業から続けて。`
