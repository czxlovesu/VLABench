from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # lazy error at load


class ScenarioState(TypedDict, total=False):
    user_query: str
    keywords: List[str]
    container_intent: bool
    scene_key: str
    scenario: Dict[str, Any]
    components: List[Dict[str, Any]]
    object_classes: List[str]
    has_container: bool
    missing_assets: List[str]
    audit: Dict[str, Any]
    config: Dict[str, Any]


# ---------- Helpers ----------

def _repo_root() -> Path:
    # repo root is one level above this file's parent
    return Path(__file__).resolve().parents[3]


def _vlabench_root() -> Path:
    default = _repo_root() / "VLABench"
    env = os.getenv("VLABENCH_ROOT")
    return Path(env) if env else default


def _load_scenes() -> Dict[str, Any]:
    path = _vlabench_root() / "configs" / "scene_config.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_keyword_mapping(path: Optional[Path] = None) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load keyword_mapping.yaml")
    if path is None:
        path = _vlabench_root() / "configs" / "langgraph" / "keyword_mapping.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_constant_name2class_xml() -> Dict[str, Dict[str, Optional[str]]]:
    """Lightweight parser to extract key -> {class, xml_dir, sample_xml_literal} from constant.py"""
    const_path = _vlabench_root() / "configs" / "constant.py"
    text = const_path.read_text(encoding="utf-8")
    start = text.find("name2class_xml = {")
    if start == -1:
        return {}
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
        return {}
    block = text[start:end]

    entries: Dict[str, Dict[str, Optional[str]]] = {}
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith('#'):
            continue
        m = re.match(r"\s*(['\"]?)([A-Za-z0-9_]+)\1\s*:\s*(.+)", line)
        if not m:
            continue
        key = m.group(2)
        rhs = m.group(3)
        cls_match = re.search(r"components\.(\w+)", rhs)
        comp_class = cls_match.group(1) if cls_match else None
        xml_literal = None
        lit = re.search(r"['\"](obj/meshes/[^'\"]+\.xml)['\"]", rhs)
        if lit:
            xml_literal = lit.group(1)
        xml_dir = None
        dir_m = re.search(r"['\"](obj/meshes/[^'\"]+)['\"]", rhs)
        if dir_m:
            val = dir_m.group(1)
            if not val.endswith('.xml'):
                xml_dir = val
        entries[key] = {"class": comp_class, "xml_dir": xml_dir, "sample_xml_literal": xml_literal}
    return entries


def _scan_first_xml_under(xml_dir: str) -> Optional[str]:
    base = _vlabench_root() / "assets" / xml_dir
    if not base.exists():
        return None
    for p in base.rglob("*.xml"):
        return str(p.relative_to(_vlabench_root() / "assets"))
    return None


