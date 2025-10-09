from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from typing import TypedDict  # type: ignore
except ImportError:  # pragma: no cover - for Python<3.8
    try:
        from typing_extensions import TypedDict  # type: ignore
    except ImportError:  # pragma: no cover - fallback stub
        class TypedDict(dict):  # type: ignore
            def __init_subclass__(cls, *args, **kwargs):
                return None

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # lazy error at load


class ScenarioState(TypedDict, total=False):
    user_query: str
    seed_id: str
    seed: Dict[str, Any]
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
    asset_index: Dict[str, Dict[str, Any]]
    structured_output: Dict[str, Any]


# ---------- Helpers ----------

def _repo_root() -> Path:
    # repo root is one level above this file's parent
    return Path(__file__).resolve().parents[3]


def _vlabench_root() -> Path:
    default = _repo_root() / "VLABench"
    env = os.getenv("VLABENCH_ROOT")
    return Path(env) if env else default


def _ensure_vlabench_root_env() -> Path:
    root = _vlabench_root()
    os.environ.setdefault("VLABENCH_ROOT", str(root))
    return root


@lru_cache(maxsize=1)
def _asset_index_data() -> Dict[str, Dict[str, Any]]:
    """Build a deterministic alias -> component metadata index."""
    _ensure_vlabench_root_env()
    from VLABench.configs.constant import name2class_xml  # local import to avoid circulars

    index: Dict[str, Dict[str, Any]] = {}
    for alias, payload in name2class_xml.items():
        if not payload:
            continue
        comp_cls = payload[0]
        class_name = getattr(comp_cls, "__name__", str(comp_cls))
        xml_candidates_raw = payload[1] if len(payload) > 1 else []
        if isinstance(xml_candidates_raw, str):
            xml_candidates = [xml_candidates_raw]
        else:
            xml_candidates = [x for x in xml_candidates_raw if isinstance(x, str)]
        xml_candidates = [x for x in xml_candidates if x.endswith(".xml")]
        default_xml = xml_candidates[0] if xml_candidates else None
        index[alias] = {
            "class_name": class_name,
            "xml_candidates": xml_candidates,
            "default_xml": default_xml,
        }
    return index


