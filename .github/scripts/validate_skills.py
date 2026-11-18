#!/usr/bin/env python3
"""Fail when any skill's SKILL.md frontmatter is not valid YAML or breaks the Agent Skills constraints.

`npx skills add . --list` only warns and skips invalid skills, so CI would otherwise pass while a skill is
undiscoverable (a "Key: value" phrase inside an unquoted description is enough to break the YAML).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
errors = []
skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
for path in skills:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append(f"{path}: missing frontmatter")
        continue
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        errors.append(f"{path}: invalid YAML frontmatter: {str(exc).splitlines()[0]}")
        continue
    name, desc = meta.get("name"), meta.get("description")
    if name != path.parent.name:
        errors.append(f"{path}: name {name!r} does not match directory {path.parent.name!r}")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(name)) or len(str(name)) > 64:
        errors.append(f"{path}: name must be lowercase letters, digits and hyphens, at most 64 characters")
    if not isinstance(desc, str) or not desc.strip():
        errors.append(f"{path}: description missing")
    elif len(desc) > 1024:
        errors.append(f"{path}: description is {len(desc)} characters (limit 1024)")
    for link in re.findall(r"\]\(((?!https?:|#)[^)#]+)", text):
        if not (path.parent / link).exists():
            errors.append(f"{path}: broken link {link}")
for e in errors:
    print("ERROR", e)
print(f"{len(skills)} skills checked, {len(errors)} problem(s)")
sys.exit(1 if errors else 0)
