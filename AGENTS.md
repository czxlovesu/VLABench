# Repository Guidelines

## Project Structure & Module Organization
- Core package: `VLABench/` — environments (`envs/`), tasks (`tasks/`), robots (`robots/`), configs (`configs/`), utils (`utils/`).
- Scripts: `scripts/` (dataset, conversion, evaluation). Shell helpers in `sh/` (data_generation, evaluation).
- Assets/configs: `VLABench/assets/` and `VLABench/configs/` (JSON/YAML).
- Docker: `docker/` for containerized setup. Docs in `docs/` and `QuickStart.md`.
- Third‑party: `third_party/` (e.g., `openpi/`), optional `lerobot/` submodule.
- Tests/examples: repo‑root `test_*.py` and `lerobot/tests/` (if submodule initialized).

## Build, Test, and Development Commands
- Create env and install: `pip install -r requirements.txt && pip install -e .`
- Download assets: `python scripts/download_assets.py`
- Set env (examples): `export VLABENCH_ROOT=$(pwd)/VLABench` and for headless GL: `export MUJOCO_GL=egl`
- Run visual smoke test: `python test_task_visual.py high_temp_harm`
- Agent data‑flow check: `python test_agents_dataflow.py`
- Evaluate VLM: `python scripts/evaluate_vlm.py --vlm_name Qwen2_VL --few-shot-num 1`

## Coding Style & Naming Conventions
- Python 3.10+. Use 4‑space indentation, PEP8 style, line length ≤ 100.
- Naming: modules/functions `snake_case`, classes `CamelCase`, constants `UPPER_SNAKE`.
- Tasks/robots register via `VLABench.utils.register`; keep new files under `VLABench/tasks/` or `VLABench/robots/` and update configs when needed.
- Optional formatting: run `black .` and `isort .` locally; `ruff` is welcome but not required.

## Testing Guidelines
- Prefer lightweight, executable tests in repo root as `test_*.py` (see existing examples).
- For new tasks: include a visual check (e.g., `env.render(...)`) and a minimal rollout.
- Optional: add `pytest` tests if useful; name files `test_*.py` and keep them fast and deterministic.
- Include instructions to reproduce (env vars, assets needed) in test docstrings.

## Commit & Pull Request Guidelines
- Commits: clear, imperative subject (e.g., "Add task: select_fruit_semantic"), concise body, reference issues (`#123`) when applicable.
- PRs: describe scope, motivation, and testing steps; link issues; include screenshots/renders for env/task changes (e.g., saved images from `test_task_visual.py`). Note any config additions under `VLABench/configs/`.

## Security & Configuration Tips
- Do not commit secrets. For GPT evaluations, set `OPENAI_API_KEY`/`OPENAI_BASE_URL` via environment.
- Keep `VLABENCH_ROOT` consistent with your checkout; many loaders read from `VLABench/configs/`.
- Large assets live outside Git; use `scripts/download_assets.py` and dataset README instructions.
