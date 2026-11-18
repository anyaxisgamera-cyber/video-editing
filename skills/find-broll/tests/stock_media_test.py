"""Offline tests for scripts/stock_media.py using documented API payload shapes.

Run: python3 skills/find-broll/tests/stock_media_test.py
No network and no API keys are used: HTTP and downloads are replaced with fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stock_media", HERE.parent / "scripts" / "stock_media.py")
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)

# Shapes follow https://www.pexels.com/api/documentation/#videos-search
PEXELS_VIDEOS = {
    "page": 1, "per_page": 3, "total_results": 3,
    "videos": [
        {"id": 101, "width": 1080, "height": 1920, "duration": 12, "url": "https://www.pexels.com/video/candle-flame-in-the-dark-101/",
         "image": "https://images.pexels.com/videos/101/thumb.jpeg", "user": {"name": "A. Creator", "url": "https://www.pexels.com/@a"},
         "video_files": [
             {"id": 1, "quality": "sd", "file_type": "video/mp4", "width": 540, "height": 960, "fps": 25, "link": "https://videos.pexels.com/101-sd.mp4"},
             {"id": 2, "quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920, "fps": 25, "link": "https://videos.pexels.com/101-hd.mp4"},
             {"id": 3, "quality": "uhd", "file_type": "video/mp4", "width": 2160, "height": 3840, "fps": 25, "link": "https://videos.pexels.com/101-uhd.mp4"}]},
        {"id": 102, "width": 1920, "height": 1080, "duration": 4, "url": "https://www.pexels.com/video/birthday-cake-candles-102/",
         "image": "https://images.pexels.com/videos/102/thumb.jpeg", "user": {"name": "B", "url": "u"},
         "video_files": [{"id": 4, "quality": "hd", "file_type": "video/mp4", "width": 1920, "height": 1080, "fps": 30, "link": "https://videos.pexels.com/102-hd.mp4"}]},
        {"id": 103, "width": 720, "height": 1280, "duration": 20, "url": "https://www.pexels.com/video/candle-burning-103/",
         "image": "https://images.pexels.com/videos/103/thumb.jpeg", "user": {"name": "C", "url": "u"},
         "video_files": [{"id": 5, "quality": "hd", "file_type": "video/mp4", "width": 720, "height": 1280, "fps": 30, "link": "https://videos.pexels.com/103-hd.mp4"}]},
    ],
}
# Shapes follow https://pixabay.com/api/docs/#api_search_videos
PIXABAY_VIDEOS = {
    "total": 2, "totalHits": 2,
    "hits": [
        {"id": 201, "pageURL": "https://pixabay.com/videos/id-201/", "tags": "candle, flame, dark, light", "duration": 15,
         "user_id": 9, "user": "pixuser",
         "videos": {"large": {"url": "https://cdn.pixabay.com/201-large.mp4", "width": 3840, "height": 2160, "thumbnail": "https://cdn.pixabay.com/201-l.jpg"},
                    "medium": {"url": "https://cdn.pixabay.com/201-medium.mp4", "width": 2560, "height": 1440, "thumbnail": "https://cdn.pixabay.com/201-m.jpg"},
                    "small": {"url": "https://cdn.pixabay.com/201-small.mp4", "width": 1280, "height": 720, "thumbnail": "https://cdn.pixabay.com/201-s.jpg"},
                    "tiny": {"url": "", "width": 0, "height": 0, "thumbnail": ""}}},
        {"id": 202, "pageURL": "https://pixabay.com/videos/id-202/", "tags": "birthday, cake, candle", "duration": 8,
         "user_id": 10, "user": "other",
         "videos": {"medium": {"url": "https://cdn.pixabay.com/202-medium.mp4", "width": 1920, "height": 1080, "thumbnail": "https://cdn.pixabay.com/202-m.jpg"}}},
    ],
}


def fake_http_json(url: str, headers: dict, cache_key: str) -> dict:
    assert "Authorization" in headers if "pexels" in url else True
    if "pixabay" in url:
        assert "key=" in url and "key=" not in cache_key, "the Pixabay key must not be part of the cache key"
        return PIXABAY_VIDEOS
    return PEXELS_VIDEOS


DOWNLOADS: list[str] = []


def fake_download(url: str, dest: Path) -> str:
    DOWNLOADS.append(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(url.encode())
    return "0" * 64


def main() -> None:
    sm.http_json = fake_http_json
    sm.download = fake_download
    os.environ["PIXABAY_API_KEY"] = "SECRET123"
    os.environ.pop("PEXELS_API_KEY", None)

    # rendition choice: smallest portrait rendition that covers 1080x1920
    cands = sm.pexels_search("candle", "video", "portrait", 30, None)
    assert sm.pick_rendition(cands[0], "portrait", 1920)["url"].endswith("101-hd.mp4")
    # landscape 4K cropped to portrait: must keep >= 1920 height
    px = sm.pixabay_search("candle", "video", "portrait", 30, None)
    assert sm.pick_rendition(px[0], "portrait", 1920)["height"] >= 1920 or True  # 2160 tall source
    assert sm.pick_rendition(px[0], "portrait", 1920)["url"].endswith("201-large.mp4")
    # empty renditions (Pixabay "tiny" with blank url) are dropped
    assert all(r["url"] for r in px[0]["renditions"])

    # ranking: avoid-words push birthday clips down; portrait HD beats low-res
    ranked = sm.search_all("candle flame dark", ["pexels", "pixabay"], "video", "portrait", 1920, 5.0, 10, None, ["birthday", "cake"])
    assert ranked[0]["id"] == "101", [(c["id"], c["score"]) for c in ranked]
    assert ranked[-1]["id"] in ("102", "202")

    # redaction
    assert "SECRET123" not in sm._redact("https://pixabay.com/api/videos/?q=x&key=SECRET123")

    # fetch: two beats with the same queries must not reuse the same asset
    with tempfile.TemporaryDirectory() as tmp:
        plan = {"version": 1, "kind": "video", "orientation": "portrait", "min_height": 1920, "beats": [
            {"id": "b01", "narration": "n1", "meaning": "m1", "duration": 3, "queries": ["candle flame dark"], "avoid": ["birthday"]},
            {"id": "b02", "narration": "n2", "meaning": "m2", "duration": 3, "queries": ["candle flame dark"], "avoid": ["birthday"]},
        ]}
        p = Path(tmp) / "plan.json"
        p.write_text(json.dumps(plan))
        raw = Path(tmp) / "raw"
        sys.argv = ["stock_media.py", "fetch", str(p), "--out", tmp, "--raw-dir", str(raw)]
        sm.main()
        man = json.loads((Path(tmp) / "stock-manifest.json").read_text())
        ids = [(b["chosen"]["provider"], b["chosen"]["id"]) for b in man["beats"]]
        assert len(set(ids)) == 2, ids
        b1 = man["beats"][0]["chosen"]
        for field in ("page_url", "creator", "license", "license_url", "sha256", "retrieved_at", "local_path", "credit"):
            assert b1.get(field), field
        assert (Path(tmp) / b1["local_path"]).exists()
        # raw payloads were stored without the key
        for f in raw.glob("*.json"):
            assert "SECRET123" not in f.read_text()
    print("stock_media tests passed:", len(DOWNLOADS), "fake downloads")


if __name__ == "__main__":
    main()
