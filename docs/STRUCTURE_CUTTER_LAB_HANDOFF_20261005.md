# Structure Cutter Lab HANDOFF — implementation experiment complete

更新日: 2026-10-05  
対象: `2rwa/tmp-music`  
アプリ: `docs/m6-status/structure-cutter-lab/`

## 結論

**Structure Cutter Lab の実装実験はここで一区切りとする。**

この実験で、ブラウザ上でも以下を組み合わせれば、楽曲構成の推定・stem分離・区間試聴・編集点候補・選択sourceのWAV出力まで実用可能なことを確認できた。

- Mix change-point
- repetition / recurrence
- beat / bar grid
- HTDemucs 4-stem
- stem activity
- vocal phrase edge
- All-In-One Section AI
- low-energy cut alignment
- multi-engine consensus

今後の主課題は解析手法ではなく **編集UI / 編集データモデル**。  
複数Section選択、複数cut、edit list、複数exportを現UIへ継ぎ足すと状態管理が複雑になるため、次段階は新しいUI / 新しいアプリとして設計する。

**現在の Structure Cutter Lab は実験baselineとして保存し、大きなUI再設計で上書きしない。**

## Public

- https://2rwa.github.io/tmp-music/m6-status/structure-cutter-lab/

current implementation snapshot:

- commit: `af6a85f964cf1baa7ac587ab0f409b84058ea8b2`
- Structure Cutter Lab CI: `37248524200` — success
- Analysis cheap CI: `37248524087` — success
- Pages deploy: `37248524276` — success
- Pages smoke: `37248579355` — success

## 現在の処理フロー

1. repository sample / local audio decode
2. Mix waveform
3. Mix Change Point
4. Repetition recurrence
5. Beat / Bars
6. HTDemucs `htdemucs` WebGPU 4-stem
7. Stem Activity
8. Vocal Phrase
9. 81-bin Section AI features
10. All-In-One Harmonix fold0 ONNX
11. Section / function labels
12. Change Point + Repetition + Stem Activity + Section AI consensus
13. Exact / beat / bar / vocal edge / low-energy cut alignment
14. source-selective playback
15. selection loop
16. source-selective WAV export

## Live engines

### Change Point

Mix RMS / ZCRの変化から候補境界を生成。

### Repetition

M3の recurrence / lag-profile の考え方を軽量化。  
非局所の繰り返し区間を検出し、反復開始/終了をboundary evidenceへ変換。

synthetic A-B-A-Cでは約16秒の再帰lagを回収する回帰テストあり。

### Beat / Bars

onset envelope自己相関でtempoを推定し、beat phaseと4拍単位のbar-gridを生成。

semantic structureではなく編集点snap用。

### HTDemucs

- model: `htdemucs`
- backend: WebGPU
- precision: fp16
- whole-track
- stereo / 44.1 kHz
- GPUなしでは長時間CPU fallbackを自動実行しない

stems:

- vocals
- drums
- bass
- other

### Stem Activity

4 stemのenergy share変化をboundary evidence化。

### Vocal Phrase

vocals stemへadaptive RMS threshold + hysteresisを適用し、歌唱区間のstart/endを編集edgeとして生成。

### Section AI

Pinned upstream:

`openmirlab/all-in-one-infer@797f1d21b115955ed81ff9161440334fefea8855`

production model:

`docs/m6-status/structure-cutter-lab/models/harmonix-fold0-section-function-long.onnx`

- size: 6,376,948 bytes
- input: `[1,4,T,81]`
- 102.4 s未満はzero-pad
- production range: 102.4–660 s
- browser preprocessing parity確認済み
- ONNX Runtime Web / WASM実行確認済み
- WebGPU EPを優先し、失敗時WASM fallback
- labels: intro / outro / break / bridge / inst / solo / verse / chorus 等

Demucs separatorをunloadしてからSection AIをloadし、2つの大きなGPU modelを同時常駐させない。

## Playback

旧実装ではMixとStem auditionが別playerで、Loop時に二重再生や古いStem再生が残る問題があった。

現在は単一playback controllerへ統合済み。

### Source model

- `MIX` はoriginal audio単独
- Stem側は `VOCALS / DRUMS / BASS / OTHER` のうち **1〜3個**
- 3 stem選択時は4個目を追加不可
- 最後の1 stemを外すとMIXへ戻る
- 再生中のsource変更は同じtimecodeから切替
- Play / Stop / Seek / Volume / Loop / Section変更は現在source setだけを制御

Stem lane labelも上部source UIと同じtoggleとして扱う。

## WAV export

WAV exportは現在のPlayback Sourceに従う。

### MIX

original audioのselectionをWAV化。

### Stems

