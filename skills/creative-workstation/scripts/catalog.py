#!/usr/bin/env python3
"""Media library + asset catalogue.

Every asset that enters a project is recorded in ``<library>/catalog.json`` with:
source URL, local path, format, dimensions or duration, license, usage restrictions,
category, checksum and the date it was added. Nothing is "assumed free": an entry
without a license is flagged by ``validate`` and refused by ``require-cleared``.

    python3 catalog.py init  /path/to/media-library
    python3 catalog.py add   /path/to/media-library FILE --category video-clips \
        --source-url URL --license "Mixkit Stock Video Free License" \
        --restrictions "No standalone redistribution" [--title T] [--tags a,b]
    python3 catalog.py scan  /path/to/media-library      # probe files missing from the catalog
    python3 catalog.py validate /path/to/media-library   # missing files, unlicensed, stale probes
    python3 catalog.py report /path/to/media-library     # writes CATALOG.md
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CATEGORIES = [
    "photos", "transparent-png", "icons", "logos", "video-clips", "backgrounds",
    "3d-assets", "fonts", "music", "sound-effects",
]
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".heic", ".heif", ".gif", ".bmp"}
VECTOR_EXT = {".svg"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}

# Licenses known to permit commercial use in an edited video (verified text kept in references/).
COMMERCIAL_OK = {
    "original": "Created by this workstation; no third-party rights",
    "Mixkit Stock Video Free License": "Commercial + non-commercial; no attribution required; see Mixkit User Terms",
    "Mixkit Sound Effects Free License": "Commercial use in an End Product; no standalone redistribution",
    "Mixkit Stock Music Free License": "Web/social/VOD/podcasts/ads; NOT TV/radio, CD/DVD, video games; no remix into music-only tracks",
    "CC0-1.0": "Public-domain dedication (trademarks in logos still apply)",
    "ISC": "Permissive software license",
    "MIT": "Permissive software license",
    "Apache-2.0": "Permissive software license",
    "OFL-1.1": "SIL Open Font License: free to use/embed; do not sell the font by itself",
}
PERSONAL_ONLY = {"Mixkit Stock Video Restricted License"}


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def probe(path: Path) -> dict:
    """Inspect the real payload; never infer from the filename."""
    ext = path.suffix.lower()
    info: dict = {"format": ext.lstrip(".") or "dir", "bytes": path.stat().st_size if path.is_file() else None}
    if path.is_dir():  # image sequence (e.g. Blender turntable)
        frames = sorted(path.glob("*.png"))
        info.update({"format": "png-sequence", "frames": len(frames)})
        if frames:
            info.update(probe(frames[0]) | {"format": "png-sequence", "frames": len(frames)})
            info["bytes"] = sum(f.stat().st_size for f in frames)
        meta = path / "meta.json"
        if meta.exists():
            info["sequence_meta"] = json.loads(meta.read_text())
        return info
    if ext in IMAGE_EXT:
        try:
            from PIL import Image
            try:
                import pillow_heif  # noqa: F401
                pillow_heif.register_heif_opener()
            except Exception:
                pass
            with Image.open(path) as im:
                info.update({"width": im.width, "height": im.height, "mode": im.mode,
                             "has_alpha": im.mode in ("RGBA", "LA") or "transparency" in im.info})
                if info["has_alpha"]:
                    alpha = im.convert("RGBA").getchannel("A")
                    lo, hi = alpha.getextrema()
                    info["alpha_range"] = [lo, hi]
                    info["truly_transparent"] = lo < 255
        except Exception as exc:  # pragma: no cover - reported, not fatal
            info["probe_error"] = str(exc)
    elif ext in VECTOR_EXT:
        txt = path.read_text(errors="ignore")[:4000]
        import re
        vb = re.search(r'viewBox="([\d.\s-]+)"', txt)
        if vb:
            parts = [float(v) for v in vb.group(1).split()]
            info.update({"viewBox": parts, "width": parts[2], "height": parts[3]})
    elif ext in VIDEO_EXT | AUDIO_EXT:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                             capture_output=True, text=True)
        if out.returncode == 0:
            d = json.loads(out.stdout)
            info["duration"] = round(float(d.get("format", {}).get("duration", 0) or 0), 3)
            for s in d.get("streams", []):
                if s.get("codec_type") == "video" and "width" not in info:
                    num, den = (s.get("avg_frame_rate") or "0/1").split("/")
                    info.update({"width": s.get("width"), "height": s.get("height"), "video_codec": s.get("codec_name"),
                                 "fps": round(float(num) / float(den), 3) if float(den) else None})
                if s.get("codec_type") == "audio" and "audio_codec" not in info:
                    info.update({"audio_codec": s.get("codec_name"), "sample_rate": int(s.get("sample_rate", 0)),
                                 "channels": s.get("channels")})
        else:
            info["probe_error"] = out.stderr.strip()[:300]
    elif ext in FONT_EXT:
        try:
            from PIL import ImageFont
            f = ImageFont.truetype(str(path), 20)
            info["font_name"] = " ".join(x for x in f.getname() if x)
        except Exception as exc:
            info["probe_error"] = str(exc)
    return info


class Catalog:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / "catalog.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            "schema": "creative-workstation/catalog@1", "created": now(), "assets": []}

    def save(self) -> None:
        self.data["updated"] = now()
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    def by_path(self, rel: str) -> dict | None:
        return next((a for a in self.data["assets"] if a["local_path"] == rel), None)

    def add(self, file: Path, category: str, source_url: str, license: str, restrictions: str = "",
            title: str = "", tags: list[str] | None = None, attribution: str = "", extra: dict | None = None,
            source_page: str = "") -> dict:
        if category not in CATEGORIES:
            raise SystemExit(f"unknown category {category!r}; use one of {CATEGORIES}")
        file = file.resolve()
        try:
            rel = str(file.relative_to(self.root))
        except ValueError:
            raise SystemExit(f"{file} is outside the library {self.root}; copy it into {category}/ first")
        entry = self.by_path(rel) or {}
        is_new = not entry
        entry.update({
            "id": entry.get("id") or f"{category}/{file.stem}",
            "title": title or entry.get("title") or file.stem.replace("-", " "),
            "category": category,
            "local_path": rel,
            "source_url": source_url,
            "source_page": source_page or entry.get("source_page", ""),
            "license": license,
            "commercial_use": "yes" if license in COMMERCIAL_OK else ("personal-only" if license in PERSONAL_ONLY else "unverified"),
            "license_notes": COMMERCIAL_OK.get(license, ""),
            "usage_restrictions": restrictions,
            "attribution": attribution,
            "tags": tags or entry.get("tags", []),
            "probe": probe(file),
            "sha256": sha256(file) if file.is_file() else None,
            "added": entry.get("added") or now(),
        })
        if extra:
            entry.setdefault("extra", {}).update(extra)
        if is_new:
            self.data["assets"].append(entry)
        return entry

    def validate(self) -> list[str]:
        problems = []
        for a in self.data["assets"]:
            p = self.root / a["local_path"]
            if not p.exists():
                problems.append(f"MISSING  {a['local_path']}")
            if not a.get("license"):
                problems.append(f"NO-LICENSE  {a['local_path']}")
            if not a.get("source_url"):
                problems.append(f"NO-SOURCE  {a['local_path']}")
            if a.get("commercial_use") == "unverified":
                problems.append(f"UNVERIFIED-LICENSE  {a['local_path']}  ({a.get('license')})")
            if a["category"] == "transparent-png" and not a.get("probe", {}).get("truly_transparent", False):
                problems.append(f"NOT-TRANSPARENT  {a['local_path']}")
        return problems

    def report(self) -> Path:
        lines = ["# Media library catalogue", "", f"Library: `{self.root}`  ", f"Updated: {now()}  ",
                 f"Assets: {len(self.data['assets'])}", ""]
        for cat in CATEGORIES:
            items = [a for a in self.data["assets"] if a["category"] == cat]
            if not items:
                continue
            lines += [f"## {cat} ({len(items)})", "",
                      "| Asset | Format | Size / duration | License | Commercial | Restrictions | Source |",
                      "|---|---|---|---|---|---|---|"]
            for a in items:
                pr = a.get("probe", {})
                dims = f"{pr.get('width')}x{pr.get('height')}" if pr.get("width") else ""
                if pr.get("duration"):
                    dims = (dims + " " if dims else "") + f"{pr['duration']}s"
                if pr.get("frames"):
                    dims += f" x{pr['frames']}f"
                src = a["source_url"]
                src_md = f"[link]({src})" if src.startswith("http") else src
                lines.append(f"| `{a['local_path']}` | {pr.get('format','')} | {dims} | {a['license']} | "
                             f"{a['commercial_use']} | {a.get('usage_restrictions','')} | {src_md} |")
            lines.append("")
        out = self.root / "CATALOG.md"
        out.write_text("\n".join(lines) + "\n")
        return out


def cmd_init(root: Path) -> None:
    for c in CATEGORIES:
        (root / c).mkdir(parents=True, exist_ok=True)
    cat = Catalog(root)
    cat.save()
    print(json.dumps({"library": str(root), "categories": CATEGORIES}, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("library", type=Path)
    s = sub.add_parser("add"); s.add_argument("library", type=Path); s.add_argument("file", type=Path)
    s.add_argument("--category", required=True, choices=CATEGORIES)
    s.add_argument("--source-url", required=True); s.add_argument("--license", required=True)
    s.add_argument("--restrictions", default=""); s.add_argument("--title", default="")
    s.add_argument("--tags", default=""); s.add_argument("--attribution", default="")
    s.add_argument("--source-page", default="")
    s = sub.add_parser("scan"); s.add_argument("library", type=Path)
    s = sub.add_parser("validate"); s.add_argument("library", type=Path)
    s = sub.add_parser("report"); s.add_argument("library", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "init":
        cmd_init(a.library)
        return 0
    cat = Catalog(a.library)
    if a.cmd == "add":
        e = cat.add(a.file, a.category, a.source_url, a.license, a.restrictions, a.title,
                    [t for t in a.tags.split(",") if t], a.attribution, source_page=a.source_page)
        cat.save()
        print(json.dumps(e, indent=2))
    elif a.cmd == "scan":
        known = {x["local_path"] for x in cat.data["assets"]}
        unknown = []
        for c in CATEGORIES:
            for p in sorted((cat.root / c).glob("*")):
                rel = str(p.relative_to(cat.root))
                if rel not in known and p.name != "meta.json" and not p.name.startswith("."):
                    unknown.append({"path": rel, "probe": probe(p)})
        print(json.dumps({"uncatalogued": unknown}, indent=2))
        return 1 if unknown else 0
    elif a.cmd == "validate":
        probs = cat.validate()
        print("\n".join(probs) if probs else f"OK: {len(cat.data['assets'])} assets, all with source + license")
        return 1 if probs else 0
    elif a.cmd == "report":
        print(cat.report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
