# 音楽・歌唱音声解析技術サーベイ — tmp-music 向け

調査日: 2026-10-03  
対象: tmp-music の生成音楽実験、とくに Whisper AO と じゅげむ  
目的: 「変な曲」「特異な歌唱」「ラップのフロウ」「12音平均律からの逸脱」「民俗歌唱らしさ」を、聴感だけでなく再現可能な測定として扱うための技術選定

---

## 0. 結論

tmp-music で今後優先すべきなのは、単純に FFT や ASR を増やすことではない。

解析を次の層に分けるのが重要である。

1. **原音の整合性・メタデータ**  
   SHA-256、実音長、無音、ID3、埋め込み歌詞を固定する。

2. **混合音の音楽構造**  
   STFT/CQT、onset、beat、tempogram、self-similarity matrix で曲全体を測る。

3. **声の分離**  
   Demucs 系と Mel-RoFormer 系など複数方式で vocal stem を作り、分離誤差も測る。

4. **歌唱音高**  
   pYIN と CREPE 等を併用し、連続 F0 と安定音高を分離する。  
   「nearest 12-TET から何 cent」という一値だけで微分音を判定しない。

5. **歌詞と発音**  
   free ASR と、既知歌詞を使う forced/reference-aware alignment を分離する。  
   日本語では WER より CER・モーラ単位を重視する。

6. **声質・歌唱法**  
   CPPS、HNR、spectral tilt、formant、register break、glissando、vibrato を、安定した有声音区間で測る。

7. **反復とラップ**  
   beat-synchronous features、DTW、反復サイクル分割により「同じ歌詞を何周目でどう崩したか」を比較する。

8. **文化的類似性**  
   「FFT が似ているから○○民謡」と断定しない。  
   実在録音コーパス、人間の評価、解釈可能な特徴量、MERT/CLAP 等の埋め込みを併用し、「特徴 X/Y が似る」という表現に止める。

現在の Whisper AO と じゅげむは、この方法論を試すのに非常に適した対照例である。

- Whisper AO: 正常な英語歌詞が、歌唱によって ASR 上は別言語のように崩れる。
- じゅげむ: 同じ既知日本語列が約 29 秒周期で反復され、周回ごとの発音・フロウ変化を比較できる。

---

## 1. 問題を「何を推定したいか」に分解する

音楽解析は一つのアルゴリズムで済ませると誤解しやすい。最低でも次の推定問題を別々に扱う。

| 問題 | 主な観測対象 | 代表的手法 | tmp-music での用途 |
|---|---|---|---|
| 音響構造 | 周波数・エネルギー | STFT, CQT | 音色、低域、倍音、セクション差 |
| 拍・テンポ | onset 時系列 | beat tracking, tempogram | rap の half/double-time 問題 |
| 曲構造 | 類似度 | SSM, novelty, recurrence | A/B、反復、約29秒周期 |
| 音高 | F0 | pYIN, CREPE, melody extraction | 裏返り、滑り、調律 |
| 歌詞 | 言語列 | Whisper 等 | free transcription |
| 既知歌詞の位置 | 時刻 | CTC/forced alignment | 歌詞→実音声の対応 |
| 音素/モーラ | 発音単位 | phoneme alignment | 異言語化、発音崩し |
| 声質 | source/filter | CPPS, HNR, H1-H2, formants | 地声/裏声、息漏れ、共鳴 |
| 音源 | source stem | Demucs, RoFormer | vocal-only 解析 |
| 類似性 | 多次元特徴 | handcrafted + embeddings | 民俗歌唱との比較 |

**重要:** 同じ数値が複数の原因から生じる。たとえば「12-TET から 30 cent 外れる」は、微分音の安定音高かもしれないし、単なるポルタメント、vibrato、F0 推定誤差、伴奏の混入かもしれない。

---

## 2. 時間周波数解析: FFT/STFT だけで終わらせない

### 2.1 STFT

STFT は時間局所化されたスペクトルを見る基礎で、現在の scripts/analyze_audio.py でも利用している。

用途:

- 声と伴奏の大まかな帯域差
- consonant / percussion による高域増加
- bass/kick による低域増加
- harmonic stack
- セクションごとの spectral centroid / flatness / rolloff

注意:

- 窓長を一つに固定すると、低周波の分解能と時間分解能がトレードオフになる。
- rap onset 用の短窓と、歌唱倍音/F0 用の長窓は分けた方がよい。
- 全曲を一回 FFT した値は、構造変化を平均化して消してしまう。

推奨:

