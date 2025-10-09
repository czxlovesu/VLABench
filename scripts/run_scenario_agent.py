#!/usr/bin/env python3
"""
Run the LangGraph ScenarioAgent from a natural-language prompt.

Usage:
  export VLABENCH_ROOT=$(pwd)/VLABench
  python scripts/run_scenario_agent.py --query "verify hot pan touching baby"
  python scripts/run_scenario_agent.py --seed MCH01

Options:
  --enable-llm        Enable LLM keyword extraction if OPENAI_* is configured.
  --mapping PATH      Path to keyword_mapping.yaml (defaults inside repo).
  --api-keys PATH     YAML with OpenAI creds (default: VLABench/configs/langgraph/api_keys.yaml)
  --debug             Print debug/audit info.
  --generate-images   Generate reference images for missing assets (OpenAI Images API).
  --images-per N      Number of images per missing asset (default 3).
  --task-slug NAME    Override task slug for output folder naming.
  --seed ID           Scenario seed identifier defined in configs/langgraph/seeds/.
  --seed-path PATH    Additional seed metadata file (repeatable).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from VLABench.langgraph_agents.scenario_graph import build_app, default_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=False, help="Natural language description")
    parser.add_argument("--enable-llm", action="store_true", help="Enable LLM assist")
    parser.add_argument("--mapping", type=str, default=None, help="keyword_mapping.yaml path")
    parser.add_argument("--debug", action="store_true", help="Print debug/audit info")
    parser.add_argument("--generate-images", action="store_true", help="Generate reference images for missing assets")
    parser.add_argument("--images-per", type=int, default=3, help="Number of images per missing asset")
    parser.add_argument("--task-slug", type=str, default=None, help="Override task slug for output folder")
    parser.add_argument("--api-keys", type=str, default=None, help="Path to api_keys.yaml")
    parser.add_argument("--seed", type=str, default=None, help="Seed identifier for deterministic scenario")
    parser.add_argument("--seed-path", action="append", default=None, help="Optional seed metadata file (can repeat)")
    args = parser.parse_args()

    if not args.query and not args.seed:
        parser.error("Either --query or --seed must be provided")

    cfg = default_config()
    if args.enable_llm:
        cfg["enable_llm"] = True
    if args.mapping:
        cfg["keyword_mapping_path"] = args.mapping
    if args.generate_images:
        cfg["enable_image_generation"] = True
        cfg["images_per_asset"] = args.images_per
    if args.task_slug:
        cfg["task_slug"] = args.task_slug
    if args.seed_path:
        cfg["seed_paths"] = args.seed_path

    # Load API keys YAML if provided or exists at default location
    if args.api_keys is not None:
        api_path = args.api_keys
    else:
        api_path = "VLABench/configs/langgraph/api_keys.yaml"
    try:
        import os
        import yaml
        # If a directory is provided, try common locations inside it
        if os.path.isdir(api_path):
            candidates = [
                os.path.join(api_path, "configs/langgraph/api_keys.yaml"),
                os.path.join(api_path, "VLABench/configs/langgraph/api_keys.yaml"),
            ]
            api_path = next((c for c in candidates if os.path.exists(c)), api_path)
        if os.path.exists(api_path) and os.path.isfile(api_path):
            with open(api_path, "r", encoding="utf-8") as f:
                api_cfg = yaml.safe_load(f) or {}
            # Common keys with fallbacks for your file
            cfg["openai_api_key"] = (
                api_cfg.get("OPENAI_API_KEY")
                or api_cfg.get("OPENAI_API_KEY_GPT4O")
                or api_cfg.get("OPENAI_API_KEY_GPT5")
                or cfg.get("openai_api_key")
            )
            cfg["openai_base_url"] = api_cfg.get("OPENAI_BASE_URL") or cfg.get("openai_base_url")
            # Model defaults: prefer explicit, else gpt-4o if GPT4O key present
            cfg["openai_model"] = (
                api_cfg.get("OPENAI_MODEL")
                or ("gpt-4o" if api_cfg.get("OPENAI_API_KEY_GPT4O") else cfg.get("openai_model"))
            )
            cfg["openai_image_model"] = api_cfg.get("OPENAI_IMAGE_MODEL") or cfg.get("openai_image_model") or "gpt-image-1"
    except Exception:
        pass

    app = build_app(cfg)
    input_state: Dict[str, Any] = {}
    if args.query:
        input_state["user_query"] = args.query
    if args.seed:
        input_state["seed_id"] = args.seed
    out = app.invoke_with_config(input_state)
    result = {
        "scenario": out.get("scenario"),
        "components": out.get("components"),
        "object_classes": out.get("object_classes"),
        "has_container": out.get("has_container"),
        "missing_assets": out.get("missing_assets", []),
        "structured_output": out.get("structured_output"),
    }
    if args.debug:
        result["audit"] = out.get("audit", {})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
