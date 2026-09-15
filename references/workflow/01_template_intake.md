# 视觉来源与模板

结果：这套页面**确定了视觉身份从哪来**；需要时确实复用了品牌资产，而不是近似重画。

## 先确认一次：视觉从哪来

读完材料、写完内容底稿之后，**一次性**确认视觉来源，不要静默默认自主设计。四条路线：

| 路线 | 什么时候用 | 机械支撑 |
|---|---|---|
| **A 自主设计** | 没有模板，也没有可参考的成品 | 无，直接进 `04_svg_stage.md` |
| **B 用模板库里的模板** | 用户点名，或库里有贴合的 | `template_library.py list` / `apply` |
| **C 视觉参考** | 用户给了别的成品（PPTX／PDF／图），要求「像这个方向」 | `prepare_visual_references.py` 渲染参考页 |
| **D 新建严格品牌模板** | 用户给了自己的 PPTX，要真实复用标志、背景与身份元素 | 八步提取流程（见下） |

**只问一次。** 用户已经明确说了就照做，不重复问。选项说不清时按 C 处理（最轻、可逆）。

**库里有什么**：`python scripts/template/template_library.py list`。内置 `planner-simple-default`（`is_default`）：5 张 canvas——`cover_dark` / `contents_light` / `section_dark` / `content_base` / `closing_dark`，一组身份组件——`bg_dark` / `bg_light` / `accent_block` / `footer_bar`，另有带颜色角色与字号层级的 `design_direction` 可直接读。**没有贴合的就别硬套**，说明情况让用户选。

---

## 路线 C：视觉参考（最轻，不建可复用包）

1. 渲染参考件：
   `python scripts/template/prepare_visual_references.py <参考文件> --project <project>`
   支持 PDF、单张图片或图片目录；`--dpi` 默认 144。产物落在 `_internal/00_project/template_visuals/`：逐页 PNG + `visual_manifest.json`。
2. **看完全部渲染页**，不是只看封面。从**色彩、字体、层级、密度、节奏**五处提炼方向。
3. 写进 `_internal/01_content/design_direction.md`，按 `../domain/style_system.md` 的顺序组织：网格与纵向步长、层级角色、色彩角色、跨页锚点、节奏。
   **提炼的是构造关系，不是照抄数值。**「它靠大尺度差建立唯一重心」可以学；「它用 24pt」不要抄。参考件是**文档型还是投屏型**，也是要在这里读出来的信息。
4. 登记模式：`python scripts/orchestrate/ppt_pipeline.py <project> template --mode reference`。
5. 进入制作。参考路线**不锁层、不建可复用包**，页面仍按 `style_system.md` 的规则自己做。

---

## 路线 B：用库里的模板（严格复用）

1. `python scripts/template/template_library.py list` 确认 `template_id`。
2. `python scripts/orchestrate/ppt_pipeline.py <project> template --mode fidelity --template-id <id>`
   （会自动调用 `template_library.py apply`）
3. 逐页实例化选中的空内容 canvas，再填内容：
   `python scripts/template/apply_fidelity_template.py --project <project> --page-key <key> --layout-id <canvas> --title <标题> [--body <正文>]`
4. 选 canvas 看信息关系；**没有精确匹配时用 `content_base`**。锁层与 required components 必须保留；业务结构不得被锁成品牌身份，案例正文不得固化。

---

## 路线 D：新建严格品牌模板（八步提取）

只在「要真实复用用户自己的品牌资产」时走。工作文件全在 `_internal/00_project/`。
**`../contracts/template_package.md` 是这条路线每一步的机器接口，以它为准**；下面是流程骨架。

1. **渲染源页** — `prepare_visual_references.py <用户文件> --project <project>` → `template_visuals/`。
2. **提取事实** — `extract_template_assets.py <用户 .pptx> --project <project>` → `template_profile.json` 的 `structural_extraction` 候选。原始 XML 与坐标只提供事实，**不是设计结论**；用实际画面确认。
3. **补方向与审批** — 模型补 `template_profile.json` 的 `design_direction` 与来源；写 `template_asset_registry.json` 的 `reviewed_source_ids`，逐个列出 `structural_extraction.assets` 的 `asset_id` 与 `native_shapes` 的 `candidate_id`，以及 approved／rejected 与原因。确保背景与标志是真实复用。
4. **写 `template_worker_result.json`** — `approved_components` + `layouts`（含 `required_components`）。一份源候选只定义一个 component；`content_base` 必须开放正文；只锁真实品牌身份，不锁业务关系和示例文字。
5. **构建** — `python scripts/template/build_fidelity_template.py --project <project>` → `fidelity_template/`（`template_registry.json`、`layout_canvases/`、`components.svg`）；再
   `python scripts/render_svg_png.py <project>/_internal/00_project/fidelity_template/layout_canvases <project>/_internal/00_project/fidelity_template/canvas_previews`。
6. **看图自审并封存** — 看源页、canvas 大图与两套 contact sheet。模型写 `template_canvas_self_review.json` 的语义观察：`status="completed"`、`vision_available=true`、两张 contact sheet 均已看、`inspection_rounds`、`source_pages_reviewed`（覆盖 `visual_manifest.json` 里每个 image 的 stem）、每个 layout 的 `canvas_png_reviewed`／`compared_source_pages`／`usable`／`visual_similarity="pass"`／`must_fix`／`retained_features`。**这些观察必须来自实际看图。** 然后运行 `python scripts/template/seal_template_review.py <project>`，由机器绑定证据 hash（模型不写 hash）。
7. **人审** — `python scripts/orchestrate/ppt_pipeline.py <project> template --mode fidelity`，再 `template-review` 打开审阅页；用户逐 canvas 通过／舍弃／返修并给模板命名。按全部反馈修订后重建再审。
8. **发布** — 全部通过后 `python scripts/template/template_library.py publish <project>`。库发布会验证当前批准与全部证据。

**没有可安全复用的品牌组件时明确说明**，让用户改选参考模式或新模板，**不静默假装 fidelity 成功**。

---

## 完成标准

- 视觉来源已明确——四条路线里选了一条，且用户确认过。
- **B／D**：`fidelity_template/` 与 `canvas_previews/` 齐备，自审证据已封存，人审通过；页面保留锁层。
- **C**：`design_direction.md` 里能看出参考方向被提炼成了**构造关系**，而不是抄来的数值。
- **A**：`design_direction.md` 至少覆盖网格与纵向步长、层级角色、色彩角色、跨页锚点、节奏。

架构约束：模板运行时**只有一套** registry 与 canvas；不新增分类字段、备份目录、并行双轨实现。canvas 的 `replace` 层保持为空，业务模型不进入 locked 层。
