# Changelog

## 2026-09-13 — v5.2.1（描边保真修复）

起因：一次 21 页实测（项目在 `01-projects/Adidas-vs-Nike-WorldCup2026/04_PPT/`）导出后发现某页坐标轴线在 PPTX 里整条消失。逐像素对照才定位到 `native_svg_to_ppt.py` 的描边换算。

- **删掉描边上的 `* 0.6` 经验系数**。`shape.line.width = Pt(sw * FONT_SCALE * 0.6)` 让每根描边只有声明值的 60%（1920 画布上 1px → 0.30pt）。这与本 Skill 自己写死的规则直接矛盾：`reference/domain/svg_rules.md` 第 5 行明确「1 SVG px = 0.5pt」。更严重的是，批准稿 PNG 由 Chromium 按 SVG 声明的满权重渲染，所以这个系数让「导出稿与批准稿一致」这个 EXPORT_VERIFY 目标在数学上永远无法达成，且失败是静默的（细线只是不画出来）。
- **新增低于 `MIN_STROKE_PT`（0.5pt）时的告警**，把静默失败变成构建期提示。阈值判断留 1e-4 余量：`SLIDE_W_IN` 是 13⅓ 的近似值，1px 实际换算为 0.49999pt，不留余量会把合法发丝线全部误报。
- **补上 `scripts/test/test_converter_geometry.py` 的 3 条回归**：描边不得被额外缩放（EMU 整数比对）、1px 不得被判过细、低于 0.5pt 必须告警。
- **给另两个魔法系数补上来源与影响边界**：`estimate_text_width` 的 0.58 与文本落位的 0.85。核实结论是两者都**不影响最终视觉位置**（三种框内对齐各自自我抵消；0.85 只造成整页统一的轻微垂直偏移），因此不做替换，只写明"要精确就按实际字体取度量，不要再叠系数"。

未处理并已登记的既有失败：`test_source_assets.py` 的 `soffice --convert-to doc` 在本机失败，在未改动的副本上同样失败，属环境问题，与本次改动无关。

## 2026-09-12 — v5.2（模板流程补全与自检落地）

v5.1 之后用户指出两件事：**视觉自检没有被真正执行**，以及**模板提取与使用流程没有出现在活跃文档里**。核实结果：机械全在（八步提取脚本、模板库、canvas 实例化），但 `01_template_intake.md` 只有 9 行存根、把流程推给 `--help` 和 contract；`--mode reference` 只登记一个字段、不渲染任何参考件；自主路径从不告知模板库存在。

- **`01_template_intake.md` 从 9 行存根写成完整流程**：四条路线（自主／库模板／视觉参考／新建严格品牌模板）+ 每条的精确命令、产物、决策点与完成标准。八步提取流程从 contract 提到 workflow 层，contract 仍为机器接口。
- **视觉来源改为内容底稿后一次性确认**，不再静默默认自主设计（`00_pipeline_controller.md`、`SKILL.md`）。
- **`template --mode reference` 需要 `--reference <文件>`**，会真正调用 `prepare_visual_references.py` 渲染参考页；没有参考件直接报错。此前该模式只写 manifest 字段，参考路线在机械上是空的。
- **自检从「5 个问题」扩到覆盖 13 条规则**，并落地为必填产物：`inspect` 新增 `--first-glance`（第一眼落在哪）与 `--design-check`（对照了哪几条规则、有无违规），两者空着不通过。此前 `inspect` 只收自由文本，自检可被跳过——而它确实被跳过了。
- **`check` 每页回一组只读测量**：字号档位、最大／最小尺度比、等面积容器组、内容底部到页脚线的空档、跨页共用基线。**只报告，不判 pass/fail**，用来替代「凭印象自检」。

## 2026-09-12 — v5.1（实测后的能力重划）

起因：v5 用老的美津浓文案做了 10 页完整实测（项目在 `07-SkillLab/PPT-Skill-around/PPTTest1/mizuno-v5-test-20260912/`，报告在同目录 `skill-run-reviews/`）。工程全绿，但视觉明显不如人做的提案；差异不在字数（每页 18.6 vs 19 个文字 run），而在设计自由度。据此重划机械与设计的边界。

- **校验器从 1383 行降到 563 行。** 只保留「转成 PPT 会坏」和「任何风格下都是缺陷」两类检查；退役全部可读性／密度／构成启发式，以及页面 metadata 概念与 `REPEATED_LAYOUT_RHYTHM` 死代码。
- **新增每页读法声明 `mode`（`讲`／`读`）。** 它唯一影响的技术量是字号下限（`讲` ≥18px、`读` ≥12px），其余是设计判断的输入。这是每页一个字段的声明，替代原来那批全局硬阈值。
- **修三个真 bug**：`estimate_text_box` 忽略 `text-anchor`（右对齐／居中文字必然误报越界，且有变成假 error 的风险——实测两轮共 20 个假警告）；`check` 对未变页面不回 `issues`（全量扫描看不到告警分布）；`check_rhythm` 依赖无人写入的 metadata。
- **`style_system.md` 从「克制建议」换成设计总规则。** 13 条正面规则 + 元规则（先声明读法）+ 迁移边界，全部停在「韵律／网格／视觉重心」这一层，不写字号、颜色、组件。依据是一份带 A/B/C/D 证据分级的文献提炼（`07-SkillLab/PPT-Skill-around/planners-ppt-hell-upgrade-20260912/design-principles-research.md`）。其中 W3C clreq／jlreq 为 A 级，给出中文版面以字面方块为网格单位的规范依据；Gestalt 原始文献未核实，相关表述已撤下。
- **内容阶段增加一次图片询问**：判断这套页面是否需要配图，一次性说明需要什么、哪几页、用户是否已有资产；不逐页追问，无图时在底稿写明原因。
- **`svg_rules.md` 写明 px↔pt 换算（1px = 0.5pt）与纵向步长构造。**

## 2026-09-12 — v5

- 轻量内容底稿＋主 Agent 自主设计，合并 Layout 与 SVG 创作。
- 删除 Layout 审阅、scaffold、wireframe 契约和旧 task/finalize 调度；取消强制子 Agent 与批次配额。
- 实际页面审阅支持上传、新增、替换、裁剪和区域反馈；反馈统一返回创作。
- 每页版本绑定源内容、SVG、真实图片和视觉方向；检查缓存、旧审批失效、稳定页批准复用。
- 保留源资产提取、严格品牌模板、原生转换和严格缺图；最终 PPTX 渲染复核单独记录。
- 工程回归与实际语义测试分开；用户选择在其他任务做真实测试，本次不将其标为已通过。


## 2026-07-18 — historical release

- 支持启动时明确选择默认模板、上传提取新模板或无模板。
- 新模板逐 Layout 审阅：通过、舍弃、返修；保留单独反馈、整体反馈和模板命名。
- Template canvas 只固定视觉身份与页面边界，replace layer 保持为空。
- Layout 独占结构、最终文案、wireframe 与 canvas 选择；无精确匹配时使用 `content_base`。
- SVG task 缩减为当前 batch 的已选 canvas、最小运行时、批准文案与 wireframe。
- 移除持久 Parent/Worker 会话编排；Template、Content、Layout 由当前 Agent 串行执行，SVG batch 只保留一次性并发能力。
- 返修任务改用冻结的旧产物快照，消除输入/输出同路径导致的 stale 循环。
- 阶段完成绑定当前 task hash 和当前输出 hash；重复 SVG finalize 在证据仍有效时幂等返回。
- 增加 wireframe 结构执行追踪，但不新增视觉质量判断或强化视觉流程门禁。