- onset/rhythm: 短めの窓
- harmonic/pitch: 長めの窓
- 解析結果に window, hop, sampling rate を必ず記録する
- 生の 44.1/48 kHz を保管し、ASR 用 16 kHz と音響測定用を分ける

### 2.2 Constant-Q Transform (CQT)

Brown (1991) の CQT は、周波数比が一定になるように周波数軸を構成する。西洋音階のような幾何学的な音高配置と相性がよい。

tmp-music では CQT を次に使える。

- stable pitch target の可視化
- chroma / harmonic representation
- 12-TET と非12-TET候補の比較
- MERT 等の音楽向け表現との接続

ただし CQT 自体が「西洋音階を前提にしない」わけではない。bins-per-octave を細かくして cent レベルの表現にする必要がある。

参考:
- Judith C. Brown, “Calculation of a constant Q spectral transform,” JASA 89(1), 425–434, 1991. DOI: 10.1121/1.400476

---

## 3. F0・旋律・調律: 「12-TETから何cent」だけでは足りない

### 3.1 pYIN

Mauch & Dixon の pYIN は YIN の閾値を確率分布として扱い、複数候補と HMM/Viterbi による時系列平滑化を組み合わせる。

利点:
- 単旋律の連続 F0 に強い
- 実装が軽い
- voiced/unvoiced の確率も扱える
- tmp-music の既存コードに導入済み

弱点:
- 混合音では伴奏を拾う
- breathy / harsh / register flip / rap consonant で不安定
- source separation artifact にも反応する

参考:
- Matthias Mauch, Simon Dixon, “PYIN: A fundamental frequency estimator using probabilistic threshold distributions,” ICASSP 2014. DOI: 10.1109/ICASSP.2014.6853678

### 3.2 CREPE

CREPE は waveform から pitch を推定する CNN 系モデル。pYIN と異なる誤り方をするため、クロスチェック用途が大きい。

参考:
- Jong Wook Kim, Justin Salamon, Peter Li, Juan Pablo Bello, “CREPE: A Convolutional Representation for Pitch Estimation,” ICASSP 2018. DOI: 10.1109/ICASSP.2018.8461329

### 3.3 SPICE

SPICE は self-supervised pitch estimation を扱う。教師付きの固定ラベルだけに依存しない方向として比較候補になる。

参考:
- Beat Gfeller et al., “SPICE: Self-supervised pitch estimation,” IEEE/ACM TASLP 28, 1118–1128, 2020. DOI: 10.1109/TASLP.2020.2982285

### 3.4 Polyphonic melody extraction

混合音から lead melody を直接取る場合、単純な monophonic F0 より predominant melody extraction を使うべきである。

代表:
- Justin Salamon, Emilia Gómez, “Melody Extraction From Polyphonic Music Signals Using Pitch Contour Characteristics,” IEEE TASLP 20(6), 1759–1770, 2012. DOI: 10.1109/TASL.2012.2188515

### 3.5 tmp-music の調律判定を改善する

現在の nearest-12-TET residual は診断としては有用だが、次の順序にする。

1. vocal stem と mix の両方で F0 を出す
2. pYIN と CREPE の一致フレームを優先
3. glissando/vibrato 区間を「安定音高」と分離
4. 安定区間ごとに note center を推定
5. global tuning offset を先に引く
6. note center の分布を 12-TET と候補モデルへ当てはめる
7. 12-TET / 19-EDO / 24-EDO / 31-EDO / just-ratio 候補を情報量基準や尤度で比較
8. 「曲全体の cent 誤差」ではなく「安定 target の誤差」と「移動中の軌跡」を別報告

これにより、
- 本当に非12TETなのか
- 12TET target 間を大きく滑っているだけなのか
を分離できる。

### 3.6 glissando / vibrato / register flip

保存すべき時系列特徴:

- F0 slope: cents/s
- vibrato rate: Hz
- vibrato extent: cents
- note-center dwell time
- register transition 前後の F0 jump
- transition 前後の spectral tilt / CPPS / formant movement

元ちとせ的な「声の裏返り」や今回の Suno の声区変化は、note label だけでは消えてしまう。**F0 軌跡そのものを一次データとして保存**する必要がある。

---

## 4. 音源分離: 声の解析前に必要だが、分離結果を真実扱いしない

### 4.1 Demucs

Demucs は waveform-to-waveform の source separation として広く使われる系統。原論文では U-Net + bidirectional LSTM を使い、音楽の voice/bass/drums/other を分離する。

参考:
- Alexandre Défossez et al., “Music Source Separation in the Waveform Domain,” arXiv:1911.13254, 2019.

### 4.2 Open-Unmix

再現性の高い基準モデルとして有用。

