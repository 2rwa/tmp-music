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
