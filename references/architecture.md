# 架构

单一控制面 `scripts/orchestrate/ppt_pipeline.py`，状态派生与版本逻辑在 `scripts/project_state.py`。主 Agent 完成轻量内容、页面设计与看图修订。

CONTENT → CREATE ↔ VISUAL_REVIEW → EXPORT → EXPORT_VERIFY → COMPLETE。

批次是工作节奏，没有单独状态、执行者身份或固定页数。Layout 思考属于 CREATE，实际 SVG 是几何唯一来源。内容底稿保留含义、来源与每页读法（`mode`）；方向 Markdown 保留全套秩序决定（网格与纵向步长、层级角色、色彩角色、跨页锚点、节奏）。改动对页面版本的影响由脚本计算。

Review 生成器与 Server 使用同一 snapshot；页面提交必须携带 review_id，Server 对照当前 SVG、依赖图片、内容、PNG、HTML、自检记录。旧浏览器不能批准新版本。图片操作来自实际 SVG image 元素，新增操作以稳定 asset_key 传回创作。反馈只有一个目的地；每条需要实际处理说明。

视觉来源是内容之后的第一个决定，四选一：自主设计、模板库里的模板、视觉参考、新建严格品牌模板。**四条路线都在 `01_template_intake.md` 里有完整命令序列与产物清单**——提取路线是八步（渲染源页 → 提取事实 → 补方向与审批 → 写 worker result → 构建 → 看图自审并封存 → 人审 → 发布），参考路线先用 `prepare_visual_references.py` 真渲染参考页再提炼方向；`--mode reference` 没有参考件会直接报错，不允许只登记模式不渲染。严格模板保留资产提取、canvas 锁层和模板库接口。导出继续使用原生 SVG→PPTX 转换器与严格缺图，最终渲染复核单独记录。

## 校验器的边界（本次重划）

`scripts/validate_svg_layout.py` 只保留两类检查：**转成 PPT 会坏**的，和**在任何风格下都是缺陷**的。它不再评价密度、字号档位、构件选择、留白或配色。

理由：那些启发式并不保护正确性，而是把每一套页面推向同一种稀疏、均匀、卡片式的样子——与一份密排、有设计感的提案正好相反。实测中按人审意见去掉卡片后，警告反而从 10 涨到 17，全部来自这些规则。设计判断改由**模型渲染后看图**承担，这是模型能力提升后的正确分工。

唯一保留的尺寸规则是**可读性下限**，且随页面 `mode` 切换：`讲` 页 ≥18px（9pt），`读` 页 ≥12px（6pt）。这是任何缩放都读不出的物理下限，不是风格偏好。

## 退役

Layout JSON scaffold、预布局 HTML、capacity gate、wireframe label、旧 make/finalize task 协议、强制并发策略和 batch 配额；以及校验器里的 `FONT_SIZE_TIERS`、20px 正文字号警告、`HIGH_TEXT_DENSITY`、`HIGH_CANVAS_COVERAGE`、`DENSITY_IMBALANCE_*`、`LARGE_EMPTY_REGION`、`LOW_MODULE_UTILIZATION`、`TABLE_READABILITY_RISK`、`FOOTER_ZONE_INVASION`、`MISSING_IMAGE_SLOT`、`MISSING_CROP_RATIO`、`NONSTANDARD_IMAGE_RATIO`、`CIRCLE_TOO_SMALL`、`TEXT_ANCHOR_MIDDLE_LONG`、`FONT_FAMILY_DRIFT`、`REPEATED_LAYOUT_RHYTHM` 与页面 metadata 概念。旧运行须使用外部归档版本，不在活跃包中保留兼容状态机。

同时修掉三个真 bug：`estimate_text_box` 忽略 `text-anchor`（右对齐／居中文字会误报越界与重叠）、`check` 对未变页面不回 `issues`（全量扫描看不到告警分布）、`check_rhythm` 是无人写入 metadata 的死代码。

测试：source asset 与 converter 回归；项目、反馈、版本、模板与 UI 集成；真实产物由用户抽查。历史资料只作历史，不进入运行路由。