参考:
- Fabian-Robert Stöter et al., “Open-Unmix — A Reference Implementation for Music Source Separation,” Journal of Open Source Software 4(41), 1667, 2019. DOI: 10.21105/joss.01667

### 4.3 RoFormer 系

2024年前後には frequency band と時間方向を Transformer で扱う方式が強くなっている。

- Mel-RoFormer: vocal separation と vocal melody transcription の双方を扱い、まず separation model を学習し、その表現から melody transcription へ fine-tune する設計。
- Wang, Lu, Chen, “Mel-RoFormer for Vocal Separation and Vocal Melody Transcription,” ISMIR 2024, pp.454–461. arXiv:2409.04702
- Lu, Wang, Kong, Hung, “Music Source Separation with Band-Split RoPE Transformer,” ICASSP 2024. DOI: 10.1109/ICASSP48485.2024.10446843

### 4.4 分離の罠

source separation は downstream F0/voice-quality を改善する一方、人工的な倍音、phasiness、bleeding、消失を発生させる。

したがって tmp-music では:

- mix
- Demucs vocal
- 別方式 vocal

の最低3系統で同じ F0/CPPS/formant を測り、**分離方式を変えても残る特徴だけを強い証拠とする**。

分離品質そのものは SDR/SI-SDR だけでなく、
- F0 一致率
- ASR/CER 改善
- formant 安定性
- residual accompaniment energy
も報告する。

---

## 5. 歌詞認識: free ASR と alignment を混同しない

### 5.1 Whisper は「歌詞の正解器」ではない

Whisper は 680,000 時間の多言語・多タスク弱教師付きデータで学習された大規模 ASR で、一般音声に強い。

参考:
- Alec Radford et al., “Robust Speech Recognition via Large-Scale Weak Supervision,” ICML 2023, PMLR 202:28492–28518. arXiv:2212.04356

しかし歌唱は、
- 音高保持
- melisma
- vibrato
- consonant deletion
- vowel extension
- accompaniment
- repetition
によって speech ASR の仮定から大きく外れる。

Whisper AO で small が Hungarian を第一候補にしたこと、じゅげむで長い反復を省略したことは、この問題を示す。

### 5.2 whole-track WER/CER は長い反復曲に弱い

じゅげむでは同じ句が何周も続くため、ASR が一部だけ認識すると deletion が巨大になる。

したがって次の2種類を分ける。

**A. Free transcription**
- 「何と聞こえたか」を測る
- auto-language と forced language を比較
- hallucination、deletion、language confusion を観測

**B. Reference-aware alignment**
- 正解歌詞が分かっている前提
- 「この歌詞のどの部分がいつ歌われたか」を測る
- 発音変形を音素/モーラ単位で比較

tmp-music の Suno MP3 は埋め込み歌詞を持つため、B が非常に有効。

### 5.3 Lyrics alignment の研究

Stoller, Durand, Ewert は polyphonic music の raw audio から character probability を出す CTC 系 alignment を提示し、line-level の弱い教師でも標準データセットで mean alignment error 0.35 s を報告した。

参考:
- Daniel Stoller, Simon Durand, Sebastian Ewert, “End-to-end Lyrics Alignment for Polyphonic Music Using An Audio-to-Character Recognition Model,” ICASSP 2019. arXiv:1902.06797

### 5.4 DALI

DALI は audio と lyrics、vocal melody を複数粒度で時間同期した大規模データセットで、lyrics alignment/transcription の重要な参照。

参考:
- Gabriel Meseguer-Brocal, Alice Cohen-Hadria, Geoffroy Peeters, “DALI: a large Dataset of synchronised Audio, LyrIcs and notes,” ISMIR 2018.

### 5.5 WhisperX

WhisperX は long-form Whisper の drift/hallucination/repetition 問題を意識し、VAD と forced phoneme alignment を加えて word-level timestamp を改善する。

参考:
- Max Bain, Jaesung Huh, Tengda Han, Andrew Zisserman, “WhisperX: Time-Accurate Speech Transcription of Long-Form Audio,” arXiv:2303.00747, 2023.

ただし元来 speech 向けなので、singing ではそのまま正解とは限らない。

### 5.6 Montreal Forced Aligner

MFA は speech-text alignment の強力な基準で、trainable acoustic model と speaker adaptation を使う。

参考:
- Michael McAuliffe et al., “Montreal Forced Aligner: Trainable Text-Speech Alignment Using Kaldi,” Interspeech 2017, pp.498–502. DOI: 10.21437/Interspeech.2017-1386

singing に使う場合:
- vocal stem
- tempoを極端に歪めない
- 語彙辞書/G2P
- singing-specific mismatch
を考慮し、alignment failure 自体も「発音が標準音声から離れた場所」の指標として保存する。

