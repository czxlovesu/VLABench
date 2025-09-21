from __future__ import annotations

from typing import Any, Dict

from pathlib import Path

from .nodes.scenario_nodes import (
    ScenarioState,
    parse_intent_node,
    select_scene_node,
    select_assets_node,
    infer_container_node,
    finalize_output_node,
)


def build_app(config: Dict[str, Any] | None = None):
    """Build and return a LangGraph app for ScenarioAgent.

    If langgraph is not installed, raises an ImportError with guidance.
    """
    try:
        from langgraph.graph import StateGraph
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "LangGraph is required. Install via: pip install langgraph"
        ) from e

    graph = StateGraph(ScenarioState)

    # Nodes
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("select_scene", select_scene_node)
    graph.add_node("select_assets", select_assets_node)
    graph.add_node("infer_container", infer_container_node)
    graph.add_node("finalize_output", finalize_output_node)

    # Edges
    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "select_scene")
    graph.add_edge("select_scene", "select_assets")
    graph.add_edge("select_assets", "infer_container")
    graph.add_edge("infer_container", "finalize_output")

    app = graph.compile()

    # attach config to app via closure
    def invoke(state: Dict[str, Any]):
        st = dict(state)
        st.setdefault("config", {})
        if config:
            # overlay provided config
            st["config"] = {**st.get("config", {}), **config}
        return app.invoke(st)

    app.invoke_with_config = invoke  # type: ignore[attr-defined]
    return app


def default_config() -> Dict[str, Any]:
    here = Path(__file__).resolve()
    # File layout: VLABench/langgraph_agents/scenario_graph.py
    # VLABench dir = parents[1]
    mapping_path = here.parents[1] / "configs" / "langgraph" / "keyword_mapping.yaml"
    return {
        "enable_llm": False,
        "keyword_mapping_path": str(mapping_path),
        # kitchen priority as discussed
        "kitchen_priority": ["kitchen_0", "kitchen_2", "kitchen_1"],
        # optional reference image generation for missing assets
        "enable_image_generation": False,
        "images_per_asset": 3,
        "additions_root": str((here.parents[1] / "assets_user_additions")),
        # OpenAI credentials (may be overridden by CLI or api_keys.yaml)
        "openai_api_key": None,
        "openai_base_url": None,
        "openai_model": None,
        "openai_image_model": None,
    }