選択中1〜3 stemをsample-by-sampleで加算し、stereo 16-bit PCM WAVへ出力。

- averageしない
- Demucs再合成と同じくsum
- ±1超過sampleはPCM量子化時にclip
- filenameに `vocals-drums` 等のsource名を含める

browser self-testでsample加算とWAV byte sizeを確認済み。

## Cut alignment

現在選択可能:

- Recommended
- Exact structure boundary
- Estimated bar
- Nearest beat
- Vocal phrase edge
- Low energy

Recommendedは大きく位置を飛ばさないことを優先し、beat/barが近ければsnap、そうでなければlow-energy fallbackを使う。

## Testing

### Structure Cutter Lab CI

- static UI / behavior contract
- JavaScript syntax
- Vite bundle build
- synthetic recurrence
- beat / bar known-answer
- vocal phrase known-answer
- low-energy known-answer
- Section AI postprocess
- Section AI runtime padding
- browser self-test

### Browser self-test

fake 4-stem + deterministic Section AI logitsを使い、

- stem activity
- repetition
- beat grid
- vocal phrases
- Section AI labels
- 4-source consensus
- selection
- loop state
- playback source switching
- 1 / 2 / 3 stem selection
- 4個目拒否
- multi-stem WAV merge

を回帰確認。

### Separate Section AI validation

実ONNX実行、dynamic model、browser preprocessing parityは専用workflowで検証。

## 実装実験で分かったこと

### 1. ブラウザ完結でもかなり実用になる

GPU-equipped machineならHTDemucsを含めて現実的。  
特にM4クラスではブラウザHTDemucsが実用範囲に入ることを確認できた。

### 2. semantic sectionだけではcut位置は決められない

VERSE / CHORUS boundaryと実編集点は分離すべき。

必要な層:

- semantic boundary
- beat / bar alignment
- vocal phrase edge
- local low-energy point
- actual cut point

この分離は今後の編集UIでも維持する。

### 3. 複数解析のevidenceを分離表示する価値がある

Consensusだけでなく、Change Point / Repetition / Stem Activity / Section AIを個別表示できることで推定理由を確認しやすい。

### 4. 再生sourceとselectionは明示的なstate modelが必要

MixとStemを別playerにすると状態が破綻しやすい。  
現在は1つのplayback controllerへ統合した。

次の編集UIでも、

- playback source set
- selection set
- cut list
- export target

を別stateとして設計すること。

## 現UIの限界

現在のUIは **1つの連続selectionを選び、試聴し、1つのWAVを取り出す** ところまでは扱いやすい。

以下を追加し始めると現構造では難しくなる。

- 複数Section同時選択
- 非連続selection
- 複数cut point
- keep / remove指定
- cut順序変更
- 複数clipのmerge
- clipごとのsource set
- clipごとのcut alignment
- batch export
- edit history / undo
- project保存 / reload

これらは単純なボタン追加ではなく、編集データモデルが必要。

## 次段階で必要な新UI

次に開発する場合は Structure Cutter Lab を直接拡張せず、**新しい別アプリ**として始める。

最低限のデータモデル例:

```text
Track
 ├─ Analysis layers
 │   ├─ Section AI
 │   ├─ Consensus
 │   ├─ Repetition
 │   ├─ Beat / Bars
 │   └─ Vocal Phrase
 │
 ├─ Playback source set
 │   └─ mix OR 1..3 stems
 │
 └─ Edit list
     ├─ Clip A: 12.4–28.1 s / vocals+drums / keep
     ├─ Clip B: 42.0–55.7 s / mix / remove
     └─ Clip C: 70.2–91.8 s / vocals+bass / keep
```

UI候補:

- timeline中央
- analysis layer表示切替
- multi-range selection
- clip list / edit decision list
- cut handles
- source-set per clip
- preview assembled result
- export selected clips / assembled timeline

**解析ブラウザではなく、non-destructive audio structure editorとして設計し直す。**

## 次に再開する場合

Structure Cutter Labの実装実験は完了扱い。

ユーザーが編集機能を再開すると明示した場合:

1. このHANDOFFを読む
2. current Structure Cutter Labをbaselineとして保持
3. 新規アプリ名 / 新規directoryを作る
4. 先にedit data modelを定義
5. multi-section / multi-cut UIを作る
6. 必要な解析coreだけ既存Labから再利用

現在Labへ場当たり的にボタンを追加して拡張しない。

## One-line continuation prompt

`GitHubの 2rwa/tmp-music の docs/STRUCTURE_CUTTER_LAB_HANDOFF_20261005.md を読み、Structure Cutter Labは実装実験baselineとして保持したまま、複数Section選択・複数cut・edit listを扱う新しい編集UIの設計から続けて。`
