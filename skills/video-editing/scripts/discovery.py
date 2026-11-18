#!/usr/bin/env python3
"""Asset discovery, fetching, and source checks for production.py (`discover`, `fetch`, `source-check`).

discover  searches live providers, normalizes licences, ranks candidates for the production's formats and licence
          needs, and records them in the source register as `candidate` (nothing is downloaded).
fetch     re-verifies the licence with the provider, downloads one candidate atomically, verifies it decodes,
          makes an H.264 working copy when the original codec is not one Remotion plays reliably, and records
          measured facts. Failures are recorded on the entry and never reported as success.
source-check  fetches cited research URLs and records status, final URL, title, and a content hash.

Every network request is logged to research/external-actions.jsonl with secret parameters redacted.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import providers as PV  # noqa: E402


def _P():
    import production  # lazy: production imports this module for its CLI
    return production


def client_for(prod: Path, max_wait: float = 90.0) -> PV.Client:
    return PV.Client(prod / "research" / "cache", prod / "research" / "external-actions.jsonl", max_wait=max_wait)


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]{3,}", (text or "").lower())}


def targets(doc: dict) -> list[tuple[str, int, int, int]]:
    P = _P()
    return [(f, r, *P.canvas_size(f, r)) for f in doc["formats"] for r in doc["resolutions"]]


def resolution_report(w: int | None, h: int | None, doc: dict) -> dict:
    if not w or not h:
        return {"known": False}
    rep = {"known": True}
    for f, r, W, H in targets(doc):
        rep[f"{f}@{r}"] = round(max(W / w, H / h), 3)
    rep["native_1080_all_formats"] = all(v <= 1.0 for k, v in rep.items() if k.endswith("@1080"))
    rep["native_2160_all_formats"] = all(v <= 1.0 for k, v in rep.items() if k.endswith("@2160")) if any(
        k.endswith("@2160") for k in rep) else None
    return rep


def score(c: dict, query: str, doc: dict) -> tuple[float, list[str]]:
    why = []
    q = tokens(query)
    text = " ".join([c.get("title") or "", " ".join(c.get("tags") or []), c.get("description") or ""])
    rel = len(q & tokens(text)) / max(1, len(q))
    why.append(f"relevance {rel:.2f}")
    res = resolution_report(c.get("width"), c.get("height"), doc)
    if res.get("known"):
        ups = [v for k, v in res.items() if "@" in k]
        r = min(1.0, 1 / max(ups)) if ups else 0.5
        why.append("native 4K" if res.get("native_2160_all_formats") else (
            "native 1080p" if res.get("native_1080_all_formats") else f"needs upscale x{max(ups):.2f}"))
    else:
        r = 0.4
        why.append("resolution unknown until fetch")
    lic = c["licence"]["commercial_use"]
    lscore = {"yes": 1.0, "conditional": 0.3, "unknown": 0.0, "no": 0.0}[lic]
    why.append(f"licence {c['licence']['name']} (commercial: {lic})")
    return round(0.5 * rel + 0.3 * r + 0.2 * lscore, 3), why


def cand_id(c: dict) -> str:
    return "c" + hashlib.sha1(f"{c['provider']}:{c['provider_id']}".encode()).hexdigest()[:7]


def cmd_discover(a) -> None:
    P = _P()
    prod = a.production.resolve()
    doc = P.load_prod(prod)
    commercial_only = doc.get("commercial", False) if a.commercial_only is None else a.commercial_only
    client = client_for(prod)
    providers = [x.strip() for x in a.providers.split(",") if x.strip()]
    found, statuses = [], {}
    for prov in providers:
        try:
            res = PV.search(client, prov, a.query, a.kind, limit=a.limit, commercial_only=commercial_only)
            errs = [r for r in res if "error" in r]
            res = [r for r in res if "error" not in r]
            statuses[prov] = {"status": "ok", "results": len(res), "item_errors": [e["error"] for e in errs]}
            found += res
        except PV.Unavailable as e:
            statuses[prov] = {"status": "unavailable", "reason": str(e)}
    reg = P.load_register(prod)
    by_id = {x["id"]: x for x in reg["assets"]}
    rows, rejected, changed_entries = [], [], []
    for c in found:
        s, why = score(c, a.query, doc)
        cid = cand_id(c)
        if doc.get("commercial") and c["licence"]["commercial_use"] in ("no", "unknown"):
            rejected.append({"id": cid, "title": c["title"], "reason": f"licence {c['licence']['name']} not usable commercially",
                             "source_url": c["source_url"]})
            continue
        rows.append((s, cid, c, why))
        prev = by_id.get(cid)
        if prev and prev.get("status") in ("downloaded", "used", "approved"):
            continue  # never downgrade an obtained asset back to candidate
        entry = {"id": cid, "kind": c["kind"], "title": c["title"], "creator": c.get("creator"),
                 "source_url": c["source_url"], "download_url": PV.redact(c["download_url"]) if c.get("download_url") else None,
                 "licence": c["licence"], "evidence": {"note": c.get("evidence"), "checked_at": c["retrieved_at"]},
                 "status": "candidate", "discovery": {
                     "provider": c["provider"], "provider_id": c["provider_id"], "query": a.query, "scene": a.scene,
                     "score": s, "reasons": why, "renditions": [{**r, "url": PV.redact(r["url"])} for r in c["renditions"]],
                     "width": c.get("width"), "height": c.get("height"), "duration": c.get("duration"),
                     "detail_url": c.get("detail_url"), "manifest": c.get("manifest"), "thumbnail": c.get("thumbnail"),
                     "resolution": resolution_report(c.get("width"), c.get("height"), doc)},
                 "recorded_at": P.now()}
        by_id[cid] = entry
        changed_entries.append(entry)
    P.save_register_entries(prod, changed_entries)
    rows.sort(key=lambda r: -r[0])
    slug = re.sub(r"[^a-z0-9]+", "-", a.query.lower()).strip("-")[:40]
    rep = {"query": a.query, "kind": a.kind, "scene": a.scene, "commercial_only": commercial_only, "providers": statuses,
           "ranked": [{"id": cid, "score": s, "title": c["title"], "provider": c["provider"], "licence": c["licence"]["name"],
                       "commercial_use": c["licence"]["commercial_use"], "size": f"{c.get('width')}x{c.get('height')}",
                       "duration": c.get("duration"), "source_url": c["source_url"], "reasons": why} for s, cid, c, why in rows],
           "rejected": rejected, "searched_at": P.now()}
    P.write_json(prod / "research" / "discovery" / f"{P.now().replace(':', '')}-{a.kind}-{slug}.json", rep)
    if a.thumbs:
        sheet = contact_sheet(prod, client, [(cid, c) for _, cid, c, _ in rows[: a.show]], slug)
        if sheet:
            print(f"contact sheet: {sheet}")
    for prov, st in statuses.items():
        print(f"{prov:20} {st['status']}" + (f" ({st['results']} results)" if st["status"] == "ok" else f": {st['reason']}"))
    for s, cid, c, why in rows[: a.show]:
        print(f"{cid}  {s:.2f}  {c['provider']:9} {c['title'][:48]:48} {why[1]:24} {c['licence']['name'][:24]}")
    if rejected:
        print(f"{len(rejected)} result(s) rejected for licence reasons (see the discovery report)")
    if not rows:
        raise SystemExit(1)


WIKIMEDIA_STEPS = [960, 1280, 1920, 3840]  # standard widths ≥ 960: https://www.mediawiki.org/wiki/Common_thumbnail_sizes


def commons_thumb(url: str | None, width: int = 500) -> str | None:
    """Wikimedia Commons thumbnail at a standard width (arbitrary widths are refused with HTTP 400)."""
    m = re.match(r"https://upload\.wikimedia\.org/wikipedia/commons/(\w/\w\w)/([^?]+)", url or "")
    if not m:
        return None
    name = m.group(2)
    suffix = ".jpg" if name.lower().endswith((".tif", ".tiff")) else ""
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{m.group(1)}/{name}/{width}px-{name}{suffix}"


def contact_sheet(prod: Path, client: PV.Client, items: list, slug: str) -> Path | None:
    """Download each candidate's provider thumbnail and tile them with their ids for visual comparison."""
    tdir = prod / "research" / "thumbs"
    tdir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for cid, c in items:
        urls = [u for u in (c.get("thumbnail"), commons_thumb(c.get("download_url"))) if u]
        dst = tdir / f"{cid}.jpg"
        for url in ([] if dst.exists() else urls):
            try:
                client.download(url, dst, c["provider"], retries=2)
                break
            except PV.Unavailable:
                continue
            finally:
                __import__("time").sleep(1.0)  # pace thumbnail requests (Wikimedia rate-limits shared egress)
        if not dst.exists():
            continue
        tile = tdir / f"{cid}.tile.png"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dst), "-vf",
                            "scale=320:320:force_original_aspect_ratio=decrease,pad=320:340:(ow-iw)/2:20:color=black,"
                            f"drawtext=text='{cid}':fontcolor=yellow:fontsize=18:x=6:y=1", "-frames:v", "1", str(tile)],
                           capture_output=True)
        if r.returncode == 0:
            tiles.append(tile)
    if not tiles:
        return None
    out = tdir / f"sheet-{slug}.png"
    cols = min(5, len(tiles))
    layout = "|".join(f"{(i % cols) * 320}_{(i // cols) * 340}" for i in range(len(tiles)))
    args = sum((["-i", str(t)] for t in tiles), [])
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex",
                        "".join(f"[{i}]" for i in range(len(tiles))) + f"xstack=inputs={len(tiles)}:layout={layout}:fill=black"
                        if len(tiles) > 1 else "null", "-frames:v", "1", str(out)], capture_output=True)
    return out if r.returncode == 0 else None


