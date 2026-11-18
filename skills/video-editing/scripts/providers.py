#!/usr/bin/env python3
"""Asset discovery providers with normalized licences, polite HTTP, caching, and an external-action log.

Used by production.py (`discover`, `fetch`, `source-check`). Standard library only.

Providers and what they need:
  openverse   images, audio (CC catalogue incl. Flickr, Wikimedia, Freesound, Jamendo)   no key
  wikimedia   images, video, audio (Wikimedia Commons)                                    no key (strict rate limits)
  nasa        images, video (NASA Image and Video Library)                                no key
  pexels      images, video                                       PEXELS_API_KEY environment variable
  pixabay     images, video                                       PIXABAY_API_KEY environment variable
  mixkit      video, music, sfx (item-level licence read from each item page)             no key
  loc         images (Library of Congress Prints & Photographs; rights advisory per item)  no key
  met         images (The Metropolitan Museum of Art Open Access; CC0 public-domain works)  no key

Every licence is normalized to {name, url, code, commercial_use: yes|no|conditional|unknown, attribution_required,
share_alike, no_derivatives, restrictions}. "conditional" (share-alike) needs an explicit approval before a
commercial production may use the asset; "unknown" is never usable commercially.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html as htmllib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Generic client identification: no user, project, or contact details are sent to third parties.
UA = "video-editing-asset-discovery/1.1 (open-source video production tooling)"
SECRET_PARAMS = {"key", "api_key", "apikey", "token", "access_token", "client_secret", "signature"}
PROVIDERS = ["openverse", "wikimedia", "nasa", "pexels", "pixabay", "mixkit", "loc", "met"]
KINDS = {"openverse": {"image", "audio", "music", "sfx"}, "wikimedia": {"image", "video", "audio", "music", "sfx"},
         "nasa": {"image", "video"}, "pexels": {"image", "video"}, "pixabay": {"image", "video"},
         "mixkit": {"video", "music", "sfx"}, "loc": {"image"}, "met": {"image"}}


class Unavailable(Exception):
    """The provider cannot be used right now (missing key, rate limit, network, unexpected payload)."""


class _RetryLater(Exception):
    """A download worth retrying: HTTP 429/503 (code set, wait from Retry-After) or a dropped connection (code None)."""

    def __init__(self, code: int | None, wait: float, reason: str = ""):
        super().__init__(code)
        self.code, self.wait, self.reason = code, wait, reason


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def redact(url: str) -> str:
    """Remove secret query parameters (e.g. Pixabay's key) before a URL is logged, cached, or stored."""
    p = urllib.parse.urlsplit(url)
    q = [(k, "REDACTED" if k.lower() in SECRET_PARAMS else v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), p.fragment))


def strip_html(s: str | None) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ------------------------------------------------------------------ licences


def classify_licence(code: str | None = None, name: str | None = None, url: str | None = None) -> dict:
    """Normalize a licence from a provider field (code like 'by-sa', 'cc-by-4.0', 'cc0', 'pdm' or a name)."""
    raw = " ".join(x for x in (code, name, url) if x).lower()
    c = (code or "").lower()
    out = {"name": name or (code or "unknown"), "url": url, "code": c or None, "commercial_use": "unknown",
           "attribution_required": "no", "share_alike": False, "no_derivatives": False, "restrictions": ""}
    if re.search(r"\bcc0\b|cc-zero|publicdomain/zero", raw) or c in ("cc0",):
        out.update(commercial_use="yes", code="cc0", name=name or "CC0 1.0")
    elif c in ("pdm", "pd", "public domain") or "public domain" in raw or "publicdomain/mark" in raw:
        out.update(commercial_use="yes", code="pdm", name=name or "Public Domain Mark")
    elif re.search(r"\b(by-)?nc\b|-nc-|noncommercial|non-commercial|by-nc", raw):
        out.update(commercial_use="no", attribution_required="yes", restrictions="non-commercial only")
    elif re.search(r"by-nd|-nd-|\bnd\b|noderiv", raw):
        out.update(commercial_use="no", attribution_required="yes", no_derivatives=True,
                   restrictions="no derivatives: cropping, cutting, or grading it in an edit is not permitted")
    elif re.search(r"by-sa|-sa-|sharealike|share-alike|share alike", raw):
        out.update(commercial_use="conditional", attribution_required="yes", share_alike=True,
                   restrictions="share-alike: a video that adapts it must be released under the same licence")
    elif re.search(r"\bby\b|cc-by|/by/|attribution", raw):
        out.update(commercial_use="yes", attribution_required="yes")
    return out