### 5.7 日本語は CER + モーラ

日本語ラップでは英語型 WER より次を重視する。

- character error rate
- kana-normalized CER
- mora error rate
- vowel sequence error
- consonant class error
- long vowel / sokuon / hatsuon の変形
- accent phrase より先に mora onset

前処理は複数表現を保存する。

1. original lyrics
2. normalized Japanese text
3. kana
4. mora sequence
5. phoneme sequence

「じゅげむ」は既知文が繰り返されるため、各周回の同一モーラを paired comparison できる。

---

## 6. ラップのリズム: BPM だけでは不十分

### 6.1 Beat tracking

Ellis の dynamic programming beat tracker は onset strength と局所的に一定な inter-beat interval を統合する基礎手法。

参考:
- Daniel P. W. Ellis, “Beat Tracking by Dynamic Programming,” Journal of New Music Research 36(1), 51–60, 2007. DOI: 10.1080/09298210701653344

### 6.2 Tactus / half-time / double-time

rap では「98 BPM か 196 BPM か」のような tempo octave ambiguity が本質的。

Condit-Schultz (ISMIR 2024) は rap flow の metric alignment を Bayesian model で扱い、異なる tempo の rhythmic value をどう整列させるかを論じている。

参考:
- Nathaniel Condit-Schultz, “Looking for Tactus in All the Wrong Places: Statistical Inference of Metric Alignment in Rap Flow,” ISMIR 2024, pp.989–995.

tmp-music の tempo 出力は一値ではなく:

- primary candidate
- half-time
- double-time
- beat confidence
- tactus hypothesis

を保存する。

### 6.3 Rap flow で測るべきもの

- mora/syllable onset の beat phase
- IOI distribution
- syllables/moras per beat
- density / burstiness
- syncopation
- phrase length
- breath gap
- rhyme-anchor position
- bar crossing
- repeated phrase の timing drift

特に じゅげむは歌詞が固定なので、「意味・語彙を固定したまま flow だけ測る」実験になる。

---

## 7. 構造・反復解析: self-similarity matrix を中核にする

### 7.1 Novelty

Foote (2000) の novelty segmentation は self-similarity を使い、silence に頼らず音楽の変化点を検出する古典的基礎。

参考:
- Jonathan Foote, “Automatic Audio Segmentation Using a Measure of Audio Novelty,” ICME 2000. DOI: 10.1109/ICME.2000.869637

### 7.2 Structure analysis の整理

Paulus, Müller, Klapuri の survey は audio structure analysis を novelty / homogeneity / repetition / combined approaches に分類する。

参考:
- Jouni Paulus, Meinard Müller, Anssi Klapuri, “State of the Art Report: Audio-Based Music Structure Analysis,” ISMIR 2010.

self-distance / self-similarity matrix では:
- stripe: 反復
- block: 同質区間
として現れやすい。

### 7.3 一つの MFCC 類似度に依存しない

現在の repetition_analysis.py は探索用にはよいが、次に multi-view SSM を作る。

- MFCC: timbre
- CQT/chroma: harmonic/pitch
- onset/tempogram: rhythm
- F0 contour: vocal melody
- phoneme/mora representation: lyric delivery
- MERT embedding: learned music representation

### 7.4 Beat-sync + DTW

反復サイクル比較は:
1. beat tracking
2. beat-synchronous feature にリサンプル
3. DTW で局所 tempo drift を吸収
4. same-position 差分を測る

とする。

じゅげむの約28.75秒周期で、
- arrangement similarity
- voice similarity
- timing similarity
- pronunciation similarity
を別軸で出す。

---

## 8. 声質・歌唱法: pitch 以外を測る

「何音か」ではなく「どう声を出しているか」を扱う。

### 8.1 Praat 系の音声学的測定

Praat は formant、pitch、intensity、harmonicity 等の基礎ツール。

参考:
- Paul Boersma, “Praat, a system for doing phonetics by computer,” Glot International 5(9/10), 341–345, 2001.

Python からは Parselmouth 等で再現可能。

### 8.2 CPPS

CPPS は周期性/声源特性に関わる指標として使われるが、singing では F0、spectral tilt、vibrato extent の影響を受ける。

Baker et al. は合成歌唱で CPPS が F0 と source spectral tilt に大きく影響され、vibrato extent とも非線形な関係を持つことを示した。

参考:
- Calvin P. Baker et al., “CPPS and Voice-Source Parameters: Objective Analysis of the Singing Voice,” Journal of Voice 38(3), 549–560, 2024. DOI: 10.1016/j.jvoice.2021.12.010

