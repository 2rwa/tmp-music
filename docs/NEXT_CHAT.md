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

### M3 Structure / cycles — MOSTLY COMPLETE

実装・実測済み:

- MFCC / chroma / rhythm multi-view SSM
- recurrence period
- cycle grid
- local template alignment
- DTW
- cycle-distance

成功run:

- `37086468933`

Jugemu:

- selected period: 28.75 s
- aligned starts:
  - 12.00
  - 40.75
  - 69.50
  - 98.50
  - 127.25
  - 156.00
  - 184.75
  - 213.50 s

未解決:

- Jules追加tempo estimatorがstructure用0.25 s gridを使い、120 / 60 / 240 BPMへ量子化
- 実音源validation run `37086741133`, `37087024183` はこのtempo条件でfailure

structure/cycle本体は正常。tempoだけ修正する。

### M4 Japanese lyrics — IMPLEMENTED / E2E REVALIDATION PENDING

実装済み:

- Japanese normalization
- kana/mora tokenizer
- CER / MER
- cycle-level Whisper
- pairwise mora distance
- cycle-specific contiguous reference partition

旧reference方式:

- cycle-ASR run `37086549657` success

Jules改善後:

- canonical reference cycle lines = 10
- expected line counts = 10,10,10,10,10,9,9,9
- latest cheap CI `37087076630` success

未完了:

- 修正版referenceで実音源E2E再実行
- 上流tempo validation failureを直せば自動chain可能

### M5 Forced alignment — NOT STARTED

次段。

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

1. **tempo estimator のhopをstructure feature gridから分離**
2. high-resolution onset envelopeでtempoを再測定
3. primary / half / double ambiguityを保存
4. Jugemu soft regressionとして約99 / 197 BPM候補を確認
5. M3 structure workflow をsuccessへ戻す
6. 自動chainされたM4 cycle-ASRをcycle-specific referenceで完走
7. 各cycleのCER / MER / deletion / substitutionを確認
8. M3/M4の完了判定
9. Milestone 5 forced alignmentへ進む

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

tempo量子化問題も修正時にfailure recordを追加する。

---

## 一行再開プロンプト

`GitHubの 2rwa/tmp-music の docs/NEXT_CHAT.md と docs/STATUS_20261003.md を読み、記載された最優先作業から続けて。`
