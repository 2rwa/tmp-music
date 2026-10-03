"""Japanese normalization and mora-level edit metrics.

The cheap core handles kana deterministically. Kanji-to-reading conversion is
kept as an explicit optional step so dictionary readings are not silently
confused with ASR output.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

SMALL_COMBINING = set("ゃゅょぁぃぅぇぉゎゕゖ")
HIRAGANA_RE = re.compile(r"[ぁ-ゖゝゞー]")
JAPANESE_RE = re.compile(r"[ぁ-ゖァ-ヺ一-龯々〆ヵヶゝゞヽヾー]")


def katakana_to_hiragana(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        # Standard full-width Katakana letters map to Hiragana at -0x60.
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        elif ch == "ヵ":
            out.append("ゕ")
        elif ch == "ヶ":
            out.append("ゖ")
        elif ch == "ヽ":
            out.append("ゝ")
        elif ch == "ヾ":
            out.append("ゞ")
        else:
            out.append(ch)
    return "".join(out)


def normalize_kana(text: str) -> str:
    """NFKC, lowercase Latin, Katakana->Hiragana, then remove separators."""
    s = unicodedata.normalize("NFKC", text).lower()
    s = katakana_to_hiragana(s)
    return "".join(
        ch
        for ch in s
        if HIRAGANA_RE.fullmatch(ch) or ch.isascii() and ch.isalnum()
    )


def contains_kanji_or_unconverted_japanese(text: str) -> bool:
    s = unicodedata.normalize("NFKC", text)
    for ch in s:
        if JAPANESE_RE.fullmatch(ch) and not (
            "ぁ" <= katakana_to_hiragana(ch) <= "ゖ" or ch in "ーヽヾゝゞヵヶ"
        ):
            return True
        if "一" <= ch <= "龯" or ch in "々〆":
            return True
    return False


def to_hiragana_reading(text: str) -> str:
    """Convert surface Japanese to normalized Hiragana reading."""
    if not contains_kanji_or_unconverted_japanese(text):
        return normalize_kana(text)
    import pykakasi

    converter = pykakasi.kakasi()
    return normalize_kana("".join(str(chunk["hira"]) for chunk in converter.convert(text)))


def morae_from_kana(text: str) -> list[str]:
    """Split normalized kana into mora-like units.

    Small ya/yu/yo and small vowels attach to the previous mora. Sokuon っ,
    moraic nasal ん, and prolonged sound mark ー each occupy one mora.
    """
    s = normalize_kana(text)
    morae: list[str] = []
    for ch in s:
        if ch in SMALL_COMBINING and morae and morae[-1] not in {"っ", "ん", "ー"}:
            morae[-1] += ch
        else:
            morae.append(ch)
    return morae


def edit_alignment(reference: Iterable[str], hypothesis: Iterable[str]) -> tuple[dict[str, float | int | None], list[dict[str, str]]]:
    ref = list(reference)
    hyp = list(hypothesis)
    n, m = len(ref), len(hyp)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    op = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
        op[i][0] = "D"
    for j in range(1, m + 1):
        cost[0][j] = j
        op[0][j] = "I"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                cost[i][j] = cost[i - 1][j - 1]
                op[i][j] = "="
            else:
                candidates = (
                    (cost[i - 1][j - 1] + 1, "S"),
                    (cost[i - 1][j] + 1, "D"),
                    (cost[i][j - 1] + 1, "I"),
                )
                cost[i][j], op[i][j] = min(candidates, key=lambda item: (item[0], item[1]))

    counts = {"S": 0, "D": 0, "I": 0, "=": 0}
    rows: list[dict[str, str]] = []
    i, j = n, m
    while i or j:
        action = op[i][j]
        if action in ("=", "S"):
            rows.append({"op": action, "ref": ref[i - 1], "hyp": hyp[j - 1]})
            i -= 1
            j -= 1
        elif action == "D":
            rows.append({"op": action, "ref": ref[i - 1], "hyp": ""})
            i -= 1
        elif action == "I":
            rows.append({"op": action, "ref": "", "hyp": hyp[j - 1]})
            j -= 1
        else:
            break
        counts[action] += 1
    rows.reverse()

    errors = counts["S"] + counts["D"] + counts["I"]
    metrics: dict[str, float | int | None] = {
        "substitutions": counts["S"],
        "deletions": counts["D"],
        "insertions": counts["I"],
        "correct": counts["="],
        "reference_units": n,
        "hypothesis_units": m,
        "error_rate": errors / n if n else None,
    }
    return metrics, rows


def mora_error(reference_kana: str, hypothesis_kana: str) -> tuple[dict[str, float | int | None], list[dict[str, str]]]:
    return edit_alignment(morae_from_kana(reference_kana), morae_from_kana(hypothesis_kana))


def _edit_error_count(reference: Iterable[str], hypothesis: Iterable[str]) -> int:
    metrics, _ = edit_alignment(reference, hypothesis)
    return int(metrics["substitutions"]) + int(metrics["deletions"]) + int(metrics["insertions"])


def partition_repeated_reference_lines(
    text: str,
    cycle_count: int,
    *,
    canonical_line_count: int,
    max_line_deviation: int = 3,
) -> list[str]:
    """Partition repeated line-oriented lyrics into contiguous cycle references.

    The first cycle defines the canonical line sequence. Later cycles may have
    line deletions/insertions; dynamic programming chooses contiguous chunks
    that minimize line-level edit distance to that canonical cycle.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if cycle_count <= 0:
        raise ValueError("cycle_count must be positive")
    if canonical_line_count <= 0:
        raise ValueError("canonical_line_count must be positive")
    if len(lines) < canonical_line_count:
        raise ValueError("reference is shorter than one canonical cycle")
    if cycle_count == 1:
        return ["\n".join(lines)]

    canonical_surface = lines[:canonical_line_count]
    canonical = [normalize_kana(line) for line in canonical_surface]
    remaining_lines = lines[canonical_line_count:]
    remaining_cycles = cycle_count - 1
    minimum = max(1, canonical_line_count - max_line_deviation)
    maximum = canonical_line_count + max_line_deviation

    from functools import lru_cache

    @lru_cache(maxsize=None)
    def solve(cycles_left: int, position: int) -> tuple[int, tuple[int, ...]]:
        if cycles_left == 0:
            return (0, ()) if position == len(remaining_lines) else (10**9, ())
        remaining = len(remaining_lines) - position
        low = max(minimum, remaining - (cycles_left - 1) * maximum)
        high = min(maximum, remaining - (cycles_left - 1) * minimum)
        if low > high:
            return 10**9, ()

        best_cost = 10**9
        best_lengths: tuple[int, ...] = ()
        for length in range(low, high + 1):
            chunk = remaining_lines[position:position + length]
            normalized_chunk = [normalize_kana(line) for line in chunk]
            chunk_cost = _edit_error_count(canonical, normalized_chunk)
            rest_cost, rest_lengths = solve(cycles_left - 1, position + length)
            total = chunk_cost + rest_cost
            lengths = (length, *rest_lengths)
            tie_break = tuple(abs(x - canonical_line_count) for x in lengths)
            best_tie = tuple(abs(x - canonical_line_count) for x in best_lengths)
            if total < best_cost or (total == best_cost and (not best_lengths or tie_break < best_tie)):
                best_cost = total
                best_lengths = lengths
        return best_cost, best_lengths

    cost, lengths = solve(remaining_cycles, 0)
    if cost >= 10**9 or len(lengths) != remaining_cycles:
        raise ValueError(
            f"could not partition {len(lines)} lines into {cycle_count} cycles "
            f"around {canonical_line_count} lines/cycle"
        )

    chunks = ["\n".join(canonical_surface)]
    position = 0
    for length in lengths:
        chunks.append("\n".join(remaining_lines[position:position + length]))
        position += length
    return chunks
