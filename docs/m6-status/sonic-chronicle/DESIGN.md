# Sonic Chronicle — design / implementation note

## Goal

`timeline-browser` の「縦型解析年表」を独立したアプリへ発展させる。主役はグラフではなく、再生位置と同期した **時間順の読み物**。

## UX principles

1. **Transport is persistent.** 再生・シーク・現在位置復帰は長いページを読んでいても失わない。
2. **No page-wide horizontal scrolling.** 指標は列ではなくカード内グリッドで折り返す。
3. **FOLLOW / BROWSE are distinct.** 自動追従中に手動スクロールしたらBROWSEへ移り、再生は継続。明示操作でFOLLOWへ戻る。
4. **Observation and interpretation are separate.** 「測定値」「読み方」「注意」「Evidence」を混同しない。
5. **Relative change matters.** 絶対値だけでなく、直前区間から何が変化したかを文章化する。
6. **Raw data remains available.** 読む → 詳細 → 20ms の semantic zoom を用意する。
7. **Candidates stay candidates.** pitch movement / register-like transition / local modulation を意図や奏法の断定に使わない。

## Names / labels

- App: **Sonic Chronicle**
- Japanese tagline: **音を、時間順に読む。**
- Vertical timeline: **解析クロニクル**
- F0/confidence: **音高・周期の確かさ**
- HNR/CPPS-like: **周期性・調波性**
- RMS/tilt: **音量・スペクトル傾向**
- local modulation: **音高の揺れ**
- pitch movement: **音高移動候補**
- register candidate: **音域・音色の急変候補** (`register-like transition candidate` in technical detail)

## Layout

- Header / loader collapses after analysis.
- Sticky transport on desktop; bottom-fixed transport on mobile.
- Chronicle cards use natural content height.
- Right minimap uses true audio-time coordinates, independent from card height.
- Cards contain responsive metric grid (3→2→1 columns).
- Only raw 20ms table may scroll horizontally.

## Follow state machine

- `FOLLOW`: current interval is kept near viewport center.
- user wheel/touch/scroll → `BROWSE`.
- playback keeps running in BROWSE.
- `現在位置へ戻る` → scroll to NOW + `FOLLOW`.

Auto scrolling must never use page-level `scrollIntoView()` in a way that hides the transport. Chronicle has its own targeted scroll logic.

## Chronicle entry model

```text
ChronicleEntry
  id
  start / end
  state
  frameStart / frameEnd
  title
  observation
  interpretation
  caution
  deltaFromPrevious
  measurements
  events[]
  evidence[]
```

## Density modes

- `読む`: summary + delta + events.
- `詳細`: metric cards + sparkline + Evidence.
- `20ms`: raw frame table additionally visible.

## Regression requirements

- synthetic analysis reaches PASS and creates chronicle entries.
- NOW entry follows `audio.currentTime`.
- manual chronicle scroll switches FOLLOW→BROWSE without pausing audio.
- `現在位置へ戻る` switches BROWSE→FOLLOW.
- seek input changes `audio.currentTime`.
- density buttons update rendered state.
- filter toggles hide/show metric groups without changing page width model.
- all major controls remain addressable after analysis.
- CSS contains no chronicle-wide `min-width` that forces page horizontal scroll.
- mobile layout retains transport controls.

## Iteration scope

First implementation prioritizes transport, follow/browse, responsive cards, delta text, Evidence, sparklines, minimap, loop, A/B comparison and 20ms detail. Further feature work can add note-name display, bookmarks/search and virtualization after real-track use.


## Visual direction — Warm Scientific Editorial

The default visual language is a **warm scientific field note / annotated score**, not a cool-blue monitoring dashboard.

- background: warm paper `#f2eee5`
- writing surface: ivory `#faf7f0`
- main ink: `#28241e`
- accent / NOW: rust red `#a64b32` / `#bd4f31`
- periodic state: muted green `#587766`
- transient / event: amber-brown `#b87635`
- mixed: muted plum `#756979`
- transport: warm charcoal `#24211c`

Typography is semantic:

- title / section interpretation: Japanese serif (Mincho)
- controls / prose: Japanese sans-serif
- timestamps / measurements / mode labels: monospace

The chronicle should feel like an annotated score or research notebook. Large boxed cards are avoided where hierarchy can be expressed with whitespace, rules and indentation. Metric identity is primarily carried by labels and placement; color is reserved for state, current position and events.

### Visual regression contract

- no return to the original cool-blue base palette;
- paper background + rust accent stay present;
- serif headings remain distinct from controls and measurements;
- current position is the strongest accent;
- metric cards wrap 3→2→1 columns without horizontal page scrolling;
- transport remains visually distinct as warm recording-equipment furniture.