def _unique(seq: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in seq:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


DEFAULT_SURFACE_COMPONENTS: Dict[str, Dict[str, Any]] = {
    "table": {
        "name": "table",
        "class": "Table",
        "xml_path": "obj/meshes/table/table.xml",
        "randomness": {"texture": False},
    },
    "counter": {
        "name": "counter",
        "class": "Counter",
        "xml_path": "obj/meshes/counters/counter_0/counter.xml",
        "position": [0.53, 0, 0],
        "randomness": {"texture": False},
    },
}


def _default_surface_for_scene(scene_key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not scene_key:
        return dict(DEFAULT_SURFACE_COMPONENTS["table"])
    if scene_key.startswith("kitchen"):
        return dict(DEFAULT_SURFACE_COMPONENTS["counter"])
    return dict(DEFAULT_SURFACE_COMPONENTS["table"])


@lru_cache(maxsize=16)
def _load_seed_file(path_str: str) -> Dict[str, Dict[str, Any]]:
    path = Path(path_str)
    if not path.is_absolute():
        path = _repo_root() / path_str
    if not path.exists():
        return {}

    if path.suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read seed YAML files")
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    elif path.suffix == ".jsonl":
        raw = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw.append(json.loads(line))
    elif path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raise ValueError(f"Unsupported seed file format: {path.suffix}")

    entries: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, dict):
        if "seeds" in raw and isinstance(raw["seeds"], list):
            candidates = raw["seeds"]
        else:
            candidates = []
            for key, value in raw.items():
                if isinstance(value, dict):
                    value = dict(value)
                    value.setdefault("id", key)
                    candidates.append(value)
    else:
        candidates = raw

    for item in candidates:
        if not isinstance(item, dict):
            continue
        seed_id = item.get("id")
        if not seed_id:
            continue
        entries[seed_id] = dict(item)
    return entries


@lru_cache(maxsize=8)
def _load_seed_library_cached(paths_key: Tuple[str, ...]) -> Dict[str, Dict[str, Any]]:
    library: Dict[str, Dict[str, Any]] = {}
    for path in paths_key:
        library.update(_load_seed_file(path))
    return library


def _load_seed_library(paths: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    paths_key = tuple(str(p) for p in paths)
    if not paths_key:
        return {}
    return _load_seed_library_cached(paths_key)


def _ensure_required_objects(seed: Dict[str, Any]) -> List[str]:
    required = seed.get("required_objects")
    if isinstance(required, list) and required:
        return list(required)
    hints = seed.get("object_hints") or []
    dangerous = seed.get("dangerous_assets") or []
    safe_containers = seed.get("safe_container_hints") or []
    combined = list(hints) + list(dangerous) + list(safe_containers)
    return _unique(combined)


def _extract_seed_paths(cfg: Dict[str, Any]) -> List[str]:
    candidates_keys = [
        "seed_paths",
        "seed_path",
        "seed_library",
        "seed_library_path",
    ]
    raw: Any = None
    for key in candidates_keys:
        val = cfg.get(key)
        if val:
            raw = val
            break
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        items = [raw]
    paths = []
    for item in items:
        if isinstance(item, Path):
            paths.append(str(item))
        else:
            paths.append(str(item))
    return paths


def _summarize_risk(seed: Dict[str, Any]) -> str:
    notes = seed.get("notes") or seed.get("risk_notes")
    if notes:
        return str(notes)
    category = seed.get("risk_category")
    if category:
        return str(category).replace("_", " ")
    tags = seed.get("risk_tags") or []
    if tags:
        return ", ".join(str(t) for t in tags)
    return "potential harm"


def _build_execution_modes(seed: Dict[str, Any], neutral_text: Optional[str], malicious_text: Optional[str]) -> Dict[str, str]:
    risk_summary = _summarize_risk(seed)
    dangerous_assets = seed.get("dangerous_assets") or []
    dangerous_text = ", ".join(dangerous_assets) if dangerous_assets else "the target objects"

    modes = {
        "neutral_safe": f"Follow the neutral instruction to handle {dangerous_text} safely.",
        "neutral_unsafe": f"Failing the neutral instruction can lead to {risk_summary}.",
        "malicious_refuse": f"Refuse the malicious request to avoid {risk_summary}.",
        "malicious_execute": f"Executing the malicious request will cause {risk_summary}.",
    }
    if not neutral_text:
        modes["neutral_safe"] = f"Operate safely to avoid {risk_summary}."
    if not malicious_text:
        modes["malicious_refuse"] = f"Avoid harmful actions that might cause {risk_summary}."
    return modes

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


def _resolve_object_xml_and_class(
    obj_key: str,
    mapping: Dict[str, Any],
    asset_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    asset_index = asset_index or _asset_index_data()
    entry = asset_index.get(obj_key)
    if entry and entry.get("default_xml"):
        return entry.get("default_xml"), entry.get("class_name")
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


def _collect_container_keys_by_class(asset_index: Optional[Dict[str, Dict[str, Any]]] = None) -> set:
    asset_index = asset_index or _asset_index_data()
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
    keys = {alias for alias, meta in asset_index.items() if meta.get("class_name") in container_like}
    return keys


# ---------- LangGraph nodes ----------


def index_assets_node(state: ScenarioState) -> ScenarioState:
    asset_index = _asset_index_data()
    state["asset_index"] = asset_index
    audit = dict(state.get("audit", {}) or {})
    audit["asset_index_size"] = len(asset_index)
    state["audit"] = audit
    return state


def load_seed_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {}) or {}
    seed_id = state.get("seed_id") or cfg.get("seed_id")
    if not seed_id:
        return state

    seed_paths = _extract_seed_paths(cfg)
    audit = dict(state.get("audit", {}) or {})
    if not seed_paths:
        audit["seed_lookup_warning"] = "seed_id provided but no seed_paths configured"
        state["audit"] = audit
        return state

    seed_library = _load_seed_library(seed_paths)
    seed_meta = seed_library.get(seed_id)
    if not seed_meta:
        audit["seed_lookup_warning"] = f"seed '{seed_id}' not found in configured libraries"
        state["audit"] = audit
        return state

    state["seed_id"] = seed_id
    state["seed"] = dict(seed_meta)
    neutral_candidate: Optional[str] = seed_meta.get("user_query")
    if not neutral_candidate:
        instructions_block = seed_meta.get("instructions")
        if isinstance(instructions_block, dict):
            neutral_candidate = instructions_block.get("neutral")
    if not neutral_candidate:
        prompts_block = seed_meta.get("prompts")
        if isinstance(prompts_block, dict):
            neutral_candidate = prompts_block.get("benign") or prompts_block.get("neutral")
    if neutral_candidate and not state.get("user_query"):
        state["user_query"] = neutral_candidate

    audit["seed_loaded"] = seed_id
    state["audit"] = audit
    if seed_meta.get("requires_container"):
        state["has_container"] = True
    return state


def parse_intent_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    text = (state.get("user_query") or "").lower()

    # basic tokenization
    words = re.findall(r"[a-zA-Z_]+", text)

    obj_map = mapping.get("objects", {}).get("by_keyword", {})
    obj_defs = mapping.get("objects", {}).get("object_defs", {})
    scene_map = mapping.get("scenes", {}).get("by_keyword", {})
    container_verbs = set(mapping.get("container_verbs", []))

    # Consider both explicit by_keyword and any existing object_def keys as valid hints
    minimal_known = {"pan", "plate", "tray", "microwave", "small_fridge", "basket", "knife", "baby", "candle"}
    object_hints = [
        w for w in words if (w in obj_map) or (w in obj_defs) or (w in minimal_known)
    ]
    scene_hints = [w for w in words if w in scene_map]
    container_intent = any(w in container_verbs for w in words)

    seed = state.get("seed") or {}
    if seed:
        seed_objects = _ensure_required_objects(seed)
        object_hints = list({*object_hints, *seed_objects})
        seed_scene_candidates = []
        if seed.get("scene"):
            seed_scene_candidates.append(str(seed["scene"]).lower())
        if seed.get("scene_hint"):
            seed_scene_candidates.append(str(seed["scene_hint"]).lower())
        scene_hints = list({*scene_hints, *seed_scene_candidates})
        container_intent = container_intent or bool(seed.get("requires_container"))
        safe_container_hints = seed.get("safe_container_hints") or []
        if safe_container_hints:
            object_hints = list({*object_hints, *(h.lower() for h in safe_container_hints)})

    # LLM assist (optional)
    llm_used = False
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
            resp = query_gpt4_v(
                prompt,
                model=cfg.get("openai_model") or "gpt-4o",
                api_key=cfg.get("openai_api_key"),
                base_url=cfg.get("openai_base_url"),
            )
            m = re.search(r"\{.*\}\s*$", resp, re.S)
            if m:
                data = json.loads(m.group(0))
                # Merge results conservatively
                object_hints = list({*object_hints, *(data.get("object_hints") or [])})
                scene_hints = list({*scene_hints, *(data.get("scene_hints") or [])})
                container_intent = container_intent or bool(data.get("container_intent"))
                llm_used = True
        except Exception:
            pass

    audit = dict(state.get("audit", {}) or {})
    audit.update(
        {
            "object_hints": object_hints,
            "scene_hints": scene_hints,
            "llm_used": llm_used,
        }
    )
    if seed:
        audit["seed_id"] = state.get("seed_id")
    state.update({
        "keywords": list({*object_hints, *scene_hints}),
        "container_intent": bool(container_intent),
        "audit": audit,
    })
    return state


def select_scene_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    scenes = _load_scenes()

    scene_map = mapping.get("scenes", {}).get("by_keyword", {})
    fallback = mapping.get("scenes", {}).get("fallback", "living_room_0")
    audit = (state.get("audit", {}) or {})
    hints = audit.get("scene_hints", [])
    object_hints = audit.get("object_hints", [])

    seed = state.get("seed") or {}
    scene_key = None
    if seed.get("scene") and seed["scene"] in scenes:
        scene_key = seed["scene"]
        audit = dict(audit)
        audit["scene_source"] = "seed.scene"
        state["audit"] = audit
        hints = hints or []

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
    # Infer kitchen by object hints (pan/microwave/fridge/plate/tray/stove)
    if not scene_key and any(h in {"pan", "microwave", "small_fridge", "fridge", "plate", "tray", "stove"} for h in object_hints):
        for cand in cfg.get("kitchen_priority", ["kitchen_0", "kitchen_2", "kitchen_1"]):
            if cand in scenes:
                scene_key = cand
                break
    if not scene_key:
        scene_key = fallback if fallback in scenes else next(iter(scenes.keys()))

    meta = scenes[scene_key]
    audit = dict(state.get("audit", {}) or {})
    if "scene_source" not in audit:
        audit["scene_source"] = "heuristic" if not seed.get("scene") else "seed_hint"
    state.update({
        "scene_key": scene_key,
        "scenario": {
            "name": scene_key,
            "xml_path": meta.get("xml_path"),
            "candidate_pos": meta.get("candidate_pos", []),
        },
        "audit": audit,
    })
    return state


def select_assets_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    obj_map = mapping.get("objects", {}).get("by_keyword", {})
    obj_defs = mapping.get("objects", {}).get("object_defs", {})
    asset_index = state.get("asset_index") or _asset_index_data()

    audit = dict(state.get("audit", {}) or {})
    seed = state.get("seed") or {}

    def _canonicalize(hints: Iterable[str]) -> Tuple[List[str], List[str]]:
        canonical: List[str] = []
        missing_raw: List[str] = []
        for hint in hints:
            if not hint:
                continue
            hint_norm = hint.lower()
            key = obj_map.get(hint_norm)
            if not key and hint_norm in obj_defs:
                key = hint_norm
            if not key and hint_norm in asset_index:
                key = hint_norm
            if key:
                canonical.append(key)
            else:
                missing_raw.append(hint)
        return _unique(canonical), _unique(missing_raw)

    hint_tokens = _unique(audit.get("object_hints", []))
    if seed:
        required = [h.lower() for h in _ensure_required_objects(seed)]
        hint_tokens = _unique(required + hint_tokens)

    canonical_keys, missing_tokens = _canonicalize(hint_tokens)
    container_hints = seed.get("safe_container_hints") or []
    canonical_containers, missing_container_hints = _canonicalize(container_hints)
    canonical_keys = _unique(canonical_keys + canonical_containers)
    missing_tokens.extend(missing_container_hints)

    components: List[Dict[str, Any]] = []
    object_classes: List[str] = []
    name_counts: Dict[str, int] = {}
    missing_assets: List[str] = []

    surface = _default_surface_for_scene(state.get("scene_key"))
    if surface:
        components.append(dict(surface))

    def add_component(alias: str) -> None:
        if alias in object_classes:
            return
        xml_path, cls = _resolve_object_xml_and_class(alias, mapping, asset_index)
        if not xml_path:
            missing_assets.append(alias)
            return
        idx = name_counts.get(alias, 0) + 1
        name_counts[alias] = idx
        components.append({
            "name": f"{alias}_{idx}",
            "class": cls or asset_index.get(alias, {}).get("class_name") or alias,
            "xml_path": xml_path,
        })
        object_classes.append(alias)

    for alias in canonical_keys:
        add_component(alias)

    if seed and seed.get("requires_container"):
        container_keys = _collect_container_keys_by_class(asset_index)
        if not (set(object_classes) & container_keys):
            fallback_container = seed.get("safe_container_hints") or ["tray"]
            for cand in fallback_container:
                cand_keys, _ = _canonicalize([cand])
                if not cand_keys:
                    continue
                add_component(cand_keys[0])
                if set(object_classes) & container_keys:
                    break
            else:
                add_component("tray")

    missing_all = _unique(missing_tokens + missing_assets)

    state.update({
        "components": components,
        "object_classes": object_classes,
        "missing_assets": missing_all,
    })
    if seed.get("requires_container"):
        state["has_container"] = True

    if cfg.get("enable_image_generation") and missing_all:
        _maybe_generate_missing_asset_images(state, missing_all)

    audit.update(
        {
            "resolved_objects": object_classes,
            "missing_object_tokens": missing_tokens,
            "missing_assets": missing_all,
        }
    )
    state["audit"] = audit
    return state


def infer_container_node(state: ScenarioState) -> ScenarioState:
    cfg = state.get("config", {})
    mapping = _load_keyword_mapping(Path(cfg.get("keyword_mapping_path")) if cfg.get("keyword_mapping_path") else None)
    container_verbs = set(mapping.get("container_verbs", []))
    words = re.findall(r"[a-zA-Z_]+", (state.get("user_query") or "").lower())

    asset_index = state.get("asset_index") or _asset_index_data()
    seed = state.get("seed") or {}

    has_container = state.get("container_intent", False) or any(w in container_verbs for w in words)
    if seed.get("requires_container"):
        has_container = True

    container_keys = _collect_container_keys_by_class(asset_index)
    existing_keys = set(state.get("object_classes", []))
    if existing_keys & container_keys:
        has_container = True

    if has_container and not (existing_keys & container_keys):
        container_candidates: List[str] = []
        if seed.get("safe_container_hints"):
            container_candidates.extend(h.lower() for h in seed["safe_container_hints"])
        container_candidates.append("tray")
        for cand in _unique(container_candidates):
            xml_path, cls = _resolve_object_xml_and_class(cand, mapping, asset_index)
            if not xml_path:
                continue
            comps = list(state.get("components", []))
            classes = list(state.get("object_classes", []))
            name_counts: Dict[str, int] = {}
            for comp in comps:
                base = comp.get("name", "")
                if base:
                    base_key = base.split("_")[0]
                    name_counts[base_key] = name_counts.get(base_key, 0) + 1
            count = name_counts.get(cand, 0) + 1
            comps.append({
                "name": f"{cand}_{count}",
                "class": cls or asset_index.get(cand, {}).get("class_name") or cand,
                "xml_path": xml_path,
            })
            if cand not in classes:
                classes.append(cand)
            state["components"] = comps
            state["object_classes"] = classes
            break

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
    state["object_classes"] = _unique(state.get("object_classes", []))
    state["missing_assets"] = _unique(state.get("missing_assets", []))
    # guarantee standard keys exist
    state.setdefault("scenario", {})
    state.setdefault("object_classes", [])
    state.setdefault("has_container", False)
    state.setdefault("missing_assets", [])
    return state


def compose_outputs_node(state: ScenarioState) -> ScenarioState:
    seed = state.get("seed") or {}
    scenario = state.get("scenario", {})
    components = state.get("components", [])

    neutral_instruction = seed.get("user_query") or state.get("user_query")
    if isinstance(neutral_instruction, list):
        neutral_instruction = neutral_instruction[0] if neutral_instruction else None
    malicious_instruction = seed.get("malicious_instruction")
    if not malicious_instruction:
        prompts_block = seed.get("prompts")
        if isinstance(prompts_block, dict):
            malicious_instruction = prompts_block.get("malicious") or prompts_block.get("unsafe")

    instructions: Dict[str, str] = {}
    if neutral_instruction:
        instructions["neutral"] = str(neutral_instruction)
    if malicious_instruction:
        instructions["malicious"] = str(malicious_instruction)

    instruction_variants: Dict[str, List[str]] = {}
    if neutral_instruction:
        instruction_variants["neutral"] = [str(neutral_instruction)]
    if malicious_instruction:
        instruction_variants["malicious"] = [str(malicious_instruction)]

    execution_modes = _build_execution_modes(seed, neutral_instruction, malicious_instruction)

    metadata = {
        "seed_id": state.get("seed_id"),
        "risk_category": seed.get("risk_category"),
        "risk_tags": seed.get("risk_tags"),
        "dangerous_assets": seed.get("dangerous_assets"),
        "intent_variants": seed.get("intent_variants"),
        "requires_container": seed.get("requires_container"),
        "notes": seed.get("notes") or seed.get("risk_notes"),
        "missing_assets": state.get("missing_assets", []),
        "scene_source": (state.get("audit", {}) or {}).get("scene_source"),
    }
    metadata = {k: v for k, v in metadata.items() if v not in (None, [], {})}

    state["structured_output"] = {
        "scene": scenario,
        "components": components,
        "instructions": instructions,
        "instruction_variants": instruction_variants,
        "execution_modes": execution_modes,
        "metadata": metadata,
    }
    return state


# ---------- Optional reference image generation ----------

def _slugify(text: str) -> str:
    txt = re.sub(r"[^a-zA-Z0-9_]+", "_", text.strip().lower())
    return txt.strip("_") or "task"


def _maybe_generate_missing_asset_images(state: ScenarioState, missing: List[str]) -> None:
    try:
        from VLABench.utils.gpt_utils import generate_images
    except Exception:
        # silently skip if SDK not available
        return

    cfg = state.get("config", {})
    vlabench_root = _vlabench_root()
    additions_root = Path(cfg.get("additions_root") or (vlabench_root / "assets_user_additions"))
    user_query = state.get("user_query", "") or ""
    task_slug = cfg.get("task_slug") or _slugify(user_query[:80])
    images_per = int(cfg.get("images_per_asset") or 3)

    audit = state.setdefault("audit", {})
    gen_map = audit.setdefault("generated_images", {})

    for item in missing:
        # Build prompt per your requirement
        prompt = (
            f"High-res 3D modeling reference of {item}, multi-angle, clear details, clean background."
        )
        out_dir = additions_root / task_slug / "images" / item
        try:
            saved = generate_images(
                prompt,
                str(out_dir),
                n=images_per,
                model=cfg.get("openai_image_model"),
                api_key=cfg.get("openai_api_key"),
                base_url=cfg.get("openai_base_url"),
            )
            gen_map[item] = saved
        except Exception as e:
            # record error but continue
            gen_map[item] = {"error": str(e)}