def provider_licence(provider: str, extra: str = "") -> dict:
    fixed = {
        "pexels": ("Pexels License", "https://www.pexels.com/license/",
                   "no attribution required; do not sell unaltered copies; do not imply endorsement by people or brands shown"),
        "pixabay": ("Pixabay Content License", "https://pixabay.com/service/license-summary/",
                    "no attribution required; do not sell unaltered copies; recognizable people, logos and brands may need releases"),
        "nasa": ("NASA Images and Media Usage Guidelines", "https://www.nasa.gov/nasa-brand-center/images-and-media/",
                 "generally not copyrighted in the US; NASA insignia/logos and identifiable people need permission; "
                 "third-party material may be marked in the description"),
        "videoFree": ("Mixkit Stock Video Free License", "https://mixkit.co/license/#videoFree",
                      "no standalone redistribution of the clip"),
        "videoRestricted": ("Mixkit Stock Video Restricted License", "https://mixkit.co/license/#videoRestricted",
                            "personal/educational only: no commercial, advertising, or monetized use"),
        "musicFree": ("Mixkit Stock Music Free License", "https://mixkit.co/license/#musicFree",
                      "web, social, VOD, ads, podcasts allowed; not TV/radio broadcast, CD/DVD, or games; no Content ID registration"),
        "sfxFree": ("Mixkit Sound Effects Free License", "https://mixkit.co/license/#sfxFree",
                    "inside an end product only; no standalone redistribution"),
    }
    name, url, restr = fixed[provider]
    commercial = "no" if provider == "videoRestricted" else "yes"
    return {"name": name, "url": url, "code": provider.lower(), "commercial_use": commercial, "attribution_required": "no",
            "share_alike": False, "no_derivatives": False, "restrictions": (restr + (f"; {extra}" if extra else ""))}


# ------------------------------------------------------------------ HTTP