def choose_rendition(c: dict, doc: dict) -> list[dict]:
    """Smallest rendition that needs no upscale for the largest deliverable; otherwise the largest available."""
    rends = [r for r in c["discovery"].get("renditions") or [] if r.get("url")]
    tg = targets(doc)
    def ok(r):
        return r.get("width") and r.get("height") and all(max(W / r["width"], H / r["height"]) <= 1.0 for _, _, W, H in tg)
    natives = sorted([r for r in rends if ok(r)], key=lambda r: r["width"] * r["height"])
    rest = sorted([r for r in rends if not ok(r)], key=lambda r: -((r.get("width") or 0) * (r.get("height") or 0)))
    return natives[:1] + rest + natives[1:]


def mixkit_download_urls(client: PV.Client, vid: str) -> list[str]:
    urls = []
    for res in ("2160", "1080", "720"):
        try:
            page = client.get(f"https://mixkit.co/free-stock-video/download/{vid}/?context=sidebar&type={res}p", "mixkit",
                              action="detail", use_cache=False).decode("utf-8", "replace")
            urls += [u for u in dict.fromkeys(re.findall(r"https://assets\.mixkit\.co/[a-z0-9]{20,40}(?=[\"'\s<])", page))]
        except PV.Unavailable:
            continue
    return urls


