# Planner's PPT Hell — current architecture

本文描述 2026-07-18 主版本的真实运行机制。它用于 GitHub 维护和升级评审，不进入正常阶段 task。

## 1. 设计目标

- 一个控制面、一个状态机、一个模板 registry、一个 Layout Plan。
- 步骤严格、输入明确、状态可验证，但失败时一次聚合问题并限制集中返修，避免逐字段死循环。
- Template 只提供视觉身份和页面边界；Layout 决定内容结构；SVG 只执行批准结果。
- 人工批准只能来自健康 Review Server，不能由 Agent 或 Controller 自动代写。

## 2. 权威分层

| 层 | 权威文件/组件 | 职责 |
|---|---|---|
| 控制面 | `scripts/orchestrate/ppt_pipeline.py` | 从磁盘事实派生唯一当前状态和动作；启动审阅；控制导出 |
| Task 冻结 | `make_stage_task.py` | 生成最小 `input_files`/`output_files`、输入 hash、完整 argv；返修冻结旧产物和反馈 |
| 阶段关闭 | `finalize_stage.py` | 校验 task、输入、输出、合同和既有门禁；写机器事件与输出 hash |
| 人工门禁 | `review_server.py` | 唯一反馈写者；批准绑定当前 HTML、PNG、SVG、registry |
| 内容事实 | `page_content.json` | 页面级完整事实、正文块和备注 |
| 结构事实 | `layout_plan.json` | 最终上屏文案、wireframe、素材角色、canvas 选择 |
| 模板事实 | `template_registry.json` + canvas | 视觉身份、页面边界、locked layer 与组件绑定 |
| 运行事实 | `flow_events.jsonl` | 机器写入的完成、失败、耗时、hash 和问题 |

模型不写 timestamp、完成状态、hash、manifest、review provenance 或持久 Agent 身份。

## 3. 状态机

```text
PROJECT_MISSING
→ TEMPLATE_INTAKE
→ TEMPLATE_RENDER_REQUIRED / TEMPLATE / TEMPLATE_REVIEW / TEMPLATE_REVISION / TEMPLATE_PUBLISH
→ CONTENT
→ LAYOUT / LAYOUT_REVIEW / LAYOUT_REVISION
→ SVG_BATCH_BUILD / SVG_BATCH_REVISION
→ VISUAL_REVIEW
→ EXPORT
→ COMPLETE
```

`next --json` 每次只返回一个当前执行单元。Template、Content、Layout 严格串行。SVG 按互不相交 batch 冻结；宿主支持时可用一次性子 Agent，并只做一次 completion join。无子 Agent 能力时，主 Agent告知用户后串行执行同一 task。

## 4. 模板链路

启动时必须等待用户明确选择：默认模板、新模板提取或无模板。上传新模板不等于自动提取授权。

新模板经过：源文件渲染 → 全页视觉提取 → fidelity registry/canvas → canvas preview → 逐 Layout 人工决定。生产 canvas 的 replace layer 为空，不固定标题、正文、图表、卡片或内容结构。`content_base` 是强制默认基础页；专用模型只有精确语义匹配时才可选。

模板审阅的“通过 / 舍弃 / 返修”属于每个 Layout。整体区域只有模板名、整体反馈、“提交批次反馈”和“全部通过”。任何代码路径都不得自动批准。

## 5. Content、Layout 与 SVG 合同

Content 只整理事实、分页内容和素材角色判断，不选择 canvas 或画 wireframe。

Layout 独占最终上屏文案、内容关系、wireframe、容量和 `template_layout_id`。没有精确专用模型匹配时必须选择 `content_base`。

SVG task 只包含当前 batch：

- 批次内容与 Layout 快照；
- 当前实际选中的 canvas；
- 只覆盖已选 layout/组件的 batch-scoped runtime；
- 最小 style、合同、批准反馈和完整 argv。

它不携带完整 profile、模板提取证据、asset registry、`components.svg`、未选 canvas 或其他 batch SVG。每个非 background wireframe 区域用同名 `data-wireframe-label` 追踪是否被执行；该追踪不评价几何或视觉质量。

## 6. 返修稳定性

返修 task 不允许同一路径同时出现在输入和输出。旧 `layout_plan.json`、模板产物和 SVG 会复制到 `_internal/00_project/tasks/inputs/` 下的冻结快照；实时路径只作为新输出。反馈也先冻结并写入 hash。

阶段完成必须同时满足：

- task 自身 hash 有效并与最新成功事件一致；
- 声明输入仍匹配冻结 hash；
- 声明输出完整且当前 hash 与成功事件一致；
- revision feedback hash 一致；
- 原有 contract、validator、locked layer、required components 和人工门禁保持成立。

SVG finalize 在 task、产物、反馈、页面 PNG 和 contact sheet 都未变化时幂等返回 `already_complete: true`，不重复渲染、不重复写完成事件。任何一项变化都会正常重新验证。

## 7. 失败与循环控制

- preflight/finalize 一次返回当前阶段全部确定性问题。
- 默认进行一次集中修复；阶段自带的明确上限不得被拆成逐字段循环。
- warning 不升级为 hard error；视觉质量仍由执行模型与既有人工审阅负责。
- 不为失败新增第二 registry、legacy fallback、最近 canvas 猜测或持久子 Agent 恢复机制。
- 若硬错误仍存在，停在当前阶段并给出可执行问题清单，而不是伪造完成。

## 8. 发布与历史材料

`references/` 是运行时权威；`docs/history/` 保存历次架构审计、升级设计、运行日志和失败分析，供维护者理解因果，不由 `SKILL.md` 或阶段 task 引用。旧可执行版本保存在仓库外的 release archive，主目录只保留当前运行路径。

