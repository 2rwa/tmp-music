# Structure Cutter Lab

新規UIの第1段階。既存 `stem-annotation-studio` を改造せず、曲全体の時間軸を主役にした構成切り出しUIを別アプリとして作る。

## この段階で実装済み

- `tmp-music` の実音源3曲を直接ロード
  - `samples/whisper-ao/source/whisper-ao.mp3`
  - `samples/jugemu/source/jugemu.mp3`
  - `samples/chichinu-fiija/source/chichinu-fiija.mp3`
- Web Audio decode
- 実音源からのoverview waveform
- 簡易 change-point 候補（RMS + zero-crossing-rate変化）
- 構成区間のクリック選択
- 波形ドラッグによる連続時間選択
- 選択区間loop
- 選択区間WAV export
- boundary inspector
- algorithm comparison UI
- `Consensus / Section AI / Repetition / Change Point / Stem Activity / Beat / Bars / Vocal Phrase` のUI契約

## 意図的に未実装

初版UIで解析結果を偽装しないため、下記は `pending` と明示している。

- HTDemucs 4-stem
- All-In-One相当のsection解析
- repetition / recurrence解析
- beat / downbeat
- vocal phrase
- 複数アルゴリズムのconsensus

次段階で `Mix + vocals + drums + bass + other` の共通時間軸データモデルへ接続する。

## UI原則

1. Treeを常設しない。
2. 画面横幅は時間軸へ使う。
3. main viewは transport / structure mode / unified timeline / selection の4層。
4. 詳細は compare panel / boundary inspector に逃がす。
5. raw boundary と final cut point は将来も別フィールドとして扱う。
6. GPU-only最終版を前提にしつつ、このUI段階ではWebGPU未対応環境でも表示・self-test可能にする。
