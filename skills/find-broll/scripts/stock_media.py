#!/usr/bin/env python3
"""Search and download licensed stock footage and photos through official APIs.

Providers (official, documented REST APIs):
  pexels   https://www.pexels.com/api/documentation/   (videos + photos, Pexels License)
  pixabay  https://pixabay.com/api/docs/               (videos + photos, Pixabay Content License)

Keys are never passed on the command line or written to disk:
  PEXELS_API_KEY   sent as the `Authorization` header (Pexels' documented scheme).
  PIXABAY_API_KEY  sent as the `key` query parameter (Pixabay's documented scheme);
                   it is redacted from anything this tool prints or saves.
  If PEXELS_API_KEY is unset, requests still go out with a placeholder header so a
  key-injecting egress proxy (network secret for api.pexels.com) can supply it.

Commands:
  search  QUERY [--provider pexels|pixabay|all] [--kind video|photo] [--orientation portrait|landscape|square]
          [--min-height N] [--min-duration S] [--limit N] [--raw-dir DIR]
      Print ranked, normalized candidates as JSON (no downloads).

  fetch   PLAN.json --out DIR [--provider ...] [--candidates 3] [--raw-dir DIR]
      For every beat in the plan, search its queries, rank, avoid reusing an asset across
      beats, download the chosen rendition plus thumbnails of the runners-up, and write
      DIR/stock-manifest.json with provider, IDs, creator, page URL, license, rendition,
      checksum, and retrieval time. Beats are marked "sourced"; approval is editorial.

Plan format (JSON):
  {"version": 1, "kind": "video", "orientation": "portrait", "min_height": 1920,
   "beats": [{"id": "b01", "narration": "...", "meaning": "...", "duration": 3.2,
              "queries": ["candle flame dark", "single candle night"],
              "avoid": ["birthday", "cake"]}]}

Rate limits (documented): Pexels 200 requests/hour, 20k/month; Pixabay 100 requests/60 s,
and Pixabay asks that responses be cached for 24 h. Responses are cached under
~/.cache/stock-media (keyed by request, key excluded) for 24 h.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_DIR = Path(os.environ.get("STOCK_MEDIA_CACHE", Path.home() / ".cache" / "stock-media"))
CACHE_TTL = 24 * 3600
USER_AGENT = "video-editing-skills/stock_media (+https://github.com/gitethanwoo/video-editing)"

LICENSES = {
    "pexels": {
        "name": "Pexels License",
        "url": "https://www.pexels.com/license/",
        "summary": "Free to use and modify, commercial use allowed, attribution not required but appreciated. "
                   "Do not sell unaltered copies, imply endorsement by people or brands shown, or redistribute "
                   "as a stock/wallpaper collection.",
    },
    "pixabay": {
        "name": "Pixabay Content License",
        "url": "https://pixabay.com/service/license-summary/",
        "summary": "Free to use and modify, commercial use allowed, no attribution required. Do not sell or "
                   "distribute unaltered copies, use depicted people/brands/trademarks in misleading or "
                   "offensive ways, or offer the content on other stock platforms.",
    },
}


# --------------------------------------------------------------------------- HTTP

def _ssl_context() -> ssl.SSLContext | None:
    bundle = os.environ.get("STOCK_MEDIA_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    return ssl.create_default_context(cafile=bundle) if bundle else None


def _redact(text: str) -> str:
    key = os.environ.get("PIXABAY_API_KEY")
    if key:
        text = text.replace(key, "REDACTED")
    return re.sub(r"([?&]key=)[^&]+", r"\1REDACTED", text)


def http_json(url: str, headers: dict[str, str], cache_key: str) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / (hashlib.sha256(cache_key.encode()).hexdigest() + ".json")
    if cached.exists() and time.time() - cached.stat().st_mtime < CACHE_TTL:
        return json.loads(cached.read_text())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, context=_ssl_context(), timeout=60) as resp:
                payload = json.load(resp)
            cached.write_text(json.dumps(payload))
            return payload
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < 3:
                time.sleep(2 ** (attempt + 2))
                continue
            body = err.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"{_redact(url.split('?')[0])}: HTTP {err.code} {_redact(body)}") from None
    raise SystemExit("unreachable")


def download(url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    digest = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=300) as resp, tmp.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            digest.update(chunk)
            fh.write(chunk)
    tmp.replace(dest)
    return digest.hexdigest()


# --------------------------------------------------------------------- providers

def pexels_search(query: str, kind: str, orientation: str | None, per_page: int, raw_dir: Path | None) -> list[dict]:
    base = "https://api.pexels.com/videos/search" if kind == "video" else "https://api.pexels.com/v1/search"
    params = {"query": query, "per_page": per_page, "size": "large"}
    if orientation:
        params["orientation"] = orientation
    url = f"{base}?{urllib.parse.urlencode(params)}"
    key = os.environ.get("PEXELS_API_KEY", "proxy-injected")
    payload = http_json(url, {"Authorization": key}, f"pexels|{url}")
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"pexels-{kind}-{_slug(query)}.json").write_text(json.dumps(payload, indent=1))
    out = []
    for item in payload.get("videos" if kind == "video" else "photos", []):
        if kind == "video":
            files = [f for f in item.get("video_files", []) if f.get("link") and f.get("width") and f.get("height")]
            out.append({
                "provider": "pexels", "kind": "video", "id": str(item["id"]),
                "page_url": item.get("url"), "creator": (item.get("user") or {}).get("name"),
                "creator_url": (item.get("user") or {}).get("url"),
                "width": item.get("width"), "height": item.get("height"), "duration": item.get("duration"),
                "thumbnail": item.get("image"),
                "renditions": [{"url": f["link"], "width": f["width"], "height": f["height"], "fps": f.get("fps"),
                                "quality": f.get("quality"), "type": f.get("file_type")} for f in files],
                "text": _slug_words(item.get("url", "")),
            })
        else:
            src = item.get("src") or {}
            out.append({
                "provider": "pexels", "kind": "photo", "id": str(item["id"]),
                "page_url": item.get("url"), "creator": item.get("photographer"), "creator_url": item.get("photographer_url"),
                "width": item.get("width"), "height": item.get("height"), "duration": None,
                "thumbnail": src.get("medium"),
                "renditions": [{"url": src["original"], "width": item.get("width"), "height": item.get("height")}] if src.get("original") else [],
                "text": " ".join(filter(None, [item.get("alt"), _slug_words(item.get("url", ""))])),
            })
    return out


def pixabay_search(query: str, kind: str, orientation: str | None, per_page: int, raw_dir: Path | None) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise SystemExit("PIXABAY_API_KEY is not set (Pixabay takes its key as a query parameter, "
                         "so a header-injecting proxy secret cannot supply it).")
    base = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    params = {"q": query, "per_page": max(3, min(per_page, 200)), "safesearch": "true"}
    if kind == "photo":
        params["image_type"] = "photo"
        if orientation in ("horizontal", "vertical"):
            params["orientation"] = orientation
        elif orientation == "portrait":
            params["orientation"] = "vertical"
        elif orientation == "landscape":
            params["orientation"] = "horizontal"
    public_url = f"{base}?{urllib.parse.urlencode(params)}"
    url = f"{public_url}&key={urllib.parse.quote(key)}"
    payload = http_json(url, {}, f"pixabay|{public_url}")
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"pixabay-{kind}-{_slug(query)}.json").write_text(_redact(json.dumps(payload, indent=1)))
    out = []
    for item in payload.get("hits", []):
        if kind == "video":
            vids = item.get("videos") or {}
            rends = [{"url": v["url"], "width": v.get("width"), "height": v.get("height"), "quality": name}
                     for name, v in vids.items() if v and v.get("url") and v.get("width")]
            best = max(rends, key=lambda r: r["width"] * r["height"], default={})
            out.append({
                "provider": "pixabay", "kind": "video", "id": str(item["id"]),
                "page_url": item.get("pageURL"), "creator": item.get("user"),
                "creator_url": f"https://pixabay.com/users/{item.get('user')}-{item.get('user_id')}/" if item.get("user") else None,
                "width": best.get("width"), "height": best.get("height"), "duration": item.get("duration"),
                "thumbnail": (vids.get("medium") or {}).get("thumbnail") or (vids.get("small") or {}).get("thumbnail"),
                "renditions": rends, "text": item.get("tags", ""),
            })
        else:
            url_full = item.get("largeImageURL")
            out.append({
                "provider": "pixabay", "kind": "photo", "id": str(item["id"]),
                "page_url": item.get("pageURL"), "creator": item.get("user"), "creator_url": None,
                "width": item.get("imageWidth"), "height": item.get("imageHeight"), "duration": None,
                "thumbnail": item.get("webformatURL"),
                "renditions": [{"url": url_full, "width": item.get("imageWidth"), "height": item.get("imageHeight")}] if url_full else [],
                "text": item.get("tags", ""),
            })
    return out


PROVIDERS = {"pexels": pexels_search, "pixabay": pixabay_search}


# ----------------------------------------------------------------------- ranking

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def _slug_words(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/").split("/")[-1] if url else ""
    return re.sub(r"-?\d+$", "", path).replace("-", " ")


def pick_rendition(cand: dict, orientation: str | None, min_height: int) -> dict | None:
    """Smallest rendition that still covers the delivery frame; else the largest available."""
    rends = [r for r in cand["renditions"] if r.get("width") and r.get("height")]
    if not rends:
        return None
    portrait = orientation == "portrait"
    # Short side must cover 1080 for a 1080x1920 deliverable (cover-crop either way).
    need_short = 1080 if min_height >= 1920 else int(min_height * 9 / 16)

    def covers(r: dict) -> bool:
        short = min(r["width"], r["height"])
        if portrait and r["height"] >= r["width"]:
            return r["width"] >= need_short and r["height"] >= min_height
        # landscape source cropped to portrait: needs height >= min_height to avoid upscaling
        return r["height"] >= min_height if portrait else short >= need_short

    good = [r for r in rends if covers(r)]
    pool = good or rends
    key = (lambda r: r["width"] * r["height"]) if good else (lambda r: -r["width"] * r["height"])
    return sorted(pool, key=key)[0]


def score(cand: dict, query_words: set[str], avoid: list[str], orientation: str | None, min_height: int,
          min_duration: float | None) -> float:
    s = 0.0
    w, h = cand.get("width") or 0, cand.get("height") or 0
    if orientation == "portrait":
        s += 3.0 if h > w else 0.0
    elif orientation == "landscape":
        s += 3.0 if w > h else 0.0
    rend = pick_rendition(cand, orientation, min_height)
    if rend:
        cover = min(rend["height"] / max(min_height, 1), 1.0) if orientation == "portrait" and rend["height"] < rend["width"] \
            else min(min(rend["width"], rend["height"]) / 1080, 1.0)
        s += 4.0 * cover
    if min_duration and cand.get("duration"):
        s += 1.5 if cand["duration"] >= min_duration else -2.0
    text = (cand.get("text") or "").lower()
    s += 1.2 * sum(1 for q in query_words if q in text)
    s -= 4.0 * sum(1 for a in avoid if a.lower() in text)
    return round(s, 3)


def search_all(query: str, providers: list[str], kind: str, orientation: str | None, min_height: int,
               min_duration: float | None, limit: int, raw_dir: Path | None, avoid: list[str] | None = None) -> list[dict]:
    results = []
    for name in providers:
        try:
            results += PROVIDERS[name](query, kind, orientation, 30, raw_dir)
        except SystemExit as err:
            print(f"[{name}] {err}", file=sys.stderr)
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
    for c in results:
        c["score"] = score(c, words, avoid or [], orientation, min_height, min_duration)
        c["query"] = query
    results.sort(key=lambda c: c["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------- commands

def cmd_search(a: argparse.Namespace) -> None:
    providers = list(PROVIDERS) if a.provider == "all" else [a.provider]
    res = search_all(a.query, providers, a.kind, a.orientation, a.min_height, a.min_duration, a.limit,
                     Path(a.raw_dir) if a.raw_dir else None)
    slim = [{k: c[k] for k in ("provider", "id", "score", "width", "height", "duration", "page_url", "creator", "text")}
            for c in res]
    print(json.dumps(slim, indent=1))


def cmd_fetch(a: argparse.Namespace) -> None:
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    out = Path(a.out)
    providers = list(PROVIDERS) if a.provider == "all" else [a.provider]
    kind = plan.get("kind", "video")
    orientation = plan.get("orientation", "portrait")
    min_height = int(plan.get("min_height", 1920))
    manifest_path = out / "stock-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"version": 1, "beats": []}
    done = {b["id"]: b for b in manifest["beats"]}
    used = {(b["chosen"]["provider"], b["chosen"]["id"]) for b in manifest["beats"] if b.get("chosen")}

    for beat in plan["beats"]:
        if beat["id"] in done and done[beat["id"]].get("chosen") and not a.refresh:
            print(f"{beat['id']}: kept {done[beat['id']]['chosen']['provider']}:{done[beat['id']]['chosen']['id']}")
            continue
        pool: dict[tuple[str, str], dict] = {}
        for q in beat["queries"]:
            for c in search_all(q, providers, kind, orientation, min_height, (beat.get("duration") or 0) + 1.0, 12,
                                Path(a.raw_dir) if a.raw_dir else None, beat.get("avoid")):
                k = (c["provider"], c["id"])
                if k not in pool or c["score"] > pool[k]["score"]:
                    pool[k] = c
        ranked = [c for c in sorted(pool.values(), key=lambda c: c["score"], reverse=True) if (c["provider"], c["id"]) not in used]
        if not ranked:
            print(f"{beat['id']}: no candidates", file=sys.stderr)
            continue
        chosen = ranked[0]
        rend = pick_rendition(chosen, orientation, min_height)
        ext = ".mp4" if kind == "video" else Path(urllib.parse.urlparse(rend["url"]).path).suffix or ".jpg"
        local = out / "media" / f"{beat['id']}-{chosen['provider']}-{chosen['id']}{ext}"
        sha = download(rend["url"], local) if not local.exists() else hashlib.sha256(local.read_bytes()).hexdigest()
        thumbs = []
        for c in ranked[: a.candidates]:
            if c.get("thumbnail"):
                tp = out / "candidates" / f"{beat['id']}-{c['provider']}-{c['id']}.jpg"
                try:
                    if not tp.exists():
                        download(c["thumbnail"], tp)
                    thumbs.append({"provider": c["provider"], "id": c["id"], "score": c["score"], "thumb": str(tp.relative_to(out)),
                                   "page_url": c["page_url"]})
                except Exception as err:  # noqa: BLE001 - thumbnails are advisory
                    print(f"{beat['id']}: thumbnail failed for {c['id']}: {err}", file=sys.stderr)
        used.add((chosen["provider"], chosen["id"]))
        lic = LICENSES[chosen["provider"]]
        done[beat["id"]] = {
            "id": beat["id"],
            "narration": beat.get("narration"),
            "meaning": beat.get("meaning"),
            "queries": beat["queries"],
            "chosen": {
                "provider": chosen["provider"], "id": chosen["id"], "kind": kind,
                "page_url": chosen["page_url"], "creator": chosen["creator"], "creator_url": chosen.get("creator_url"),
                "matched_query": chosen["query"], "score": chosen["score"],
                "source_width": chosen.get("width"), "source_height": chosen.get("height"), "duration": chosen.get("duration"),
                "rendition": {k: rend.get(k) for k in ("width", "height", "fps", "quality")},
                "local_path": str(local.relative_to(out)), "sha256": sha,
                "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "license": lic["name"], "license_url": lic["url"], "license_summary": lic["summary"],
                "credit": f"{chosen['creator']} / {chosen['provider'].capitalize()}",
            },
            "alternatives": thumbs[1:],
            "status": "sourced",
        }
        print(f"{beat['id']}: {chosen['provider']}:{chosen['id']} score {chosen['score']} "
              f"{rend.get('width')}x{rend.get('height')} ({chosen['query']})")
        manifest["beats"] = [done[b["id"]] for b in plan["beats"] if b["id"] in done]
        out.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest: {manifest_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--provider", default="all", choices=["all", *PROVIDERS])
    s.add_argument("--kind", default="video", choices=["video", "photo"])
    s.add_argument("--orientation", default="portrait", choices=["portrait", "landscape", "square"])
    s.add_argument("--min-height", type=int, default=1920)
    s.add_argument("--min-duration", type=float)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--raw-dir")
    s.set_defaults(func=cmd_search)
    f = sub.add_parser("fetch")
    f.add_argument("plan")
    f.add_argument("--out", required=True)
    f.add_argument("--provider", default="all", choices=["all", *PROVIDERS])
    f.add_argument("--candidates", type=int, default=4)
    f.add_argument("--raw-dir")
    f.add_argument("--refresh", action="store_true", help="re-pick beats that already have a chosen asset")
    f.set_defaults(func=cmd_fetch)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
