# 02 — Content阶段

只读取task、规范化源Markdown、`source_assets.json`、task列出的图片和`page_content_contract.md`。不要读取Template/Layout/SVG或导出实现。

目标：生成完整、可追溯的`_internal/01_content/page_content.json`。

## 做

- 保留源文案含义、事实、数字、来源、speaker notes和素材需求。
- 若`source_asset_handoff.has_images=true`，逐一查看task列出的本地图片；在相关页面用`source_assets`保留asset_id、原始位置语境、说明及用途候选。图片不是装饰性“有/无”标签。
- 按叙事目的分页；每页有唯一`page_key`、action title、core message和body blocks。
- 不因预估版面空间提前删除重要内容；可把明显不宜上屏的解释放入notes候选。
- 保持输出为合法UTF-8 JSON，并严格遵守contract。

## 不做

- 不选择模板canvas。
- 不设计wireframe、网格、字号或SVG。
- 不写manifest、flow events、feedback或任何机器元数据。
- 不决定图片裁剪、缩放、槽位或最终是否上屏；这些属于Layout。

完成后运行task返回的`finalize`。Controller会验证输出并从Content页序生成manifest和batch索引。失败时根据一次性完整issues集中修一次；不要另写result JSON。
