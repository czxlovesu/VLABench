# ScenarioAgent & TaskAgent Rebuild Plan

## 快速使用指南（如何阅读与复制）
- **这份文档做什么**：聚焦 LangGraph 自动化路线，分解 ScenarioAgent/TaskAgent 的节点职责与落地 checklist。如果你在推进 Codex 补丁路线，请改看 `task_generation_prompt_guidelines.md`。
- **如何获取内容**：常规情况下直接打开本文件即可；若终端提示文件缺失，请参考 `doc_sync_quickstart.md` 的“文档角色速览”和“一键生成脚本”。
- **阅读顺序建议**：先看“现状诊断”和“需求合理性评估”了解缺口，再按“落地开发指南”逐项拆分任务。

> 与 Codex 路线配套时，只需把这里的 LangGraph 步骤总结成 bullet，再附上提示词文档中的模板，让模型或同事清楚两条路线分别负责**自动化管线**与**手工补丁**。

> FAQ：ScenarioAgent 可以在节点里访问仓库文件吗？可以。LangGraph 节点就是普通的 Python 函数，你可以在其中使用 `pathlib.Path`/`os` 等库去读取 `VLABench/assets/`、`VLABench/configs/` 里的文件，只需确保在节点返回的新状态里写入（或缓存）你需要的结果。

## 当前目标概述
- 以手工构造的 `seed` 为输入，ScenarioAgent 需要产出一个可在 VLABench 中落地的“场景版本”。每个版本只负责**最小资产模板**：危险物体、受害对象/干扰物，以及默认桌面（table/counter）。桌面属于默认环境组件，无需额外“安全支撑”。
- 容器在 VLABench 中视为普通资产。ScenarioAgent 仅根据 seed 的 `object_hints` / `safe_container_hints` 摆放对应容器，不再尝试做“安全/危险”分类。
- TaskAgent 读取 ScenarioAgent 的输出并生成符合 VLABench 生态的 Python 任务代码，使其能够被 `LM4ManipBaseTask` 等基类加载并运行。
- 每个 seed 需要衍生**一个任务文件**，在配置中保留 `instruction_variants` 与四种 `execution_modes`（`neutral_safe`、`neutral_unsafe`、`malicious_refuse`、`malicious_execute`），用于 VLA/VLM 行为评估。
- 中性指令强调颜色/方位等正向描述；恶意指令保持真实语境但只写入 metadata，不作为可执行指令。

## 现状诊断
1. **ScenarioAgent 输出偏离 VLABench 资产体系**
   - 当前节点链路只依赖关键词映射和 `constant.py` 的静态解析，在缺失 XML 资产或类映射时以兜底目录和硬编码方式补全，导致组件与实际可用资产不匹配（如 tray 回退逻辑）。【F:VLABench/langgraph_agents/nodes/scenario_nodes.py†L291-L347】
   - 场景选择逻辑基于关键词/对象启发式，而不是面向 seed 的确定性映射，容易与真实 seed 预期不符。【F:VLABench/langgraph_agents/nodes/scenario_nodes.py†L235-L276】

2. **TaskAgent 生成的任务未遵循原生任务的配置流**
   - 目前直接把 ScenarioAgent 的组件列表硬编码进 ConfigManager，缺少 `BenchTaskConfigManager` 默认的资产采样、条件/指令构建逻辑，因此 camera、桌面、容器等默认设置全部缺失。【F:VLABench/langgraph_agents/task_agent.py†L117-L212】【F:VLABench/tasks/config_manager.py†L14-L166】
   - 生成代码没有调用注册系统与配置 JSON 配合，导致 `LM4ManipBaseTask` 在加载任务时无法复用摄像机、workspace 等既有配置。【F:VLABench/langgraph_agents/task_agent.py†L162-L233】【F:VLABench/tasks/dm_task.py†L22-L200】

3. **缺少端到端校验**
   - 原生任务通过 `BenchTaskConfigManager` 自动抽样场景、组件并由 `LM4ManipBaseTask` 设置摄像机；我们没有把生成任务跑过 `test_task_visual.py`/`test_task_trajectory.py` 等冒烟用例，问题无法及早暴露。【F:VLABench/tasks/dm_task.py†L76-L200】

## 项目理解（VLABench 的“正确姿势”）
- Task 配置由 `BenchTaskConfigManager` 负责，统一从 `task_config.json` 读取引擎与基础组件，再根据任务资产池采样目标实体/容器，并输出给 `LM4ManipBaseTask`。【F:VLABench/tasks/config_manager.py†L33-L166】
- 任务类通过 `@register.add_task` 注册，继承 `PrimitiveTask` 等基类，仅重写少量行为（例如专家技能序列）。【F:VLABench/tasks/hierarchical_tasks/primitive/select_fruit_series.py†L8-L113】
- `LM4ManipBaseTask` 构建流程：加载配置管理器 → 读取场景 XML → 加载组件 → 初始化摄像机；任何偏离该流程的自定义代码都会破坏默认视角与实体布局。【F:VLABench/tasks/dm_task.py†L22-L200】

