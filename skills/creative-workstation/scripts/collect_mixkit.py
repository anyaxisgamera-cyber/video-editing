#!/usr/bin/env python3
"""License-checked collector for Mixkit (https://mixkit.co) footage, music and sound effects.

Mixkit was the only Reference-Video-2 footage source reachable without a bot challenge from
this workstation (PNGEgg, Icon-Icons, Pexels and Pixabay answer automated clients with a
Cloudflare challenge/block; this tool does not attempt to bypass that).

License enforcement (verified against https://mixkit.co/license/modal/<type>/):
  * Video items carry either ``videoFree`` (commercial OK) or ``videoRestricted`` (personal use
    only). The item page is fetched and BOTH the ``data-license`` marker and the JSON-LD
    ``license`` URL must say videoFree, otherwise the clip is skipped (unless --allow-personal).
  * Music = Stock Music Free License (web/social/ads OK; not TV/radio, CD/DVD, games).
  * SFX = Sound Effects Free License (no standalone redistribution).

    python3 collect_mixkit.py search "purple ink" --type video --limit 12
    python3 collect_mixkit.py fetch-video https://mixkit.co/free-stock-video/<slug>-<id>/ \
        --library /path/media-library --res 1080
    python3 collect_mixkit.py fetch-audio sfx whoosh --library /path/media-library --limit 3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import Catalog  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) creative-workstation-asset-collector"
LIC = {
    "videoFree": ("Mixkit Stock Video Free License", "No standalone redistribution of the clip; see Mixkit User Terms",
                  "https://mixkit.co/license/#videoFree"),
    "videoRestricted": ("Mixkit Stock Video Restricted License",
                        "PERSONAL/EDUCATIONAL ONLY: no commercial, advertising, company social or monetized YouTube",
                        "https://mixkit.co/license/#videoRestricted"),
    "musicFree": ("Mixkit Stock Music Free License",
                  "Web/social/VOD/ads/podcasts OK; NOT TV/radio, CD/DVD, video games; no remix into music-only tracks; "
                  "do not register with Content ID", "https://mixkit.co/license/#musicFree"),
    "sfxFree": ("Mixkit Sound Effects Free License", "Use inside an End Product only; no standalone redistribution",
                "https://mixkit.co/license/#sfxFree"),
}


def get(url: str, binary: bool = False, retries: int = 3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return data if binary else data.decode("utf-8", "replace")
        except Exception as exc:  # network hiccup: back off and retry
            last = exc
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def search(term: str, kind: str = "video", limit: int = 12) -> list[dict]:
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    base = {"video": "free-stock-video", "music": "free-stock-music/tag", "sfx": "free-sound-effects"}[kind]
    page_url = f"https://mixkit.co/{base}/{slug}/"
    html = get(page_url)
    items = []
    if kind == "video":
        for m in re.finditer(r'href="(/free-stock-video/([a-z0-9-]+)-(\d+)/)"', html):
            url = urllib.parse.urljoin("https://mixkit.co", m.group(1))
            if all(i["url"] != url for i in items):
                items.append({"url": url, "id": m.group(3), "title": m.group(2).replace("-", " ")})
    else:
        pat = r"https://assets\.mixkit\.co/(?:active_storage/sfx|music)/(\d+)/[\w.-]+\.mp3"
        for m in re.finditer(pat, html):
            if all(i["id"] != m.group(1) for i in items):
                items.append({"url": m.group(0), "id": m.group(1), "title": f"{term} {m.group(1)}"})
    lic = re.findall(r'data-license="([a-zA-Z]+)"', html)
    for it in items:
        it["listing"] = page_url
        it["listing_license"] = lic[0] if lic else None
    return items[:limit]


def video_item(url: str) -> dict:
    html = get(url)
    marker = re.findall(r'data-license="([a-zA-Z]+)"', html)
    jsonld = re.findall(r'"license":"https://mixkit\.co/license/#([a-zA-Z]+)"', html)
    title = re.search(r'"name":"([^"]+)","description":"([^"]*)"', html)
    mid = re.search(r"-(\d+)/?$", url.rstrip("/") + "/").group(1) if re.search(r"-(\d+)/?$", url) else None
    return {"url": url, "id": mid, "license_marker": marker[0] if marker else None,
            "license_jsonld": jsonld[0] if jsonld else None,
            "title": title.group(1) if title else url.rstrip("/").rsplit("/", 1)[-1],
            "description": title.group(2) if title else ""}


def fetch_video(url: str, library: Path, res: str = "1080", allow_personal: bool = False, category: str = "video-clips",
                tags: list[str] | None = None) -> dict:
    meta = video_item(url)
    lic = meta["license_marker"]
    if lic != meta["license_jsonld"]:
        return {"status": "skipped", "reason": f"license signals disagree ({lic} vs {meta['license_jsonld']})", **meta}
    if lic not in LIC:
        return {"status": "skipped", "reason": f"unknown license {lic!r}", **meta}
    if lic == "videoRestricted" and not allow_personal:
        return {"status": "skipped", "reason": "Restricted License (personal use only)", **meta}
    slug = re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-")
    order = list(dict.fromkeys([res, "1080", "720", "2160", "360"]))  # not every clip has every rendition
    asset = dest = None
    for r in order:
        cand = f"https://assets.mixkit.co/videos/{meta['id']}/{meta['id']}-{r}.mp4"
        out = library / category / f"mixkit-{meta['id']}-{slug}-{r}.mp4"
        if out.exists():
            asset, dest = cand, out
            break
        try:
            data = get(cand, binary=True, retries=1)
        except RuntimeError:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        asset, dest = cand, out
        break
    if dest is None:
        return {"status": "failed", "reason": f"no rendition of {order} downloadable", **meta}
    name, restrictions, lic_url = LIC[lic]
    cat = Catalog(library)
    entry = cat.add(dest, category, asset, name, restrictions, title=meta["title"], tags=tags or ["mixkit", "footage"],
                    attribution="Mixkit (attribution appreciated, not required)", source_page=url,
                    extra={"mixkit_id": meta["id"], "license_url": lic_url, "description": meta["description"],
                           "license_evidence": {"data-license": lic, "json-ld": meta["license_jsonld"]}})
    cat.save()
    return {"status": "downloaded", "path": str(dest), "license": name, "entry": entry["id"]}


def fetch_audio(kind: str, term: str, library: Path, limit: int = 3) -> list[dict]:
    items = search(term, kind, limit)
    out = []
    key = {"sfx": "sfxFree", "music": "musicFree"}[kind]
    category = {"sfx": "sound-effects", "music": "music"}[kind]
    cat = Catalog(library)
    for it in items:
        if it["listing_license"] != key:
            out.append({"status": "skipped", "reason": f"listing license {it['listing_license']!r} != {key}", **it})
            continue
        dest = library / category / f"mixkit-{kind}-{it['id']}-{re.sub(r'[^a-z0-9]+', '-', term.lower())}.mp3"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(get(it["url"], binary=True))
        name, restrictions, lic_url = LIC[key]
        e = cat.add(dest, category, it["url"], name, restrictions, title=it["title"], tags=["mixkit", kind, term],
                    source_page=it["listing"], extra={"mixkit_id": it["id"], "license_url": lic_url})
        out.append({"status": "downloaded", "path": str(dest), "license": name, "entry": e["id"]})
    cat.save()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("term"); s.add_argument("--type", default="video", choices=["video", "music", "sfx"])
    s.add_argument("--limit", type=int, default=12); s.add_argument("--check-license", action="store_true")
    s = sub.add_parser("fetch-video"); s.add_argument("urls", nargs="+"); s.add_argument("--library", type=Path, required=True)
    s.add_argument("--res", default="1080", choices=["360", "720", "1080", "2160"]); s.add_argument("--allow-personal", action="store_true")
    s = sub.add_parser("fetch-audio"); s.add_argument("type", choices=["sfx", "music"]); s.add_argument("term")
    s.add_argument("--library", type=Path, required=True); s.add_argument("--limit", type=int, default=3)
    a = ap.parse_args(argv)
    if a.cmd == "search":
        items = search(a.term, a.type, a.limit)
        if a.check_license and a.type == "video":
            for it in items:
                m = video_item(it["url"])
                it["license"] = m["license_marker"]
                it["license_jsonld"] = m["license_jsonld"]
        print(json.dumps(items, indent=2))
    elif a.cmd == "fetch-video":
        results = []
        for u in a.urls:
            try:
                results.append(fetch_video(u, a.library, a.res, a.allow_personal))
            except Exception as exc:  # one bad item must not abort a batch
                results.append({"status": "failed", "url": u, "reason": str(exc)})
        print(json.dumps(results, indent=2))
    elif a.cmd == "fetch-audio":
        print(json.dumps(fetch_audio(a.type, a.term, a.library, a.limit), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
