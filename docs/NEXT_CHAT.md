# NEXT CHAT — tmp-music handoff

更新日: 2026-10-03  
対象: `2rwa/tmp-music`

## 最初に読む

1. `2rwa/chatgpt-workspace/docs/build-test-fix.md`
2. `docs/STATUS_20261003.md`
3. `docs/M6_HANDOFF_20261003.md`
4. `docs/audio-analysis-implementation-plan.md`
5. 必要に応じて `docs/audio-analysis-research-survey.md` / `scripts/README.md`

GitHub操作は GitHub Connector を使用し、**gh CLIは使わない**。  
変更前に必ず current `main` HEAD と最新Actionsを確認する。

## 現在の方針

当面の唯一の目標は **Milestone 6 — Voice quality の完了**。

M7 Cultural comparison は保留。M6完了後に実測結果を見て次の目標を決める。

## 現在のmain

handoff作成前HEAD:

`5a8edfdb05d8dc5724a68994f2a2eaea9bfeb67c`

commit:

`Integrate calibrated Praat metrics into M6`

このhandoff更新commitでHEADは進むため、新会話では必ず再取得する。

## Milestone status

- M1 Analyzer foundation — COMPLETE
- M2 Vocal / pitch — COMPLETE
- M3 Structure / cycles — COMPLETE
- M4 Japanese lyrics — COMPLETE
- M5 Forced alignment — COMPLETE
- M6 Voice quality — IN PROGRESS
- M7 Cultural comparison — HOLD / NOT STARTED

## M6現在地

実装済み/着手済み:

- stable vocal targetを対象にしたvoice-quality analyzer
- RMS
- autocorrelation peak
- autocorrelation HNR estimate
- spectral tilt
- Praat calibrated CPPS known-answer smoke
- Praat Harmonicity(cc) known-answer smoke
- Praat CPPS/HNRの本体統合コード
- M6 Actions workflow

Praat smoke:

- run `37097054086` — success
- Praat 6.4.49
- periodic CPPS 27.25 dB / noise CPPS 2.60 dB

## 最初に直すfailure

### cheap CI

run `37097290629` — failure

Praat result regexのescape過剰でtabをmatchできない。

### M6 E2E

run `37098551676` — 両曲 failure

`NameError: name 'py' is not defined`

`scripts/cli.py` のvoice-quality command生成blockが `stage_output()` 側へ誤配置されている。

詳細は必ず `docs/M6_HANDOFF_20261003.md` を読む。

## M5について

M5はcomplete扱いを維持。

最新の一部failure `37097371836` は Whisper AO のMFA model download時の `ModelsConnectionError`。  
alignment実装の既知成功run:

- `37095819243`
- `37096648316`

## M6完了条件

- calibrated CPPS
- Praat HNR + autocorrelation HNR
- spectral tilt
- F1/F2/F3
- vibrato / glissando統合
- register transition候補
- Whisper AO / Jugemu 両方E2E success
- cheap CI success
- provenance / tool versions / artifact
- M1〜M5非回帰
- docs更新

## 一行再開プロンプト

`GitHubの 2rwa/tmp-music の docs/NEXT_CHAT.md、docs/STATUS_20261003.md、docs/M6_HANDOFF_20261003.md を読み、M6完了を最優先目標として記載された既知failureから修正・検証を続けて。`
