#!/usr/bin/env python3
"""English script → verified Telugu script → timed Telugu subtitles.

    python3 telugu_script.py segment SCRIPT.txt script.json [--version tel2017] [--speak-reference]
    python3 telugu_script.py sheet   script.json                     # what still needs translating (+ glossary)
    python3 telugu_script.py fill    script.json translations.json [--by "translator name"]
    /opt/cws-venv/bin/python telugu_script.py validate script.json [--labse]
    python3 telugu_script.py subtitles script.json voice.json placements.json OUT_PREFIX

Rules this tool enforces (the brief: "never invent or alter Bible quotations"):
  * A scripture segment's Telugu is ALWAYS copied from the licensed corpus (bible.py) for its reference — it is never
    translated. `fill` refuses to write into scripture segments; `validate` re-looks every verse up and fails on any
    character of difference.
  * The English quotation is compared with the World English Bible; a low score is reported as a likely wrong
    reference or a different English version — the reference is never silently "corrected".
  * Narration is translated (by the agent or a person) into natural Telugu; validate checks it is Telugu script, that
    nothing is left untranslated or empty, that the length ratio is plausible, and (with --labse) scores meaning
    preservation with LaBSE cross-lingual sentence embeddings (Apache-2.0).

Script input format (plain text): one paragraph per block (blank line between). Optional per-paragraph hints:
    [visual: candle in the dark, slow push-in]      → segment["visual"]
    [title]                                         → on-screen title card, not spoken
A scripture paragraph is any paragraph containing a reference ("Psalm 23:1") together with a quotation, e.g.
    "The LORD is my shepherd; I shall lack nothing." (Psalm 23:1)
    Jesus said, "I am the good shepherd..." — John 10:11
A lead-in before the quotation ("Jesus said,") becomes its own narration segment.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bible  # noqa: E402
from telugu_text import aksharas, latin_words, spoken_reference, telugu_ratio  # noqa: E402

HERE = Path(__file__).resolve().parent
GLOSSARY = HERE.parent / "references" / "glossary.json"
QUOTE = re.compile(r"[\"“]([^\"”]+)[\"”]")
HINT = re.compile(r"\[(visual|title|note)\s*:?\s*([^\]]*)\]", re.I)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“])")


def _split_scripture(par: str, version: str, speak_ref: bool) -> list[dict]:
    refs = bible.find_refs(par)
    if not refs:
        return []
    r = refs[0]
    quotes = QUOTE.findall(par)
    if not quotes:  # "Psalm 23:1: The LORD is my shepherd" / "The LORD is my shepherd — Psalm 23:1"
        body = (par[:r["start"]] + " " + par[r["end"]:]).strip(" \t—–-:,()")
        if len(body.split()) < 3:
            return [{"kind": "narration", "en": par, "mentions": [r["usfm"]]}]
        quotes = [body]
        lead = ""
    else:
        q0 = par.find(quotes[0])
        lead = par[:max(0, q0 - 1)]
        lead = lead.replace(r["match"], "").strip(" \t—–-:,()")
    v = bible.lookup(r["usfm"], version)
    chk = bible.check_english(quotes[0], r["usfm"])
    code, ch, v1, v2 = bible.parse_ref(r["usfm"])
    names = bible.corpus(version)["books"][code]
    # spoken: the full book name when it is one word (కీర్తనలు, ఆదికాండం), else the short name (యోహాను)
    book_te = names["long_name"] if names.get("long_name") and len(names["long_name"].split()) == 1 else names["name"]
    out = []
    if len(lead.split()) >= 2:
        out.append({"kind": "narration", "en": lead})
    out.append({"kind": "scripture", "en": quotes[0].strip(), "te": v["text"], "speak_reference": speak_ref,
                "ref": {"usfm": v["usfm"], "version": version, "local": v["local_reference"],
                        "spoken": spoken_reference(book_te, ch, v1, v2 if v2 != v1 else None),
                        "attribution": v["attribution"], "license": v["license"], "source": v["source"]},
                "english_check": chk})
    return out


def cmd_segment(a) -> int:
    text = Path(a.script).read_text(encoding="utf-8")
    pars = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    segs = []
    for par in pars:
        hints = {k.lower(): v.strip() for k, v in HINT.findall(par)}
        body = re.sub(r"\s+", " ", HINT.sub("", par)).strip()
        if not body:
            continue
        if "title" in hints:
            segs.append({"kind": "title", "en": body, "speak": False, "visual": hints.get("visual")})
            continue
        parts = _split_scripture(body, a.version, a.speak_reference)
        if not parts:
            parts = [{"kind": "narration", "en": s} for s in ([body] if a.whole_paragraphs else SENT.split(body))]
        for p in parts:
            p.setdefault("te", None)
            p["visual"] = hints.get("visual")
            segs.append(p)
    for i, s in enumerate(segs, 1):
        s["id"] = f"s{i:02d}"
    out = {"meta": {"source": str(Path(a.script).resolve()), "bible_version": a.version,
                    "bible_name": bible.VERSIONS[a.version]["name"], "language": "te"},
           "segments": [{"id": s.pop("id"), **s} for s in segs]}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    for s in out["segments"]:
        flag = ""
        if s["kind"] == "scripture":
            flag = f"  [{s['ref']['usfm']} → {s['ref']['local']}; English check: {s['english_check']['verdict']} " \
                   f"({s['english_check']['similarity']})]"
        print(f"{s['id']} {s['kind']:<9} {s['en'][:70]}{flag}")
    return 0


def cmd_sheet(a) -> int:
    sc = json.loads(Path(a.script).read_text())
    gl = json.loads(GLOSSARY.read_text()) if GLOSSARY.exists() else {}
    todo = [s for s in sc["segments"] if s["kind"] in ("narration", "title") and not s.get("te")]
    print(json.dumps({"bible_version": sc["meta"]["bible_version"], "glossary": gl,
                      "translate": {s["id"]: s["en"] for s in todo},
                      "context_scripture": {s["id"]: {"en": s["en"], "te": s["te"]} for s in sc["segments"]
                                            if s["kind"] == "scripture"}}, ensure_ascii=False, indent=2))
    return 0


def cmd_fill(a) -> int:
    sc = json.loads(Path(a.script).read_text())
    tr = json.loads(Path(a.translations).read_text())
    by_id = {s["id"]: s for s in sc["segments"]}
    for sid, te in tr.items():
        s = by_id.get(sid)
        if s is None:
            raise SystemExit(f"unknown segment {sid}")
        if s["kind"] == "scripture":
            raise SystemExit(f"{sid} is scripture: its Telugu comes only from the Bible corpus and cannot be filled")
        s["te"] = te.strip()
        s["translated_by"] = a.by
    Path(a.script).write_text(json.dumps(sc, ensure_ascii=False, indent=2))
    print(f"filled {len(tr)} segments")
    return 0


def labse_scores(pairs: list[tuple[str, str]]) -> list[float]:
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("sentence-transformers/LaBSE")
    import numpy as np
    en = m.encode([p[0] for p in pairs], normalize_embeddings=True)
    te = m.encode([p[1] for p in pairs], normalize_embeddings=True)
    return [float(x) for x in np.sum(en * te, axis=1)]


def validate(sc: dict, use_labse: bool = False) -> dict:
    errors, warnings, rows = [], [], []
    gl = json.loads(GLOSSARY.read_text()) if GLOSSARY.exists() else {}
    allowed_latin = set(gl.get("allowed_latin", []))
    for s in sc["segments"]:
        sid, te = s["id"], (s.get("te") or "").strip()
        row = {"id": sid, "kind": s["kind"]}
        if not te:
            errors.append(f"{sid}: no Telugu text")
            rows.append(row)
            continue
        if s["kind"] == "scripture":
            v = bible.lookup(s["ref"]["usfm"], s["ref"]["version"])
            row["exact_corpus_match"] = te == v["text"]
            if te != v["text"]:
                errors.append(f"{sid}: scripture text differs from {s['ref']['version']} {s['ref']['usfm']} — must be the exact corpus text")
            if s["english_check"]["similarity"] < 0.5:
                errors.append(f"{sid}: English quote does not match {s['ref']['usfm']} (similarity "
                              f"{s['english_check']['similarity']}) — check the reference with the author")
            elif s["english_check"]["similarity"] < 0.85:
                warnings.append(f"{sid}: English quote differs from WEB wording ({s['english_check']['similarity']}): "
                                "probably another English version; Telugu uses the corpus verse")
        else:
            r = telugu_ratio(te)
            lat = [w for w in latin_words(te) if w not in allowed_latin]
            ratio = len(te) / max(1, len(s["en"]))
            row.update({"telugu_ratio": round(r, 3), "latin_words": lat, "length_ratio": round(ratio, 2)})
            if r < 0.97:
                errors.append(f"{sid}: only {r:.0%} Telugu letters")
            if lat:
                errors.append(f"{sid}: untranslated Latin words {lat}")
            if len(s["en"]) >= 25 and not 0.6 <= ratio <= 2.6:
                warnings.append(f"{sid}: unusual length ratio {ratio:.2f} (Telugu/English chars) — check for omissions")
            if bible.find_refs(s["en"]) and s["kind"] == "narration":
                warnings.append(f"{sid}: mentions {[r['match'] for r in bible.find_refs(s['en'])]} — the Telugu should "
                                "use the local book name")
        row["aksharas"] = aksharas(te)
        rows.append(row)
    if use_labse:
        todo = [(i, s) for i, s in enumerate(sc["segments"]) if s.get("te") and s["kind"] != "title" or
                (s["kind"] == "title" and s.get("te"))]
        scores = labse_scores([(s["en"], s["te"]) for _, s in todo])
        for (i, s), sc_ in zip(todo, scores):
            rows[i]["labse"] = round(sc_, 3)
            if sc_ < 0.6:
                warnings.append(f"{s['id']}: low cross-lingual similarity {sc_:.2f} — review the meaning")
    return {"passed": not errors, "errors": errors, "warnings": warnings, "segments": rows}


def cmd_validate(a) -> int:
    sc = json.loads(Path(a.script).read_text())
    rep = validate(sc, a.labse)
    sc["validation"] = rep
    Path(a.script).write_text(json.dumps(sc, ensure_ascii=False, indent=2))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["passed"] else 1


# ------------------------------------------------------------------ subtitles

LINE_AKSHARAS = 30      # per line at 1080p, Noto Sans Telugu ~50 px
MAX_LINES = 2
MIN_CUE = 1.0
MAX_AKSHARA_RATE = 17.0  # aksharas per second; above this a cue is hard to read


def _split_words(text: str, limit: int) -> list[str]:
    """Greedy split of a clause into chunks of <= limit aksharas at word boundaries."""
    words, chunks, cur = text.split(), [], []
    for w in words:
        if cur and aksharas(" ".join(cur + [w])) > limit:
            chunks.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def _two_lines(text: str) -> str:
    if aksharas(text) <= LINE_AKSHARAS:
        return text
    words = text.split()
    best, best_d = text, 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        d = max(aksharas(a), aksharas(b))
        if d < best_d:
            best, best_d = f"{a}\n{b}", d
    return best


def subtitle_cues(sc: dict, voice: dict, placements: dict) -> list[dict]:
    """Cues from exact clause timings. placements: {segment id: absolute start seconds of its voice clip}."""
    cues = []
    for s in sc["segments"]:
        if s["id"] not in placements or s["id"] not in voice["segments"]:
            continue
        v = voice["segments"][s["id"]]
        t0 = placements[s["id"]]
        spoken_ref = s.get("ref", {}).get("spoken") if s["kind"] == "scripture" and s.get("speak_reference") else None
        units = []
        for c in v["clauses"]:
            txt = c["text"]
            if spoken_ref and spoken_ref in txt:
                txt = s["ref"]["local"]   # display the reference as numerals
            units.append({"text": txt, "start": t0 + c["start"], "end": t0 + c["end"]})
        # merge clauses into cues of <= MAX_LINES lines; split over-long clauses by words
        merged: list[dict] = []
        for u in units:
            limit = LINE_AKSHARAS * MAX_LINES
            if aksharas(u["text"]) > limit:
                parts = _split_words(u["text"], limit)
                tot = sum(aksharas(p) for p in parts)
                t = u["start"]
                for p in parts:
                    d = (u["end"] - u["start"]) * aksharas(p) / tot
                    merged.append({"text": p, "start": t, "end": t + d})
                    t += d
                continue
            if merged and merged[-1].get("seg") == s["id"] and \
                    aksharas(merged[-1]["text"] + " " + u["text"]) <= limit and \
                    not re.search(r"[.!?]$", merged[-1]["text"]):
                merged[-1]["text"] += " " + u["text"]
                merged[-1]["end"] = u["end"]
            else:
                merged.append({**u, "seg": s["id"]})
        for m in merged:
            m["seg"] = s["id"]
            m["kind"] = s["kind"]
        cues.extend(merged)
    # minimum duration (extend into the following gap), no overlaps, 2-frame gap
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else c["end"] + 10
        if c["end"] - c["start"] < MIN_CUE:
            c["end"] = min(c["start"] + MIN_CUE, nxt - 0.07)
        c["end"] = min(c["end"] + 0.25, nxt - 0.07)   # hold a beat after the words end
        c["lines"] = _two_lines(c["text"])
        c["rate"] = round(aksharas(c["text"]) / max(0.1, c["end"] - c["start"]), 2)
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
    return cues


def _ts(t: float, sep: str = ",") -> str:
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s - int(s)) * 1000)):03d}"


def write_srt(cues: list[dict], path: Path) -> None:
    path.write_text("".join(f"{i}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['lines']}\n\n"
                            for i, c in enumerate(cues, 1)), encoding="utf-8")


def write_ass(cues: list[dict], path: Path, w: int = 1920, h: int = 1080) -> None:
    def ass_t(t):
        hh, r = divmod(t, 3600)
        mm, ss = divmod(r, 60)
        return f"{int(hh)}:{int(mm):02d}:{ss:05.2f}"
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            f"Style: Default,Noto Sans Telugu,{int(h * 0.046)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,"
            f"{max(2, h // 400)},1,2,120,120,{int(h * 0.07)},1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    body = "".join(f"Dialogue: 0,{ass_t(c['start'])},{ass_t(c['end'])},Default,,0,0,0,,{c['lines'].replace(chr(10), r'\N')}\n"
                   for c in cues)
    path.write_text(head + body, encoding="utf-8")


def cmd_subtitles(a) -> int:
    sc = json.loads(Path(a.script).read_text())
    voice = json.loads(Path(a.voice).read_text())
    pl = json.loads(Path(a.placements).read_text())
    cues = subtitle_cues(sc, voice, pl)
    pre = Path(a.out_prefix)
    write_srt(cues, pre.with_suffix(".te.srt"))
    write_ass(cues, pre.with_suffix(".te.ass"))
    pre.with_suffix(".cues.json").write_text(json.dumps(cues, ensure_ascii=False, indent=2))
    fast = [c for c in cues if c["rate"] > MAX_AKSHARA_RATE]
    print(json.dumps({"cues": len(cues), "max_rate": max((c["rate"] for c in cues), default=0),
                      "too_fast": [c["text"] for c in fast]}, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("segment"); s.add_argument("script"); s.add_argument("out")
    s.add_argument("--version", default="tel2017", choices=[v for v in bible.VERSIONS if v.startswith("tel")])
    s.add_argument("--speak-reference", action="store_true", help="the voice reads the reference after each verse")
    s.add_argument("--whole-paragraphs", action="store_true", help="one narration segment per paragraph")
    s = sub.add_parser("sheet"); s.add_argument("script")
    s = sub.add_parser("fill"); s.add_argument("script"); s.add_argument("translations"); s.add_argument("--by", default="agent")
    s = sub.add_parser("validate"); s.add_argument("script"); s.add_argument("--labse", action="store_true")
    s = sub.add_parser("subtitles"); s.add_argument("script"); s.add_argument("voice"); s.add_argument("placements")
    s.add_argument("out_prefix")
    a = ap.parse_args(argv)
    return {"segment": cmd_segment, "sheet": cmd_sheet, "fill": cmd_fill, "validate": cmd_validate,
            "subtitles": cmd_subtitles}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
