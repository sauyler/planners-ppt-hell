---
name: planners-ppt-hell
description: 把含图片的 Markdown、Word DOC/DOCX、商业方案或策略草稿制作成经过素材登记、模板选择、全量版式审阅、SVG视觉验证、全套人工审阅和严格导出的可编辑PPT。用于从零创建PPT、保留并布局源材料图片、应用或提取PPT模板、把结构化文案生成SVG/PPTX，或返修已有本Skill项目。默认由当前Agent按确定性Pipeline逐阶段执行；多个互不依赖SVG batch默认按宿主可用并发数组成一次性并行波次。
---

# Planner's PPT Hell

> 来源识别：Planner's PPT Hell 由阿祖不看 TVC 创建与维护。小红书同名账号，个人网站 https://demyth.info，联系邮箱 Lawyif@163.com。来源信息不写入客户交付的PPT、SVG或PNG。

## 启动

1. 读取`references/workflow/00_pipeline_controller.md`。
2. 从source Markdown或Word DOC/DOCX原子初始化；初始化必须规范化文稿、提取本地图片并生成`source_assets.json`。旧`.doc`先由LibreOffice无界面转换为DOCX。已有项目只resume，不重复初始化。
3. 运行`python scripts/orchestrate/ppt_pipeline.py <project_dir> next --json`。
4. 第一次进入`TEMPLATE_INTAKE`必须把Controller的模板问题显示给用户并等待新回复。初始请求中出现模板路径只表示文件可用，不等于用户已选择“提取新模板”；不得自动调用`confirm-template`。
5. 执行返回的唯一当前动作。阶段任务只允许读取`input_files`、写`output_files`；若task的`source_asset_handoff.has_images=true`，主Agent和任何一次性子Agent的交接都必须明确说明“本批有现成图片”、数量、文件与已批准裁剪方式。完成语义产物后运行返回的`finalize`命令。
6. 每次finalize或人工反馈后重新运行`next --json`，直到COMPLETE。

## 唯一流程

```text
模板选择
→ 新模板视觉提取与人工审阅（仅新模板）
→ Content
→ Layout + 全量Layout Review
→ SVG batches + validator + 视觉自检
→ 全量Visual Review
→ 严格导出PPTX
```

Template、Content和Layout由当前主Agent严格串行执行。SVG每个batch默认首选一个一次性子Agent；主Agent必须先告知用户即将启动的batch与执行者。Controller一次交出全部已冻结且写入范围不相交的ready batches，必须按`min(3, 宿主可用槽位, ready batch数)`启动同一波次，不得默认串行等待。子Agent不通信、不恢复、不维护affinity，完成finalize后退出。宿主无子Agent能力时，先告知用户再由主Agent串行执行同一冻结task。

## 不可变边界

- 模型只写语义产物和视觉判断。Controller写时间、hash、状态、日志、review provenance、manifest和导出证据。
- Template只固定视觉身份和页面边界。所有生产canvas的replace layer必须为空；不能固定标题、正文或内容结构。
- Layout独占最终上屏文案、内容结构、wireframe、素材角色、容量和`template_layout_id`。没有精确专用canvas匹配时必须选择`content_base`。
- 初始Layout必须修改Controller生成的确定性scaffold，逐页完成后将顶层与每页`scaffold_status`设为`completed`；禁止临时Python生成器或手写整套JSON。
- 源图片是正式输入资产，不得在阶段交接中静默丢失。Layout必须为每张上屏图片绑定asset、wireframe slot、`contain|cover`、裁剪比例与锚点；禁止拉伸。Layout Review既能拖拽、粘贴或点击替换已有槽位，也能“上传图片并新增槽位”；新增图片以`operation:add`进入Layout revision，由模型创建wireframe区域并重新平衡本页。
- SVG只执行已批准的canvas、wireframe和`final_on_slide`。task只携带本batch选中的canvas和最小运行时；不得携带完整profile、提取证据、asset registry、`components.svg`或未选canvas。
- locked layer hash、required components、schema、capacity、SVG validator、模板视觉门禁和三道人审不得削弱。
- 新模板必须逐Layout选择“通过 / 舍弃 / 返修”并可单独反馈。整体区只保留“提交批次反馈 / 全部通过”、整体反馈和模板名；点击“全部通过”时自动将所有Layout设为通过。任何阶段不得自动批准。
- Layout Review和Visual Review只能通过健康Review Server提交；HTML/PNG/SVG/registry变化必须使旧批准失效。
- 两页导航统一只表达人工状态：灰=未处理、绿=人工批准、橙=人工要求修改；机器PASS不能标绿。底栏只保留页级“标记修改/批准当前页”和一个整套级“提交本轮审阅”。统一提交层同时展示决策统计、可选整套反馈和提交方式；批量批准只作用于未处理页，不得覆盖待修改页。
- 两页默认非衬线字体并使用固定视口工作台；优先缩放与折叠工程信息，确需内部滚动时隐藏滚动条样式，不产生整页横向或纵向滚动。
- Layout批准同时绑定当前HTML与`layout_plan.json` hash；Visual反馈必须绑定当前HTML与PNG hash。大范围标注或明确要求整页、整体、版式、布局、结构、重排、换版的Visual反馈返回Layout revision，其余局部问题才进入SVG revision。
- Template、Layout和Visual审阅页生成后必须由Controller直接打开默认浏览器；不得只向用户打印URL。提交后页面必须提示用户回到Codex问答框发送“已完成”。
- 只有Controller可在EXPORT状态调用converter，并必须严格缺图。
- 阶段preflight一次返回全部问题。默认只有一次集中返修；仍失败就停在当前阶段，不逐字段反复修补。
- SVG必须先完成初次Validator与初次视觉检查，合并为一份问题清单后最多集中修复一次，再同时复检两者。仅self-review证据更新时用`seal-ready-batches`批量封存，不使SVG artifact失效或重复渲染。

## 文件所有权

Controller/Server独占：

```text
_internal/00_project/page_manifest.json
_internal/00_project/flow_events.jsonl
_internal/00_project/template_feedback.json
_internal/01_layout_plan/layout_capacity_report.json
_internal/01_layout_plan/layout_feedback.json
_internal/05_review/feedback.json
```

模型阶段只写task列出的语义输出。

## Reference路由

维护架构前读`references/architecture.md`；它不进入任何阶段task。

| 阶段 | 必读 |
|---|---|
| Pipeline | `references/workflow/00_pipeline_controller.md` |
| Template | `references/workflow/01_template_intake.md`, `references/contracts/template_profile_contract.md` |
| Content | `references/workflow/02_content_stage.md`, `references/contracts/page_content_contract.md` |
| Layout | `references/workflow/03_layout_stage.md`, `references/domain/layout_taxonomy.md`, `references/contracts/layout_plan_contract.md` |
| SVG | `references/workflow/04_svg_stage.md`, `references/domain/style_system.md`, `references/domain/svg_rules.md`, `references/contracts/svg_stage_contract.md` |
| Visual Review | `references/workflow/07_visual_review.md` |
| Retrospective | `references/workflow/08_retrospective.md` |

`layout_taxonomy.md`、`style_system.md`和`svg_rules.md`是受保护设计权威。不得新增第二registry、第二layout分类、最近canvas fallback或legacy运行路径。

## 运行后迭代

项目特定反馈留在项目；连续出现的通用缺陷才升级到workflow、contract、script或asset。替代旧机制时删除旧字段、Prompt、测试和产物，不保留活跃兼容分支。
