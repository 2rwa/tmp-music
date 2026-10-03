# NEXT CHAT — tmp-music handoff

更新日: 2026-10-04  
対象: `2rwa/tmp-music`

## 最初に読む

1. `2rwa/chatgpt-workspace/docs/build-test-fix.md`
2. `docs/STATUS_20261003.md`
3. `docs/M1_M6_FINAL_20261004.md`
4. 必要なら `docs/M6_HANDOFF_20261003.md`

GitHub操作は GitHub Connector を使い、**gh CLIは使わない**。変更前に current `main` HEAD と最新Actionsを確認する。

## 現在地

- M1 Analyzer foundation — COMPLETE
- M2 Vocal / pitch — COMPLETE
- M3 Structure / cycles — COMPLETE
- M4 Japanese lyrics — COMPLETE
- M5 Forced alignment — COMPLETE
- M6 Voice quality — COMPLETE
- M7 Cultural comparison — HOLD / NOT STARTED

**M7を自動開始しない。**

## M6 latest

segment-level confidence-guard snapshot:

- Whisper AO: stable 97 / 47.80 s / movement 82 / register 16
- Jugemu: stable 18 / 5.18 s / movement 45 / register 0
- Chichinu Fiija: stable 43 / 13.47 s / movement 41 / register 1

segment artifacts:

- `11268226119`
- `11268640196`
- `11267579268`

Level 2 continuous time series:

- successful run `37116225090`
- snapshot commit `fc96a9e1545d0b8c363789ec26c7dc9127227b61`
- Pages deploy `37116722140` — success + live validation
- Level 2 artifacts:
  - Whisper AO `11272086196`
  - Jugemu `11271726804`
  - Chichinu Fiija `11271721474`

Pages:

- `https://2rwa.github.io/tmp-music/m6-status/`
- `https://2rwa.github.io/tmp-music/m6-status/timeline/`
- `https://2rwa.github.io/tmp-music/m6-status/timeline-v2/`

## Interpretive guardrails

- pitch movement / register / local modulation はcandidateまたはdescriptor。
- intentional glissando / vibrato / register changeを自動断定しない。
- CPPS / HNR / formantを声の優劣や文化分類へ直接変換しない。
- Praat HNRとautocorrelation HNRを混同しない。
- Level 1 segment値とLevel 2 continuous値はscopeが違う。

## Known non-current failures

- `37116031516`: Level 2初回解析jobは成功、publishのnon-fast-forwardのみ失敗。後続 `37116225090` が最終success。
- `37097371836`: MFA model download failure。M5実装回帰ではない。

## 再開時

ユーザーの明示した次目標から着手する。M6の再実装やM7開始を勝手に行わない。
