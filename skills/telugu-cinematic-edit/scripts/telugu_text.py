#!/usr/bin/env python3
"""Telugu text utilities shared by the script, TTS, subtitle and validation tools.

* script checks   telugu_ratio(), latin_words(), aksharas() (syllable count used for subtitle timing / reading speed)
* numbers         cardinal(n) / ordinal(n) in Telugu words (1..999) and spoken_reference("కీర్తనలు", 23, 1)
* TTS input       clauses(text) splits at sentence / clause punctuation (the MMS tokenizer has no punctuation, so
                  pauses must be inserted by the caller), tts_clean() keeps only characters the voice can say
"""

from __future__ import annotations

import re
import unicodedata

TELUGU = re.compile(r"[ఀ-౿]")
TE_LETTER = re.compile(r"[అ-హౘ-ౚౠౡ]")  # independent vowels + consonants
VIRAMA = "్"
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")

_UNITS = ["", "ఒకటి", "రెండు", "మూడు", "నాలుగు", "ఐదు", "ఆరు", "ఏడు", "ఎనిమిది", "తొమ్మిది"]
_TEENS = ["పది", "పదకొండు", "పన్నెండు", "పదమూడు", "పద్నాలుగు", "పదిహేను", "పదహారు", "పదిహేడు", "పద్దెనిమిది",
          "పందొమ్మిది"]
_TENS = {2: "ఇరవై", 3: "ముప్పై", 4: "నలభై", 5: "యాభై", 6: "అరవై", 7: "డెబ్బై", 8: "ఎనభై", 9: "తొంభై"}
_HUNDREDS = {1: ("వంద", "నూట"), 2: ("రెండు వందలు", "రెండు వందల"), 3: ("మూడు వందలు", "మూడు వందల"),
             4: ("నాలుగు వందలు", "నాలుగు వందల"), 5: ("ఐదు వందలు", "ఐదు వందల"), 6: ("ఆరు వందలు", "ఆరు వందల"),
             7: ("ఏడు వందలు", "ఏడు వందల"), 8: ("ఎనిమిది వందలు", "ఎనిమిది వందల"), 9: ("తొమ్మిది వందలు", "తొమ్మిది వందల")}


def cardinal(n: int) -> str:
    if not 1 <= n <= 999:
        raise ValueError(f"cardinal: {n} out of range 1..999")
    h, r = divmod(n, 100)
    if h:
        alone, joined = _HUNDREDS[h]
        return alone if r == 0 else f"{joined} {cardinal(r)}"
    if r < 10:
        return _UNITS[r]
    if r < 20:
        return _TEENS[r - 10]
    t, u = divmod(r, 10)
    return _TENS[t] if u == 0 else f"{_TENS[t]} {_UNITS[u]}"


def ordinal(n: int) -> str:
    """23 → ఇరవై మూడవ, 1 → ఒకటవ, 20 → ఇరవయ్యవ, 100 → వందవ."""
    words = cardinal(n).split(" ")
    last = words[-1]
    if last.endswith("ై"):
        last = last[:-1] + "య్యవ"
    elif last.endswith("లు"):
        last = last[:-2] + "లవ"
    elif last[-1] in "ుి":
        last = last[:-1] + "వ"
    else:
        last = last + "వ"
    return " ".join(words[:-1] + [last])


def spoken_reference(book_te: str, chapter: int, verse: int | None = None, verse_end: int | None = None) -> str:
    """How a Telugu reader announces a reference: "కీర్తనలు ఇరవై మూడవ అధ్యాయం ఒకటవ వచనం"."""
    s = f"{book_te} {ordinal(chapter)} అధ్యాయం"
    if verse is not None and verse_end and verse_end != verse:
        s += f" {cardinal(verse)} నుండి {cardinal(verse_end)} వచనాలు"
    elif verse is not None:
        s += f" {ordinal(verse)} వచనం"
    return s


def telugu_ratio(text: str) -> float:
    """Share of letters that are Telugu (punctuation, digits and spaces ignored)."""
    letters = [c for c in text if unicodedata.category(c)[0] in "LM"]
    return sum(1 for c in letters if TELUGU.match(c)) / len(letters) if letters else 0.0


def latin_words(text: str) -> list[str]:
    return LATIN_WORD.findall(text)


def aksharas(text: str) -> int:
    """Approximate syllable (akshara) count: independent vowels + consonants not followed by a virama."""
    n = 0
    for i, c in enumerate(text):
        if TE_LETTER.match(c) and not (i + 1 < len(text) and text[i + 1] == VIRAMA):
            n += 1
    return n


CLAUSE_SPLIT = re.compile(r"(?<=[.!?।॥;:,—–])\s+|(?<=[.!?।])(?=\S)")
SENT_END = re.compile(r"[.!?।॥]['\"”’)]*$")


def clauses(text: str) -> list[dict]:
    """Split at punctuation. Returns [{"text", "pause"}] where pause is the kind of break that FOLLOWS the clause
    ("sentence" | "clause" | "end")."""
    parts = [p.strip() for p in CLAUSE_SPLIT.split(text.strip()) if p and p.strip()]
    out = []
    for i, p in enumerate(parts):
        kind = "end" if i == len(parts) - 1 else ("sentence" if SENT_END.search(p) else "clause")
        out.append({"text": p, "pause": kind})
    return out


def tts_clean(text: str, vocab: set[str] | None = None) -> tuple[str, list[str]]:
    """Text for the voice: digits must already be words; quotes/punctuation removed; returns (clean, dropped_chars)."""
    t = unicodedata.normalize("NFC", text).replace("‌", "").replace("‍", "")
    t = re.sub(r"[\"“”‘’()\[\]«»]", "", t)
    t = re.sub(r"[.,!?;:।॥—–-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    dropped: list[str] = []
    if vocab is not None:
        keep = []
        for c in t:
            if c in vocab or c == " ":
                keep.append(c)
            elif c not in dropped:
                dropped.append(c)
        t = re.sub(r"\s+", " ", "".join(keep)).strip()
    return t, dropped


# Spelling variants an ASR writes for the same sound: word-initial యే/యె = ఏ/ఎ (యేసు ~ ఏసు). Applied to both sides.
# (word-initial ye/e and its vowel length are written inconsistently: యెహోవా ~ ఏహోవా ~ ఎహోవా)
_VARIANTS = [(re.compile(r"(^|\s)య[ేె]"), r"\1ఏ"), (re.compile(r"(^|\s)ఎ"), r"\1ఏ")]


def norm_for_cer(text: str) -> str:
    """Telugu letters/marks only (with spelling-variant folding) — used to compare a transcript with the script."""
    t = unicodedata.normalize("NFC", text)
    for rx, rep in _VARIANTS:
        t = rx.sub(rep, t)
    return "".join(c for c in t if TELUGU.match(c))


def cer(ref: str, hyp: str) -> float:
    """Character error rate (Levenshtein / len(ref)) on Telugu characters."""
    a, b = norm_for_cer(ref), norm_for_cer(hyp)
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1] / len(a)


if __name__ == "__main__":
    for n in (1, 2, 10, 11, 20, 23, 99, 100, 101, 119, 150, 176):
        print(n, cardinal(n), "|", ordinal(n))
    print(spoken_reference("కీర్తనలు", 23, 1))
    print(spoken_reference("యోహాను", 10, 11))
    print(clauses("యెహోవా నా కాపరి. నాకు ఏ లోటూ లేదు."))
    print(aksharas("యెహోవా నా కాపరి"), telugu_ratio("యెహోవా Lord నా"), cer("నేను గొర్రెలకు", "నేను గొర్లెలకు"))
