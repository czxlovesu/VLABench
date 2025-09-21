#!/usr/bin/env python3
"""
Run the LangGraph ScenarioAgent from a natural-language prompt.

Usage:
  export VLABENCH_ROOT=$(pwd)/VLABench
  python scripts/run_scenario_agent.py --query "verify hot pan touching baby"

Options:
  --enable-llm    Enable LLM keyword extraction if OPENAI_* is configured.
  --mapping PATH  Path to keyword_mapping.yaml (defaults inside repo).
"""

from __future__ import annotations

import argparse
import json

from VLABench.langgraph_agents.scenario_graph import build_app, default_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Natural language description")
    parser.add_argument("--enable-llm", action="store_true", help="Enable LLM assist")
    parser.add_argument("--mapping", type=str, default=None, help="keyword_mapping.yaml path")
    args = parser.parse_args()

    cfg = default_config()
    if args.enable_llm:
        cfg["enable_llm"] = True
    if args.mapping:
        cfg["keyword_mapping_path"] = args.mapping

    app = build_app(cfg)
    out = app.invoke_with_config({"user_query": args.query})
    print(json.dumps({
        "scenario": out.get("scenario"),
        "components": out.get("components"),
        "object_classes": out.get("object_classes"),
        "has_container": out.get("has_container"),
        "missing_assets": out.get("missing_assets", []),
    }, indent=2))


if __name__ == "__main__":
    main()

