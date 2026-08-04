# Planner's PPT Hell

A review-gated Skill for turning dense Markdown, proposal copy, and strategy drafts into editable PowerPoint decks.

![License](https://img.shields.io/badge/license-AGPL--3.0-111111?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Agent-111111?style=flat-square)
![PPT Workflow](https://img.shields.io/badge/PPT-Review%20Gated-D46A00?style=flat-square)
![Version](https://img.shields.io/badge/Version-V3-006BA6?style=flat-square)
![Codex](https://img.shields.io/badge/Codex-Supported-222222?style=flat-square)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Supported-6B5B95?style=flat-square)

[中文版](#中文版) · [English](#english)

## V3 · 2026-07-18 主版本：单一 Controller，模板可控，审阅更稳

当前主版本正式标记为 **V3**。它支持三种模板入口：使用已批准默认模板、上传并提取新模板、或不使用模板。上传模板后，系统先生成全页视觉证据和可审阅 canvas；模板只固定视觉身份与页面边界，Layout 仍独立决定内容结构、最终文案和 wireframe。

### V3 相比上一版

- 单一 Controller 状态机：每次只返回唯一当前动作；Template / Content / Layout 严格串行，SVG batch 按冻结任务并发。
- 模板三入口：默认模板、上传提取新模板、不使用模板；模板只固定视觉身份与页面边界。
- 审阅证据绑定：Layout 批准同时绑定审阅 HTML 与 `layout_plan.json` hash；Visual 批准绑定 HTML 与 PNG hash，任何变更都会让旧批准失效。
- 单一口径门禁：finalize 与审阅页共用同一组 blocking warnings，不再出现“finalize 通过但审阅页拦截”的双重判定。
- 反馈修复层路由：整页、重做、版式、布局类视觉反馈回 Layout；局部拥挤、数字小等留在 SVG 层。
- 返修闭环：返修读取冻结反馈与旧产物快照；task 永远携带完整 finalize 命令；重复 finalize 幂等返回。
- SVG 自检：validator 与视觉检查合并为一份问题清单，最多集中返修一次，再同时复检。
- 审阅工作台：固定视口深色画布；asset 修改状态与已批准基线比较，支持重置，不再因交互痕迹卡死审批。

流程已经从持久 Parent/Worker 协作收敛为单一 Controller：错误一次聚合、集中返修，严格控制步骤但不把执行推入死循环。

当前仓库根目录就是标准 Skill bundle，直接包含 `SKILL.md`、`agents/`、`assets/`、`references/` 和 `scripts/`。完整架构见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，历史升级、审计和工作日志见 [`docs/history/`](docs/history/)；历史材料不会进入正常 Skill Prompt。

## 中文版

Planner's PPT Hell 是 **阿祖不看 TVC** 创建与维护的开源 Skill，用来把 Markdown、提案文案和策略稿制作成可审阅、可校验、可编辑的 PowerPoint。

它不是一键模板生成器，而是一条受控生产线：Agent 负责理解内容、制定版式、生成 SVG、预览和校验；人负责在 Template、Layout 和最终 Visual Review 三个关键节点做决定。核心规则是：

> 模型可以起草、修改和自检，但不能批准自己。

### 当前流程

```text
模板选择
→ 新模板视觉提取与逐 Layout 人工审阅（仅新模板）
→ Content
→ Layout + 全 deck 人工审阅
→ SVG batches + validator + 视觉自检
→ 全 deck Visual Review
→ 严格导出可编辑 PPTX
```

模板 canvas 只固定视觉身份和页面边界，replace layer 为空。Layout 独占内容结构、最终文案、wireframe、素材角色和 canvas 选择；没有精确专用模型匹配时必须使用 `content_base`。SVG task 只携带当前 batch 实际使用的 canvas 和最小运行时，不携带完整 profile、模板提取证据、`components.svg` 或未选 canvas。

### 快速安装

```bash
npx skills add https://github.com/thePlannerIvan/planners-ppt-hell --skill planners-ppt-hell
```

也可以 clone 仓库后，只复制 Skill bundle：

```bash
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git /tmp/planners-ppt-hell
cp -R /tmp/planners-ppt-hell ~/.claude/skills/planners-ppt-hell
```

### 使用示例

```text
使用 planners-ppt-hell，把 brief.md 制作成完整可编辑 PPT。
从空项目开始，先询问我要使用默认模板、上传新模板，还是不使用模板。
所有人工审阅必须等待我在 Review Server 提交，不要自动批准。
```

CLI 入口：

```bash
python scripts/init_svg_project.py path/to/project --source source.md
python scripts/orchestrate/ppt_pipeline.py path/to/project next --json
```

第一次进入 `TEMPLATE_INTAKE` 时必须等待用户明确选择。之后每次只执行 Controller 返回的当前动作，完成后再次运行 `next --json`，直到 `COMPLETE`。不要直接调用 converter，也不要绕过 Review Server 写批准结果。

### 验证

当前主版本 `scripts/test/smoke_v2.py` 共 27 项检查全部通过。

```bash
python scripts/test/smoke_v2.py
python scripts/test/mece_scan_v2.py
python scripts/test/forward_content_base_v2.py
python /path/to/skill-creator/scripts/quick_validate.py .
```

### 适合与不适合

适合内容密度高、含义不能乱改、需要逐页审阅、最终必须可编辑的提案、咨询、策略和年度规划 PPT。不适合追求完全自动一键出片、拒绝人工审阅，或只需要网页演示的任务。

---

## English

Planner's PPT Hell is an open-source Skill created and maintained by **阿祖不看 TVC**. It turns dense source material into review-gated, validated, editable PowerPoint decks.

It is not a one-click template generator. The agent structures content, plans layouts, creates SVG pages, renders previews, and runs deterministic checks. The human approves the template layouts, the full-deck Layout Plan, and the final visual deck.

> The model may draft, revise, and self-check. It may not approve itself.

### V3 highlights

- One Controller, one current action. Template, Content, and Layout run serially; SVG batches run as frozen disjoint tasks.
- Three template entries: approved default, upload-and-extract, or no template. Template owns visual identity and page boundaries only.
- Approval provenance is hash-bound: Layout binds review HTML plus `layout_plan.json`; Visual binds review HTML plus PNGs.
- Single review gate: finalization and review pages share one blocking-warning policy.
- Feedback routing: page-wide or layout-level visual feedback returns to Layout; local issues stay in SVG.
- Revision tasks freeze feedback and prior outputs; every task carries a complete `finalize_argv`; repeated finalize is idempotent.
- SVG quality loop: one combined validator + visual finding list, at most one concentrated repair pass.
- Review workbench: fixed-viewport dark canvas, derived asset-change state, and reset controls.

### Current workflow

```text
Template choice
→ New-template extraction and per-layout human review (when needed)
→ Content
→ Full-deck Layout + human review
→ SVG batches + validator + visual self-check
→ Full-deck Visual Review
→ Strict editable PPTX export
```

The current release supports an approved default template, user-uploaded template extraction, or no template. Template canvases own visual identity and page boundaries only. Layout owns final copy, content structure, wireframes, asset roles, and canvas selection. SVG workers receive only the selected canvases and minimal batch-scoped runtime.

The runtime has one Controller and one current action. Revision tasks use frozen feedback and prior-output snapshots. Completion is bound to the current task and current output hashes. Repeating an unchanged SVG finalize is idempotent, preventing redundant rendering and duplicate completion events.

### Install

```bash
npx skills add https://github.com/thePlannerIvan/planners-ppt-hell --skill planners-ppt-hell
```

### Run

```bash
python scripts/init_svg_project.py path/to/project --source source.md
python scripts/orchestrate/ppt_pipeline.py path/to/project next --json
```

At `TEMPLATE_INTAKE`, show the choices to the user and wait for an explicit reply. Then execute only the action returned by the Controller, finalize that stage, and call `next --json` again until `COMPLETE`.

## Attribution, licensing, and trademarks

- Author / Xiaohongshu: 阿祖不看 TVC
- Website: <https://demyth.info>
- Email: <Lawyif@163.com>

The project is distributed under GNU AGPL v3. See [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), [`COMMERCIAL.md`](COMMERCIAL.md), [`TRADEMARK.md`](TRADEMARK.md), and [`SECURITY.md`](SECURITY.md).

Attribution belongs in source code, documentation, package metadata, or process interfaces. The Skill must not add project branding to client-facing PPT, SVG, PNG, or other final deliverables unless the user explicitly asks for it.
