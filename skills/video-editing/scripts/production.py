#!/usr/bin/env python3
"""Script-to-video production tooling: deliverable matrix, source register, timing maps, Remotion props, renders.

Commands (paths inside a production are relative to the production directory):

  init PROD --videos 2 --languages en,te --durations 60,90 --formats 9:16,16:9 --resolutions 1080,2160 [--commercial]
  register-add PROD --id a01 --kind video --file assets/a01.mp4 --title … --source-url … --licence … [...]
  audit PROD [--credits reports/credits.md]
  timing PROD --video v01 --language te [--fit gaps]
  props PROD --video v01 --language te --format 9:16 --resolution 1080 --motion-project PROD/remotion [--copy]
  render PROD --video v01 --language te --format 9:16 --resolution 1080 --motion-project PROD/remotion
  feasibility PROD [--video v01]
  status PROD
  discover PROD --query "lighthouse at night" --kind image --providers openverse:wikimedia,nasa,met,loc,pexels,pixabay [--thumbs]
  fetch PROD --id c1a2b3c4
  source-check PROD URL [URL ...] [--note "what it supports"]
  qc PROD --video v01 --language te --format 9:16 --resolution 1080 [--file x.mp4]

Only `discover`, `fetch`, and `source-check` contact external services (see discovery.py / providers.py); every request
is logged to research/external-actions.jsonl with secrets redacted. `render` runs the Remotion CLI, which may fetch
Remotion's own browser on first use. Every reported fact is measured from local files (ffprobe, silencedetect,
ebur128, SHA-256, cross-correlation) or read from the project's own records.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKBENCH = HERE / "video_workbench.py"
SR = 48000
FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
ASSET_KINDS = ["video", "image", "audio", "music", "sfx", "voice", "font", "graphic", "animation", "other"]
STATUSES = ["candidate", "approved", "downloaded", "used", "rejected"]
# Conservative caption defaults (graphemes per line, graphemes per second). Replace them with the target platform's
# language-specific style guide when one applies.
CJK = {"zh", "ja", "ko"}
WIDE_GLYPH = {"hi", "te", "ta", "kn", "ml", "bn", "mr", "gu", "pa", "or", "si", "th", "my", "km", "lo", "ne"}
RTL = {"ar", "he", "fa", "ur", "ps", "yi"}


def fail(msg: str) -> None:
    raise SystemExit(f"error: {msg}")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, value) -> None:
    """Write via a temporary file and rename, so an interrupted write never leaves truncated JSON behind."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fmt_key(fmt: str) -> str:
    return fmt.replace(":", "x")


def canvas_size(fmt: str, resolution: int) -> tuple[int, int]:
    if fmt not in FORMATS:
        fail(f"unknown format {fmt!r}; use one of {sorted(FORMATS)}")
    w, h = FORMATS[fmt]
    k = resolution / 1080
    return int(round(w * k / 2) * 2), int(round(h * k / 2) * 2)


def graphemes(text: str) -> int:
    """Visible characters: combining marks (Indic vowel signs, viramas, accents) do not count separately."""
    return sum(1 for c in text if not c.isspace() and unicodedata.category(c)[0] != "M")


def lang_defaults(code: str) -> dict:
    base = code.split("-")[0].lower()
    if base in CJK:
        mc, cps = 16, 9
    elif base in WIDE_GLYPH:
        mc, cps = 32, 15
    else:
        mc, cps = 42, 17
    return {"code": code, "direction": "rtl" if base in RTL else "ltr", "font": None, "max_chars": mc, "max_cps": cps}


# ------------------------------------------------------------------ media facts