## 需求合理性评估
- **默认桌面沿用原生任务**：`configs/task_config.json` 中的 `table_surface` 与 `counter_surface` 已被所有 primitive 任务复用，因此 ScenarioAgent 仅需确认场景引用默认桌面即可，无需额外加“安全支撑”。【F:VLABench/configs/task_config.json†L12-L118】
- **容器作为普通资产**：原生任务通过 `load_containers`/`load_init_containers` 将托盘、碗等加入场景，从不区分安全等级。将容器视为普通实体更贴近现有资产加载逻辑。【F:VLABench/tasks/config_manager.py†L96-L138】
- **每 seed 一份任务文件**：原生 bench 中每个 primitive 任务独立注册并拥有稳定的 config manager；延续该做法，能保证指令/执行模式、metadata 在任务级别自洽。【F:VLABench/tasks/hierarchical_tasks/primitive/select_fruit_series.py†L8-L113】
- **四种执行模式**：安全基准评测依赖于 neutral/malicious × safe/unsafe 的组合，以验证模型在风险识别与拒绝上的能力；在 config 中显式保留这些模式更易于 TaskAgent 与评估脚本对接。【F:VLABench/langgraph_agents/task_agent.py†L162-L212】

以上假设都与现有 VLABench 运行机制保持一致，因而开发方案具有可行性。

## 细化需求
1. **Seed → 场景映射规范（部分完成）**
   - 每个 seed 必须显式声明：目标场景 key、必需对象、容器需求、潜在风险描述，以支持 ScenarioAgent 做确定性匹配。
   - 提供 seed 元数据仓库（YAML/JSON）供代理读取，减少对模糊关键词的依赖。

2. **ScenarioAgent 能力目标（已完成）**
   - 支持从 seed 元数据读取“场景版本”基础信息，并在需要时补充缺失资产（例如默认桌面、必要的 support 物体）。
   - 输出格式必须包含以下块：
     - `scene`：确定的场景 key（优先来自 seed 的 `scene_hint`）。
     - `assets`：最小资产模板，含危险物、受害者/干扰物、桌面（默认 table/counter），若 `requires_container=True` 则直接摆放容器资产。
     - `instructions`：至少包含 `neutral` 与 `malicious` 文字。中性版本加入位置/颜色提示，恶意版本忠实记录 seed 语境。
     - `instruction_variants`：面向 TaskAgent 的结构化版本，保存 neutral/malicious 字段。
     - `execution_modes`：四种模式的目标行为描述，ScenarioAgent 需根据 seed 生成对应解释。
     - `metadata`：保留 `risk_category`、`dangerous_assets`、`risk_tags`、`intent_variants` 等字段，便于后续评估。
   - **仓库资产索引能力**：增加“资产索引”节点，在流程最前面把 `VLABENCH_ROOT`（或基于 `Path(__file__)` 推导的仓库根目录）传入，通过遍历 `VLABench/assets/` 与 `configs/constant.py` 生成一个 `{别名: {"xml": ..., "class": ...}}` 的缓存，写入 `state["asset_index"]`，供后续节点 O(1) 查找。

3. **TaskAgent 能力目标（未完成）**
   - 读取 ScenarioAgent 的结构化输出后，产出：
     - `generated_tasks/<task_name>.json`（或等价数据结构），写入 `scene`、`components`、`dangerous_assets`、`instruction_variants`、`execution_modes`、`metadata` 等字段。
     - 最小 Python 补丁（必要时），通过继承原生模板在 `build_from_config` 或 config manager 中消费上述 deterministic config，而非重新拼装摄像机/桌面。
   - 生成代码需继续沿用注册系统，可被 `register.load_task` 正常加载，同时在 config 中保留四种执行模式以匹配评测脚本。

4. **验证流程（未完成）**
   - 对每个生成任务运行 `python test_task_visual.py <task_name>` 和 `python test_task_trajectory.py <task_name>` 作为回归。
   - 为 ScenarioAgent/TaskAgent 增加单元或集成测试，确保 seed→task 流水线稳定。

## 落地开发指南
1. **整理 seed 数据**
   - 建立 `VLABench/langgraph_agents/seeds/`（或 `configs/langgraph/seeds/`）目录，使用 YAML 存储每个 seed：
     ```yaml
     id: malicious_usb_copy
     scene: kitchen_2
     required_objects: ["usb", "laptop", "tray"]
     requires_container: true
     prompts:
       malicious: "..."
       benign: "..."
     risk_notes: "..."
     ```
   - 编写加载工具函数，供 ScenarioAgent 首节点直接读取而不是依赖模糊关键词。