class Client:
    """GET with caching, Retry-After handling, and a JSONL log of every external request (secrets redacted)."""

    def __init__(self, cache_dir: Path | None, log_path: Path | None, ttl_hours: float = 24.0, max_wait: float = 90.0):
        self.cache_dir, self.log_path, self.ttl, self.max_wait = cache_dir, log_path, ttl_hours * 3600, max_wait
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def log(self, **entry) -> None:
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": now(), **entry}, ensure_ascii=False) + "\n")

    def _cache_file(self, url: str) -> Path | None:
        return self.cache_dir / (hashlib.sha256(redact(url).encode()).hexdigest() + ".json") if self.cache_dir else None

    def get(self, url: str, provider: str, headers: dict | None = None, action: str = "search", use_cache: bool = True,
            binary: bool = False, retries: int = 3, timeout: float = 45) -> bytes:
        cf = self._cache_file(url) if (use_cache and not binary) else None
        if cf and cf.exists() and time.time() - cf.stat().st_mtime < self.ttl:
            self.log(provider=provider, action=action, method="GET", url=redact(url), status=200, cached=True)
            return json.loads(cf.read_text())["body"].encode()
        last = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                    self.log(provider=provider, action=action, method="GET", url=redact(url), status=r.status,
                             bytes=len(body), cached=False)
                    if cf:
                        cf.write_text(json.dumps({"url": redact(url), "fetched_at": now(), "body": body.decode("utf-8", "replace")}))
                    return body
            except urllib.error.HTTPError as e:
                self.log(provider=provider, action=action, method="GET", url=redact(url), status=e.code, cached=False)
                last = f"HTTP {e.code}"
                if e.code in (401, 403):
                    raise Unavailable(f"{provider}: HTTP {e.code} (missing or invalid credentials, or access refused)")
                if e.code in (429, 503) and attempt < retries:
                    wait = float(e.headers.get("Retry-After") or (5 * (attempt + 1)))
                    if wait > self.max_wait:
                        raise Unavailable(f"{provider}: rate limited (Retry-After {wait:.0f}s exceeds {self.max_wait:.0f}s)")
                    time.sleep(wait)
                    continue
                if e.code in (429, 503):
                    raise Unavailable(f"{provider}: rate limited (HTTP {e.code}) after {retries} retries")
                raise Unavailable(f"{provider}: {last} for {redact(url)}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, http.client.HTTPException) as e:
                # HTTPException covers IncompleteRead (body cut off mid-transfer) and malformed responses: transient
                last = str(getattr(e, "reason", None) or f"{type(e).__name__}: {e}")
                self.log(provider=provider, action=action, method="GET", url=redact(url), status=None, error=last[:200])
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise Unavailable(f"{provider}: unreachable ({last})")
        raise Unavailable(f"{provider}: {last}")

    def json(self, url: str, provider: str, **kw) -> dict:
        body = self.get(url, provider, **kw)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise Unavailable(f"{provider}: response was not JSON ({body[:80]!r})")

    def download(self, url: str, dest: Path, provider: str, headers: dict | None = None, max_bytes: int = 4 << 30,
                 timeout: float = 120, retries: int = 4) -> dict:
        """Stream to a temporary file and move into place only when complete; honour Retry-After on 429/503."""
        for attempt in range(retries + 1):
            try:
                return self._download_once(url, dest, provider, headers, max_bytes, timeout)
            except _RetryLater as r:
                if attempt == retries or r.wait > self.max_wait:
                    raise Unavailable(f"{provider}: " + (f"rate limited (HTTP {r.code}) — retry later" if r.code
                                                         else f"download failed after {attempt + 1} attempts ({r.reason})"))
                time.sleep(r.wait)
        raise Unavailable(f"{provider}: download failed")

    def _download_once(self, url, dest, provider, headers, max_bytes, timeout) -> dict:
        tmp = dest.with_name(dest.name + ".part")
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        h = hashlib.sha256()
        size = 0
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r, tmp.open("wb") as fh:
                ctype = r.headers.get("Content-Type", "")
                expected = int(r.headers.get("Content-Length") or 0)
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise Unavailable(f"{provider}: download exceeds {max_bytes} bytes")
                    h.update(chunk)
                    fh.write(chunk)
                status = r.status
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            self.log(provider=provider, action="download", method="GET", url=redact(url), status=e.code)
            if e.code in (429, 503):
                raise _RetryLater(e.code, float(e.headers.get("Retry-After") or 10))
            raise Unavailable(f"{provider}: download failed with HTTP {e.code}")
        except urllib.error.URLError as e:
            # DNS failure, refused connection, TLS error: the site is unavailable, retrying soon will not help
            tmp.unlink(missing_ok=True)
            self.log(provider=provider, action="download", method="GET", url=redact(url), status=None, error=str(e)[:200])
            raise Unavailable(f"{provider}: download failed ({getattr(e, 'reason', e)})")
        except (TimeoutError, ConnectionError, OSError, http.client.HTTPException) as e:
            # connection dropped or body cut off mid-transfer: transient, retried a few times
            tmp.unlink(missing_ok=True)
            self.log(provider=provider, action="download", method="GET", url=redact(url), status=None,
                     error=f"{type(e).__name__}: {e}"[:200])
            raise _RetryLater(None, 5.0, f"{type(e).__name__}: {e}"[:120])
        except Unavailable:
            tmp.unlink(missing_ok=True)
            raise
        if expected and size != expected:
            tmp.unlink(missing_ok=True)
            self.log(provider=provider, action="download", method="GET", url=redact(url), status=status, bytes=size,
                     error=f"truncated: {size}/{expected} bytes")
            raise Unavailable(f"{provider}: download truncated ({size} of {expected} bytes)")
        if size == 0:
            tmp.unlink(missing_ok=True)
            raise Unavailable(f"{provider}: empty download")
        tmp.replace(dest)
        self.log(provider=provider, action="download", method="GET", url=redact(url), status=status, bytes=size)
        return {"bytes": size, "sha256": h.hexdigest(), "content_type": ctype}


# ------------------------------------------------------------------ providers


def cand(provider: str, pid, kind: str, title: str, source_url: str, renditions: list[dict], licence: dict, **extra) -> dict:
    renditions = [r for r in renditions if r.get("url")]
    best = max(renditions, key=lambda r: (r.get("width") or 0) * (r.get("height") or 0)) if renditions else {}
    return {"provider": provider, "provider_id": str(pid), "kind": kind, "title": title.strip() or f"{provider} {pid}",
            "source_url": source_url, "renditions": renditions, "download_url": best.get("url"),
            "width": best.get("width"), "height": best.get("height"), "licence": licence, "retrieved_at": now(), **extra}


def openverse(client: Client, query: str, kind: str, limit: int, commercial_only: bool, source: str | None = None) -> list[dict]:
    media = "audio" if kind in ("audio", "music", "sfx") else "images"
    params = {"q": query, "page_size": str(min(limit, 20)), "mature": "false"}
    if commercial_only:
        params["license"] = "cc0,pdm,by"  # commercial + modification allowed, no share-alike obligation
    if source:
        params["source"] = source  # e.g. wikimedia: full-resolution originals with per-file licences
    if kind == "music":
        params["category"] = "music"
    if kind == "sfx":
        params["category"] = "sound_effect"
    d = client.json(f"https://api.openverse.org/v1/{media}/?{urllib.parse.urlencode(params)}", "openverse")
    out = []
    for r in d.get("results", [])[:limit]:
        lic = classify_licence(r.get("license"), f"CC {str(r.get('license', '')).upper()} {r.get('license_version') or ''}".strip()
                               if r.get("license") not in ("cc0", "pdm") else None, r.get("license_url"))
        lic["attribution"] = r.get("attribution")
        title = strip_html(r.get("title") or "").removeprefix("File:")
        title = re.sub(r"\.(jpe?g|png|tiff?|webp|gif)$", "", title, flags=re.I)
        out.append(cand("openverse", r["id"], "image" if media == "images" else kind, title,
                        r.get("foreign_landing_url") or r.get("url"),
                        [{"url": r.get("url"), "width": r.get("width"), "height": r.get("height"), "filetype": r.get("filetype")}],
                        lic, creator=r.get("creator"), creator_url=r.get("creator_url"), upstream=r.get("source"),
                        duration=(r.get("duration") or 0) / 1000 if media == "audio" else None,
                        tags=[t.get("name") for t in r.get("tags") or []][:12], detail_url=r.get("detail_url"),
                        thumbnail=r.get("thumbnail"),
                        evidence=f"Openverse API license={r.get('license')} version={r.get('license_version')} "
                                 f"provider={r.get('provider')}"))
    return out


def wikimedia(client: Client, query: str, kind: str, limit: int, commercial_only: bool, title: str | None = None) -> list[dict]:
    ft = {"image": "filetype:bitmap", "video": "filetype:video", "audio": "filetype:audio", "music": "filetype:audio",
          "sfx": "filetype:audio"}[kind]
    params = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata|mediatype",
              "iiurlwidth": "640", "maxlag": "5"}
    if title:
        params["titles"] = title
    else:
        params.update({"generator": "search", "gsrnamespace": "6", "gsrsearch": f"{ft} {query}", "gsrlimit": str(min(limit * 2, 30))})
    d = client.json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params), "wikimedia",
                    action="detail" if title else "search")
    out = []
    pages = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        em = {k: v.get("value") for k, v in (ii.get("extmetadata") or {}).items()}
        if str(em.get("NonFree", "")).lower() == "true":
            continue
        lic = classify_licence(em.get("License"), em.get("LicenseShortName"), em.get("LicenseUrl"))
        if str(em.get("AttributionRequired", "")).lower() == "true":
            lic["attribution_required"] = "yes"
        artist = strip_html(em.get("Artist"))
        lic["attribution"] = f"\"{em.get('ObjectName') or p['title']}\" by {artist or 'unknown'}, {lic['name']}" + \
            (f", {em.get('LicenseUrl')}" if em.get("LicenseUrl") else "") + ", via Wikimedia Commons"
        if em.get("Restrictions"):
            lic["restrictions"] = (lic["restrictions"] + "; " if lic["restrictions"] else "") + f"Commons restrictions: {em['Restrictions']}"
        url = (ii.get("url") or "").split("?")[0]
        mt = ii.get("mediatype", "")
        k = "video" if mt == "VIDEO" else ("audio" if mt == "AUDIO" else "image")
        if kind in ("music", "sfx") and k == "audio":
            k = kind
        if commercial_only and lic["commercial_use"] != "yes":
            continue
        out.append(cand("wikimedia", p["title"], k, em.get("ObjectName") or p["title"].removeprefix("File:"),
                        ii.get("descriptionurl") or "", [{"url": url, "width": ii.get("width"), "height": ii.get("height"),
                                                          "mime": ii.get("mime"), "bytes": ii.get("size")}],
                        lic, creator=artist, duration=ii.get("duration"), thumbnail=ii.get("thumburl"),
                        evidence=f"Commons extmetadata License={em.get('License')} LicenseShortName={em.get('LicenseShortName')} "
                                 f"AttributionRequired={em.get('AttributionRequired')}"))
        if len(out) >= limit:
            break
    return out