したがって CPPS を「声の良さ」や「民謡らしさ」の単純スカラーとして使わない。

### 8.3 推奨する voice-quality features

安定した有声音/母音区間で:

- CPPS
- HNR / harmonicity
- spectral tilt
- H1-H2 等
- F1/F2/F3
- formant trajectory
- intensity
- open/pressed/breathy の補助特徴
- voice break 前後差

### 8.4 jitter / shimmer の注意

jitter/shimmer は quasi-periodic な安定発声に向く。glissando、激しい vibrato、rap、voice break の最中へ無理に適用しない。

「測れない」区間を欠損として残す方が、誤った数値よりよい。

---

## 9. 音響埋め込み・foundation model

### 9.1 MERT

MERT は music-specific self-supervised model で、RVQ-VAE acoustic teacher と CQT-based musical teacher を組み合わせ、14の音楽理解タスクで評価されている。

参考:
- Yizhi Li et al., “MERT: Acoustic Music Understanding Model with Large-Scale Self-supervised Training,” ICLR 2024. arXiv:2306.00107

用途:
- section/cycle embedding
- nearest-neighbor retrieval
- unusualness / clustering
- cross-song similarity

弱点:
- embedding の近さの理由が解釈しづらい
- training corpus bias
- 文化的起源の証明には使えない

### 9.2 CLAP

CLAP は audio と natural language を contrastive に対応させる。自然言語による検索やラベル候補の探索に便利。

参考:
- Benjamin Elizalde et al., “CLAP Learning Audio Concepts from Natural Language Supervision,” ICASSP 2023. DOI: 10.1109/ICASSP49357.2023.10095889

用途:
- “chant-like”, “rap”, “vocalise”, “folk vocal” 等の exploratory retrieval
- reference corpus の粗い検索

ただし「Sámi」「Ainu」等の民族・文化ラベルを embedding だけで確定しない。

---

## 10. 民俗音楽・文化圏比較: 最重要の方法論上の注意

### 10.1 Computational ethnomusicology

計算音楽学は大規模比較を可能にするが、記録・選曲・文化ラベル・音楽理論の偏りを持つ。

参考:
- George Tzanetakis et al., “Computational Ethnomusicology,” Journal of Interdisciplinary Music Studies 1(2), 2007.

### 10.2 world music の outlier / similarity

世界各地の録音を計算的に比較する研究は存在するが、「国＝一つの音響スタイル」ではない。

参考:
- Maria Panteli et al., “A computational study on outliers in world music,” PLOS ONE / PMC, 2017.

### 10.3 人間の類似判断も文化依存

Daikoku et al. は India/Japan 間の音楽類似知覚を調べ、経験・文化背景による差を示している。

参考:
- Tatsuya Daikoku et al., “Cross-cultural Perception of Musical Similarity Within and Between India and Japan,” Music & Science, 2023. DOI: 10.1177/20592043231207998

### 10.4 2026年の cross-cultural similarity 研究

Papaioannou, Benetos, Potamianos (2026) は9つの音楽伝統、125人、1,130 audio pairs を用いて、人間の cross-cultural similarity と signal-processing features / foundation models を比較した。foundation model は強い一方、解釈可能特徴と組み合わせる ensemble に価値がある。

参考:
- Charilaos Papaioannou, Emmanouil Benetos, Alexandros Potamianos, “Cross-Cultural Music Similarity: Bridging Human Perception, Signal Processing, and Foundation Models,” Transactions of the International Society for Music Information Retrieval 9(1), 2026. DOI: 10.5334/tismir.341

### 10.5 tmp-music で「どこの民謡に聞こえるか」を扱う手順

禁止すべき近道:

    FFT → 似ている → 「この国の民謡」

推奨:

1. candidate tradition を複数提示
2. それぞれ実在録音の reference corpus を作る
3. vocal-only / mix の双方で特徴抽出
4. melody, rhythm, timbre, vocal quality を別軸で比較
5. MERT/CLAP embedding は補助として使う
6. nearest neighbor の具体的録音を人間が聴く
7. 可能なら当該伝統の知識を持つ人による評価
8. 結論は
   - 「Xの特徴が近い」
   - 「Yは一致しない」
   - 「由来は同定できない」
   と分解する

AI生成音では特に、学習データ中の複数文化の特徴が混合され得るため、「起源」より「知覚上・特徴上の類似」を扱う。

---

## 11. 評価指標をタスク別に固定する

### F0 / melody
- voicing recall / false alarm
- raw pitch accuracy
- raw chroma accuracy
- overall accuracy
- pYIN vs CREPE agreement
- stable-note target cent residual

