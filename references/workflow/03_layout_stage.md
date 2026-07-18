# 03 — Layout阶段

只读取task列出的Content、可信模板方向、单一registry、`layout_taxonomy.md`和`layout_plan_contract.md`。

Layout独占：最终上屏文案、内容关系、`layout_id`、wireframe、素材角色、容量和`template_layout_id`。

## Canvas选择

- 只有内容关系与专用canvas精确一致时才选择专用canvas。
- 没有精确匹配时必须选择`content_base`；禁止最近模型fallback。
- 选择必须存在于当前单一registry。

## Wireframe

- 为每个上屏区写明确x/y/w/h、zone和label。
- `copy_handling.final_on_slide`必须能映射到wireframe区域。
- 需要移入notes或拆页时明确记录，不让SVG阶段重新做内容取舍。
- 全deck检查节奏、密度和重复构图。

## 完成

只写`layout_plan.json`。revision时必须逐条落实`constraints.required_feedback_items`，并在顶层`feedback_resolution`中写明每条的实际改动；不得只修最显眼的一条。运行task返回的`finalize`；Controller会一次运行反馈集合、contract、capacity和HTML生成。任何未落实反馈、overfull、未知canvas、缺失区域或文案映射错误会在同一issue列表返回。不要写机器元数据、feedback或SVG。