def nasa(client: Client, query: str, kind: str, limit: int, commercial_only: bool) -> list[dict]:
    d = client.json("https://images-api.nasa.gov/search?" + urllib.parse.urlencode(
        {"q": query, "media_type": kind, "page_size": str(min(limit, 25))}), "nasa")
    out = []
    for it in (d.get("collection") or {}).get("items", [])[:limit]:
        data = (it.get("data") or [{}])[0]
        lic = provider_licence("nasa", "secondary creator: " + data["secondary_creator"] if data.get("secondary_creator") else "")
        out.append(cand("nasa", data.get("nasa_id"), kind, data.get("title") or "",
                        f"https://images.nasa.gov/details/{urllib.parse.quote(str(data.get('nasa_id')))}", [],
                        lic, creator=data.get("photographer") or data.get("center"), manifest=it.get("href"),
                        description=strip_html(data.get("description"))[:400], tags=(data.get("keywords") or [])[:12],
                        thumbnail=next((l.get("href") for l in it.get("links") or []), None),
                        evidence="NASA Image and Video Library item (images-api.nasa.gov); usage per NASA guidelines"))
    return out


def nasa_renditions(client: Client, c: dict) -> list[dict]:
    files = client.json(c["manifest"], "nasa", action="detail")
    rend = []
    for u in files:
        m = re.search(r"~(orig|large|medium|small)\.(jpg|jpeg|png|tif|mp4)$", u, re.I)
        if m:
            rend.append({"url": u.replace("http://", "https://"), "quality": m.group(1).lower()})
    order = {"orig": 0, "large": 1, "medium": 2, "small": 3}
    return sorted(rend, key=lambda r: order[r["quality"]])


