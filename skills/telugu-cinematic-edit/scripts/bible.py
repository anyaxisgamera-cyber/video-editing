#!/usr/bin/env python3
"""Exact Bible verse lookup and quotation checking from licensed USFM corpora (never generated text).

Corpora (ebible.org USFM, licence verified on the source page — see references/sources.md):
  tel2017  Telugu Indian Revised Version (IRV) 2019 — © 2017, 2019 Bridge Connectivity Solutions, CC BY-SA 4.0
  telotsa  Biblica® Open Telugu Contemporary        — © 1976–2024 Biblica, Inc., CC BY-SA 4.0
  engwebp  World English Bible                       — public domain (used to check English quotes in scripts)

    python3 bible.py build  --root /home/user/creative-studio/bibles            # parse USFM -> corpus JSON
    python3 bible.py lookup "John 10:11" --version tel2017                       # exact text + attribution
    python3 bible.py refs   script.txt                                           # find references in English text
    python3 bible.py check-english "The LORD is my shepherd; I shall lack nothing." "Psalm 23:1"

Verse text excludes headings (\\d, \\s#, \\r …), footnotes (\\f…\\f*), cross references (\\x…\\x*) and
markup (\\wj, \\w …|attrs\\w*, \\bd …): only the words of the verse remain, exactly as published.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path("/home/user/creative-studio/bibles")
VERSIONS = {
    "tel2017": {"name": "Telugu Indian Revised Version (IRV) 2019", "short": "IRV",
                "license": "CC BY-SA 4.0", "copyright": "© 2017, 2019 Bridge Connectivity Solutions",
                "source": "https://ebible.org/find/details.php?id=tel2017"},
    "telotsa": {"name": "Biblica® Open Telugu Contemporary Version", "short": "OTCV",
                "license": "CC BY-SA 4.0", "copyright": "© 1976, 1990, 2022, 2024 Biblica, Inc.",
                "source": "https://ebible.org/find/details.php?id=telotsa"},
    "engwebp": {"name": "World English Bible", "short": "WEB", "license": "Public Domain",
                "copyright": "Public Domain", "source": "https://ebible.org/find/details.php?id=engwebp"},
}

# English book names / abbreviations -> USFM code
BOOKS = {
    "GEN": ["genesis", "gen", "gn"], "EXO": ["exodus", "exod", "exo", "ex"], "LEV": ["leviticus", "lev", "lv"],
    "NUM": ["numbers", "num", "nm"], "DEU": ["deuteronomy", "deut", "deu", "dt"], "JOS": ["joshua", "josh", "jos"],
    "JDG": ["judges", "judg", "jdg"], "RUT": ["ruth", "rut", "ru"], "1SA": ["1 samuel", "1 sam", "1sa"],
    "2SA": ["2 samuel", "2 sam", "2sa"], "1KI": ["1 kings", "1 kgs", "1ki"], "2KI": ["2 kings", "2 kgs", "2ki"],
    "1CH": ["1 chronicles", "1 chron", "1ch"], "2CH": ["2 chronicles", "2 chron", "2ch"], "EZR": ["ezra", "ezr"],
    "NEH": ["nehemiah", "neh"], "EST": ["esther", "esth", "est"], "JOB": ["job", "jb"],
    "PSA": ["psalms", "psalm", "psa", "ps", "pss"], "PRO": ["proverbs", "prov", "pro", "prv", "pr"],
    "ECC": ["ecclesiastes", "eccl", "ecc", "qoh"], "SNG": ["song of songs", "song of solomon", "song", "sng"],
    "ISA": ["isaiah", "isa", "is"], "JER": ["jeremiah", "jer"], "LAM": ["lamentations", "lam"],
    "EZK": ["ezekiel", "ezek", "ezk"], "DAN": ["daniel", "dan", "dn"], "HOS": ["hosea", "hos"], "JOL": ["joel", "jl"],
    "AMO": ["amos", "amo"], "OBA": ["obadiah", "obad", "oba"], "JON": ["jonah", "jon"], "MIC": ["micah", "mic"],
    "NAM": ["nahum", "nah"], "HAB": ["habakkuk", "hab"], "ZEP": ["zephaniah", "zeph", "zep"], "HAG": ["haggai", "hag"],
    "ZEC": ["zechariah", "zech", "zec"], "MAL": ["malachi", "mal"], "MAT": ["matthew", "matt", "mat", "mt"],
    "MRK": ["mark", "mrk", "mk"], "LUK": ["luke", "luk", "lk"], "JHN": ["john", "jhn", "jn"], "ACT": ["acts", "act"],
    "ROM": ["romans", "rom", "rm"], "1CO": ["1 corinthians", "1 cor", "1co"], "2CO": ["2 corinthians", "2 cor", "2co"],
    "GAL": ["galatians", "gal"], "EPH": ["ephesians", "eph"], "PHP": ["philippians", "phil", "php"],
    "COL": ["colossians", "col"], "1TH": ["1 thessalonians", "1 thess", "1th"], "2TH": ["2 thessalonians", "2 thess", "2th"],
    "1TI": ["1 timothy", "1 tim", "1ti"], "2TI": ["2 timothy", "2 tim", "2ti"], "TIT": ["titus", "tit"],
    "PHM": ["philemon", "phlm", "phm"], "HEB": ["hebrews", "heb"], "JAS": ["james", "jas", "jm"],
    "1PE": ["1 peter", "1 pet", "1pe"], "2PE": ["2 peter", "2 pet", "2pe"], "1JN": ["1 john", "1 jn", "1jn"],
    "2JN": ["2 john", "2 jn", "2jn"], "3JN": ["3 john", "3 jn", "3jn"], "JUD": ["jude", "jud"],
    "REV": ["revelation", "rev", "rv"],
}
ALIAS = {}
for code, names in BOOKS.items():
    for n in names:
        ALIAS[n] = code
        ALIAS[n.replace(" ", "")] = code
        for roman, num in (("1", "i"), ("2", "ii"), ("3", "iii")):
            if n.startswith(roman + " "):
                ALIAS[num + " " + n[2:]] = code
                ALIAS["first " + n[2:]] = code if roman == "1" else ALIAS.get("first " + n[2:], code)

_name_alt = "|".join(sorted((re.escape(k) for k in ALIAS), key=len, reverse=True))
REF_RE = re.compile(rf"\b({_name_alt})\.?\s+(\d{{1,3}}):(\d{{1,3}})(?:\s*[-–]\s*(\d{{1,3}}))?\b", re.I)

DROP_PARA = re.compile(r"^\\(id|ide|h|toc\d?|mt\d?|ms\d?|mr|s\d?|sr|r|d|sp|cl|cp|iot|io\d?|is\d?|ip|imt\d?|ie|rem|sts)\b.*$")
NOTE = re.compile(r"\\(f|fe|x|ef|ex)\s.*?\\\1\*", re.S)
WATTR = re.compile(r"\|[^\\]*?(?=\\\+?w\*)")   # also nested \+w …|attrs\+w*


def clean(text: str) -> str:
    text = NOTE.sub("", text)
    text = WATTR.sub("", text)                       # \w word|lemma="…"\w*  -> word
    text = re.sub(r"\\\+?[a-z]+\d?\*?", "", text)    # remaining character/paragraph markers
    return re.sub(r"\s+", " ", text).strip()


def parse_usfm(path: Path) -> tuple[str, dict, dict]:
    book, meta, verses = None, {}, {}
    chap, cur, buf = 0, None, []

    def flush():
        if cur is not None:
            t = clean(" ".join(buf))
            if t:
                verses[f"{chap}:{cur}"] = t

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\\id\s+(\w{3})", line)
        if m:
            book = m.group(1)
            continue
        for key in ("h", "toc1", "toc2", "toc3"):
            m = re.match(rf"^\\{key}\s+(.+)$", line)
            if m:
                meta[key] = clean(m.group(1))
        if DROP_PARA.match(line):
            continue
        m = re.match(r"^\\c\s+(\d+)", line)
        if m:
            flush()
            chap, cur, buf = int(m.group(1)), None, []
            continue
        # a line may hold several verses: split on \v markers
        parts = re.split(r"\\v\s+(\d+(?:-\d+)?)\s*", line)
        head, rest = parts[0], parts[1:]
        if cur is not None and head.strip():
            buf.append(head)
        for i in range(0, len(rest), 2):
            flush()
            cur, buf = rest[i].split("-")[0], [rest[i + 1]]
    flush()
    return book, meta, verses


def build(root: Path, versions=VERSIONS) -> dict:
    out = {}
    for vid in versions:
        files = sorted((root / vid / "usfm").glob("*.usfm"))
        corpus = {"version": vid, **versions[vid], "books": {}}
        for f in files:
            book, meta, verses = parse_usfm(f)
            if book and verses:
                corpus["books"][book] = {"name": meta.get("toc2") or meta.get("h") or book,
                                         "long_name": meta.get("toc1", ""), "verses": verses}
        p = root / f"{vid}.corpus.json"
        p.write_text(json.dumps(corpus, ensure_ascii=False))
        out[vid] = {"books": len(corpus["books"]), "verses": sum(len(b["verses"]) for b in corpus["books"].values()),
                    "file": str(p)}
    return out


_cache: dict = {}


def corpus(vid: str, root: Path = ROOT) -> dict:
    if vid not in _cache:
        _cache[vid] = json.loads((root / f"{vid}.corpus.json").read_text())
    return _cache[vid]


def parse_ref(ref: str) -> tuple[str, int, int, int]:
    m = REF_RE.search(ref)
    if not m:
        raise ValueError(f"not a Bible reference: {ref!r}")
    name = re.sub(r"\s+", " ", m.group(1).lower())
    code = ALIAS.get(name) or ALIAS.get(name.replace(" ", ""))
    v1 = int(m.group(3))
    return code, int(m.group(2)), v1, int(m.group(4) or v1)


def lookup(ref: str, vid: str = "tel2017", root: Path = ROOT) -> dict:
    code, ch, v1, v2 = parse_ref(ref)
    c = corpus(vid, root)
    book = c["books"].get(code)
    if not book:
        raise KeyError(f"{code} not in {vid}")
    texts, missing = [], []
    for v in range(v1, v2 + 1):
        t = book["verses"].get(f"{ch}:{v}")
        (texts.append(t) if t else missing.append(v))
    if missing:
        raise KeyError(f"{code} {ch}:{missing} not found in {vid}")
    local = f"{book['name']} {ch}:{v1}" + (f"-{v2}" if v2 != v1 else "")
    return {"reference": ref, "usfm": f"{code} {ch}:{v1}" + (f"-{v2}" if v2 != v1 else ""), "version": vid,
            "version_name": c["name"], "short": c["short"], "local_reference": local, "text": " ".join(texts),
            "license": c["license"], "copyright": c["copyright"], "source": c["source"],
            "attribution": f"{local} ({c['short']}) — {c['name']}, {c['copyright']}, {c['license']}"}


def find_refs(text: str) -> list[dict]:
    out = []
    for m in REF_RE.finditer(text):
        try:
            code, ch, v1, v2 = parse_ref(m.group(0))
        except ValueError:
            continue
        if code:
            out.append({"match": m.group(0), "start": m.start(), "end": m.end(), "usfm": f"{code} {ch}:{v1}" +
                        (f"-{v2}" if v2 != v1 else "")})
    return out


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[“”\"'’‘`]", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def check_english(quote: str, ref: str, vid: str = "engwebp") -> dict:
    """How close is an English quotation to the cited verse (WEB)? Low scores flag a wrong reference or a
    different English translation (NIV/ESV/KJV wording) — reported, never 'corrected' silently."""
    v = lookup(ref, vid)
    a, b = _norm(quote), _norm(v["text"])
    ratio = difflib.SequenceMatcher(None, a.split(), b.split()).ratio()
    return {"reference": ref, "web_text": v["text"], "similarity": round(ratio, 3),
            "verdict": "matches WEB" if ratio >= 0.85 else ("close (another English version?)" if ratio >= 0.5
                                                           else "MISMATCH — check the reference")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    s = sub.add_parser("lookup"); s.add_argument("ref"); s.add_argument("--version", default="tel2017")
    s = sub.add_parser("refs"); s.add_argument("file", type=Path)
    s = sub.add_parser("check-english"); s.add_argument("quote"); s.add_argument("ref")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        print(json.dumps(build(a.root), indent=2))
    elif a.cmd == "lookup":
        print(json.dumps(lookup(a.ref, a.version, a.root), ensure_ascii=False, indent=2))
    elif a.cmd == "refs":
        print(json.dumps(find_refs(a.file.read_text()), indent=2))
    else:
        print(json.dumps(check_english(a.quote, a.ref), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