def ffprobe(p: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"ffprobe could not read {p}: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def media_facts(p: Path) -> dict:
    d = ffprobe(p)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    facts: dict = {"duration": float(d["format"]["duration"]) if d["format"].get("duration") else None}
    if v:
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        if abs(rot) % 180 == 90:
            w, h = h, w
        num, den = (v.get("r_frame_rate") or "0/1").split("/")
        facts.update({"width": w, "height": h, "video_codec": v["codec_name"],
                      "fps": round(float(num) / float(den), 3) if float(den) else None})
        # single images report a tiny duration; mark them so they can hold any length
        if v["codec_name"] in ("png", "mjpeg", "webp", "bmp", "tiff") and (facts["duration"] or 0) < 0.1:
            facts["still"] = True
    if a:
        facts.update({"audio_codec": a["codec_name"], "sample_rate": int(a["sample_rate"]), "channels": a.get("channels")})
    return facts


def speech_window(p: Path, dur: float, noise_db: int = -40) -> tuple[float, float]:
    """(start, end) of sound inside a narration file: leading/trailing silence found by silencedetect."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", f"silencedetect=n={noise_db}dB:d=0.12",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    s0, s1 = 0.0, dur
    if starts and starts[0] <= 0.02 and ends:
        s0 = ends[0]
    if starts and (len(ends) < len(starts) or ends[-1] >= dur - 0.02):
        s1 = starts[-1] if starts[-1] > s0 else dur
    if s1 - s0 < 0.05:
        s0, s1 = 0.0, dur
    return round(s0, 3), round(s1, 3)


def loudness(p: Path) -> dict:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    try:
        return {"I": float(summ.split("I:")[1].split("LUFS")[0]), "TP": float(summ.split("Peak:")[1].split("dBFS")[0])}
    except (IndexError, ValueError):
        return {"I": float("-inf"), "TP": float("-inf")}


# ------------------------------------------------------------------ project


def load_prod(prod: Path) -> dict:
    f = prod / "production.json"
    if not f.exists():
        fail(f"{f} not found — run `production.py init` first")
    return read_json(f)


def register_path(prod: Path) -> Path:
    return prod / "research" / "source-register.json"


def load_register(prod: Path) -> dict:
    p = register_path(prod)
    return read_json(p) if p.exists() else {"assets": []}


def save_register_entries(prod: Path, entries: list[dict]) -> None:
    """Merge entries (by id) into the register on disk under an exclusive lock. Long-running commands (fetch waiting
    out a rate limit, narrate) hold an in-memory copy; writing that copy whole would discard what other commands
    recorded meanwhile, so every command saves only the entries it changed."""
    import fcntl
    rp = register_path(prod)
    rp.parent.mkdir(parents=True, exist_ok=True)
    with open(rp.with_name(rp.name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reg = load_register(prod)
        merged = {x["id"]: x for x in reg.get("assets", [])}
        merged.update({e["id"]: e for e in entries})
        reg["assets"] = sorted(merged.values(), key=lambda x: x["id"])
        write_json(rp, reg)


def update_deliverable(prod: Path, path: str, fields: dict, drop: tuple = ()) -> None:
    """Change one deliverable in production.json under a lock, re-reading the file first: renders run for minutes and
    several may run at once, so none may write back the whole document it loaded at its start."""
    import fcntl
    pj = prod / "production.json"
    with open(pj.with_name(pj.name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        doc = read_json(pj)
        for d in doc["deliverables"]:
            if d["path"] == path:
                for k in drop:
                    d.pop(k, None)
                d.update(fields)
        write_json(pj, doc)


def asset_by_id(reg: dict) -> dict:
    return {a["id"]: a for a in reg.get("assets", [])}


def cmd_init(a) -> None:
    prod = a.production.resolve()
    if (prod / "production.json").exists():
        fail(f"{prod / 'production.json'} already exists")
    ids = [x.strip() for x in a.video_ids.split(",")] if a.video_ids else [f"v{i:02d}" for i in range(1, a.videos + 1)]
    durs = [float(x) for x in a.durations.split(",")] if a.durations else [None]
    if len(durs) not in (1, len(ids)):
        fail("--durations needs one value or one per video")
    durs = durs * len(ids) if len(durs) == 1 else durs
    langs_all = [x.strip() for x in a.languages.split(",") if x.strip()]
    per_video = {}
    if a.video_languages:
        for part in a.video_languages.split(";"):
            vid, ls = part.split("=")
            per_video[vid.strip()] = [x.strip() for x in ls.split(",") if x.strip()]
    formats = [x.strip() for x in a.formats.split(",")]
    for f in formats:
        canvas_size(f, 1080)
    resolutions = [int(x) for x in a.resolutions.split(",")]
    videos = []
    used_langs: list[str] = []
    for vid, dur in zip(ids, durs):
        ls = per_video.get(vid, langs_all)
        used_langs += [l for l in ls if l not in used_langs]
        videos.append({"id": vid, "duration_seconds": dur, "languages": ls,
                       "scripts": {l: f"scripts/{vid}/{l}.txt" for l in ls}})
    deliverables = []
    for v in videos:
        for l in v["languages"]:
            for f in formats:
                for r in resolutions:
                    name = f"{v['id']}-{l}-{fmt_key(f)}-{r}"
                    deliverables.append({"video": v["id"], "language": l, "format": f, "resolution": r,
                                         "path": f"deliverables/{v['id']}/{l}/{name}.mp4", "status": "planned"})
    doc = {"version": 1, "created": now(), "commercial": bool(a.commercial), "fps": a.fps,
           "languages": {l: lang_defaults(l) for l in used_langs}, "videos": videos, "formats": formats,
           "resolutions": resolutions, "deliverables": deliverables,
           "loudness": {"I": -16.0, "TP": -1.5}}
    for d in ["research", "assets", "reports", "review"]:
        (prod / d).mkdir(parents=True, exist_ok=True)
    for v in videos:
        for d in [f"scripts/{v['id']}", f"plan/{v['id']}", f"timing/{v['id']}", f"captions/{v['id']}"]:
            (prod / d).mkdir(parents=True, exist_ok=True)
        for l in v["languages"]:
            (prod / "narration" / v["id"] / l).mkdir(parents=True, exist_ok=True)
            (prod / "deliverables" / v["id"] / l).mkdir(parents=True, exist_ok=True)
        sp = prod / "plan" / v["id"] / "scenes.json"
        if not sp.exists():
            write_json(sp, {"video": v["id"], "fps": a.fps, "lead_in_seconds": 0.6, "gap_seconds": 0.35,
                            "tail_seconds": 1.5, "scenes": [], "music": None})
    write_json(prod / "production.json", doc)
    write_json(register_path(prod), {"assets": []})
    write_json(prod / "research" / "references.json", {"references": []})
    write_json(prod / "research" / "approvals.json", {"approvals": []})
    (prod / "reports" / "revisions.md").write_text("# Revisions\n\n", encoding="utf-8")
    print(f"initialized {prod}: {len(videos)} video(s), {len(used_langs)} language(s), {len(deliverables)} deliverable(s)")


def cmd_register_add(a) -> None:
    prod = a.production.resolve()
    reg = load_register(prod)
    entry = {k: v for k, v in {
        "id": a.id, "kind": a.kind, "title": a.title, "creator": a.creator, "source_url": a.source_url,
        "download_url": a.download_url,
        "licence": {"name": a.licence, "url": a.licence_url, "commercial_use": a.commercial_use,
                    "attribution_required": a.attribution_required, "attribution": a.attribution,
                    "restrictions": a.restrictions},
        "evidence": {"note": a.evidence, "checked_at": a.checked_at or now()},
        "status": a.status, "cost": a.cost, "approval": a.approval, "notes": a.notes}.items() if v is not None}
    if a.file:
        f = Path(a.file)
        fp = f if f.is_absolute() else prod / f
        if not fp.exists():
            fail(f"{fp} does not exist — register only files that were actually obtained")
        try:
            entry["local_path"] = str(fp.resolve().relative_to(prod))
        except ValueError:
            entry["local_path"] = str(fp.resolve())
        entry["sha256"] = sha256(fp)
        entry["bytes"] = fp.stat().st_size
        if a.kind != "font":
            entry["probe"] = media_facts(fp)
    elif a.status in ("downloaded", "used"):
        fail(f"status {a.status!r} needs --file")
    entry["recorded_at"] = now()
    save_register_entries(prod, [entry])
    print(json.dumps({"registered": a.id, "status": a.status, "sha256": entry.get("sha256"), "probe": entry.get("probe")},
                     ensure_ascii=False))


def scene_plans(prod: Path, doc: dict) -> dict:
    out = {}
    for v in doc["videos"]:
        p = prod / "plan" / v["id"] / "scenes.json"
        if p.exists():
            out[v["id"]] = read_json(p)
    return out


def referenced_assets(plan: dict) -> set[str]:
    ids = set()
    for s in plan.get("scenes", []):
        if s.get("visual", {}).get("asset"):
            ids.add(s["visual"]["asset"])
        for x in s.get("sfx", []):
            ids.add(x["asset"])
    if plan.get("music") and plan["music"].get("asset"):
        ids.add(plan["music"]["asset"])
    return ids


def load_approvals(prod: Path) -> dict:
    p = prod / "research" / "approvals.json"
    return {x["id"]: x for x in read_json(p).get("approvals", [])} if p.exists() else {}


def licence_blockers(e: dict, doc: dict, approvals: dict) -> list[str]:
    """Why an asset may not appear in this production's deliverables (empty list = usable)."""
    lic = e.get("licence", {}) or {}
    cu = str(lic.get("commercial_use", "unknown")).lower()
    out = []
    if doc.get("commercial"):
        if cu in ("no", "false"):
            out.append(f"{e['id']}: licence {lic.get('name')!r} does not allow commercial use")
        elif cu in ("", "unknown"):
            out.append(f"{e['id']}: licence {lic.get('name')!r} — commercial use not verified; commercial output is blocked until it is")
        elif cu == "conditional":
            ap = approvals.get(e.get("approval") or "")
            if not ap or ap.get("decision") != "approved":
                out.append(f"{e['id']}: {lic.get('restrictions') or 'conditional licence'} — needs an approved approval record")
    if lic.get("no_derivatives"):
        out.append(f"{e['id']}: licence forbids derivatives (editing)")
    if e.get("cost") and str(e["cost"]).strip() not in ("0", "free", "none"):
        ap = approvals.get(e.get("approval") or "")
        if not ap or ap.get("decision") != "approved":
            out.append(f"{e['id']}: paid asset ({e['cost']}) without an approved approval record")
    return out


def narration_files(prod: Path, vid: str | None = None, lang: str | None = None) -> list[Path]:
    root = prod / "narration"
    if not root.exists():
        return []
    pat = f"{vid or '*'}/{lang or '*'}/*"
    return sorted(p for p in root.glob(pat) if p.suffix.lower() in AUDIO_EXT)


def font_files(doc: dict, lang: str | None = None) -> list[str]:
    """Caption/title font files configured per language in production.json (part of every deliverable in that language)."""
    langs = [lang] if lang else list(doc.get("languages", {}))
    return [f for f in (((doc.get("languages", {}).get(l) or {}).get("font") or {}).get("file") for l in langs) if f]


def register_by_path(reg: dict) -> dict:
    return {x.get("local_path"): x for x in reg.get("assets", []) if x.get("local_path")}


def deliverable_assets(prod: Path, doc: dict, reg: dict, vid: str, lang: str) -> tuple[list[dict], list[str]]:
    """Every register entry that ends up in (video, language): scene media, music, SFX, narration files."""
    by_id, by_path = asset_by_id(reg), register_by_path(reg)
    plan = scene_plans(prod, doc).get(vid, {})
    entries, missing = [], []
    for aid in sorted(referenced_assets(plan)):
        (entries.append(by_id[aid]) if aid in by_id else missing.append(f"{aid}: referenced by {vid} but not registered"))
    for f in narration_files(prod, vid, lang):
        rel = str(f.relative_to(prod))
        (entries.append(by_path[rel]) if rel in by_path else
         missing.append(f"{rel}: narration file not registered (record its voice and licence with register-add or narrate)"))
    for rel in font_files(doc, lang):
        (entries.append(by_path[rel]) if rel in by_path else
         missing.append(f"{rel}: font file not registered (record its licence with register-add --kind font)"))
    return entries, missing


def cmd_audit(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    reg = load_register(prod)
    approvals = load_approvals(prod)
    by_id = asset_by_id(reg)
    errors, warnings = [], []
    used = set()
    for vid, plan in scene_plans(prod, doc).items():
        for aid in referenced_assets(plan):
            used.add(aid)
            if aid not in by_id:
                errors.append(f"{vid}: asset {aid} is used in scenes.json but not in the source register")
    by_path = register_by_path(reg)
    for f in narration_files(prod):
        rel = str(f.relative_to(prod))
        if rel in by_path:
            used.add(by_path[rel]["id"])
        else:
            errors.append(f"{rel}: narration file not registered (record its voice and licence with register-add or narrate)")
    for rel in font_files(doc):
        if rel in by_path:
            used.add(by_path[rel]["id"])
        else:
            errors.append(f"{rel}: font file not registered (record its licence with register-add --kind font)")
    for aid, e in by_id.items():
        lic = e.get("licence", {})
        if e.get("status") in ("downloaded", "used") or aid in used:
            if e.get("status") in ("candidate", "rejected"):
                errors.append(f"{aid}: used in a scene but its status is {e.get('status')!r}")
            lp = e.get("local_path")
            fp = (prod / lp) if lp and not Path(lp).is_absolute() else Path(lp) if lp else None
            if not fp or not fp.exists():
                errors.append(f"{aid}: local file missing ({lp})")
            elif e.get("sha256") and sha256(fp) != e["sha256"]:
                errors.append(f"{aid}: checksum changed since registration ({lp})")
            if not lic.get("name"):
                errors.append(f"{aid}: no licence recorded")
            if not (e.get("evidence") or {}).get("note") and e.get("source_url") not in ("generated", "user-supplied"):
                errors.append(f"{aid}: no licence evidence recorded")
            if not e.get("source_url"):
                errors.append(f"{aid}: no source URL (use 'generated' or 'user-supplied' when applicable)")
            blockers = licence_blockers(e, doc, approvals)
            if aid in used:
                errors += [b + " — but it is used in this commercial production" if "commercial" in b and doc.get("commercial")
                           else b for b in blockers]
            elif blockers:
                warnings.append(f"{aid}: downloaded but not usable here ({'; '.join(blockers)}); keep it unused")
            if not doc.get("commercial") and aid in used and (lic.get("share_alike") or str(lic.get("commercial_use")) == "conditional"):
                warnings.append(f"{aid}: share-alike licence — the finished video must be released under {lic.get('name')}")
        if aid not in used and e.get("status") == "used":
            warnings.append(f"{aid}: marked used but no scene references it")
    credits = []
    for aid in sorted(used):
        e = by_id.get(aid)
        if not e:
            continue
        lic = e.get("licence", {})
        line = f"- {e.get('title', aid)}"
        if e.get("creator"):
            line += f" — {e['creator']}"
        if e.get("source_url") not in (None, "generated", "user-supplied"):
            line += f" — {e['source_url']}"
        line += f" — {lic.get('name', '?')}"
        if lic.get("credit_line"):
            line += f" — {lic['credit_line']}"
        if lic.get("attribution"):
            line += f" — {lic['attribution']}"
        credits.append(line)
        if str(lic.get("attribution_required", "")).lower() in ("yes", "true") and not lic.get("attribution"):
            warnings.append(f"{aid}: attribution required — add the exact attribution text (--attribution)")
    report = {"checked_at": now(), "assets": len(by_id), "used": sorted(used), "errors": errors, "warnings": warnings,
              "passed": not errors}
    write_json(prod / "reports" / "audit.json", report)
    if a.credits:
        cp = Path(a.credits)
        cp = cp if cp.is_absolute() else prod / cp
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text("# Credits and licences\n\n" + "\n".join(credits) + "\n", encoding="utf-8")
    for x in errors:
        print("ERROR  " + x)
    for x in warnings:
        print("WARN   " + x)
    print(f"audit {'passed' if not errors else 'FAILED'}: {len(used)} used asset(s), {len(errors)} error(s), {len(warnings)} warning(s)")
    raise SystemExit(0 if not errors else 1)


# ------------------------------------------------------------------ timing


AUDIO_EXT = [".wav", ".flac", ".m4a", ".mp3", ".aac", ".ogg", ".opus"]


def find_narration(prod: Path, vid: str, lang: str, sid: str) -> Path | None:
    for ext in AUDIO_EXT:
        p = prod / "narration" / vid / lang / f"{sid}{ext}"
        if p.exists():
            return p
    return None


def norm_word(w: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFC", w).lower())


def word_times(words: list[str], window: tuple[float, float], words_json: Path | None) -> tuple[list[tuple[float, float]], str]:
    """Per-word (start, end) in file seconds: from Whisper-style word timestamps when they match the script's words,
    otherwise distributed over the speech window in proportion to word length (+ a pause weight after punctuation)."""
    if words_json and words_json.exists():
        data = read_json(words_json)
        ww = [w for seg in data.get("segments", []) for w in seg.get("words", [])]
        if len(ww) == len(words) and all(norm_word(x["word"]) == norm_word(y) or not norm_word(y) for x, y in zip(ww, words)):
            return [(float(x["start"]), float(x["end"])) for x in ww], "word-timestamps"
    s0, s1 = window
    weights = [max(1, graphemes(w)) + (2 if re.search(r"[.,!?;:،。，、！？]$", w) else 0) for w in words]
    total = sum(weights) or 1
    out, t = [], s0
    for w in weights:
        d = (s1 - s0) * w / total
        out.append((t, t + d))
        t += d
    return out, "proportional" + (" (word timestamps did not match the script words)" if words_json and words_json.exists() else "")


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def caption_cues(tokens: list[dict], max_chars: int, max_lines: int = 2) -> list[dict]:
    """Group caption tokens (absolute ms) into cues of <= max_lines lines of <= max_chars graphemes,
    preferring breaks after punctuation."""
    cues, cur, lines, line = [], [], [], ""
    def flush():
        nonlocal cur, lines, line
        if line:
            lines.append(line)
        if cur:
            cues.append({"startMs": cur[0]["startMs"], "endMs": cur[-1]["endMs"], "text": "\n".join(lines),
                         "scene": cur[0]["scene"]})
        cur, lines, line = [], [], ""
    for i, t in enumerate(tokens):
        w = t["text"].strip()
        if cur and t["scene"] != cur[-1]["scene"]:
            flush()
        cand = (line + " " + w).strip()
        if graphemes(cand) > max_chars and line:
            lines.append(line)
            line = w
            if len(lines) >= max_lines:
                line = ""
                flush()
                line = w
        else:
            line = cand
        cur.append(t)
        if re.search(r"[.!?。！？]$", w) and graphemes(" ".join(lines + [line])) > max_chars * 0.6:
            flush()
    flush()
    return cues


def cmd_timing(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    video = next((v for v in doc["videos"] if v["id"] == a.video), None)
    if not video:
        fail(f"unknown video {a.video}")
    if a.language not in video["languages"]:
        fail(f"{a.video} has no language {a.language}")
    lang = {**lang_defaults(a.language), **doc.get("languages", {}).get(a.language, {})}
    if a.max_chars:
        lang["max_chars"] = a.max_chars
    if a.max_cps:
        lang["max_cps"] = a.max_cps
    plan = read_json(prod / "plan" / a.video / "scenes.json")
    scenes = plan.get("scenes", [])
    if not scenes:
        fail(f"plan/{a.video}/scenes.json has no scenes")
    fps = float(plan.get("fps") or doc["fps"])
    reg = asset_by_id(load_register(prod))
    lead, gap0, tail0 = float(plan.get("lead_in_seconds", 0.6)), float(plan.get("gap_seconds", 0.35)), float(plan.get("tail_seconds", 1.5))
    preroll = float(plan.get("preroll_seconds", 0.15))
    errors, warnings = [], []
    rows = []
    for i, s in enumerate(scenes):
        text = (s.get("narration") or {}).get(a.language, "") or ""
        onscreen = (s.get("on_screen") or {}).get(a.language, "") or ""
        row = {"id": s["id"], "text": text, "on_screen": onscreen, "pre": lead if i == 0 else preroll,
               "hold": float(s.get("hold_after_seconds", 0.3)), "gap": gap0, "min": float(s.get("min_seconds", 1.0))}
        nf = find_narration(prod, a.video, a.language, s["id"])
        if text.strip() and not nf:
            errors.append(f"{s['id']}: narration text exists for {a.language} but narration/{a.video}/{a.language}/{s['id']}.* is missing")
        if nf:
            f = media_facts(nf)
            dur = float(f["duration"] or 0)
            win = speech_window(nf, dur)
            row.update({"narration": nf, "narr_dur": dur, "window": win})
        else:
            row.update({"narration": None, "narr_dur": 0.0, "window": (0.0, 0.0)})
        row["reading"] = (graphemes(onscreen) / lang["max_cps"] + 0.8) if onscreen else 0.0
        rows.append(row)

    def length(r, gap, hold):
        speech = r["pre"] + r["window"][1] + hold + gap if r["narration"] else 0.0
        return max(speech, r["min"], r["reading"])

    target = video.get("duration_seconds")
    if a.fit == "full" and target:
        # first rebalance scenes without narration (title cards, visual holds) within readable limits
        free = [r for r in rows if not r["narration"]]
        fixed = sum(length(r, r["gap"], r["hold"]) for r in rows if r["narration"]) + tail0
        if free:
            want = (target - fixed) / len(free)
            for r in free:
                lo = max(1.5, r["reading"])
                hi = max(r["min"] * 2.0, 4.0, lo)
                r["min"] = min(hi, max(lo, want))
                r["fit_note"] = f"visual-only scene length set to {r['min']:.2f}s (allowed {lo:.2f}–{hi:.2f}s)"
    tail = tail0
    gaps = [r["gap"] for r in rows]
    holds = [r["hold"] for r in rows]
    if a.fit in ("gaps", "full") and target:
        cur = sum(length(r, g, h) for r, g, h in zip(rows, gaps, holds)) + tail
        lo_g, hi_g, lo_h, hi_h, lo_t, hi_t = 0.15, 1.2, 0.1, 1.0, 0.8, 3.0
        for _ in range(60):  # iterate: lengths are max() of terms, so solve numerically
            delta = target - cur
            if abs(delta) < 0.5 / fps:
                break
            room = [(hi_g - g if delta > 0 else g - lo_g) + (hi_h - h if delta > 0 else h - lo_h) for g, h in zip(gaps, holds)]
            troom = hi_t - tail if delta > 0 else tail - lo_t
            tot = sum(room) + troom
            if tot <= 1e-6:
                break
            k = max(-1.0, min(1.0, delta / tot))
            gaps = [min(hi_g, max(lo_g, g + k * (hi_g - g if delta > 0 else g - lo_g))) for g in gaps]
            holds = [min(hi_h, max(lo_h, h + k * (hi_h - h if delta > 0 else h - lo_h))) for h in holds]
            tail = min(hi_t, max(lo_t, tail + k * troom))
            new = sum(length(r, g, h) for r, g, h in zip(rows, gaps, holds)) + tail
            if abs(new - cur) < 1e-4:
                break
            cur = new
    lengths = [length(r, g, h) for r, g, h in zip(rows, gaps, holds)]
    lengths[-1] += tail
    bounds = [0]
    acc = 0.0
    for L in lengths:
        acc += L
        bounds.append(int(round(acc * fps)))
    total_frames = bounds[-1]
    out_scenes, narration, sfx, tokens = [], [], [], []
    for i, (s, r) in enumerate(zip(scenes, rows)):
        b0, b1 = bounds[i], bounds[i + 1]
        tin = s.get("transition_in") or {"type": "cut", "seconds": 0}
        tnext = (scenes[i + 1].get("transition_in") or {"type": "cut"}) if i + 1 < len(scenes) else {"type": "cut"}
        if tin["type"] not in ("cut", "fade", "fade_from_black", "dip"):
            errors.append(f"{s['id']}: unknown transition {tin['type']!r} (use cut, fade, fade_from_black, dip)")
        ot_in = int(round(float(tin.get("seconds", 0)) * fps)) if tin["type"] == "fade" and i > 0 else 0
        ot_out = int(round(float(tnext.get("seconds", 0)) * fps)) if tnext["type"] == "fade" else 0
        v0 = max(0, b0 - ot_in // 2)
        v1 = min(total_frames, b1 + (ot_out - ot_out // 2))
        vis = dict(s.get("visual") or {})
        media = None
        if vis.get("asset"):
            e = reg.get(vis["asset"])
            if not e:
                errors.append(f"{s['id']}: visual asset {vis['asset']} not in the source register")
            else:
                pr = e.get("probe") or {}
                kind = "image" if (e.get("kind") == "image" or pr.get("still")) else "video"
                rate = float(vis.get("rate", 1.0))
                need = (v1 - v0) / fps * rate
                avail = (pr.get("duration") or 0) - float(vis.get("in", 0))
                if kind == "video" and avail + 1 / fps < need:
                    errors.append(f"{s['id']}: {vis['asset']} has {avail:.2f}s after its in-point but the shot needs {need:.2f}s")
                zoom = vis.get("zoom", 1.0)
                if any(float(z) < 1 for z in (zoom.values() if isinstance(zoom, dict) else [zoom])):
                    errors.append(f"{s['id']}: zoom {zoom} < 1 (zoom is a punch-in on top of the cover scale)")
                auto = (e.get("analysis") or {}).get("focus")
                focus = vis.get("focus") or auto or [0.5, 0.5]
                media = {"asset": vis["asset"], "kind": kind, "path": e.get("local_path"), "in": float(vis.get("in", 0)),
                         "rate": rate, "fit": vis.get("fit", "cover"), "focus": focus, "zoom": zoom,
                         "focus_source": "scene" if vis.get("focus") else ("analysis" if auto else "default centre"),
                         "width": pr.get("width"), "height": pr.get("height")}
        nar = None
        if r["narration"]:
            nfrom = b0 + int(round(r["pre"] * fps))
            nar = {"path": str(r["narration"].relative_to(prod)), "from": nfrom,
                   "durationInFrames": int(math.ceil(r["narr_dur"] * fps)), "seconds": round(r["narr_dur"], 3),
                   "speech": [round(nfrom / fps + r["window"][0], 3), round(nfrom / fps + r["window"][1], 3)]}
            narration.append({"scene": s["id"], **nar})
            words = r["text"].split()
            if words:
                wjson = r["narration"].with_name(f"{s['id']}.words.json")
                times, method = word_times(words, r["window"], wjson)
                for j, (w, (ws, we)) in enumerate(zip(words, times)):
                    tokens.append({"scene": s["id"], "text": (w if j == 0 else " " + w),
                                   "startMs": int(round((nfrom / fps + ws) * 1000)), "endMs": int(round((nfrom / fps + we) * 1000)),
                                   "timestampMs": None, "confidence": None, "method": method})
            speech_end = nfrom + int(round(r["window"][1] * fps))
            if speech_end > b1 and i + 1 < len(scenes):
                warnings.append(f"{s['id']}: speech runs {(speech_end - b1) / fps:.2f}s past the cut into the next scene")
        for x in s.get("sfx", []):
            at = x.get("at", "start")
            base = b0 if at == "start" else (b1 if at == "end" else b0 + int(round(float(at) * fps)))
            e = reg.get(x["asset"])
            sfx.append({"scene": s["id"], "asset": x["asset"], "path": e.get("local_path") if e else None,
                        "from": max(0, base + int(round(float(x.get("offset_seconds", 0)) * fps))),
                        "volume": float(x.get("volume", 0.5))})
        ons = None
        if r["on_screen"]:
            o0 = b0 + int(round(0.3 * fps))
            o1 = b1 - int(round(0.2 * fps))
            ons = {"text": r["on_screen"], "from": o0, "durationInFrames": max(1, o1 - o0)}
        out_scenes.append({"id": s["id"], "cut": b0, "end": b1, "from": v0, "durationInFrames": v1 - v0,
                           "seconds": round((b1 - b0) / fps, 3), "media": media,
                           "move": (vis.get("move") or {"type": "static", "amount": 0}),
                           "transitionIn": {"type": tin["type"] if i > 0 else "cut", "durationInFrames": ot_in if tin["type"] == "fade"
                                            else int(round(float(tin.get("seconds", 0)) * fps))},
                           "transitionOut": ({"type": "dip", "durationInFrames": int(round(float(tnext.get("seconds", 0)) * fps))}
                                             if tnext["type"] == "dip" else None),
                           "onScreen": ons, "onScreenStyle": (s.get("on_screen_style") or "title"), "narration": nar,
                           "fit_note": r.get("fit_note")})
    # captions → cues (SRT) and reading-rate checks
    cues = caption_cues(tokens, lang["max_chars"])
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["startMs"] if i + 1 < len(cues) else c["endMs"] + 2000
        c["endMs"] = min(c["endMs"] + 250, nxt - 40)
        dur = max(0.001, (c["endMs"] - c["startMs"]) / 1000)
        c["cps"] = round(graphemes(c["text"]) / dur, 2)
        if c["cps"] > lang["max_cps"]:
            warnings.append(f"caption {i + 1} reads at {c['cps']} chars/s (limit {lang['max_cps']}): {c['text'][:50]!r}")
    # music ducking keyframes
    music = None
    mplan = plan.get("music")
    if mplan and mplan.get("asset"):
        e = reg.get(mplan["asset"])
        if not e:
            errors.append(f"music asset {mplan['asset']} not in the source register")
        else:
            v = float(mplan.get("volume", 0.3))
            d = float(mplan.get("duck_to", v * 0.35))
            att, rel = int(round(0.25 * fps)), int(round(0.6 * fps))
            wins = []
            for n in narration:
                a0, a1 = int(round(n["speech"][0] * fps)), int(round(n["speech"][1] * fps))
                if wins and a0 - att <= wins[-1][1] + rel:
                    wins[-1][1] = max(wins[-1][1], a1)
                else:
                    wins.append([a0, a1])
            fin = int(round(1.0 * fps))
            fout = max(1, int(round(float(mplan.get("fade_out_seconds", 2.0)) * fps)))
            keys = [(0, 0.0), (fin, v)]
            for a0, a1 in wins:
                keys += [(max(fin + 1, a0 - att), v), (max(fin + 2, a0), d), (max(fin + 3, a1), d), (max(fin + 4, a1 + rel), v)]
            keys.sort()
            mono = []
            for f_, vol in keys:  # strictly increasing frames (interpolate() requires it)
                if mono and f_ <= mono[-1][0]:
                    mono[-1] = (mono[-1][0], vol)
                    continue
                mono.append((f_, vol))
            fstart = max(mono[1][0] + 1 if len(mono) > 1 else 1, total_frames - fout)

            def vol_at(fr: int) -> float:
                for (f0, v0), (f1, v1) in zip(mono, mono[1:]):
                    if f0 <= fr <= f1:
                        return v0 + (v1 - v0) * (fr - f0) / max(1, f1 - f0)
                return mono[-1][1]
            clean = [(f_, round(vol, 4)) for f_, vol in mono if f_ < fstart]
            clean += [(fstart, round(vol_at(fstart), 4)), (max(fstart + 1, total_frames), 0.0)]
            music = {"asset": mplan["asset"], "path": e.get("local_path"), "keyframes": clean,
                     "source_seconds": (e.get("probe") or {}).get("duration")}
            if music["source_seconds"] and music["source_seconds"] < total_frames / fps:
                warnings.append(f"music {mplan['asset']} is {music['source_seconds']:.1f}s, shorter than the video ({total_frames / fps:.1f}s); it will loop")
    total_s = total_frames / fps
    fit = {"target_seconds": target, "actual_seconds": round(total_s, 3),
           "delta_seconds": round(total_s - target, 3) if target else None, "method": a.fit}
    if target and abs(total_s - target) > max(0.5, 0.03 * target):
        warnings.append(f"duration {total_s:.2f}s vs target {target:.2f}s ({total_s - target:+.2f}s): adjust the script for "
                        f"{a.language} or confirm the target; narration is never time-stretched")
    tm = {"version": 1, "video": a.video, "language": a.language, "fps": fps, "durationInFrames": total_frames,
          "seconds": round(total_s, 3), "generated_at": now(), "language_settings": lang, "fit": fit,
          "scenes": out_scenes, "narration": narration, "sfx": sfx, "music": music,
          "captions": [{k: t[k] for k in ("scene", "text", "startMs", "endMs", "timestampMs", "confidence")} for t in tokens],
          "caption_method": sorted({t["method"] for t in tokens}), "caption_cues": cues,
          "errors": errors, "warnings": warnings}
    write_json(prod / "timing" / a.video / f"{a.language}.timing.json", tm)
    srt = "".join(f"{i}\n{srt_time(c['startMs'] / 1000)} --> {srt_time(c['endMs'] / 1000)}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))
    (prod / "captions" / a.video).mkdir(parents=True, exist_ok=True)
    (prod / "captions" / a.video / f"{a.language}.srt").write_text(srt, encoding="utf-8")
    for x in errors:
        print("ERROR  " + x)
    for x in warnings:
        print("WARN   " + x)
    print(json.dumps({"timing": f"timing/{a.video}/{a.language}.timing.json", "seconds": tm["seconds"], "frames": total_frames,
                      "scenes": len(out_scenes), "captions": len(cues), "caption_method": tm["caption_method"],
                      "target_delta": fit["delta_seconds"]}, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


# ------------------------------------------------------------------ props / render


def link_into(src: Path, dst: Path, copy: bool) -> None:
    """Place a file in the motion project's public/ folder. Remotion's bundler copies public/ and does not follow
    symlinks, so use a hard link (a real file, no extra space) and fall back to a copy across filesystems."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if not copy:
        try:
            os.link(src.resolve(), dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def still_working_copy(prod: Path, src: Path, w: int, h: int, scale: float) -> tuple[Path, int, int]:
    """A still far larger than the frame needs is decoded at full size by the renderer's browser: 35-45 MP images at 4K
    logged `EncodingError: The source image cannot be decoded` and once crashed the page. Give the renderer a Lanczos
    copy 2 % larger than the largest size the scene displays (cover/contain × zoom × camera move), so the delivered
    pixels stay native. `scale` is that display scale relative to the source; below 0.75 a copy is made."""
    if scale >= 0.75:
        return src, w, h
    tw = int(math.ceil(w * scale * 1.02 / 2) * 2)
    th = int(round(h * tw / w / 2) * 2)
    ext = src.suffix.lower() if src.suffix.lower() in (".png", ".webp") else ".jpg"
    dst = prod / "assets" / ".work" / f"{src.stem}.{tw}x{th}{'.png' if ext != '.jpg' else '.jpg'}"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(".tmp-" + dst.name)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf",
                            f"scale={tw}:{th}:flags=lanczos", *(["-q:v", "2"] if dst.suffix == ".jpg" else []),
                            "-frames:v", "1", str(tmp)], capture_output=True, text=True)
        if r.returncode or not tmp.exists():
            fail(f"could not make a working copy of {src.name}: {r.stderr.strip()[:200]}")
        tmp.replace(dst)
    return dst, tw, th


def build_props(prod: Path, doc: dict, vid: str, lang: str, fmt: str, res: int, motion: Path, copy: bool) -> Path:
    tp = prod / "timing" / vid / f"{lang}.timing.json"
    if not tp.exists():
        fail(f"{tp} missing — run `production.py timing --video {vid} --language {lang}` first")
    tm = read_json(tp)
    if tm.get("errors"):
        fail(f"timing map has errors: {tm['errors'][:3]}")
    W, H = canvas_size(fmt, res)
    pub = motion / "public"
    if not (motion / "src" / "script-video").is_dir():
        fail(f"{motion} is not a motion project with the ScriptVideo composition (run video_workbench.py init-motion)")

    def place(rel: str | None, sub: str) -> str | None:
        if not rel:
            return None
        src = Path(rel) if Path(rel).is_absolute() else prod / rel
        dst_rel = f"{sub}/{src.name}"
        link_into(src, pub / dst_rel, copy)
        return dst_rel

    langset = tm["language_settings"]
    font_src = None
    if langset.get("font") and langset["font"].get("file"):
        font_src = place(langset["font"]["file"], f"fonts/{lang}")
    unit = min(W, H) / 1080
    vertical = H > W
    scenes = []
    for s in tm["scenes"]:
        m = s.get("media")
        media = {"kind": "none", "src": None, "trimBefore": 0, "playbackRate": 1, "fit": "cover", "focusX": 0.5, "focusY": 0.5,
                 "width": None, "height": None}
        if m:
            fit, zoom = fit_for(m["fit"], fmt), zoom_for(m.get("zoom"), fmt)
            path, mw, mh = m["path"], m.get("width"), m.get("height")
            if m["kind"] == "image" and mw and mh:
                shown = (max if fit == "cover" else min)(W / mw, H / mh) * (zoom if fit == "cover" else 1.0) \
                    * (1 + float((s.get("move") or {}).get("amount", 0) or 0))
                src = Path(path) if Path(path).is_absolute() else prod / path
                wc, mw, mh = still_working_copy(prod, src, mw, mh, shown)
                path = str(wc)
            media = {"kind": m["kind"], "src": place(path, f"media/{vid}"), "trimBefore": int(round(m["in"] * tm["fps"])),
                     "playbackRate": m["rate"], "fit": fit, "focusX": float(m["focus"][0]), "focusY": float(m["focus"][1]),
                     "width": mw, "height": mh, "zoom": zoom}
        scenes.append({"id": s["id"], "from": s["from"], "durationInFrames": s["durationInFrames"], "media": media,
                       "move": s["move"], "transitionIn": s["transitionIn"], "transitionOut": s.get("transitionOut"),
                       "onScreen": s["onScreen"], "onScreenStyle": s.get("onScreenStyle") or "title"})
    narration = [{"id": n["scene"], "src": place(n["path"], f"narration/{vid}/{lang}"), "from": n["from"],
                  "durationInFrames": n["durationInFrames"]} for n in tm["narration"]]
    sfx = [{"src": place(x["path"], f"sfx/{vid}"), "from": x["from"], "volume": x["volume"]} for x in tm["sfx"] if x.get("path")]
    music = None
    if tm.get("music"):
        music = {"src": place(tm["music"]["path"], f"music/{vid}"), "keyframes": tm["music"]["keyframes"],
                 "loop": bool(tm["music"].get("source_seconds") and tm["music"]["source_seconds"] < tm["seconds"])}
    tracks: dict[str, list] = {}
    for c in tm["captions"]:
        tracks.setdefault(c["scene"], []).append({k: c[k] for k in ("text", "startMs", "endMs", "timestampMs", "confidence")})
    props = {
        "canvas": {"width": W, "height": H, "fps": tm["fps"], "durationInFrames": tm["durationInFrames"], "background": "#000000"},
        "format": fmt,
        "language": {"code": lang, "direction": langset.get("direction", "ltr"),
                     "fontFamily": (langset.get("font") or {}).get("family") or "sans-serif", "fontSrc": font_src},
        "scenes": scenes, "narration": narration, "music": music, "sfx": sfx,
        "captionTracks": [{"sceneId": k, "captions": v} for k, v in tracks.items()],
        "captionStyle": {"fontSize": round((58 if vertical else 46) * unit), "bottom": 0.2 if vertical else 0.085,
                         "maxWidth": 0.84 if vertical else 0.8, "combineTokensWithinMilliseconds": 1400 if vertical else 2200,
                         "highlightActiveWord": vertical,
                         # plan/<video>/style.json "caption_backing": dark plate opacity for bright or busy footage
                         "backing": float((read_json(prod / "plan" / vid / "style.json").get("caption_backing") or 0)
                                          if (prod / "plan" / vid / "style.json").exists() else 0)},
        "onScreenStyle": {"fontSize": round((84 if vertical else 72) * unit), "top": 0.14 if vertical else 0.1},
        # per-video look from plan/<video>/style.json ("look"): applied identically to every shot for consistency
        "look": {**{"contrast": 1.0, "saturation": 1.0, "brightness": 1.0, "warmth": 0.0, "vignette": 0.0},
                 **((read_json(prod / "plan" / vid / "style.json").get("look") or {}) if (prod / "plan" / vid / "style.json").exists() else {})},
    }
    out = motion / "props" / f"{vid}-{lang}-{fmt_key(fmt)}-{res}.json"
    write_json(out, props)
    return out


def cmd_props(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    out = build_props(prod, doc, a.video, a.language, a.format, a.resolution, a.motion_project.resolve(), a.copy)
    W, H = canvas_size(a.format, a.resolution)
    print(json.dumps({"props": str(out), "width": W, "height": H,
                      "render": f"npx remotion render src/index.ts ScriptVideo out.mp4 --props={out.relative_to(a.motion_project.resolve())}"},
                     ensure_ascii=False))


def colour_tag_args(video: Path) -> list[str]:
    """Remotion's --color-space=bt709 marks only the matrix; transfer and primaries stay "unknown". When an H.264
    stream has a BT.709 matrix and no transfer/primaries, write all three into the bitstream (VUI) and the container
    while stream-copying. Pixels are untouched (decoded frames are bit-identical)."""
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=codec_name,color_space,color_transfer,color_primaries,color_range", "-of", "json",
                                    str(video)], capture_output=True, text=True).stdout or "{}").get("streams", [{}])
    v = pr[0] if pr else {}
    if v.get("codec_name") != "h264" or v.get("color_space") != "bt709" or \
            (v.get("color_transfer") not in (None, "unknown") and v.get("color_primaries") not in (None, "unknown")):
        return []
    full = v.get("color_range") == "pc"
    return ["-bsf:v", f"h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:"
                      f"video_full_range_flag={1 if full else 0}",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "pc" if full else "tv"]


def master_audio(raw: Path, out: Path, target: dict, max_passes: int = 4, audio: Path | None = None) -> dict:
    """Measured loop: gain → 4x-oversampled true-peak limiter → AAC → re-measure, video stream copied.
    `audio` is a separate (WAV) programme mix; without it the audio of `raw` is used."""
    I_t, TP_t = float(target.get("I", -16)), float(target.get("TP", -1.5))
    src = loudness(audio or raw)
    if not math.isfinite(src["I"]) or src["I"] < -70:
        fail(f"{audio or raw} has no measurable programme loudness (silent?) — refusing to master")
    inputs = ["-i", str(raw)] + (["-i", str(audio)] if audio else [])
    amap = "1:a:0" if audio else "0:a:0"
    gain, ceiling, passes = I_t - src["I"], TP_t - 2.0, []
    tags = colour_tag_args(raw)
    for k in range(max_passes):
        lim = max(0.0625, 10 ** (ceiling / 20))
        af = f"volume={gain:.3f}dB,aresample={SR * 4},alimiter=limit={lim:.5f}:attack=2:release=80:level=false:latency=true,aresample={SR}"
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-map", "0:v:0", "-map", amap,
                            "-c:v", "copy", *tags, "-af", af, "-ar", str(SR), "-c:a", "aac", "-b:a", "256k", "-shortest",
                            "-movflags", "+faststart", str(out)], capture_output=True, text=True)
        if r.returncode:
            fail(f"mastering failed: {r.stderr.strip()[:300]}")
        m = loudness(out)
        ok = abs(m["I"] - I_t) <= 0.5 and m["TP"] <= TP_t
        passes.append({"pass": k + 1, "gain_db": round(gain, 2), "ceiling_dbfs": round(ceiling, 2), "measured": m, "ok": ok})
        if ok:
            break
        if m["TP"] > TP_t:
            ceiling -= (m["TP"] - TP_t) + 0.2
        gain += I_t - m["I"]
    return {"source": src, "target": {"I": I_t, "TP": TP_t}, "passes": passes, "compliant": passes[-1]["ok"],
            "colour_tags": "BT.709 primaries/transfer/matrix written while stream-copying" if tags else "unchanged"}


def narration_offsets(prod: Path, tm: dict, media: Path) -> dict | None:
    """Locate every narration file in a rendered file's audio by cross-correlation; offsets in ms (needs numpy)."""
    try:
        import numpy as np
    except ImportError:
        return None

    def pcm(path: Path) -> "np.ndarray":
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             capture_output=True).stdout
        return np.frombuffer(raw, np.float32)

    mix, fps, out = pcm(media), tm["fps"], {}
    for n in tm["narration"]:
        x = pcm(prod / n["path"])
        at = n["from"] / fps
        a0 = max(0, int((at - 0.3) * 16000))
        seg = mix[a0:a0 + len(x) + 9600]
        if len(seg) < len(x) or not len(x):
            out[n["scene"]] = None
            continue
        size = 1 << int(math.ceil(math.log2(len(seg) + len(x))))
        cc = np.fft.irfft(np.fft.rfft(seg, size) * np.conj(np.fft.rfft(x, size)), size)[: len(seg) - len(x) + 1]
        out[n["scene"]] = round((int(np.argmax(cc)) + a0 - int(round(at * 16000))) / 16, 2)
    return out


def per_format(value, fmt: str, default):
    """`visual.fit` and `visual.zoom` take one value or a per-format dict such as {"9:16": "contain", "16:9": "cover"};
    "default" in the dict covers formats it does not name."""
    if isinstance(value, dict):
        return value.get(fmt, value.get("default", default))
    return default if value is None else value


def zoom_for(zoom, fmt: str) -> float:
    return max(1.0, float(per_format(zoom, fmt, 1.0)))


def fit_for(fit, fmt: str) -> str:
    """cover or contain for this format (letterbox a landscape subject in the vertical cut instead of cropping it away)."""
    fit = per_format(fit, fmt, "cover")
    if fit not in ("cover", "contain"):
        fail(f"fit {fit!r} is not cover or contain")
    return fit


def resolution_class(prod: Path, doc: dict, vid: str, fmt: str, res: int) -> dict:
    """native / upscaled for one deliverable, from the pixel sizes of the raster assets its scenes use. The scale is
    the one the composition applies: cover fills the canvas (max of the ratios) times any punch-in `zoom`, contain fits
    inside it (min), and a camera move enlarges the frame by its amount on top."""
    reg = asset_by_id(load_register(prod))
    plan = scene_plans(prod, doc).get(vid, {})
    W, H = canvas_size(fmt, res)
    worst, per = 0.0, []
    for s in plan.get("scenes", []):
        vis = s.get("visual") or {}
        e = reg.get(vis.get("asset") or "")
        pr = (e or {}).get("probe") or {}
        if pr.get("width"):
            zoom = 1 + float((vis.get("move") or {}).get("amount", 0) or 0)
            fit = fit_for(vis.get("fit", "cover"), fmt)
            ratio = (max if fit == "cover" else min)(W / pr["width"], H / pr["height"])
            if fit == "cover":
                zoom *= zoom_for(vis.get("zoom"), fmt)
            up = ratio * zoom
            worst = max(worst, up)
            per.append({"scene": s["id"], "asset": vis.get("asset"), "source": f"{pr['width']}x{pr['height']}", "fit": fit,
                        "upscale": round(up, 3)})
    label = f"{'4K' if res >= 2160 else f'{res}p'}"
    verdict = (f"native {label}" if worst <= 1.01 else f"upscaled {label} x{worst:.2f}") if per else f"{label} (no raster assets)"
    return {"canvas": f"{W}x{H}", "verdict": verdict, "max_upscale": round(worst, 3), "scenes": per}


def framing_check(prod: Path, doc: dict, vid: str, fmt: str) -> tuple[bool, dict]:
    """Scenes whose cover crop for this format cuts the subject (analyze_media.py crop_check). A scene passes when the
    crop keeps the subject, uses contain, or a person positioned/reviewed it: an explicit `visual.focus`, or
    `visual.crop_reviewed` (true or per format, e.g. {"9:16": true}) recorded after looking at the review stills."""
    reg = asset_by_id(load_register(prod))
    cut, reviewed, unknown = [], [], []
    for s in scene_plans(prod, doc).get(vid, {}).get("scenes", []):
        vis = s.get("visual") or {}
        e = reg.get(vis.get("asset") or "")
        if not e or e.get("kind") not in ("image", "video") or fit_for(vis.get("fit", "cover"), fmt) != "cover":
            continue
        cc = ((e.get("analysis") or {}).get("crop_check") or {}).get(fmt)
        if cc is None:
            unknown.append(s["id"])
        elif not cc.get("subject_inside"):
            (reviewed if vis.get("focus") or per_format(vis.get("crop_reviewed"), fmt, False) else cut).append(s["id"])
    return not cut, {"subject_cut": cut, "positioned_or_reviewed": reviewed, "not_analysed": unknown,
                     "method": "saliency/face subject box vs the focus-weighted cover window (analyze_media.py)"}


def qc_deliverable(prod: Path, doc: dict, vid: str, lang: str, fmt: str, res: int, video: Path) -> dict:
    import qc
    tm = read_json(prod / "timing" / vid / f"{lang}.timing.json")
    langset = tm["language_settings"]
    font = None
    if langset.get("font") and langset["font"].get("file"):
        f = Path(langset["font"]["file"])
        font = f if f.is_absolute() else prod / f
    texts = [c["text"] for c in tm["captions"]] + [s["onScreen"]["text"] for s in tm["scenes"] if s.get("onScreen")]
    still_dir = prod / "review" / "qc" / f"{vid}-{lang}-{fmt_key(fmt)}-{res}"
    rep = qc.run_qc(video, tm, prod / "captions" / vid / f"{lang}.srt", font, texts, tm["fps"],
                    resolution_class(prod, doc, vid, fmt, res), still_dir)
    ok, detail = framing_check(prod, doc, vid, fmt)
    rep["checks"]["subject_in_frame"] = {"passed": ok, "detail": detail}
    rep["passed"] = all(c["passed"] for c in rep["checks"].values())
    rep["method"] = qc.__doc__.strip().splitlines()[0]
    return rep


def cmd_qc(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    name = f"{a.video}-{a.language}-{fmt_key(a.format)}-{a.resolution}"
    video = Path(a.file).resolve() if a.file else prod / "deliverables" / a.video / a.language / f"{name}.mp4"
    if not video.exists():
        fail(f"{video} does not exist")
    rep = qc_deliverable(prod, doc, a.video, a.language, a.format, a.resolution, video)
    tm = read_json(prod / "timing" / a.video / f"{a.language}.timing.json")
    offs = narration_offsets(prod, tm, video)
    rep["checks"]["narration_sync_10ms"] = {"passed": offs is not None and all(v is not None and abs(v) <= 10 for v in offs.values()),
                                            "detail": offs if offs is not None else "numpy unavailable — not measured"}
    rep["passed"] = all(c["passed"] for c in rep["checks"].values())
    write_json(video.with_suffix(".qc.json"), rep)
    for k, c in rep["checks"].items():
        print(f"{'PASS' if c['passed'] else 'FAIL'}  {k}: {json.dumps(c['detail'], ensure_ascii=False)[:160]}")
    print(f"QC {'passed' if rep['passed'] else 'FAILED'} → {video.with_suffix('.qc.json')}")
    raise SystemExit(0 if rep["passed"] else 1)


def gate(prod: Path, doc: dict, vid: str, lang: str) -> list[str]:
    """Licence/provenance gate for one (video, language): every asset and narration file must be registered, present,
    unchanged, and licensed for this production's use. Commercial productions block on non-commercial, unverified,
    share-alike-without-approval, no-derivatives, or unpaid-approval assets."""
    reg = load_register(prod)
    approvals = load_approvals(prod)
    entries, problems = deliverable_assets(prod, doc, reg, vid, lang)
    for e in entries:
        problems += licence_blockers(e, doc, approvals)
        lp = e.get("local_path")
        fp = prod / lp if lp and not Path(lp).is_absolute() else (Path(lp) if lp else None)
        if not fp or not fp.exists():
            problems.append(f"{e['id']}: file missing ({lp})")
        elif e.get("sha256") and sha256(fp) != e["sha256"]:
            problems.append(f"{e['id']}: file changed since it was registered")
    return problems


def cmd_render(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    motion = a.motion_project.resolve()
    entry = next((d for d in doc["deliverables"] if d["video"] == a.video and d["language"] == a.language
                  and d["format"] == a.format and d["resolution"] == a.resolution), None)
    if entry is None:
        fail(f"{a.video}/{a.language}/{a.format}/{a.resolution} is not in this production's deliverable matrix")
    blockers = gate(prod, doc, a.video, a.language)
    if blockers:
        update_deliverable(prod, entry["path"], {"status": "blocked", "blocked_at": now(), "blockers": blockers})
        print("BLOCKED — this deliverable is not rendered:")
        for b in blockers:
            print("  - " + b)
        raise SystemExit(3)
    # recorded before rendering: if the render is interrupted, status shows a render that never completed
    update_deliverable(prod, entry["path"], {"status": "rendering", "render_started_at": now()}, drop=("blockers", "blocked_at"))
    props = build_props(prod, doc, a.video, a.language, a.format, a.resolution, motion, a.copy)
    pr = read_json(props)
    W, H, fps = pr["canvas"]["width"], pr["canvas"]["height"], pr["canvas"]["fps"]
    frames = pr["canvas"]["durationInFrames"]
    name = f"{a.video}-{a.language}-{fmt_key(a.format)}-{a.resolution}"
    dest = prod / "deliverables" / a.video / a.language / f"{name}.mp4"
    work = prod / "review" / "render" / name
    work.mkdir(parents=True, exist_ok=True)
    raw = work / f"{name}.remotion.mp4"
    raw_audio = work / f"{name}.remotion.wav"
    env = dict(os.environ)
    if (env.get("HTTPS_PROXY") or env.get("https_proxy")) and "NODE_USE_ENV_PROXY" not in env:
        env["NODE_USE_ENV_PROXY"] = "1"  # let Node (Remotion's browser download) use the environment's proxy
    common = [f"--props={props}"]
    if a.concurrency:
        common.append(f"--concurrency={a.concurrency}")
    if env.get("REMOTION_BROWSER_EXECUTABLE"):
        common.append(f"--browser-executable={env['REMOTION_BROWSER_EXECUTABLE']}")
    if env.get("REMOTION_LICENSE_KEY"):
        common.append(f"--license-key={env['REMOTION_LICENSE_KEY']}")
    # Picture and sound are rendered separately: Remotion's AAC-in-MP4 output measured 42.7 ms (2048 samples) late
    # against its own WAV render; FFmpeg's AAC encode during mastering signals its priming, so sync stays exact.
    for cmd, out in (
        (["npx", "remotion", "render", "src/index.ts", "ScriptVideo", str(raw), "--codec=h264", "--muted",
          "--pixel-format=yuv420p", "--color-space=bt709", f"--crf={a.crf}", *common], raw),
        (["npx", "remotion", "render", "src/index.ts", "ScriptVideo", str(raw_audio), "--codec=wav", *common], raw_audio),
    ):
        print("$ " + " ".join(cmd), flush=True)
        r = subprocess.run(cmd, cwd=motion, env=env)
        if r.returncode or not out.exists():
            fail(f"Remotion render failed (exit {r.returncode}): {out.name}")
    tmp = dest.with_name(dest.stem + ".candidate.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    mastering = master_audio(raw, tmp, doc.get("loudness", {}), audio=raw_audio)
    tm = read_json(prod / "timing" / a.video / f"{a.language}.timing.json")
    offsets = narration_offsets(prod, tm, tmp)
    sync_ok = offsets is None or all(v is not None and abs(v) <= 10 for v in offsets.values())
    print(f"narration sync (ms): {offsets if offsets is not None else 'not measured (numpy unavailable)'}")
    report = dest.with_suffix(".validation.json")
    vcmd = [sys.executable, str(WORKBENCH), "validate", str(tmp), "--report", str(work / "validation.candidate.json"),
            "--width", str(W), "--height", str(H), "--fps", str(fps), "--duration", f"{frames / fps:.3f}",
            "--audio-rate", str(SR), "--lufs", str(doc.get("loudness", {}).get("I", -16)),
            "--true-peak", str(doc.get("loudness", {}).get("TP", -1.5)), "--pixel-format", "yuv420p"]
    v = subprocess.run(vcmd)
    vr = read_json(work / "validation.candidate.json")
    vr.setdefault("checks", {})["narration_sync_10ms"] = sync_ok
    qrep = qc_deliverable(prod, doc, a.video, a.language, a.format, a.resolution, tmp)
    for k, c in qrep["checks"].items():
        vr["checks"][f"qc_{k}"] = c["passed"]
    vr["qc"] = qrep
    for k, c in qrep["checks"].items():
        print(f"{'PASS' if c['passed'] else 'FAIL'}  qc_{k}: {json.dumps(c['detail'], ensure_ascii=False)[:140]}")
    vr["passed"] = bool(vr.get("passed")) and sync_ok and qrep["passed"]
    if vr.get("passed"):
        tmp.replace(dest)
        vr["source"] = str(dest)
        vr["mastering"] = mastering
        vr["narration_offsets_ms"] = offsets
        write_json(report, vr)
        update_deliverable(prod, entry["path"], {
            "status": "validated", "sha256": vr["sha256"], "validated_at": now(),
            "resolution_class": qrep["checks"].get("resolution_class", {}).get("detail", {}).get("verdict")},
            drop=("failed_at", "candidate", "failed_checks"))
        print(f"validated deliverable: {dest}")
        if not getattr(a, "keep_intermediates", False):  # the separate picture/WAV renders are now inside the deliverable
            for f in (raw, raw_audio):
                f.unlink(missing_ok=True)
        raise SystemExit(0)
    update_deliverable(prod, entry["path"], {"status": "failed", "failed_at": now(), "candidate": str(tmp.relative_to(prod)),
                                             "failed_checks": [k for k, ok in vr.get("checks", {}).items() if not ok]})
    write_json(work / "validation.candidate.json", vr)
    print(f"validation FAILED — candidate kept at {tmp}; report {work / 'validation.candidate.json'}")
    raise SystemExit(1)


# ------------------------------------------------------------------ feasibility / status


def cmd_feasibility(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    rows = []
    for vid, plan in scene_plans(prod, doc).items():
        if a.video and vid != a.video:
            continue
        for fmt in doc["formats"]:
            for res in doc["resolutions"]:
                rc = resolution_class(prod, doc, vid, fmt, res)
                verdict = ("native" if rc["max_upscale"] <= 1.01 else f"upscaled x{rc['max_upscale']:.2f}") if rc["scenes"] \
                    else "no raster assets (resolution-independent)"
                rows.append({"video": vid, "format": fmt, "resolution": res, "canvas": rc["canvas"], "verdict": verdict,
                             "max_upscale": rc["max_upscale"], "scenes": rc["scenes"]})
    fp = prod / "reports" / "feasibility.json"
    if a.video and fp.exists():  # keep the other videos' rows
        rows = [r for r in read_json(fp).get("rows", []) if r["video"] != a.video] + rows
    write_json(fp, {"checked_at": now(), "rows": rows})
    for r in rows:
        if not a.video or r["video"] == a.video:
            print(f"{r['video']} {r['format']:>5} {r['resolution']:>5}p {r['canvas']:>10}  {r['verdict']}")


def cmd_status(a) -> None:
    prod = a.production.resolve()
    doc = load_prod(prod)
    rows, complete, gates = [], True, {}
    for d in doc["deliverables"]:
        rcl = resolution_class(prod, doc, d["video"], d["format"], d["resolution"])
        p = prod / d["path"]
        rep = p.with_suffix(".validation.json")
        state = "missing"
        detail = ""
        if not p.exists():
            # blockers are re-evaluated now, never repeated from an earlier render attempt
            key = (d["video"], d["language"])
            if key not in gates:
                gates[key] = gate(prod, doc, *key)
            if gates[key]:
                state, detail = "blocked", "; ".join(gates[key][:2])
            elif d.get("status") == "rendering":
                detail = f"render started {d.get('render_started_at')} never completed (interrupted or crashed)"
            elif d.get("status") == "failed":
                state, detail = "failed", f"candidate {d.get('candidate')} failed: {', '.join(d.get('failed_checks', [])[:4])}"
        if p.exists():
            state = "unvalidated"
            if rep.exists():
                vr = read_json(rep)
                digest = sha256(p)
                if not vr.get("passed"):
                    state, detail = "failed", ", ".join(k for k, ok in vr.get("checks", {}).items() if not ok)
                elif vr.get("sha256") != digest:
                    state, detail = "stale", "file changed after validation"
                else:
                    state = "validated"
                    props = Path(str(a.motion_project or "")) / "props" / (p.stem + ".json") if a.motion_project else None
                    if props and props.exists() and props.stat().st_mtime > p.stat().st_mtime:
                        state, detail = "stale", "props newer than the render"
                    if state == "validated" and rcl["verdict"].startswith("upscaled") and not d.get("upscale_accepted"):
                        state, detail = "upscaled", f"{rcl['verdict']} — needs the user's acceptance (set upscale_accepted)"
        complete &= state == "validated"
        rows.append({**d, "state": state, "detail": detail, "resolution_class": rcl["verdict"]})
    write_json(prod / "reports" / "status.json", {"checked_at": now(), "deliverables": rows, "complete": complete})
    for r in rows:
        print(f"{r['state']:>11}  {r['path']:<52} {r['resolution_class']:<22}" + (f"  ({r['detail']})" if r["detail"] else ""))
    n = sum(r["state"] == "validated" for r in rows)
    print(f"{n}/{len(rows)} deliverables validated")
    raise SystemExit(0 if complete else 1)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="create a production with its deliverable matrix and registers")
    p.add_argument("production", type=Path)
    p.add_argument("--videos", type=int, default=1)
    p.add_argument("--video-ids", help="comma-separated ids instead of v01..vNN")
    p.add_argument("--languages", required=True, help="comma-separated language codes for every video")
    p.add_argument("--video-languages", help="per-video override: 'v01=en,te;v02=en'")
    p.add_argument("--durations", help="target seconds: one value or one per video")
    p.add_argument("--formats", default="9:16,16:9")
    p.add_argument("--resolutions", default="1080,2160")
    p.add_argument("--fps", type=float, default=30)
    p.add_argument("--commercial", action="store_true", help="deliverables are for commercial use")
    p = sub.add_parser("register-add", help="record an obtained or generated asset with measured facts")
    p.add_argument("production", type=Path)
    p.add_argument("--id", required=True); p.add_argument("--kind", required=True, choices=ASSET_KINDS)
    p.add_argument("--file"); p.add_argument("--title", required=True); p.add_argument("--creator")
    p.add_argument("--source-url", required=True, help="item page URL, or 'generated' / 'user-supplied'")
    p.add_argument("--download-url"); p.add_argument("--licence", required=True); p.add_argument("--licence-url")
    p.add_argument("--commercial-use", choices=["yes", "no", "conditional", "unknown"], default="unknown")
    p.add_argument("--attribution-required", choices=["yes", "no"], default="no"); p.add_argument("--attribution")
    p.add_argument("--restrictions"); p.add_argument("--evidence", help="what on the item page shows the licence")
    p.add_argument("--checked-at"); p.add_argument("--status", choices=STATUSES, default="downloaded")
    p.add_argument("--cost"); p.add_argument("--approval"); p.add_argument("--notes")
    p = sub.add_parser("audit", help="check the source register against scenes, files, licences and approvals")
    p.add_argument("production", type=Path); p.add_argument("--credits")
    p = sub.add_parser("timing", help="build a frame-accurate timing map for one video and language")
    p.add_argument("production", type=Path); p.add_argument("--video", required=True); p.add_argument("--language", required=True)
    p.add_argument("--fit", choices=["none", "gaps", "full"], default="none",
                   help="gaps: pauses/holds/tail; full: also the length of scenes without narration")
    p.add_argument("--max-chars", type=int); p.add_argument("--max-cps", type=float)
    for name, hlp in (("props", "write Remotion props for ScriptVideo"), ("render", "render, master, validate one deliverable")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("production", type=Path); p.add_argument("--video", required=True); p.add_argument("--language", required=True)
        p.add_argument("--format", required=True, choices=sorted(FORMATS)); p.add_argument("--resolution", type=int, default=1080)
        p.add_argument("--motion-project", type=Path, required=True)
        p.add_argument("--copy", action="store_true", help="copy media into public/ instead of hard-linking")
        if name == "render":
            p.add_argument("--crf", type=int, default=18); p.add_argument("--concurrency", type=int)
            p.add_argument("--keep-intermediates", action="store_true",
                           help="keep the separate Remotion picture and WAV renders after a validated master")
    p = sub.add_parser("feasibility", help="upscale needed per format/resolution (4K feasibility)")
    p.add_argument("production", type=Path); p.add_argument("--video")
    p = sub.add_parser("status", help="honest state of every deliverable")
    p.add_argument("production", type=Path); p.add_argument("--motion-project", type=Path)
    p = sub.add_parser("qc", help="quality-check an encoded deliverable against its timing map")
    p.add_argument("production", type=Path); p.add_argument("--video", required=True); p.add_argument("--language", required=True)
    p.add_argument("--format", required=True, choices=sorted(FORMATS)); p.add_argument("--resolution", type=int, default=1080)
    p.add_argument("--file", help="check this file instead of the deliverable path")
    p = sub.add_parser("discover", help="search live providers, rank candidates, record them in the register")
    p.add_argument("production", type=Path); p.add_argument("--query", required=True)
    p.add_argument("--kind", required=True, choices=["image", "video", "audio", "music", "sfx"])
    p.add_argument("--providers", default="openverse:wikimedia,openverse,wikimedia,nasa,met,loc,pexels,pixabay,mixkit")
    p.add_argument("--limit", type=int, default=6, help="results per provider")
    p.add_argument("--scene", help="scene id the search is for (recorded with the candidates)")
    p.add_argument("--show", type=int, default=10)
    p.add_argument("--thumbs", action="store_true", help="save provider thumbnails and a labelled contact sheet")
    p.add_argument("--commercial-only", dest="commercial_only", action="store_true", default=None)
    p.add_argument("--any-licence", dest="commercial_only", action="store_false")
    p = sub.add_parser("fetch", help="re-verify the licence and download one discovered candidate")
    p.add_argument("production", type=Path); p.add_argument("--id", required=True); p.add_argument("--force", action="store_true")
    p.add_argument("--max-wait", type=float, default=90, help="longest Retry-After (s) to wait out on HTTP 429/503")
    p = sub.add_parser("source-check", help="fetch cited research URLs and record what was found")
    p.add_argument("production", type=Path); p.add_argument("urls", nargs="+"); p.add_argument("--note")
    return ap


def main() -> None:
    a = parser().parse_args()
    import discovery
    {"init": cmd_init, "register-add": cmd_register_add, "audit": cmd_audit, "timing": cmd_timing, "props": cmd_props,
     "render": cmd_render, "feasibility": cmd_feasibility, "status": cmd_status, "discover": discovery.cmd_discover,
     "fetch": discovery.cmd_fetch, "source-check": discovery.cmd_source_check, "qc": cmd_qc}[a.command](a)


if __name__ == "__main__":
    main()