def pexels(client: Client, query: str, kind: str, limit: int, commercial_only: bool) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise Unavailable("pexels: PEXELS_API_KEY is not set (free key from https://www.pexels.com/api/ — the account owner must create it)")
    base = "https://api.pexels.com/videos/search" if kind == "video" else "https://api.pexels.com/v1/search"
    d = client.json(base + "?" + urllib.parse.urlencode({"query": query, "per_page": str(min(limit, 40))}), "pexels",
                    headers={"Authorization": key}, use_cache=True)
    out = []
    lic = provider_licence("pexels")
    if kind == "video":
        for v in d.get("videos", [])[:limit]:
            rend = [{"url": f.get("link"), "width": f.get("width"), "height": f.get("height"), "fps": f.get("fps"),
                     "quality": f.get("quality"), "filetype": f.get("file_type")} for f in v.get("video_files", [])
                    if f.get("quality") != "hls" and f.get("width")]
            out.append(cand("pexels", v["id"], "video", re.sub(r"[-/]", " ", v.get("url", "").rstrip("/").rsplit("/", 1)[-1]),
                            v.get("url"), rend, dict(lic), creator=(v.get("user") or {}).get("name"),
                            creator_url=(v.get("user") or {}).get("url"), duration=v.get("duration"), thumbnail=v.get("image"),
                            evidence="Pexels API video result; all Pexels content is under the Pexels License"))
    else:
        for ph in d.get("photos", [])[:limit]:
            src = ph.get("src") or {}
            out.append(cand("pexels", ph["id"], "image", ph.get("alt") or "", ph.get("url"),
                            [{"url": src.get("original"), "width": ph.get("width"), "height": ph.get("height"), "quality": "original"}],
                            dict(lic), creator=ph.get("photographer"), creator_url=ph.get("photographer_url"),
                            thumbnail=src.get("medium"), evidence="Pexels API photo result; Pexels License"))
    return out


def pixabay(client: Client, query: str, kind: str, limit: int, commercial_only: bool) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise Unavailable("pixabay: PIXABAY_API_KEY is not set (free key from https://pixabay.com/api/docs/ — the account owner must create it)")
    base = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    # Pixabay requires API responses to be cached for 24 hours; the client cache does that.
    d = client.json(base + "?" + urllib.parse.urlencode({"key": key, "q": query[:100], "per_page": str(max(3, min(limit, 50))),
                                                          "safesearch": "true"}), "pixabay")
    out = []
    lic = provider_licence("pixabay")
    for h in d.get("hits", [])[:limit]:
        if kind == "video":
            rend = [{"url": v.get("url"), "width": v.get("width"), "height": v.get("height"), "quality": q, "bytes": v.get("size")}
                    for q, v in (h.get("videos") or {}).items() if v.get("url")]
            out.append(cand("pixabay", h["id"], "video", h.get("tags", ""), h.get("pageURL"), rend, dict(lic),
                            creator=h.get("user"), duration=h.get("duration"), tags=[t.strip() for t in h.get("tags", "").split(",")],
                            evidence="Pixabay API video hit; Pixabay Content License"))
        else:
            rend = [{"url": h.get(k), "width": w, "height": hh, "quality": k} for k, w, hh in (
                ("imageURL", h.get("imageWidth"), h.get("imageHeight")),
                ("fullHDURL", 1920 if h.get("fullHDURL") else None, None),
                ("largeImageURL", 1280, None)) if h.get(k)]
            out.append(cand("pixabay", h["id"], "image", h.get("tags", ""), h.get("pageURL"), rend, dict(lic),
                            creator=h.get("user"), tags=[t.strip() for t in h.get("tags", "").split(",")],
                            width_full=h.get("imageWidth"), height_full=h.get("imageHeight"),
                            evidence="Pixabay API image hit; Pixabay Content License"))
    return out