2. **改造 ScenarioAgent**
   - 在 `parse_intent_node` 前增加一个 seed 识别/读取节点：若输入 seed id，则加载对应配置；否则回退到关键词逻辑。
   - `select_scene_node` 应优先使用 seed 中的 `scene` 字段，仅当 seed 未指明时才使用关键词推断。【F:VLABench/langgraph_agents/nodes/scenario_nodes.py†L235-L276】
   - `select_assets_node` 根据 seed 的 `required_objects` 生成 deterministic 列表，只有缺少时再调用 `_resolve_object_xml_and_class`；同时补充桌面、背景等默认组件（可从 `task_config.json` 读取）。【F:VLABench/langgraph_agents/nodes/scenario_nodes.py†L291-L347】【F:VLABench/tasks/config_manager.py†L33-L166】
   - 新增 `compose_outputs_node`（或同等节点），负责把场景/资产/seed 元数据拼装成结构化输出：
     - `scene`、`assets`：复用上述节点结果；
     - `instructions` 与 `instruction_variants`：neutral 版需要指出目标容器位置或颜色提示；malicious 版保持 seed 原文；
     - `execution_modes`：为四种模式生成一句话解释（例如 neutral_safe = 正常完成任务、neutral_unsafe = 中性指令执行失败造成风险、malicious_refuse = 拒绝恶意指令、malicious_execute = 按恶意指令执行后果描述）；
     - `metadata`：携带 `risk_category`、`risk_tags`、`dangerous_assets`、`intent_variants` 等。
   - 输出结构调整为 ConfigManager 可消费的 deterministic config（`scene`、`components`、`instructions`、`execution_modes`、`metadata`）。
   - **LangGraph 中使用资产索引节点的方式**：
     1. 在 `build_app` 时先添加 `graph.add_node("index_assets", index_assets_node)`，并把其设置为起点（`graph.set_entry_point("index_assets")`），随后将其输出路由到 `parse_intent`。
     2. `index_assets_node(state)` 内部可以：
        ```python
        from pathlib import Path
        import os

        def index_assets_node(state: ScenarioState) -> ScenarioState:
            repo_root = Path(os.environ.get("VLABENCH_ROOT", Path(__file__).resolve().parents[3]))
            asset_root = repo_root / "VLABench" / "assets"
            xml_map = {}
            for xml_path in asset_root.rglob("*.xml"):
                xml_map[xml_path.stem] = {
                    "xml_path": xml_path.relative_to(repo_root).as_posix(),
                    "class_name": name2class_xml.get(xml_path.stem),
                }
            state["asset_index"] = xml_map
            return state
        ```
     3. 后续节点直接读取 `state["asset_index"]`（若 key 缺失则 fallback 到现有 `_resolve_object_xml_and_class`）。这样既保留 LangGraph 的状态共享优势，又能把“访问仓库目录”的成本集中在一个节点里。

3. **重写 TaskAgent 流程**
   - 读取 ScenarioAgent 输出的结构化字典：
     - 写入 `generated_tasks/<task_name>.json`（或等价数据结构），字段对齐 `BenchTaskConfigManager.get_task_config`：`task.scene`、`task.components`、`task.dangerous_assets`、`task.instruction_variants`、`task.execution_modes`、`task.metadata`。
     - `task.instruction_variants` 中至少包含 `neutral`/`malicious` 键，分别引用 ScenarioAgent 的提示。
     - `task.execution_modes` 需要包含四种模式，每个值对应模型期望行为描述（safe/unsafe）。
   - 若必须生成 Python 代码，优先继承现有任务模板：
     - 根据 seed 指定的任务类型选择基类（如 `PrimitiveTask`）。
     - ConfigManager 子类仅覆写指令/条件生成逻辑，从 deterministic config 中读取 ScenarioAgent 的输出；摄像机、桌面、容器由父类与 config JSON 处理。【F:VLABench/tasks/hierarchical_tasks/primitive/select_fruit_series.py†L8-L113】
   - 提供生成后的注册补丁（`@register.add_task` 与 `@register.add_config_manager`），并引用 deterministic config 文件而非硬编码组件列表。

4. **测试与验证**
   - 对 ScenarioAgent：编写集成测试，给定 seed 输入，校验输出组件的 `xml_path` 都存在于 `assets/`，且 `class` 出自 `name2class_xml`。【F:VLABench/configs/constant.py†L55-L120】
   - 对 TaskAgent：生成任务后运行视觉/轨迹测试脚本，确保摄像机视角与容器配置正确。【F:VLABench/tasks/dm_task.py†L76-L200】
   - 在 CI/本地提供一键脚本：`python scripts/run_scenario_agent.py --seed ...` → `python scripts/run_task_agent.py --config ...` → `python test_task_visual.py ...`。

5. **迭代策略**
   - Phase 1：纯 deterministic（无 LLM），保证所有 seed 覆盖的任务均可运行。
   - Phase 2：在保证 deterministic 基线的前提下，引入 LLM 用于补全未知资产或生成说明文字，但任何 LLM 结果都要先过资产/配置验证再落地。

通过以上步骤，可让 ScenarioAgent 和 TaskAgent 输出与 VLABench 原生任务完全兼容的配置与代码，从而避免摄像机、容器等基础设置出错，并为后续自动化评测打下稳定基线。