### 調律
- global tuning offset
- stable target residual distribution
- model likelihood: 12-TET vs candidate systems
- duration-weighted target fit
- glissando を含む全frame値とは分離

### Beat / rap
- tempo candidates
- beat F-measure / continuity
- mora/syllable onset phase
- IOI distribution
- events per beat
- half/double-time consistency

### Structure
- boundary F-score with tolerance
- recurrence / pairwise repetition
- DTW distance per cycle
- feature-view agreement

### ASR / lyrics
- WER
- CER
- Japanese normalized CER
- mora error rate
- insertion/deletion/substitution separately
- language detection confidence
- alignment MAE / median timing error

### Separation
- SDR / SI-SDR when ground truth exists
- residual accompaniment
- downstream F0 agreement
- downstream CER improvement
- separator-to-separator consistency

### Voice quality
- CPPS
- HNR
- spectral tilt
- formants
- register-break change score
- vibrato rate/extent
- glissando slope

### Cross-cultural similarity
- nearest-neighbor retrieval
- rank correlation to human ratings
- per-feature similarity
- uncertainty / corpus coverage
- no single “country probability” as final verdict

---

## 12. Synthetic regression tests を作る

解析器は「実曲でそれっぽい値が出た」だけでは検証できない。

tmp-music では人工信号をテストデータに追加すべき。

### Pitch fixtures
- pure sine at A4=440 Hz
- A4 +10/+25/+50 cent
- 12-TET scale
- 19-EDO / 31-EDO scale
- linear glissando
- vibrato with known rate/extent
- register jump

### Rhythm fixtures
- exact 100 BPM clicks
- 200 BPM subdivision
- syncopated pattern
- gradual tempo drift

### Structure fixtures
- A-A-A-A
- A-B-A-B
- repeated phrase with time stretch
- repeated phrase with timbre change

### ASR fixtures
- normal TTS
- time-stretched speech
- pitch-shifted speech
- vowel-extended pseudo-singing
- repeated known Japanese mora strings

各 analyzer の出力が既知値へ収束するかを CI の cheap test にする。重い neural model は Actions の別 job にする。

---

## 13. tmp-music への具体的実装ロードマップ

### Phase A — 優先度最高

#### A1. vocal separation
追加:
- scripts/separate_vocals.py
- Demucs 系
- 別方式1本（Mel-RoFormer系を候補）

出力:
- analysis/<track>/stems/<model>/vocals.wav
- accompaniment.wav
- separator metadata

#### A2. multi-estimator F0
追加:
- pYIN
- CREPE
- optional melody model

出力:
- f0-pyin.csv
- f0-crepe.csv
- f0-consensus.csv
- disagreement.json

#### A3. stable pitch target / tuning model
追加:
- slope threshold
- minimum dwell
- vibrato-aware center estimate
- global tuning correction
- candidate tuning model comparison

出力:
- stable-notes.csv
- tuning-models.json

#### A4. cycle-level ASR
じゅげむを最初の対象にする。

各 cycle:
- auto ASR
- forced ja
- known-lyrics alignment
- kana normalization
- mora conversion
- CER/MER

出力:
- cycles/cycle-01/...cycle-08/
- cycle-comparison.csv

#### A5. multi-view repetition
- MFCC SSM
- chroma/CQT SSM
- rhythm/tempogram SSM
- F0 SSM
- embeddings SSM
- DTW

出力:
- ssm-*.npz/png
- cycle-distance.csv

### Phase B — 声の「変さ」を定量化

#### B1. voice-quality analyzer
stable voiced sections を自動選択して:
- CPPS
- HNR
- spectral tilt
- formants
- register breaks
- glissando/vibrato

#### B2. phoneme / mora alignment
- lyrics→kana→mora/phoneme
- forced alignment
- alignment confidence
- failed alignment spans

Whisper AO:
- 英語 phoneme cluster / diphthong の変形

じゅげむ:
- mora deletion / vowel change / consonant weakening

### Phase C — 文化的類似性

#### C1. reference corpus
候補ごとに:
- source URL
- recording metadata
- region/tradition
- singer/instrumentation
- license
- confidence

#### C2. interpretable + embedding
- melody
- rhythm
- timbre
- vocal quality
- MERT/CLAP embeddings

#### C3. comparison report
「似ている/似ていない」を dimension 別に報告。

---