def mixkit_item(client: Client, url: str) -> dict:
    page = client.get(url, "mixkit", action="detail", use_cache=False).decode("utf-8", "replace")
    marker = re.findall(r'data-license="([a-zA-Z]+)"', page)
    title = re.search(r'"name":"([^"]+)","description"', page) or re.search(r'<meta property="og:title" content="([^"|]+)', page)
    return {"licence_marker": marker[0] if marker else None, "title": htmllib.unescape(title.group(1)).strip() if title else None,
            "html": page}


def mixkit(client: Client, query: str, kind: str, limit: int, commercial_only: bool) -> list[dict]:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    base = {"video": "free-stock-video", "music": "free-stock-music/tag", "sfx": "free-sound-effects"}[kind]
    listing = f"https://mixkit.co/{base}/{slug}/"
    page = client.get(listing, "mixkit").decode("utf-8", "replace")
    out = []
    if kind == "video":
        seen = []
        for m in re.finditer(r'href="(/free-stock-video/([a-z0-9-]+)-(\d+)/)"', page):
            if m.group(3) in seen:
                continue
            seen.append(m.group(3))
            if len(seen) > limit:
                break
            url = "https://mixkit.co" + m.group(1)
            try:
                item = mixkit_item(client, url)  # the licence is per item: read it from the item page itself
            except Unavailable as e:
                out.append({"provider": "mixkit", "provider_id": m.group(3), "error": str(e)})
                continue
            marker = item["licence_marker"]
            if marker not in ("videoFree", "videoRestricted"):
                continue
            lic = provider_licence(marker)
            if commercial_only and lic["commercial_use"] != "yes":
                continue
            vid = m.group(3)
            rend = [{"url": f"https://assets.mixkit.co/videos/{vid}/{vid}-{r}.mp4", "quality": r} for r in ("2160", "1080", "720")]
            out.append(cand("mixkit", vid, "video", item["title"] or m.group(2).replace("-", " "), url, rend, lic,
                            creator="Mixkit", evidence=f"item page data-license={marker}"))
    else:
        key = {"music": "musicFree", "sfx": "sfxFree"}[kind]
        listing_lic = re.findall(r'data-license="([a-zA-Z]+)"', page)
        pat = r"https://assets\.mixkit\.co/(?:active_storage/sfx|music)/(\d+)/[\w.-]+\.mp3"
        ids = []
        for m in re.finditer(pat, page):
            if m.group(1) not in ids:
                ids.append(m.group(1))
                if (listing_lic[0] if listing_lic else None) != key:
                    continue
                out.append(cand("mixkit", m.group(1), kind, f"{query} {m.group(1)}", listing, [{"url": m.group(0)}],
                                provider_licence(key), creator="Mixkit", evidence=f"listing data-license={listing_lic[:1]}"))
            if len(out) >= limit:
                break
    return out



# ------------------------------------------------------------------ Library of Congress


def loc_licence(advisory: str | None, item_url: str) -> dict:
    """The Library grants no licence; each item carries a rights advisory. Only "No known restrictions on publication"
    is treated as commercially usable. The U.S.-Government-work advisory (HABS/HAER/HALS and similar) covers images the
    Government made but not copies of other sources inside the same survey, so it needs a human check (conditional);
    anything else is unknown."""
    ra = re.sub(r"\s+", " ", advisory or "").strip()
    base = {"url": item_url, "share_alike": False, "no_derivatives": False, "attribution_required": "no",
            "rights_advisory": ra or None}
    if re.match(r"no known restrictions on publication", ra, re.I):
        return {**base, "name": "No known restrictions on publication (Library of Congress)", "code": "loc-nkr",
                "commercial_use": "yes",
                "restrictions": "credit line requested: Library of Congress, Prints & Photographs Division, with the "
                                "reproduction number; people shown may have publicity/privacy rights"}
    if re.match(r"no known restrictions on images made by the u\.?s\.? government", ra, re.I):
        return {**base, "name": "U.S. Government work (Library of Congress advisory)", "code": "loc-usgov",
                "commercial_use": "conditional",
                "restrictions": "only images made by the U.S. Government are unrestricted; photocopies of other sources "
                                "in the same record may be restricted — confirm the maker, then record an approval"}
    return {**base, "name": f"Library of Congress rights advisory: {ra[:120] or 'none given'}", "code": "loc-other",
            "commercial_use": "unknown", "restrictions": "rights not cleared by the advisory; research before any use"}


def loc_item(client: Client, item_url: str, action: str = "detail", use_cache: bool = True) -> dict:
    url = item_url.replace("http://", "https://").rstrip("/") + "/?fo=json"
    return client.json(url, "loc", action=action, use_cache=use_cache)


