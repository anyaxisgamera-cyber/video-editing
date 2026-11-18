#!/usr/bin/env python3
"""Offline tests for asset discovery (scripts/providers.py), register merging, and font coverage (scripts/qc.py).

Provider parsing runs against trimmed copies of real API responses (fixtures/provider_payloads.json, recorded from
Openverse, NASA, The Met, and the Library of Congress). Pexels and Pixabay need account keys that were not available,
so their parsers run against payloads shaped like the examples in their public API documentation; those are marked
as documentation-derived below. HTTP robustness (Retry-After, truncated bodies, refused credentials, partial
downloads) is exercised against a local HTTP server. No external network access.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"  # the local test server is never proxied

import production as P  # noqa: E402
import providers as PV  # noqa: E402
import qc  # noqa: E402

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "provider_payloads.json").read_text(encoding="utf-8"))["responses"]


class FakeClient(PV.Client):
    """Serves recorded responses by URL; anything not recorded behaves like an unavailable site."""

    def __init__(self, extra: dict | None = None):
        super().__init__(None, None)
        self.routes = {v["url"].replace("http://", "https://"): v["body"] for v in FIXTURES.values()}
        self.routes.update(extra or {})
        self.seen: list[tuple[str, dict]] = []

    def json(self, url: str, provider: str, **kw) -> dict:
        self.seen.append((url, kw.get("headers") or {}))
        url = url.replace("http://", "https://")
        for u, body in self.routes.items():
            if url == u or url.split("?")[0] == u.split("?")[0] and "?" not in u:
                return body
        if url in self.routes:
            return self.routes[url]
        raise PV.Unavailable(f"{provider}: HTTP 404 for {url}")


def check_licences() -> None:
    L = PV.classify_licence
    table = [
        (("cc0", None, None), "yes", False), (("pdm", None, None), "yes", False), (("by", "CC BY 4.0", None), "yes", False),
        (("by-sa", "CC BY-SA 4.0", None), "conditional", True), (("by-nc", None, None), "no", False),
        (("by-nc-sa", None, None), "no", False), (("by-nd", None, None), "no", False), ((None, None, None), "unknown", False),
        ((None, None, "https://creativecommons.org/licenses/by-sa/3.0/"), "conditional", True),
        ((None, "Attribution 2.0 Generic", None), "yes", False),
    ]
    for args, commercial, sa in table:
        got = L(*args)
        assert got["commercial_use"] == commercial and got["share_alike"] == sa, (args, got)
    assert L("by-nd")["no_derivatives"] and L("by")["attribution_required"] == "yes"

    nkr = PV.loc_licence("No known restrictions on publication.", "https://www.loc.gov/item/x/")
    gov = PV.loc_licence("No known restrictions on images made by the U.S. Government; images copied from other sources "
                         "may be restricted.", "https://www.loc.gov/item/y/")
    other = PV.loc_licence("Rights status not evaluated.", "https://www.loc.gov/item/z/")
    assert (nkr["commercial_use"], gov["commercial_use"], other["commercial_use"]) == ("yes", "conditional", "unknown")
    assert PV.loc_licence(None, "u")["commercial_use"] == "unknown"

    pd = PV.met_licence(FIXTURES["met_object_587676"]["body"])
    closed = PV.met_licence(FIXTURES["met_object_486353"]["body"])
    assert pd["commercial_use"] == "yes" and pd["code"] == "cc0" and "Metropolitan" in pd["restrictions"], pd
    assert closed["commercial_use"] == "unknown", closed

    for p in ("pexels", "pixabay", "nasa", "videoFree", "musicFree", "sfxFree"):
        assert PV.provider_licence(p)["commercial_use"] == "yes"
    assert PV.provider_licence("videoRestricted")["commercial_use"] == "no"


def check_providers() -> None:
    c = FakeClient()
    ov = PV.openverse(c, "Fresnel lens", "image", 8, True, source="wikimedia")
    assert len(ov) == 3 and all(x["licence"]["commercial_use"] == "yes" for x in ov), ov
    assert all(not x["title"].startswith("File:") and x["width"] and x["detail_url"] for x in ov)
    q = dict(kv.split("=", 1) for kv in c.seen[-1][0].split("?", 1)[1].split("&"))
    assert q["license"] == "cc0%2Cpdm%2Cby" and q["source"] == "wikimedia", q  # commercial filter is sent upstream

    au = PV.openverse(c, "ambient", "music", 5, True)
    assert au and all(x["kind"] == "music" and 100 < x["duration"] < 600 for x in au), [x["duration"] for x in au]

    na = PV.nasa(c, "gibbous moon", "image", 6, False)
    assert len(na) == 2 and all(x["licence"]["code"] == "nasa" and x["manifest"] for x in na)
    rends = PV.nasa_renditions(c, {"manifest": FIXTURES["nasa_collection"]["url"]})
    assert [r["quality"] for r in rends] == ["orig", "large", "medium", "small"] and rends[0]["url"].startswith("https://")

    met = PV.met(c, "Map of Alexandria", "image", 4, True)
    good = [x for x in met if "error" not in x]
    assert [x["provider_id"] for x in good] == ["587676"], met  # 486353 is not Open Access; others unrecorded
    assert good[0]["renditions"][0]["quality"] == "original" and good[0]["width"] is None  # size measured on fetch
    assert any("error" in x for x in met), "unreachable objects must be reported, not dropped silently"

    lc = PV.loc(c, "lighthouse", "image", 10, True)  # the recording was made with c=20 (limit 10)
    good = [x for x in lc if "error" not in x]
    assert [x["provider_id"] for x in good] == ["2011633529"], lc
    g = good[0]
    assert g["licence"]["commercial_use"] == "yes" and "\n" not in g["licence"]["credit_line"], g["licence"]
    assert g["licence"]["credit_line"].endswith("LC-DIG-highsm-15336 (digital file from original)")
    assert g["renditions"][0]["quality"] == "iiif-full" and g["renditions"][0]["url"].endswith("/full/pct:100/0/default.jpg")
    assert (g["width"], g["height"]) == (6600, 5126) or g["width"] == 6600, g["renditions"]
    habs = PV.loc_renditions(FIXTURES["loc_item_ca1357"]["body"])
    assert [r["quality"] for r in habs] == ["tiff-master", "largest-jpeg"] and habs[1]["width"] == 1024, habs
    # the HABS advisory (U.S. Government works only) is excluded from commercial searches
    c2 = FakeClient({"https://www.loc.gov/photos/?q=habs&fo=json&c=4&fa=online-format%3Aimage":
                     {"results": [{"id": "http://www.loc.gov/item/ca1357/", "title": "Point Reyes"}]}})
    assert PV.loc(c2, "habs", "image", 2, True) == []
    assert PV.loc(c2, "habs", "image", 2, False)[0]["licence"]["commercial_use"] == "conditional"

    # keys: never guessed, never logged
    for name, var in (("pexels", "PEXELS_API_KEY"), ("pixabay", "PIXABAY_API_KEY")):
        os.environ.pop(var, None)
        try:
            PV.search(c, name, "lighthouse", "image", 3)
            raise AssertionError(f"{name} must refuse to run without {var}")
        except PV.Unavailable as e:
            assert var in str(e)
    # documentation-derived payloads (shape of the examples at pexels.com/api/documentation and pixabay.com/api/docs)
    os.environ["PEXELS_API_KEY"] = "test-pexels-key"
    pex = {"photos": [{"id": 2014422, "width": 3024, "height": 3024, "url": "https://www.pexels.com/photo/2014422/",
                       "photographer": "Joey Farina", "photographer_url": "https://www.pexels.com/@joey",
                       "alt": "Brown Rocks During Golden Hour",
                       "src": {"original": "https://images.pexels.com/photos/2014422/pexels-photo-2014422.jpeg",
                               "medium": "https://images.pexels.com/photos/2014422/pexels-photo-2014422.jpeg?h=350"}}]}
    cp = FakeClient({"https://api.pexels.com/v1/search?query=rocks&per_page=3": pex})
    r = PV.pexels(cp, "rocks", "image", 3, True)
    assert r[0]["width"] == 3024 and r[0]["licence"]["name"] == "Pexels License"
    assert cp.seen[-1][1] == {"Authorization": "test-pexels-key"}, "Pexels takes the bare key, no Bearer prefix"
    os.environ["PIXABAY_API_KEY"] = "test-pixabay-key"
    pix = {"total": 1, "totalHits": 1, "hits": [{"id": 195893, "pageURL": "https://pixabay.com/en/blossom-bloom-flower-195893/",
                                               "tags": "blossom, bloom, flower", "imageWidth": 4000, "imageHeight": 2250,
                                               "largeImageURL": "https://pixabay.com/get/ed6a99fd0a76647_1280.jpg",
                                               "user": "Josch13"}]}
    cx = FakeClient({"https://pixabay.com/api/?key=test-pixabay-key&q=blossom&per_page=3&safesearch=true": pix})
    r = PV.pixabay(cx, "blossom", "image", 3, True)
    assert r[0]["licence"]["name"] == "Pixabay Content License" and r[0]["width_full"] == 4000
    assert "test-pixabay-key" not in PV.redact(cx.seen[-1][0]) and "REDACTED" in PV.redact(cx.seen[-1][0])
    os.environ.pop("PEXELS_API_KEY"); os.environ.pop("PIXABAY_API_KEY")


class Handler(http.server.BaseHTTPRequestHandler):
    hits: dict[str, int] = {}

    def log_message(self, *a):  # keep test output quiet
        pass

    def do_GET(self):
        n = Handler.hits[self.path] = Handler.hits.get(self.path, 0) + 1
        if self.path == "/limited" and n == 1:
            self.send_response(429); self.send_header("Retry-After", "1"); self.end_headers(); return
        if self.path == "/limited-long":
            self.send_response(429); self.send_header("Retry-After", "3600"); self.end_headers(); return
        if self.path == "/denied":
            self.send_response(401); self.end_headers(); return
        if self.path == "/truncated" or (self.path == "/flaky" and n == 1):
            self.send_response(200); self.send_header("Content-Length", "1000"); self.end_headers()
            self.wfile.write(b'{"partial": tru'); return
        body = b'{"ok": true, "path": "' + self.path.encode() + b'"}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


def check_http(tmp: Path) -> None:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    log = tmp / "actions.jsonl"
    cl = PV.Client(tmp / "cache", log, max_wait=5)
    try:
        assert cl.json(base + "/limited", "test")["ok"] and Handler.hits["/limited"] == 2  # waited out Retry-After
        assert cl.json(base + "/limited", "test")["ok"] and Handler.hits["/limited"] == 2  # second read from cache
        for path, words in (("/limited-long", "Retry-After 3600"), ("/denied", "HTTP 401")):
            try:
                cl.json(base + path, "test", use_cache=False)
                raise AssertionError(path)
            except PV.Unavailable as e:
                assert words in str(e), e
        assert cl.json(base + "/flaky", "test", use_cache=False)["ok"]  # IncompleteRead is retried, not a crash
        dest = tmp / "dl" / "file.json"
        info = cl.download(base + "/ok", dest, "test")
        assert dest.exists() and info["bytes"] == dest.stat().st_size and len(info["sha256"]) == 64
        cl.max_wait = 0.5
        try:
            cl.download(base + "/truncated", tmp / "dl" / "bad.json", "test", retries=1)
            raise AssertionError("a truncated download must fail")
        except PV.Unavailable:
            pass
        assert not list((tmp / "dl").glob("bad.json*")), "no partial file may be left behind"
        try:
            cl.download("http://127.0.0.1:9/unreachable", tmp / "dl" / "x.bin", "test")
            raise AssertionError("an unreachable host must fail")
        except PV.Unavailable as e:
            assert "download failed" in str(e)
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        assert all("ts" in r and "url" in r for r in rows) and any(r.get("cached") for r in rows)
    finally:
        srv.shutdown()


def check_register_merge(tmp: Path) -> None:
    prod = tmp / "prod"
    P.write_json(P.register_path(prod), {"assets": [{"id": "a1", "status": "candidate"}]})
    stale = P.load_register(prod)  # a long-running command's snapshot
    P.save_register_entries(prod, [{"id": "a2", "status": "downloaded"}])  # another command meanwhile
    mine = next(e for e in stale["assets"] if e["id"] == "a1")
    mine["status"] = "downloaded"
    P.save_register_entries(prod, [mine])
    got = {e["id"]: e["status"] for e in P.load_register(prod)["assets"]}
    assert got == {"a1": "downloaded", "a2": "downloaded"}, got
    assert not list(P.register_path(prod).parent.glob(".*.tmp")), "atomic writes leave no temporary files"


def check_fonts() -> None:
    latin = next((p for p in (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),) if p.exists()), None)
    telugu = next((p for p in Path("/usr/share/fonts").rglob("*.ttf") if "telu" in p.name.lower()), None) \
        if Path("/usr/share/fonts").exists() else None
    if latin:
        assert qc.missing_glyphs(latin, ["Guardians of the coast"]) == []
        miss = qc.missing_glyphs(latin, ["తీరానికి కాపలాదారులు"])
        assert miss and all(0x0C00 <= ord(ch) <= 0x0C7F for ch in miss), miss  # boxes would render: detected
    if telugu:
        assert qc.missing_glyphs(telugu, ["తీరానికి కాపలాదారులు", "చంద్రుని కళలు"]) == [], telugu
    print(f"font coverage checked with {latin.name if latin else 'no Latin font'} and {telugu.name if telugu else 'no Telugu font'}")


def main() -> None:
    check_licences()
    check_providers()
    with tempfile.TemporaryDirectory(prefix="providers-test-") as raw:
        tmp = Path(raw)
        check_http(tmp)
        check_register_merge(tmp)
    check_fonts()
    print("providers test passed")


if __name__ == "__main__":
    main()