## 14. 推奨ディレクトリ

    analysis/<track>/
      source/
      metadata/
      structure/
        boundaries.json
        tempo.json
        self-similarity/
        cycles/
      stems/
        demucs/
        roformer/
      pitch/
        pyin/
        crepe/
        consensus/
        tuning/
      lyrics/
        reference/
        asr/
        alignment/
        phonemes/
        mora/
      voice/
        cpps/
        hnr/
        formants/
        register/
        vibrato/
      embeddings/
        mert/
        clap/
      comparisons/
        cycles/
        cultural-reference/
      report/
        measurements.md
        interpretation.md
        provenance.json

**measurements と interpretation を分ける。**

これは今回の「英語として成立していないと思ったが、ID3を読むと正常な英語だった」「Sámi と断定しかけた」といった誤りを再発させないために重要。

---

## 15. 再現性・Actions運用

各 run で保存:

- source SHA-256
- git commit SHA
- Actions run URL
- OS / Python
- ffmpeg
- package freeze
- model name/version/checkpoint hash
- random seed
- analysis parameters
- source-separation model
- resampling parameters

順序:

1. cheap preflight
2. metadata
3. lightweight signal analysis
4. structure
5. source separation
6. F0 / voice
7. ASR / alignment
8. embeddings
9. interpretation

重い処理は artifact を先に確保し、その後 repo に compact results を書き戻す。

同一 branch へ書き戻す場合:

    pull/rebase → result generation/download → add → commit → push

artifact の展開先と git add の対象を一致させる。Whisper AO / じゅげむで実際に起きた write-back 漏れを regression case として残す。

---

## 16. この2曲への次の実験

### Whisper AO

最優先:
1. vocal separation
2. pYIN/CREPE consensus
3. English lyrics forced alignment
4. phoneme-level alignment failure map
5. non-lexical singing vs rap の voice-quality comparison

検証したい仮説:

- source lyrics は英語として正常
- 異質さの主要因は scale ではなく phonetic / register / continuous-pitch transformation
- whole mix の 12-TET residual は vocal-only 解析で変わる

### じゅげむ

最優先:
1. 8サイクルを DTW で対応付け
2. 各 cycle を独立 ASR
3. kana/mora alignment
4. cycle-to-cycle F0/voice/timing drift
5. same-mora pronunciation embedding comparison

検証したい仮説:

- pitch target は Whisper AO より 12-TET に強く集中
- 全曲 CER の高さは、発音だけでなく ASR の repetition deletion に大きく依存
- flow は比較的固定されつつ、発音実現が周回ごとに変わる可能性

---

## 17. 文献一覧

### Signal / pitch / melody

1. Brown, J. C. (1991). Calculation of a constant Q spectral transform. Journal of the Acoustical Society of America, 89(1), 425–434. DOI: https://doi.org/10.1121/1.400476
2. Mauch, M., & Dixon, S. (2014). PYIN: A fundamental frequency estimator using probabilistic threshold distributions. ICASSP. DOI: https://doi.org/10.1109/ICASSP.2014.6853678
3. Kim, J. W., Salamon, J., Li, P., & Bello, J. P. (2018). CREPE: A Convolutional Representation for Pitch Estimation. ICASSP. DOI: https://doi.org/10.1109/ICASSP.2018.8461329
4. Gfeller, B. et al. (2020). SPICE: Self-supervised pitch estimation. IEEE/ACM TASLP 28, 1118–1128. DOI: https://doi.org/10.1109/TASLP.2020.2982285
5. Salamon, J., & Gómez, E. (2012). Melody Extraction From Polyphonic Music Signals Using Pitch Contour Characteristics. IEEE TASLP 20(6), 1759–1770. DOI: https://doi.org/10.1109/TASL.2012.2188515

### Rhythm / structure / rap

6. Ellis, D. P. W. (2007). Beat Tracking by Dynamic Programming. Journal of New Music Research 36(1), 51–60. DOI: https://doi.org/10.1080/09298210701653344
7. Foote, J. (2000). Automatic Audio Segmentation Using a Measure of Audio Novelty. ICME. DOI: https://doi.org/10.1109/ICME.2000.869637
8. Paulus, J., Müller, M., & Klapuri, A. (2010). State of the Art Report: Audio-Based Music Structure Analysis. ISMIR 2010.
9. Grosche, P., Müller, M., & Kurth, F. (2010). Cyclic tempogram — a mid-level tempo representation for music signals. ICASSP 2010.
10. Condit-Schultz, N. (2024). Looking for Tactus in All the Wrong Places: Statistical Inference of Metric Alignment in Rap Flow. ISMIR 2024.

### Lyrics / ASR / alignment

