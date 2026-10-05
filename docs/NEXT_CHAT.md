# NEXT CHAT — tmp-music handoff

更新日: 2026-10-05  
対象: `2rwa/tmp-music`

## 最初に読む

1. `2rwa/chatgpt-workspace/docs/build-test-fix.md`
2. `docs/STATUS_20261005.md`
3. `docs/M1_M6_FINAL_20261004.md`
4. Structure / editing関連なら `docs/STRUCTURE_CUTTER_LAB_HANDOFF_20261005.md`
5. M6詳細が必要なら `docs/M6_HANDOFF_20261003.md`

GitHub操作は GitHub Connector を使い、**gh CLIは使わない**。変更前に current `main` HEAD と最新Actionsを確認する。

## 現在地

- M1 Analyzer foundation — COMPLETE
- M2 Vocal / pitch — COMPLETE
- M3 Structure / cycles — COMPLETE
- M4 Japanese lyrics — COMPLETE
- M5 Forced alignment — COMPLETE
- M6 Voice quality — COMPLETE
- M7 Cultural comparison — HOLD / NOT STARTED
- Structure Cutter Lab — IMPLEMENTATION EXPERIMENT COMPLETE

**M7を自動開始しない。**

## Structure Cutter Lab

current baseline:

- `docs/m6-status/structure-cutter-lab/`
- public: https://2rwa.github.io/tmp-music/m6-status/structure-cutter-lab/
- baseline commit: `af6a85f964cf1baa7ac587ab0f409b84058ea8b2`

実装実験で確認済み:

- Change Point / Repetition / Beat-Bars
- HTDemucs 4-stem
- Stem Activity / Vocal Phrase
- Section AI
- 4-source Consensus
- cut alignment
- MIXまたは1〜3 stemの再生
- source-selective WAV export

### 重要

現在Labは **1つの連続selectionを扱う解析・試聴実験UI** として十分成立した。

次に欲しい:

- multiple section selection
- multiple cut points
- keep/remove
- clip list
- reorder
- assembled preview
- batch export

は、現在UIへ継ぎ足さない。

**Structure Cutter Labをbaselineとして保持し、新規directory / 新規appとしてnon-destructive editor UIを設計する。**

先にedit data modelを決めてからUIを作る。

## M6 latest

M6の正本:

- `docs/M1_M6_FINAL_20261004.md`
- `docs/M6_HANDOFF_20261003.md`

過去の赤runがActions履歴にあっても現行failureとは限らない。known superseded failuresは上記docs参照。

## Write-back

workflowからのartifact書き戻しは `scripts/common/github_writeback.py` を使用。raw `git push` をworkflowへ追加しない。

## 再開時

ユーザーが明示した次目標から着手する。

Structure editingを再開する場合の一行:

`GitHubの 2rwa/tmp-music の docs/STRUCTURE_CUTTER_LAB_HANDOFF_20261005.md を読み、Structure Cutter Labは実装実験baselineとして保持したまま、複数Section選択・複数cut・edit listを扱う新しい編集UIの設計から続けて。`