def loc_renditions(d: dict) -> list[dict]:
    """Full-size renditions for one item: the IIIF service at 100 % (sized from the JP2 master) when the item has one,
    otherwise the TIFF master (size known only after download), then the largest listed JPEG."""
    files = [f for r in (d.get("resources") or [])[:1] for group in (r.get("files") or [])[:1] for f in group]
    rend = []
    iiif = next((f["url"].split("/full/")[0] for f in files if "image-services/iiif/" in (f.get("url") or "")), None)
    jp2 = next((f for f in files if f.get("mimetype") == "image/jp2" and f.get("width")), None)
    if iiif:
        rend.append({"url": iiif + "/full/pct:100/0/default.jpg", "width": (jp2 or {}).get("width"),
                     "height": (jp2 or {}).get("height"), "quality": "iiif-full"})
    tif = next((f for f in files if f.get("mimetype") == "image/tiff"), None)
    if tif and not iiif:
        rend.append({"url": tif["url"], "width": None, "height": None, "quality": "tiff-master", "bytes": tif.get("size")})
    jpgs = [f for f in files if (f.get("mimetype") or "").startswith("image/jp") and f.get("mimetype") != "image/jp2"
            and f.get("width")]
    if jpgs:
        j = max(jpgs, key=lambda f: f["width"] * (f.get("height") or 0))
        rend.append({"url": j["url"], "width": j["width"], "height": j.get("height"), "quality": "largest-jpeg"})
    return [{**r, "url": r["url"].replace("http://", "https://")} for r in rend]


def loc(client: Client, query: str, kind: str, limit: int, commercial_only: bool) -> list[dict]:
    """Prints & Photographs search, then one item request per result for its rights advisory and files
    (the loc.gov API allows short bursts only; results are cached for 24 hours)."""
    d = client.json("https://www.loc.gov/photos/?" + urllib.parse.urlencode(
        {"q": query, "fo": "json", "c": str(min(max(limit * 2, 4), 25)), "fa": "online-format:image"}), "loc")
    out = []
    for r in d.get("results", []):
        if len(out) >= limit:
            break
        item_url = (r.get("id") or r.get("url") or "").replace("http://", "https://")
        if "/item/" not in item_url:
            continue
        try:
            it = loc_item(client, item_url)
        except Unavailable as e:
            out.append({"error": f"loc item {item_url}: {e}"})
            continue
        time.sleep(0.3)  # stay well inside the item endpoint's burst limit
        meta = it.get("item") or {}
        ra = meta.get("rights_advisory")
        ra = " ".join(ra) if isinstance(ra, list) else ra
        lic = loc_licence(ra, item_url)
        if commercial_only and lic["commercial_use"] != "yes":
            continue
        rend = loc_renditions(it)
        if not rend:
            continue
        repro = meta.get("reproduction_number")
        repro = repro[0] if isinstance(repro, list) and repro else repro
        repro = re.split(r"\s*\n\s*", repro.strip())[0] if isinstance(repro, str) and repro.strip() else None
        lic["credit_line"] = "Library of Congress, Prints & Photographs Division" + (f", {repro}" if repro else "")
        pid = item_url.rstrip("/").rsplit("/", 1)[-1]
        out.append(cand("loc", pid, "image", strip_html(meta.get("title") or r.get("title") or ""), item_url, rend, lic,
                        creator="; ".join(meta.get("contributor_names") or [])[:200] or None,
                        date=(meta.get("created_published") or [None])[0] if isinstance(meta.get("created_published"), list)
                        else meta.get("created_published"),
                        description=strip_html(" ".join(meta.get("notes") or []) if isinstance(meta.get("notes"), list)
                                               else meta.get("notes"))[:400],
                        detail_url=item_url.rstrip("/") + "/?fo=json",
                        thumbnail=next((u.split("#")[0] for u in (r.get("image_url") or [])), None),
                        evidence=f"loc.gov item record; rights advisory: {ra!r}; reproduction number {repro}"))
    return out


# ------------------------------------------------------------------ The Met Open Access

MET = "https://collectionapi.metmuseum.org/public/collection"


