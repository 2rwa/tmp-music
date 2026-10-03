# NEXT CHAT — tmp-music handoff

更新日: 2026-10-03  
対象: `2rwa/tmp-music`

## 最初に読む

1. `2rwa/chatgpt-workspace/docs/build-test-fix.md`
2. `docs/STATUS_20261003.md`
3. `docs/M6_HANDOFF_20261003.md`
4. `docs/audio-analysis-implementation-plan.md`

GitHub操作は GitHub Connector を使用し、**gh CLIは使わない**。変更前に current `main` HEAD と最新Actionsを確認する。

## 現在の方針

**Milestone 6 — Voice quality は COMPLETE。**

M7 Cultural comparison は引き続き HOLD。次の目標はM6実測結果を見た上でユーザーと決める。自動的にM7へ進まない。

## Milestone status

- M1 Analyzer foundation — COMPLETE
- M2 Vocal / pitch — COMPLETE
- M3 Structure / cycles — COMPLETE
- M4 Japanese lyrics — COMPLETE
- M5 Forced alignment — COMPLETE
- M6 Voice quality — COMPLETE
- M7 Cultural comparison — HOLD / NOT STARTED

## M6完了validation

最終validation:

- PR: #4 `Complete M6 voice-quality measurements`
- cheap CI: run `37101306895` — success
- Praat known-answer smoke: run `37101306899` — success
- real-audio M6 E2E: run `37101306889` — Whisper AO / Jugemu とも success
- Praat: 6.4.49
- artifact:
  - `voice-quality-whisper-ao` — artifact `11266196721`
  - `voice-quality-jugemu` — artifact `11266885749`

実artifactを展開して `provenance.json` の `tool_versions.praat` まで確認済み。

## M6実測スナップショット

| Track | stable targets | duration | CPPS median | Praat HNR median | autocorr HNR median | tilt median | F1/F2/F3 median | vibrato extent median | pitch-movement candidates | register candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Whisper AO | 95 | 47.35 s | 10.28 dB | 23.64 dB | 15.82 dB | -2.99 dB/oct | 466 / 1766 / 2543 Hz | 40.65 cent | 88 | 16 |
| Jugemu | 20 | 5.32 s | 10.48 dB | 16.61 dB | 12.81 dB | -2.49 dB/oct | 735 / 1662 / 2694 Hz | 17.61 cent | 109 | 0 |

注意:

- pitch-movement は「glissando候補」であり、歌唱意図を断定しない。
- register transition は F0 discontinuity + CPPS/Praat HNR/autocorr HNR/tilt のうち最低2種類の独立変化を要求する候補検出。
- formant / intensity / vibrato はregister判定の補助情報であり、単独では候補成立に使わない。
- source separation と singing acoustics がformant推定へ影響し得る。

## 解消した既知failure

- cheap CI `37097290629`: Praat regex過剰escape → 修正、version regexも同時修正。
- M6 E2E `37098551676`: `voice-quality` command blockが `stage_output()` へ誤配置 → `stage_command()` へ移動。
- analyzerで `shutil/subprocess/tempfile` import不足 → 修正。
- pitch-movement結合後に低R²候補が残る → 最終eventでも閾値を再検証。
- register候補がformant変化だけで過検出し得る → F0 + 2 voice-quality変化を必須化。
- provenanceにPraat実versionが無い → `tool_versions.praat` を追加。

## M5について

M5はCOMPLETE扱いを維持。run `37097371836` のWhisper AO failureはMFA remote model downloadの `ModelsConnectionError`。既知成功runは `37095819243`, `37096648316`。

## 次の会話

M6実測結果をレビューし、次の優先目標を決める。M7は明示的に選ばれるまで着手しない。
