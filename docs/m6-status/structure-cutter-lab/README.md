# Structure Cutter Lab

Timeline-first の楽曲構成・切り出し実験アプリ。既存 `stem-annotation-studio` とは別実装。

## 現在の処理フロー

1. repository sample / local audio を decode
2. Mix waveform を生成
3. Mix の RMS + zero-crossing-rate 変化から Change Point 候補を生成
4. M3と同じ recurrence / lag-profile の考え方を軽量化し、非局所の反復ペアから Repetition boundary を生成
5. WebGPU が利用可能なら曲全体を HTDemucs `htdemucs` 4-stem へ分離
6. `vocals / drums / bass / other` の実データを共通時間軸へ描画
7. 550 ms 窓の stem energy share 変化から Stem Activity boundary を生成
8. Repetition はDemucs後にstem shareを特徴へ追加して再計算
9. Mix Change Point + Repetition + Stem Activity を ±1.5 s で cluster し Consensus boundary を生成
10. 区間選択 / loop / WAV export

## 実音源

- `samples/whisper-ao/source/whisper-ao.mp3`
- `samples/jugemu/source/jugemu.mp3`
- `samples/chichinu-fiija/source/chichinu-fiija.mp3`

## UIでliveになった解析

- Consensus — Mix Change Point + Repetition + Stem Activity
- Change Point — mix RMS/ZCR
- Repetition — M3-style recurrence / lag similarity / repeated-pair alignment
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
