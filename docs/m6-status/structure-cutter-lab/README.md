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
9. Repetition はDemucs後にstem shareを特徴へ追加して再計算
10. Mix Change Point + Repetition + Stem Activity を ±1.5 s で cluster し Consensus boundary を生成
11. 切断点は Exact / Nearest beat / Estimated bar / Recommended から選択
12. 区間選択 / loop / WAV export

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

## Pending

結果を偽装せず、未接続の解析は pending のまま表示する。

- Section AI
- Beat / Downbeat
- Vocal Phrase

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