def verify_media(path: Path, kind: str) -> tuple[bool, str, dict]:
    P = _P()
    try:
        facts = P.media_facts(path)
    except SystemExit as e:
        return False, str(e), {}
    if kind in ("video", "image") and not facts.get("width"):
        return False, "no video/image stream", facts
    if kind in ("audio", "music", "sfx", "voice") and not facts.get("audio_codec"):
        return False, "no audio stream", facts
    probe_len = ["-t", "3"] if kind == "video" else (["-frames:v", "1"] if kind == "image" else ["-t", "5"])
    r = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), *probe_len, "-f", "null", "-"],
                       capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        return False, f"decode error: {r.stderr.strip()[:200]}", facts
    return True, "", facts


def working_copy(src: Path, facts: dict) -> Path | None:
    """H.264/yuv420p copy for codecs Remotion's browser decoding may not handle (VP8/Theora/ProRes/HEVC…)."""
    if facts.get("video_codec") in ("h264",) and src.suffix.lower() in (".mp4", ".mov", ".m4v"):
        return None
    dst = src.with_suffix(".work.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-c:v", "libx264", "-crf", "16",
                        "-preset", "medium", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(dst)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        dst.unlink(missing_ok=True)
        raise PV.Unavailable(f"working copy failed: {r.stderr.strip()[:200]}")
    return dst


def cmd_fetch(a) -> None:
    P = _P()
    prod = a.production.resolve()
    doc = P.load_prod(prod)
    reg = P.load_register(prod)
    by_id = {x["id"]: x for x in reg["assets"]}
    e = by_id.get(a.id)
    if not e:
        P.fail(f"{a.id} is not in the source register")
    if e.get("status") in ("downloaded", "used") and not a.force:
        print(f"{a.id} already downloaded: {e.get('local_path')}")
        return
    if "discovery" not in e:
        P.fail(f"{a.id} was not found by `discover`; use register-add for files obtained another way")
    client = client_for(prod, a.max_wait)

    def record_failure(reason: str) -> None:
        e.setdefault("download_attempts", []).append({"at": P.now(), "error": reason})
        e["download_status"] = "failed"
        P.save_register_entries(prod, [e])
        print(f"FETCH FAILED {a.id}: {reason}")
        raise SystemExit(1)

    disc = e["discovery"]
    c = {"provider": disc["provider"], "provider_id": disc["provider_id"], "kind": e["kind"], "source_url": e["source_url"],
         "detail_url": disc.get("detail_url"), "licence": e["licence"]}
    try:
        lic = PV.reverify(client, c)
    except PV.Unavailable as ex:
        record_failure(f"licence re-verification failed: {ex}")
    changed = lic.get("commercial_use") != e["licence"].get("commercial_use") or lic.get("name") != e["licence"].get("name")
    if doc.get("commercial") and lic["commercial_use"] in ("no", "unknown"):
        e["licence"] = lic
        record_failure(f"licence is now {lic['name']} (commercial use: {lic['commercial_use']}) — not usable in this commercial production")
    rends = []
    if disc["provider"] == "nasa":
        try:
            rends = PV.nasa_renditions(client, {"manifest": disc["manifest"]})
        except PV.Unavailable as ex:
            record_failure(str(ex))
    else:
        rends = choose_rendition(e, doc)
    urls = [r["url"] for r in rends]
    # Wikimedia asks automated clients to use standard thumbnail widths instead of originals (originals from
    # shared egress are throttled with HTTP 429). Use the smallest standard width that needs no upscaling for the
    # production's largest deliverable; fall back to the original only when that is larger than any step.
    commons = [u for u in urls if "upload.wikimedia.org/wikipedia/commons/" in u and "/thumb/" not in u]
    if commons and disc.get("width") and disc.get("height"):
        w0, h0 = disc["width"], disc["height"]
        need = max(max(W, H * w0 / h0) for _, _, W, H in targets(doc))
        step = next((st for st in WIKIMEDIA_STEPS if st >= need), None)
        if step and step < w0:
            urls = [commons_thumb(commons[0], step)] + urls
            e["discovery"]["rendition_policy"] = f"Commons standard thumbnail {step}px (needed {need:.0f}px of {w0}px)"
        else:
            # no standard width is large enough: try the original, then each smaller standard thumbnail in turn
            # (when originals are throttled the result is smaller; resolution_class reports the upscale honestly)
            steps = sorted((st for st in WIKIMEDIA_STEPS if st < w0), reverse=True)
            urls = urls + [commons_thumb(commons[0], st) for st in steps]
            e["discovery"]["rendition_policy"] = (f"original preferred (needed {need:.0f}px of {w0}px); "
                                                  f"fallback Commons thumbnails {steps}px")
    elif commons:
        urls = [commons_thumb(commons[0], 1920)] + urls
    if disc["provider"] == "mixkit" and e["kind"] == "video":
        urls += mixkit_download_urls(client, disc["provider_id"])
    if any("REDACTED" in u for u in urls):
        # renditions were stored redacted; Pixabay download URLs carry no key, others never had secrets
        urls = [u for u in urls if "REDACTED" not in u]
    slug = re.sub(r"[^a-z0-9]+", "-", (e["title"] or a.id).lower()).strip("-")[:40] or a.id
    errors = []
    for u in urls:
        ext = Path(urllib.parse.urlsplit(u).path).suffix.lower() or {"image": ".jpg", "video": ".mp4"}.get(e["kind"], ".bin")
        if len(ext) > 6 or not re.fullmatch(r"\.[a-z0-9]+", ext):
            ext = {"image": ".jpg", "video": ".mp4"}.get(e["kind"], ".mp3")
        dest = prod / "assets" / f"{a.id}-{slug}{ext}"
        try:
            info = client.download(u, dest, disc["provider"].split(":")[0])  # media CDNs need no credentials
        except PV.Unavailable as ex:
            errors.append(f"{PV.redact(u)}: {ex}")
            continue
        ok, why, facts = verify_media(dest, e["kind"])
        if not ok:
            dest.unlink(missing_ok=True)
            errors.append(f"{PV.redact(u)}: downloaded but not valid media ({why})")
            continue
        work = None
        if e["kind"] == "video":
            try:
                work = working_copy(dest, facts)
            except PV.Unavailable as ex:
                errors.append(str(ex))
                continue
        used = work or dest
        e.update({"status": "downloaded", "download_status": "ok", "fetched_at": P.now(), "download_url": PV.redact(u),
                  "local_path": str(used.relative_to(prod)), "sha256": P.sha256(used), "bytes": used.stat().st_size,
                  "probe": P.media_facts(used) if work else facts, "licence": lic,
                  "original": {"path": str(dest.relative_to(prod)), "sha256": info["sha256"], "bytes": info["bytes"],
                               "content_type": info["content_type"]} if work else None,
                  "evidence": {**(e.get("evidence") or {}), "reverified_at": P.now(),
                               "reverify_note": "licence re-read from the provider at download time" +
                                                (" — CHANGED since discovery" if changed else ", unchanged")}})
        if errors:
            e["download_attempts"] = e.get("download_attempts", []) + [{"at": P.now(), "error": x} for x in errors]
        P.save_register_entries(prod, [e])
        pr = e["probe"]
        print(f"fetched {a.id}: {e['local_path']} {pr.get('width')}x{pr.get('height')} "
              f"{pr.get('duration') or ''} {e['licence']['name']} (commercial: {e['licence']['commercial_use']})")
        return
    record_failure("; ".join(errors) or "no downloadable rendition")


def cmd_source_check(a) -> None:
    P = _P()
    prod = a.production.resolve()
    client = client_for(prod)
    path = prod / "research" / "subject-sources.json"
    data = P.read_json(path) if path.exists() else {"sources": []}
    failed = 0
    for url in a.urls:
        entry = {"url": url, "checked_at": P.now(), "note": a.note}
        try:
            body = client.get(url, "web", action="check", use_cache=False)
            text = body.decode("utf-8", "replace")
            t = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
            entry.update({"status": "reachable", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                          "title": PV.strip_html(t.group(1))[:200] if t else None})
        except PV.Unavailable as ex:
            entry.update({"status": "unavailable", "reason": str(ex)})
            failed += 1
        data["sources"] = [s for s in data["sources"] if s["url"] != url] + [entry]
        print(f"{entry['status']:11} {url}" + (f"  — {entry.get('title')}" if entry.get("title") else f"  ({entry.get('reason')})"))
    P.write_json(path, data)
    raise SystemExit(1 if failed else 0)
