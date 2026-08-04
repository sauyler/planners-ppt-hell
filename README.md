# Planner's PPT Hell

A review-gated Skill for turning dense Markdown, proposal copy, and strategy drafts into editable PowerPoint decks.

![License](https://img.shields.io/badge/license-AGPL--3.0-111111?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Agent-111111?style=flat-square)
![PPT Workflow](https://img.shields.io/badge/PPT-Review%20Gated-D46A00?style=flat-square)
![Version](https://img.shields.io/badge/Version-V3-006BA6?style=flat-square)
![Codex](https://img.shields.io/badge/Codex-Supported-222222?style=flat-square)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Supported-6B5B95?style=flat-square)

[中文版](#中文版) · [English](#english)

## V3 · 2026-08-04 今日更新：图片全流程、全新审阅界面、前置 Skill 推荐

当前版本正式标记为 **V3（2026-08-04）**。相比仓库上一版本，本次更新集中在三件事：

### 1. 图片全流程支持

图片现在作为正式输入资产贯穿全流程：Content 登记素材角色，Layout 绑定图槽与裁剪决策，SVG 按批准比例执行，PNG 预览复检，最终导出到可编辑 PPTX。图片支持 `contain` / `cover`、原始比例和多种裁剪锚点，全程禁止拉伸。

### 2. 全新设计的审阅界面，支持图片上传

Layout 与 Visual 审阅页重新设计为固定视口工作台：深色画布、逐页主工作台、底部统一提交。图片支持拖拽、点击和剪贴板上传，可逐槽位查看裁剪方案、替换或重置图片，也能新增图片槽位；图片变更状态与已批准基线分离，不再因为交互痕迹卡死审批。

### 3. 前置 Skill 推荐

进入本 Skill 之前，建议先按场景选择前置 Skill：

- 营销 / 策略从业者：先使用 `PlannersProposalSystem` 完成策略方向、Storyline 与逐页提案文案。
- 非营销 / 内容材料场景：先使用 `PPT by page` 把 Word、PDF、Markdown 或多源资料整理成逐页内容稿与图片资产。

前置 Skill 完成内容整理后，再交给 Planner's PPT Hell 完成版式、审阅和可编辑 PPTX 导出。

底层流程仍由单一 Controller 驱动：每次只返回唯一当前动作，错误一次聚合、集中返修，严格控制步骤但不把执行推入死循环。

当前仓库根目录就是标准 Skill bundle，直接包含 `SKILL.md`、`agents/`、`assets/`、`references/` 和 `scripts/`。完整架构见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，历史升级、审计和工作日志见 [`docs/history/`](docs/history/)；历史材料不会进入正常 Skill Prompt。

## 中文版

Planner's PPT Hell 是 **阿祖不看 TVC** 创建与维护的开源 Skill，用来把 Markdown、提案文案和策略稿制作成可审阅、可校验、可编辑的 PowerPoint。

它不是一键模板生成器，而是一条受控生产线：Agent 负责理解内容、制定版式、生成 SVG、预览和校验；人负责在 Template、Layout 和最终 Visual Review 三个关键节点做决定。核心规则是：

> 模型可以起草、修改和自检，但不能批准自己。

### 前置 Skill 推荐

- 营销 / 策略提案场景：先使用 `PlannersProposalSystem` 完成策略方向、Storyline 与逐页提案文案。
- 非营销 / 内容材料场景：先使用 `PPT by page` 把 Word、PDF、Markdown 或多源资料整理成逐页内容稿与图片资产。

前置 Skill 完成内容整理后，再交给 Planner's PPT Hell 完成版式、人工审阅与可编辑 PPTX 导出。

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

### V3 highlights (2026-08-04)

- Full-pipeline image support: images are registered as source assets, bound to layout slots with approved crop decisions, executed in SVG, checked in PNG previews, and exported into editable PPTX without stretching.
- Newly designed review workbench with image upload: drag, click, or paste images; per-slot crop comparison, replace, reset, and add-new-slot flows on a fixed-viewport dark canvas.
- Upstream Skill recommendations: marketing and strategy work should start with `PlannersProposalSystem`; non-marketing content material should start with `PPT by page`, then hand off to this Skill for editable PPT production.

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