def _resolve_object_xml_and_class(obj_key: str, mapping: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    # Prefer mapping.object_defs.sample_xml
    defs = mapping.get("objects", {}).get("object_defs", {})
    ent = defs.get(obj_key)
    if ent:
        sample = ent.get("sample_xml")
        cls = ent.get("class")
        if sample:
            return sample, cls
    # Fallback to constant.py parsed
    const = _parse_constant_name2class_xml()
    meta = const.get(obj_key)
    if meta:
        if meta.get("sample_xml_literal"):
            return meta.get("sample_xml_literal"), meta.get("class")
        if meta.get("xml_dir"):
            sample = _scan_first_xml_under(meta["xml_dir"]) or None
            return sample, meta.get("class")
    # Hard-coded minimal dirs as last resort
    fallback_dirs = {
        "pan": "obj/meshes/tablewares/pans",
        "plate": "obj/meshes/tablewares/plates",
        "tray": "obj/meshes/containers/tray",
        "microwave": "obj/meshes/containers/microwaves",
        "small_fridge": "obj/meshes/containers/fridge/small_fridge",
        "basket": "obj/meshes/containers/basket",
        "knife": "obj/meshes/tablewares/knifes",
        "baby": "obj/meshes/characters/baby",
    }
    xml_dir = fallback_dirs.get(obj_key)
    if xml_dir:
        sample = _scan_first_xml_under(xml_dir)
        return sample, None
    return None, None


def _collect_container_keys_by_class() -> set:
    const = _parse_constant_name2class_xml()
    container_like = {
        "CommonContainer",
        "FlatContainer",
        "ContainerWithDrawer",
        "Microwave",
        "Vase",
        "Fridge",
        "CoffeeMachine",
        "Shelf",
        "Plate",
    }
    keys = {k for k, v in const.items() if v.get("class") in container_like}
    return keys


# ---------- LangGraph nodes ----------

def parse_intent_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    text = (state.get("user_query") or "").lower()

    # basic tokenization
    words = re.findall(r"[a-zA-Z_]+", text)

    obj_map = mapping.get("objects", {}).get("by_keyword", {})
    scene_map = mapping.get("scenes", {}).get("by_keyword", {})
    container_verbs = set(mapping.get("container_verbs", []))

    object_hints = [w for w in words if w in obj_map]
    scene_hints = [w for w in words if w in scene_map]
    container_intent = any(w in container_verbs for w in words)

    # LLM assist (optional)
    if cfg.get("enable_llm"):
        try:
            from VLABench.utils.gpt_utils import query_gpt4_v

            prompt = (
                "You are an extraction assistant. Given a user request, "
                "extract structured JSON with fields: scene_hints (list of words), "
                "object_hints (list of words), container_intent (true/false). "
                "Use only lowercase English keywords; do not invent assets.\n\n"
                f"User: {text}\n"
                "Respond with pure JSON only."
            )
            resp = query_gpt4_v(prompt)
            m = re.search(r"\{.*\}\s*$", resp, re.S)
            if m:
                data = json.loads(m.group(0))
                # Merge results conservatively
                object_hints = list({*object_hints, *(data.get("object_hints") or [])})
                scene_hints = list({*scene_hints, *(data.get("scene_hints") or [])})
                container_intent = container_intent or bool(data.get("container_intent"))
        except Exception:
            pass

    state.update({
        "keywords": list({*object_hints, *scene_hints}),
        "container_intent": bool(container_intent),
        "audit": {
            **state.get("audit", {}),
            "object_hints": object_hints,
            "scene_hints": scene_hints,
        },
    })
    return state


def select_scene_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    scenes = _load_scenes()

    scene_map = mapping.get("scenes", {}).get("by_keyword", {})
    fallback = mapping.get("scenes", {}).get("fallback", "living_room_0")
    hints = (state.get("audit", {}) or {}).get("scene_hints", [])

    scene_key = None
    # kitchen priority
    if any(h in ("kitchen",) for h in hints):
        for cand in cfg.get("kitchen_priority", ["kitchen_0", "kitchen_2", "kitchen_1"]):
            if cand in scenes:
                scene_key = cand
                break
    if not scene_key:
        for h in hints:
            key = scene_map.get(h)
            if key and key in scenes:
                scene_key = key
                break
    if not scene_key:
        scene_key = fallback if fallback in scenes else next(iter(scenes.keys()))

    meta = scenes[scene_key]
    state.update({
        "scene_key": scene_key,
        "scenario": {
            "name": scene_key,
            "xml_path": meta.get("xml_path"),
            "candidate_pos": meta.get("candidate_pos", []),
        },
    })
    return state


def select_assets_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    obj_map = mapping.get("objects", {}).get("by_keyword", {})

    object_hints: List[str] = list((state.get("audit", {}) or {}).get("object_hints", []))
    selected_keys: List[str] = []
    components: List[Dict[str, Any]] = []
    missing: List[str] = []

    # map hints -> object keys
    for w in object_hints:
        key = obj_map.get(w)
        if not key:
            missing.append(w)
            continue
        if key in selected_keys:
            continue
        xml_path, cls = _resolve_object_xml_and_class(key, mapping)
        if not xml_path:
            missing.append(w)
            continue
        name = f"{key}_1"
        components.append({"name": name, "class": cls or key, "xml_path": xml_path})
        selected_keys.append(key)

    object_classes = selected_keys.copy()

    state.update({
        "components": components,
        "object_classes": object_classes,
        "missing_assets": missing,
    })
    return state


def infer_container_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    container_verbs = set(mapping.get("container_verbs", []))
    words = re.findall(r"[a-zA-Z_]+", (state.get("user_query") or "").lower())

    has_container = state.get("container_intent", False) or any(w in container_verbs for w in words)
    # If already has a container-like component, set true
    container_keys = _collect_container_keys_by_class()
    existing_keys = set(state.get("object_classes", []))
    if existing_keys & container_keys:
        has_container = True

    # Add default tray when container is needed but none selected
    if has_container and not (existing_keys & container_keys):
        xml_path, cls = _resolve_object_xml_and_class("tray", mapping)
        if xml_path:
            comps = state.get("components", [])
            comps.append({"name": "tray_1", "class": cls or "FlatContainer", "xml_path": xml_path})
            classes = state.get("object_classes", [])
            if "tray" not in classes:
                classes.append("tray")
            state["components"] = comps
            state["object_classes"] = classes

    state["has_container"] = bool(has_container)
    return state


def finalize_output_node(state: ScenarioState) -> ScenarioState:
    # ensure uniqueness of names and minimal fields present
    seen = set()
    unique_components = []
    for comp in state.get("components", []):
        name = comp.get("name")
        base = name
        idx = 1
        while name in seen:
            name = f"{base}_{idx}"
            idx += 1
        comp = dict(comp)
        comp["name"] = name
        unique_components.append(comp)
        seen.add(name)

    state["components"] = unique_components
    # guarantee standard keys exist
    state.setdefault("scenario", {})
    state.setdefault("object_classes", [])
    state.setdefault("has_container", False)
    state.setdefault("missing_assets", [])
    return state

