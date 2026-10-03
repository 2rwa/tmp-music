# tmp-music documentation index

文書の役割を分け、同じ進捗値を複数箇所で正本化しない。

## 現在の正本

1. **`M1_M6_FINAL_20261004.md`**
   - M1〜M6の完了履歴
   - milestoneごとの主なvalidation
   - M6 confidence-guard後の最終segment値
   - Level 1 / Level 2 timeline
   - superseded failureと研究上の注意

2. **`STATUS_20261003.md`**
   - 現在の短い状態
   - 最新run / Pages
   - M7 HOLD

3. **`NEXT_CHAT.md`**
   - 次会話の最小handoff
   - 再開時の注意

4. **`M6_HANDOFF_20261003.md`**
   - M6実装・candidate semantics・Level 1/2詳細

5. **`audio-analysis-implementation-plan.md`**
   - 設計とMilestone 1〜7
   - M1〜M6は完了済み
   - M7はHOLD

## 技術根拠

### `audio-analysis-research-survey.md`

論文・技術調査の正本。F0、source separation、ASR、mora、rhythm、SSM/DTW、voice quality、embeddings、computational ethnomusicologyを扱う。

### `audio-analysis.md`

初期解析方法論の履歴。現在進捗の正本ではない。

### `jugemu-analysis.md`

Jugemu固有の観測・実測。

## 実行方法

`../scripts/README.md`

## failure記録

`../analysis/common/failures/`

failureは修正後も消さず、症状・root cause・fix・regression expectationを残す。

## Pages

- M6 summary: `https://2rwa.github.io/tmp-music/m6-status/`
- Level 1 timeline: `https://2rwa.github.io/tmp-music/m6-status/timeline/`
- Level 2 timeline: `https://2rwa.github.io/tmp-music/m6-status/timeline-v2/`

## 更新ルール

- M1〜M6の歴史的完了記録は `M1_M6_FINAL_20261004.md` を基準にする。
- 現在状態だけ変わる場合はSTATUS/NEXT_CHATを更新する。
- milestone状態が変わる場合はimplementation planも更新する。
- 新しい実測値はscope（segment / continuous / mix / vocals）を明記する。
- measurementとinterpretationを同じ事実として書かない。
- M7は明示的な開始指示があるまでHOLDを維持する。