11. Radford, A. et al. (2023). Robust Speech Recognition via Large-Scale Weak Supervision. ICML 2023 / PMLR 202. arXiv: https://arxiv.org/abs/2212.04356
12. Bain, M., Huh, J., Han, T., & Zisserman, A. (2023). WhisperX: Time-Accurate Speech Transcription of Long-Form Audio. arXiv: https://arxiv.org/abs/2303.00747
13. Stoller, D., Durand, S., & Ewert, S. (2019). End-to-end Lyrics Alignment for Polyphonic Music Using An Audio-to-Character Recognition Model. ICASSP. arXiv: https://arxiv.org/abs/1902.06797
14. Meseguer-Brocal, G., Cohen-Hadria, A., & Peeters, G. (2018). DALI: a large Dataset of synchronised Audio, LyrIcs and notes. ISMIR 2018.
15. McAuliffe, M., Socolof, M., Mihuc, S., Wagner, M., & Sonderegger, M. (2017). Montreal Forced Aligner: Trainable Text-Speech Alignment Using Kaldi. Interspeech. DOI: https://doi.org/10.21437/Interspeech.2017-1386
16. Gupta, C., Yılmaz, E., & Li, H. (2020). Automatic Lyrics Alignment and Transcription in Polyphonic Music: Does Background Music Help? ICASSP 2020. DOI: https://doi.org/10.1109/ICASSP40776.2020.9054567
17. Cífka, O., Schreiber, H., Miner, L., & Stöter, F.-R. (2024). Lyrics Transcription for Humans: A Readability-Aware Benchmark. ISMIR 2024 / arXiv:2408.06370
18. MIREX. Audio Lyrics Transcription task documentation, 2025.

### Source separation

19. Défossez, A., Usunier, N., Bottou, L., & Bach, F. (2019). Music Source Separation in the Waveform Domain. arXiv: https://arxiv.org/abs/1911.13254
20. Stöter, F.-R. et al. (2019). Open-Unmix — A Reference Implementation for Music Source Separation. JOSS 4(41), 1667. DOI: https://doi.org/10.21105/joss.01667
21. Lu, W.-T., Wang, J.-C., Kong, Q., & Hung, Y.-N. (2024). Music Source Separation with Band-Split RoPE Transformer. ICASSP. DOI: https://doi.org/10.1109/ICASSP48485.2024.10446843
22. Wang, J.-C., Lu, W.-T., & Chen, J. (2024). Mel-RoFormer for Vocal Separation and Vocal Melody Transcription. ISMIR 2024, 454–461. arXiv: https://arxiv.org/abs/2409.04702

### Voice quality / phonetics

23. Boersma, P. (2001). Praat, a system for doing phonetics by computer. Glot International 5(9/10), 341–345.
24. Baker, C. P., Sundberg, J., Purdy, S. C., Rakena, T. O., & Leão, S. H. de S. (2024). CPPS and Voice-Source Parameters: Objective Analysis of the Singing Voice. Journal of Voice 38(3), 549–560. DOI: https://doi.org/10.1016/j.jvoice.2021.12.010

### Foundation models / cross-cultural MIR

25. Li, Y. et al. (2024). MERT: Acoustic Music Understanding Model with Large-Scale Self-supervised Training. ICLR 2024. arXiv: https://arxiv.org/abs/2306.00107
26. Elizalde, B. et al. (2023). CLAP Learning Audio Concepts from Natural Language Supervision. ICASSP 2023. DOI: https://doi.org/10.1109/ICASSP49357.2023.10095889
27. Tzanetakis, G. et al. (2007). Computational Ethnomusicology. Journal of Interdisciplinary Music Studies 1(2).
28. Panteli, M. et al. (2017). A computational study on outliers in world music. PLOS ONE.
29. Daikoku, T. et al. (2023). Cross-cultural Perception of Musical Similarity Within and Between India and Japan. Music & Science. DOI: https://doi.org/10.1177/20592043231207998
30. Papaioannou, C., Benetos, E., & Potamianos, A. (2026). Cross-Cultural Music Similarity: Bridging Human Perception, Signal Processing, and Foundation Models. Transactions of the International Society for Music Information Retrieval 9(1). DOI: https://doi.org/10.5334/tismir.341

---

## 18. 読み方

この文書での「推奨」は、論文に書かれた一つの決定版パイプラインではなく、上記研究と tmp-music で実際に発生した失敗・観測を組み合わせた工学的提案である。

特に以下は区別する。

- **文献上確認されたこと**: 各論文の手法・評価結果
- **tmp-music で観測したこと**: Whisper AO / じゅげむの実測
- **今後検証する仮説**: 民俗歌唱との類似、非12TET、発音変形の原因

測定値と解釈を別ファイル・別段階にすることが、今後この実験を深くしても誤推論を増やさないための中心原則である。