def met_licence(obj: dict) -> dict:
    """Open Access objects (isPublicDomain) are released under CC0; everything else has no image rights from the API."""
    if obj.get("isPublicDomain"):
        lic = classify_licence("cc0", "CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
        lic["name"] = "CC0 1.0 (The Met Open Access)"
        lic["restrictions"] = ((lic.get("restrictions") or "") + "; credit requested: The Metropolitan Museum of Art"
                               + (f", {obj['creditLine']}" if obj.get("creditLine") else "")).strip("; ")
        return lic
    return {"name": "The Met: not Open Access", "url": obj.get("objectURL"), "code": "met-restricted",
            "commercial_use": "unknown", "attribution_required": "unknown", "share_alike": False, "no_derivatives": False,
            "restrictions": "not released as Open Access; no image licence from the API"}


def met(client: Client, query: str, kind: str, limit: int, commercial_only: bool) -> list[dict]:
    """Search (v1.1, paginated) then one object request per hit; only Open Access objects carry downloadable images.
    The API gives no pixel size: the original's size is measured after download."""
    d = client.json(f"{MET}/v1.1/search?" + urllib.parse.urlencode({"q": query, "hasImages": "true",
                                                                     "limit": str(min(max(limit * 3, 6), 40))}), "met")
    out = []
    for oid in (d.get("objectIDs") or []):
        if len(out) >= limit:
            break
        try:
            obj = client.json(f"{MET}/v1/objects/{oid}", "met", action="detail")
        except Unavailable as e:
            out.append({"error": f"met object {oid}: {e}"})
            continue
        lic = met_licence(obj)
        if not obj.get("primaryImage") or (commercial_only and lic["commercial_use"] != "yes"):
            continue
        rend = [{"url": obj["primaryImage"], "width": None, "height": None, "quality": "original"}]
        if obj.get("primaryImageSmall"):
            rend.append({"url": obj["primaryImageSmall"], "width": None, "height": None, "quality": "web-large"})
        title = " — ".join(x for x in (obj.get("title"), obj.get("objectDate")) if x)
        out.append(cand("met", oid, "image", title, obj.get("objectURL") or f"https://www.metmuseum.org/art/collection/search/{oid}",
                        rend, lic, creator=obj.get("artistDisplayName") or obj.get("culture") or None,
                        description=" | ".join(x for x in (obj.get("medium"), obj.get("dimensions"), obj.get("creditLine")) if x)[:400],
                        detail_url=f"{MET}/v1/objects/{oid}", thumbnail=obj.get("primaryImageSmall"),
                        evidence=f"Met Collection API object {oid}: isPublicDomain={obj.get('isPublicDomain')}"))
        time.sleep(0.1)
    return out

SEARCH = {"openverse": openverse, "wikimedia": wikimedia, "nasa": nasa, "pexels": pexels, "pixabay": pixabay, "mixkit": mixkit,
          "loc": loc, "met": met}


def search(client: Client, provider: str, query: str, kind: str, limit: int = 8, commercial_only: bool = False) -> list[dict]:
    """provider may carry an upstream filter: 'openverse:wikimedia' searches Openverse's Wikimedia Commons index."""
    name, _, sub = provider.partition(":")
    if name not in SEARCH:
        raise Unavailable(f"unknown provider {provider!r}")
    if kind not in KINDS[name]:
        raise Unavailable(f"{name} has no {kind} search")
    if name == "openverse":
        return openverse(client, query, kind, limit, commercial_only, source=sub or None)
    return SEARCH[name](client, query, kind, limit, commercial_only)


def reverify(client: Client, c: dict) -> dict:
    """Re-read the licence from the provider at fetch time. Returns the current licence dict (raises Unavailable)."""
    p = c["provider"]
    if p == "openverse" and c.get("detail_url"):
        r = client.json(c["detail_url"], "openverse", action="detail", use_cache=False)
        lic = classify_licence(r.get("license"), None, r.get("license_url"))
        lic["attribution"] = r.get("attribution")
        return lic
    if p == "wikimedia":
        res = wikimedia(client, "", c["kind"] if c["kind"] in ("image", "video", "audio") else "audio", 1, False, title=c["provider_id"])
        if not res:
            raise Unavailable("wikimedia: file no longer available or now marked non-free")
        return res[0]["licence"]
    if p == "mixkit" and c["kind"] == "video":
        marker = mixkit_item(client, c["source_url"])["licence_marker"]
        if marker not in ("videoFree", "videoRestricted"):
            raise Unavailable("mixkit: item page no longer shows a licence marker")
        return provider_licence(marker)
    if p == "met":
        obj = client.json(c["detail_url"] or f"{MET}/v1/objects/{c['provider_id']}", "met", action="reverify", use_cache=False)
        return met_licence(obj)
    if p == "loc":
        meta = loc_item(client, c["source_url"], action="reverify", use_cache=False).get("item") or {}
        ra = meta.get("rights_advisory")
        lic = loc_licence(" ".join(ra) if isinstance(ra, list) else ra, c["source_url"])
        lic["credit_line"] = (c.get("licence") or {}).get("credit_line")
        return lic
    # Pexels, Pixabay and NASA apply one licence to all of their content; Mixkit audio listings carry it per page.
    return c["licence"]
