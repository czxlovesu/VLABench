#!/usr/bin/env python3
"""
Build or update VLABench/configs/langgraph/keyword_mapping.yaml

- Reuses existing lists:
  - scenes from VLABench/configs/scene_config.json
  - objects from VLABench/configs/constant.py (name2class_xml)

- Does NOT import heavy modules. Parses constant.py textually to extract:
  - object key
  - component class (e.g., CommonContainer, FlatContainer)
  - xml_dir or explicit sample xml path

- Optionally scans assets to pick a sample xml file under xml_dir.

Usage:
  VLABENCH_ROOT=/path/to/VLABench python scripts/build_keyword_mapping.py
"""

from __future__ import annotations

import os
import re
import sys
import json
from pathlib import Path
from typing import Dict, Any, Tuple

try:
    import yaml  # type: ignore
except Exception:
    print("PyYAML not found. Install it to write YAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_scene_index(vlabench_root: Path) -> Dict[str, Any]:
    scene_path = vlabench_root / "configs" / "scene_config.json"
    with open(scene_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)
    return scenes


def extract_name2class_xml(constant_py: Path) -> Dict[str, Dict[str, Any]]:
    """
    Textually parse name2class_xml from constant.py to avoid importing heavy deps.
    Returns mapping: key -> {class: str, xml_dir: str|None, sample_xml_literal: str|None}
    """
    text = constant_py.read_text(encoding="utf-8")
    start = text.find("name2class_xml = {")
    if start == -1:
        raise RuntimeError("name2class_xml not found in constant.py")
    # crude brace matching to find end of dict
    i = start + len("name2class_xml = ")
    depth = 0
    end = None
    while i < len(text):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    if end is None:
        raise RuntimeError("Failed to match closing brace for name2class_xml")
    block = text[start:end]

    entries: Dict[str, Dict[str, Any]] = {}
    # Iterate over potential entry lines (top-level keys)
    for line in block.splitlines():
        # Skip comments/empty
        if not line.strip() or line.strip().startswith('#'):
            continue
        # Match:  "key": [components.Class, get_object_list(os.path.join(xml_root, "obj/meshes/..."))],
        m = re.match(r"\s*(['\"]?)([A-Za-z0-9_]+)\1\s*:\s*(.+)", line)
        if not m:
            continue
        key = m.group(2)
        rhs = m.group(3)
        cls_match = re.search(r"components\.(\w+)", rhs)
        comp_class = cls_match.group(1) if cls_match else None
        # Try to capture literal xml path or directory hint
        # literal sample xml path: 'obj/meshes/... .xml'
        xml_literal = None
        lit = re.search(r"['\"](obj/meshes/[^'\"]+\.xml)['\"]", rhs)
        if lit:
            xml_literal = lit.group(1)
        # directory hint inside get_object_list(..., "obj/meshes/..." )
        xml_dir = None
        dir_m = re.search(r"['\"](obj/meshes/[^'\"]+)['\"]", rhs)
        if dir_m:
            dir_val = dir_m.group(1)
            # if it was a file path, skip; keep dir without trailing .xml
            if not dir_val.endswith('.xml'):
                xml_dir = dir_val

        entries[key] = {
            "class": comp_class,
            "xml_dir": xml_dir,
            "sample_xml_literal": xml_literal,
        }
    return entries


def pick_sample_xml(vlabench_root: Path, xml_dir: str | None, literal: str | None) -> str | None:
    if literal:
        return literal
    if not xml_dir:
        return None
    base = vlabench_root / "assets" / xml_dir
    if not base.exists():
        return None
    # Walk dir and pick first .xml file
    for p in base.rglob("*.xml"):
        rel = p.relative_to(vlabench_root / "assets")
        return str(rel)
    return None


def load_skill_verbs(skill_lib: Path) -> list[str]:
    text = skill_lib.read_text(encoding="utf-8")
    verbs = set()
    for m in re.finditer(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text, flags=re.M):
        name = m.group(1)
        if name in {"place", "pour", "open_door", "close_door", "open_drawer"}:
            verbs.add(name.replace("_door", "").replace("_drawer", "").replace("open_", "open").replace("close_", "close"))
    # add common NL verbs to detect container semantics
    verbs.update({"put", "place", "into", "in", "inside"})
    return sorted(verbs)


def main():
    repo_root = Path(__file__).resolve().parents[1]
    vlabench_root = Path(os.getenv("VLABENCH_ROOT", repo_root / "VLABench"))
    if not (vlabench_root / "configs").exists():
        print(f"VLABENCH_ROOT seems wrong: {vlabench_root}", file=sys.stderr)
        sys.exit(1)

    scenes = load_scene_index(vlabench_root)
    const_entries = extract_name2class_xml(vlabench_root / "configs" / "constant.py")
    skill_verbs = load_skill_verbs(vlabench_root / "utils" / "skill_lib.py")

    # Build object_defs with sample xml hints
    object_defs = {}
    for key, meta in const_entries.items():
        sample = pick_sample_xml(vlabench_root, meta.get("xml_dir"), meta.get("sample_xml_literal"))
        object_defs[key] = {
            "class": meta.get("class"),
            "xml_dir": meta.get("xml_dir"),
            "sample_xml": sample,
        }

    # Starter by_keyword maps (identity suggestions for a minimal subset only)
    minimal_object_hints = [
        "pan", "plate", "tray", "microwave", "small_fridge", "basket", "knife", "baby"
    ]
    # Always include minimal hints to enable rule fallback resolution
    by_keyword_objects = {k: k for k in minimal_object_hints}

    # Scenes available list
    scenes_available = {}
    for s_name, s_meta in scenes.items():
        scenes_available[s_name] = {
            "xml_path": s_meta.get("xml_path"),
            "candidate_pos_count": len(s_meta.get("candidate_pos", [])),
        }

    # Minimal scene keyword mapping
    by_keyword_scenes = {
        "kitchen": "kitchen_0" if "kitchen_0" in scenes else next(iter(scenes.keys()), "living_room_0"),
        "living_room": "living_room_0" if "living_room_0" in scenes else next(iter(scenes.keys()), "living_room_0"),
        "lab": "lab_0" if "lab_0" in scenes else next(iter(scenes.keys()), "living_room_0"),
        "study": "studyroom_0" if "studyroom_0" in scenes else next(iter(scenes.keys()), "living_room_0"),
    }

    data = {
        "scenes": {
            "by_keyword": by_keyword_scenes,
            "available": scenes_available,
            "fallback": "living_room_0",
        },
        "objects": {
            "by_keyword": by_keyword_objects,
            "object_defs": object_defs,
        },
        "container_verbs": skill_verbs,
    }

    out_dir = vlabench_root / "configs" / "langgraph"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "keyword_mapping.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=True, allow_unicode=True)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
