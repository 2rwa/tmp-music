# tmp-music documentation index

このディレクトリの文書は、目的別に正本を分ける。

## まず読む

1. **`STATUS_20261003.md`**
   - 現在の実装状態
   - Actionsで実測済みの内容
   - Milestoneごとの完了度
   - 既知の未解決問題
   - 次の優先順位

2. **`NEXT_CHAT.md`**
   - 新しいChatGPT会話での再開手順
   - 最小限のrepo背景
   - 現在の最優先タスク
   - 一行再開プロンプト

3. **`audio-analysis-implementation-plan.md`**
   - Milestone 1〜7
   - 実装順序
   - Definition of Done
   - 今後の設計

## 技術根拠・背景

### `audio-analysis-research-survey.md`

論文・技術調査の正本。

主題:

- F0 / melody
- source separation
- ASR / lyrics alignment
- Japanese mora
- rap rhythm
- SSM / DTW
- voice quality
- embeddings
- computational ethnomusicology

### `audio-analysis.md`

Whisper AOから始まった解析方法論の履歴。

現在の進捗正本ではない。古い「future / optional」記述が残るため、現在状態は `STATUS_20261003.md` を参照する。

### `jugemu-analysis.md`

Jugemu固有の観測と実測。

2026-10-03以降は:

- mix vs vocal pitch
- 28.75 s recurrence
- aligned cycle starts
- tempo regression
- cycle-ASR reference partition

も記録している。

## 実行方法

`../scripts/README.md`

- common CLI
- synthetic fixtures
- Demucs
- pitch / tuning
- structure
- Japanese metrics
- cycle ASR

## failure記録

`../analysis/common/failures/`

失敗は削除せず、原因・修正・regression expectationを保存する。

現在の主な記録:

- `20261003-setup-python-cache-path.md`
- `20261003-jugemu-crepe-confidence.md`
- `20261003-structure-tempo-quantization.md`

## 文書更新ルール

- 現在の実測値が変わったら `STATUS_YYYYMMDD.md` または最新STATUSを更新
- Milestoneの状態が変わったら実装計画とNEXT_CHATを更新
- 曲固有の新しい観測は各曲のanalysis docへ追記
- 実行コマンドやartifact layoutが変わったら `scripts/README.md` を更新
- failureを直してもfailure recordは残す
- measurementとinterpretationを同じ事実として書かない
