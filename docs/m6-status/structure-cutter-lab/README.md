# Structure Cutter Lab

Timeline-first の楽曲構成・切り出し実験アプリ。既存 `stem-annotation-studio` とは別実装。

## 現在の処理フロー

1. repository sample / local audio を decode
2. Mix waveform を生成
3. Mix の RMS + zero-crossing-rate 変化から Change Point 候補を生成
4. M3と同じ recurrence / lag-profile の考え方を軽量化し、非局所の反復ペアから Repetition boundary を生成
5. onset envelope自己相関からtempo/beat phaseを推定し、4拍単位のbar-grid候補を生成
6. WebGPU が利用可能なら曲全体を HTDemucs `htdemucs` 4-stem へ分離
7. `vocals / drums / bass / other` の実データを共通時間軸へ描画
8. 550 ms 窓の stem energy share 変化から Stem Activity boundary を生成
9. vocals stemへadaptive RMS threshold + hysteresisを掛けてVocal Phrase開始/終了を生成
10. Repetition はDemucs後にstem shareを特徴へ追加して再計算
11. Mix Change Point + Repetition + Stem Activity を ±1.5 s で cluster し Consensus boundary を生成
12. 切断点は Exact / Nearest beat / Estimated bar / Vocal phrase edge / Low energy / Recommended から選択
13. 区間選択 / loop / WAV export

## 実音源

- `samples/whisper-ao/source/whisper-ao.mp3`
- `samples/jugemu/source/jugemu.mp3`
- `samples/chichinu-fiija/source/chichinu-fiija.mp3`

## UIでliveになった解析

- Consensus — Mix Change Point + Repetition + Stem Activity
- Change Point — mix RMS/ZCR
- Repetition — M3-style recurrence / lag similarity / repeated-pair alignment
- Beat / Bars — onset自己相関によるtempo/phase推定、4拍子bar-grid。意味的構成ではなく編集用snap layer
- Stem Activity — HTDemucs 4-stem energy share change
- Vocal Phrase — vocals stemのadaptive energy hysteresisによる歌唱区間start/end。semantic sectionではなく編集用edge

## Pending

結果を偽装せず、未接続の解析は pending のまま表示する。

- Section AI — All-In-One Harmonix fold0 の ONNX export / ONNX Runtime 数値一致 probe は成功済み。次はブラウザ側81-bin log-filterbank前処理と ONNX Runtime Web 接続。

## Demucs

- model: `htdemucs`
- backend: `webgpu`
- weights: `fp16`
- source audio は `OfflineAudioContext` で stereo / 44.1 kHz に変換して曲全体を渡す
- model cache を利用
- 処理中のみ Cancel を表示
- GPUなし環境では Mix Change Point までを利用可能とし、DemucsをCPU fallbackで長時間実行しない

## テスト

- static UI/behavior contract
- JavaScript syntax
- Vite bundle build
- synthetic 4-stem を使う browser self-test
- Pages live smoke

Browser self-testでは実モデルdownloadを行わず、fake stem を `installStemResult` へ入れて、Stem Activity / Consensus / lane描画まで回帰確認する。

## Repetition regression

`tests/repetition-core-test.mjs` は A–B–A–C synthetic signal から約16秒の反復ラグ、反復ペア、反復境界を回収する既知解テスト。ブラウザself-testではこのRepetitionをsynthetic 4-stemと統合し、3-source Consensusまで確認する。

## Beat / cut alignment regression

`tests/beat-core-test.mjs` は120 BPM・4拍ごと強拍のsynthetic click trackからtempo / beat grid / bar gridを回収し、3.08秒がRecommendedで3.00秒の近傍beatへsnapすることを検証する。barが遠い場合に約1秒飛ばさないことも回帰条件。

## Vocal phrase regression

`tests/vocal-core-test.mjs` は3つのsynthetic歌唱区間を約±0.2秒以内で回収する。browser self-testではfake HTDemucs vocalsに明示的な無音gapを作り、Vocal Phrase boundary生成と`Vocal phrase edge` alignmentの両方を確認する。

## Low-energy cut regression

`tests/cut-core-test.mjs` は±0.35秒の範囲で局所RMS最小点を探索し、synthetic troughへ約27–30 dB低い切断点を回収する。Recommendedはbeat/bar snapが成立しないedgeだけLow energyをfallbackとして使い、大きな位置移動を避ける。

## Section AI ONNX probe

Pinned upstream `openmirlab/all-in-one-infer@797f1d21b115955ed81ff9161440334fefea8855` の `harmonix-fold0` を Section/Function logits に限定して ONNX export。Actions probe で `export_ok=true` / `ort_ok=true`、legacy exporter、ONNX 3,199,894 bytes、input `[1, 4, 600, 81]` を確認。モデル接続前にブラウザ側の81-bin log-filterbank再現と実音源一致検証を行う。
