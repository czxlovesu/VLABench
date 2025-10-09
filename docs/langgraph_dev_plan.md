# ScenarioAgent & TaskAgent Rebuild Plan

## 快速使用指南（如何阅读与复制）
- **目的**：本文件描述 LangGraph 方案的整体修复路线；与 Codex 直接改写任务代码的策略是并行推进的另一条线索。
- **如何复制内容**：在命令行中执行 `sed -n '1,120p' docs/langgraph_dev_plan.md`（或使用你本地编辑器）即可选中需要的段落并复制到你的协作文档/提示词中。
- **如果命令报错**：确认当前工作目录是仓库根目录（`pwd` 应该显示 `.../VLABench`），再执行 `ls docs` 验证文件是否已同步；若不存在，请先 `git pull` 或切换到包含该文件的分支。
- **推荐用法**：
  1. 先阅读“现状诊断”“细化需求”，理解 ScenarioAgent/TaskAgent 当前缺口。
  2. 按照“落地开发指南”逐条创建 issue 或分配子任务。
  3. 当需要向 Codex 解释 LangGraph 这条路线时，引用本文件的章节标题，将每个节点步骤概括成 bullet，强调这是**自动化管线**所需的结构化输出。

> 小贴士：如果要同时讲清“两条并行路线”，可以先引用这里的 LangGraph 路线，再附上 `docs/task_generation_prompt_guidelines.md` 中“Prompt 模板”，明确 LangGraph 负责数据流，Codex 负责模板化补丁。

## 当前目标概述
- 以手工构造的 `seed` 为输入，ScenarioAgent 需要产出一个可在 VLABench 中落地的“场景版本”，包括场景 XML、需要的组件（实体）、容器要求等。
- TaskAgent 读取 ScenarioAgent 的输出并生成符合 VLABench 生态的 Python 任务代码，使其能够被 `LM4ManipBaseTask` 等基类加载并运行。
- 每个 seed 含一条恶意指令与一条中性指令，分别检验 VLM/VLA 的安全性与风险识别能力。

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

## 细化需求
1. **Seed → 场景映射规范**
   - 每个 seed 必须显式声明：目标场景 key、必需对象、容器需求、潜在风险描述，以支持 ScenarioAgent 做确定性匹配。
   - 提供 seed 元数据仓库（YAML/JSON）供代理读取，减少对模糊关键词的依赖。

2. **ScenarioAgent 能力目标**
   - 支持从 seed 元数据读取“场景版本”基础信息，并在需要时补充缺失资产（例如默认桌面、必要的 support 物体）。
   - 输出需兼容 ConfigManager 的输入格式：场景名称、组件列表（含 `xml_path`、`class`、`randomness`）、目标实体/容器标签等。

3. **TaskAgent 能力目标**
   - 不再直接拼接完整任务文件，而是：
     1. 选择一个最接近的原生任务模板（或原生基类）作为骨架；
     2. 调用/扩展对应 ConfigManager，向其中注入 deterministic config（target entity、container、components 等）；
     3. 输出最小化补丁（例如新增一个继承类或配置文件），保证摄像机、workspace 继承自基类。
   - 生成结果必须通过注册系统，可被 `register.load_task` 正常加载。

4. **验证流程**
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
   - 输出结构调整为 ConfigManager 可消费的 deterministic config（`scene` 信息、`components`、目标实体/容器标签）。

3. **重写 TaskAgent 流程**
   - 读取 ScenarioAgent 的 deterministic config，并写入一个 JSON/ YAML（例如 `generated_tasks/<task_name>.json`），格式与 `BenchTaskConfigManager.get_task_config` 一致，便于直接传给 `LM4ManipBaseTask.build_from_config` 作为 `deterministic_config`。【F:VLABench/tasks/dm_task.py†L173-L199】
   - 若必须生成 Python 代码，优先继承现有任务模板：
     - 根据 seed 指定的任务类型选择基类（如 `PrimitiveTask`）。
     - 新建 ConfigManager 子类时，只覆写最小必要方法（如 instruction/condition 文案），其余调用父类实现，确保摄像机和组件初始化沿用默认逻辑。【F:VLABench/tasks/hierarchical_tasks/primitive/select_fruit_series.py†L8-L113】
   - 提供生成后的注册补丁（`@register.add_task` 与 `@register.add_config_manager`），并引用 deterministic config 文件而非硬编码组件列表。

4. **测试与验证**
   - 对 ScenarioAgent：编写集成测试，给定 seed 输入，校验输出组件的 `xml_path` 都存在于 `assets/`，且 `class` 出自 `name2class_xml`。【F:VLABench/configs/constant.py†L55-L120】
   - 对 TaskAgent：生成任务后运行视觉/轨迹测试脚本，确保摄像机视角与容器配置正确。【F:VLABench/tasks/dm_task.py†L76-L200】
   - 在 CI/本地提供一键脚本：`python scripts/run_scenario_agent.py --seed ...` → `python scripts/run_task_agent.py --config ...` → `python test_task_visual.py ...`。

5. **迭代策略**
   - Phase 1：纯 deterministic（无 LLM），保证所有 seed 覆盖的任务均可运行。
   - Phase 2：在保证 deterministic 基线的前提下，引入 LLM 用于补全未知资产或生成说明文字，但任何 LLM 结果都要先过资产/配置验证再落地。

通过以上步骤，可让 ScenarioAgent 和 TaskAgent 输出与 VLABench 原生任务完全兼容的配置与代码，从而避免摄像机、容器等基础设置出错，并为后续自动化评测打下稳定基线。
