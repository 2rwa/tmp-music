# Structure Cutter Lab

> **2026-10-05: implementation experiment complete.**  
> ブラウザ上で構造解析・HTDemucs・Section AI・区間試聴・cut alignment・選択sourceのWAV出力まで十分実用になり得ることを確認した。今後の複数Section選択・複数cut・edit listは、このUIへ継ぎ足さず新規editor UIとして設計する。詳細は `docs/STRUCTURE_CUTTER_LAB_HANDOFF_20261005.md`。

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
11. 4 stemsを上流互換の81-bin log-filterbankへ変換し、All-In-One Harmonix fold0 ONNXでSection AIを実行
12. Section AIから INTRO / VERSE / CHORUS / BRIDGE / OUTRO 等の機能ラベルと境界を生成
13. Mix Change Point + Repetition + Stem Activity + Section AI を ±1.5 s で cluster し Consensus boundary を生成
14. 切断点は Exact / Nearest beat / Estimated bar / Vocal phrase edge / Low energy / Recommended から選択
15. 区間選択 / loop / WAV export

## 実音源

- `samples/whisper-ao/source/whisper-ao.mp3`
- `samples/jugemu/source/jugemu.mp3`
- `samples/chichinu-fiija/source/chichinu-fiija.mp3`

## UIでliveになった解析

- Consensus — Mix Change Point + Repetition + Stem Activity + Section AI（Section AI成功時）
- Change Point — mix RMS/ZCR
- Repetition — M3-style recurrence / lag similarity / repeated-pair alignment
- Beat / Bars — onset自己相関によるtempo/phase推定、4拍子bar-grid。意味的構成ではなく編集用snap layer
- Stem Activity — HTDemucs 4-stem energy share change
- Vocal Phrase — vocals stemのadaptive energy hysteresisによる歌唱区間start/end。semantic sectionではなく編集用edge
- Section AI — All-In-One Harmonix fold0。HTDemucs 4 stems → 81-bin特徴 → ONNX Runtime Web。WebGPUを優先し失敗時はWASMへfallback

## Pending

現時点で構造ビューに表示している主要engineは接続済み。今後はSection AI実音源評価・複数fold/ensemble・長尺時の前処理高速化を検討する。

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

Browser self-testでは実モデルdownloadを行わず、fake stem と deterministic Section AI logits を使い、Stem Activity / Section AI label UI / 4-source Consensus / lane描画まで回帰確認する。実ONNX実行はSection AI ONNX probe、81-bin前処理の数値一致はSection AI feature parity CIで別々に担保する。

## Repetition regression

`tests/repetition-core-test.mjs` は A–B–A–C synthetic signal から約16秒の反復ラグ、反復ペア、反復境界を回収する既知解テスト。ブラウザself-testではこのRepetitionをsynthetic 4-stemと統合し、3-source Consensusまで確認する。

## Beat / cut alignment regression

`tests/beat-core-test.mjs` は120 BPM・4拍ごと強拍のsynthetic click trackからtempo / beat grid / bar gridを回収し、3.08秒がRecommendedで3.00秒の近傍beatへsnapすることを検証する。barが遠い場合に約1秒飛ばさないことも回帰条件。

## Vocal phrase regression

`tests/vocal-core-test.mjs` は3つのsynthetic歌唱区間を約±0.2秒以内で回収する。browser self-testではfake HTDemucs vocalsに明示的な無音gapを作り、Vocal Phrase boundary生成と`Vocal phrase edge` alignmentの両方を確認する。

## Low-energy cut regression

`tests/cut-core-test.mjs` は±0.35秒の範囲で局所RMS最小点を探索し、synthetic troughへ約27–30 dB低い切断点を回収する。Recommendedはbeat/bar snapが成立しないedgeだけLow energyをfallbackとして使い、大きな位置移動を避ける。

## Section AI

Pinned upstream `openmirlab/all-in-one-infer@797f1d21b115955ed81ff9161440334fefea8855` の `harmonix-fold0` を Section / Function logits に限定してONNX化。

- production model: `models/harmonix-fold0-section-function-long.onnx`
- size: 6,376,948 bytes
- input: `[1, 4, T, 81]`
- supported production range: 102.4–660 s。短い入力は102.4秒相当へzero-pad
- labels: start / end / intro / outro / break / bridge / inst / solo / verse / chorus
- ORT CPUとPyTorchの検証差: おおむね1e-6〜1e-5
- browser ORT Web/WASM実行確認済み
- WebGPU execution providerを優先し、失敗時はWASMへfallback
- 4 stemsの前処理はproduction `section-ai-features.js` とPython reference間でparity CIを実施
- checkpoint license metadata: CC-BY-NC-SA-4.0。NOTICEとmodel metadataを同梱

Section AIはHTDemucs完了後に実行し、separatorを先にunloadしてGPUモデル2本の同時常駐を避ける。

## Playback

Mix と HTDemucs stems は単一の playback controller で扱う。

- playback source は `MIX` または HTDemucs stems の組み合わせ
- Stem側は `VOCALS / DRUMS / BASS / OTHER` から **1〜3個**を同時選択可能
- `MIX` はoriginal audioの単独source。MIX選択時はStem選択を解除
- 3 Stem選択中は未選択の4個目をdisabledにし、どれか1個外すまで追加不可
- 最後の1 Stemを外すとMIXへ戻る
- 再生中に組み合わせを変えると同じタイムコードから新しい組み合わせへ切り替える
- Play / Stop / Seek / Volume / Loop は現在のsource setだけを制御する
- Section loop中に別Sectionを選ぶと旧nodeを停止し、新しい区間で同一source setを再起動する
- Clearはselection/loopを解除し、再生中なら同一source setの通常再生へ戻す
- Stemレーン名のクリックも上部PLAYBACK SOURCESと同じtoggleとして扱う

### WAV export

`Extract … WAV` は現在のPlayback Sourceに従う。

- MIX: original audioから選択区間をWAV化
- Stem: 選択した1〜3 Stemをsample-by-sampleで加算してstereo WAV化
- Stem mergeは平均化しない。Demucsの再合成と同様にsumする
- 16-bit PCM量子化時に±1を超えたサンプルだけclipする
- filenameに `vocals-drums` など選択sourceを入れる

