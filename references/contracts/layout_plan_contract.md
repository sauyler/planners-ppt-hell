# Layout Plan 合同

`layout_plan.json`记录SVG生成前的Layout阶段组织决策。用户审批的是这个计划；SVG阶段必须服从它。

## 路径

```text
_internal/01_layout_plan/layout_plan.json
```

容量诊断文件：

```text
_internal/01_layout_plan/layout_capacity_report.json

没有精确匹配的可选 canvas 时，`template_layout_id` 必须选择 `content_base`；禁止最近模型或隐式 fallback。
```

## 页面必填字段

Controller初始生成的scaffold顶层及每页都含`scaffold_status: "incomplete"`。Layout执行者必须在原文件上完成逐页判断，再将顶层和每页设为`completed`。不允许删除该字段来绕过检查；旧项目中本来不含该字段的plan仍可按原contract验证。

| 字段 | 规则 |
|---|---|
| `page_key` | 必须匹配 content 和 manifest |
| `layout_id` | layout taxonomy 中的参考族，或 `L00` 自定义 |
| `page_mode` | `rational` 或 `emotional` |
| `visual_density` | `dense`、`balanced` 或 `airy` |
| `grid` | 计划空间策略 |
| `wireframe` | 非空区域列表，使用 1920x1080 坐标 |
| `copy_handling` | 精确上屏文案和压缩理由 |
| `visual_asset_strategy` | 素材/图像需求和位置 |
| `layout_reason` | 人类可读的版式理由 |
| `scaffold_status` | scaffold项目必须为`completed` |

Fidelity模式额外必填`template_layout_id`，且必须来自单一registry。该ID直接选中layout的`canvas_file`作为SVG阶段起始画布；SVG根节点的`data-layout-id`必须完全一致。

可选字段：`layout_usage`、`design_judgment`、`why_this_layout`、`why_not_other_layouts`、`adaptation_note`、`anti_laziness_check`、`capacity_notes`、`design_risks`、`review_suggestions`。这些字段只在增加新信息时使用；不得与 `layout_reason` 或彼此重复同一句判断。Taxonomy 要求的反偷懒和替代方案判断至少进入 `layout_reason` 或其中一个对应字段。

## Common Mistakes

### `review_suggestions` 必须是数组，不是字符串

❌ **错误**：
```json
"review_suggestions": "建议将标题字号从 48px 降至 42px，并增加段间距。"
```

✅ **正确**：
```json
"review_suggestions": [
  "建议将标题字号从 48px 降至 42px",
  "建议增加段间距"
]
```

### `compression_rationale` 必须是数组，不是字符串

❌ **错误**：
```json
"compression_rationale": "原始文本 120 字压缩为 60 字上屏文案"
```

✅ **正确**：
```json
"compression_rationale": [
  "原始文本 120 字压缩为 60 字上屏文案"
]
```

### `final_on_slide` 必须是对象，不是字符串

❌ **错误**：
```json
"final_on_slide": "产品销售额同比增长 35%"
```

✅ **正确**：
```json
"final_on_slide": {
  "title": "核心指标",
  "body": ["产品销售额同比增长 35%", "环比增长 8%"]
}
```

`title` 必填。其他上屏内容可以使用通用 `subtitle`、`body`、`footer_takeaway`，也可以按页面语义使用 `items`、`data`、`strategies`、`capabilities` 等嵌套对象或数组。只要所有可见文案都完整保存在 `final_on_slide` 中即可；不要求自定义结构重复填入 `body`。Layout Review、容量估算与 SVG 阶段必须递归读取所有非 `title` 字段。

## Revision反馈闭环

revision task的`constraints.required_feedback_items`是当轮必须全部落实的冻结清单。`layout_plan.json`顶层必须增加`feedback_resolution`，对每一项原样记录`scope`、`page_key`、`request`，并用非空`implemented_change`说明实际改动。finalize会对集合进行硬校验；遗漏任一反馈不得进入新审阅或SVG。

## 完整 JSON 示例

```json
{
  "page_key": "page_01",
  "layout_id": "L03",
  "page_mode": "rational",
  "visual_density": "balanced",
  "grid": {"columns": 2, "rows": 3},
  "wireframe": [
    {"label": "title", "x": 80, "y": 40, "w": 1760, "h": 100, "zone": "header"},
    {"label": "body_left", "x": 80, "y": 160, "w": 850, "h": 800, "zone": "body"},
    {"label": "body_right", "x": 990, "y": 160, "w": 850, "h": 800, "zone": "body"}
  ],
  "copy_handling": {
    "final_on_slide": {"title": "Q2 业绩概览", "body": ["营收同比增长 35%", "利润率提升至 28%"]},
    "kept_on_slide": ["营收同比增长 35%", "利润率提升至 28%"],
    "compression_rationale": ["原始 150 字压缩为 2 条核心指标"],
    "compressed": true,
    "moved_to_notes": []
  },
  "visual_asset_strategy": {
    "asset_need": "required",
    "asset_type": "data_visual",
    "placement": "main_right",
    "reason": "右侧放置柱状图展示季度对比"
  },
  "layout_reason": "双栏布局适合同时展示文字指标和数据图表",
  "review_suggestions": ["标题字号建议 48px", "图表区域需要标注数据来源"]
}
```

## Wireframe

每个区域应包含：

- `label`
- `x`
- `y`
- `w`
- `h`
- 可选语义 `zone`

Wireframe 是空间计划，不是视觉装饰。空 wireframe 会被 `generate_layout_html.py` 拒绝。

## Copy Handling

`copy_handling` 必须包含：

- `final_on_slide`：SVG 应绘制的精确可见文案
- `kept_on_slide`：被代表在画面上的源内容
- `compression_rationale`：保留、压缩、移动或拆分的理由
- `compressed`：是否发生压缩，布尔值；具体压缩原则写入 `compression_rationale`
- `moved_to_notes`：移入 notes 的源内容；没有则为空数组

强规则：

- SVG 必须使用 `final_on_slide`，不得静默重写。
- 事实、数字、来源、品牌/产品名和核心结论必须保持精确。
- 放不下时，改 layout、移入 notes 或拆页；不得靠不可读字号或删意义解决。

## Visual Asset Strategy

必填字段：

- `asset_need`: `required`、`optional` 或 `none`
- `asset_type`: `real_asset`、`data_visual`、`editable_schematic`、`photo_placeholder`、`screenshot_placeholder`、`svg_background`、`svg_illustration`、`generated_image`、`chart` 或 `none`
- `placement`: `main_right`、`full_bleed`、`background`、`card_visual`、`evidence_slot`、`inline_diagram` 或 `none`
- `reason`

如果 `asset_need=none`，`asset_type` 和 `placement` 也必须为 `none`。

现有或上传图片上屏时还必须提供`assets`数组，每项包含：

| 字段 | 规则 |
|---|---|
| `asset_id` | 源资产ID；Layout Review上传图可为空 |
| `path` | 项目内相对路径，必须存在 |
| `slot_label` | 精确匹配一个非background wireframe label |
| `fit` | `contain`或`cover`；禁止`stretch` |
| `crop_ratio` | `original`、`16:9`、`4:3`、`1:1`或`3:4` |
| `crop_anchor` | `center`、`top`、`bottom`、`left`或`right` |
| `crop_options` | 2–3个真实可选方案；每项给`label/fit/crop_ratio/crop_anchor/tradeoff` |

`contain`完整显示，可以留白；`cover`填满槽位，可以裁剪。两者都必须保持原图比例。Layout Review上传返回的`path`和裁剪选择是revision的冻结输入，不能由SVG阶段另选。

Layout Review可新增图片槽。反馈中的新增图片必须含`is_new:true`、`operation:add`、唯一非空`slot_label`、项目内真实`path`、`changed:true`以及明确的`fit/crop_ratio/crop_anchor`。revision必须把它加入`visual_asset_strategy.assets`，创建对应wireframe label并重排本页；既有槽位仍须完整保留。批准反馈同时绑定审阅HTML和当前`layout_plan.json` hash。

## Capacity

容量状态：

- `ok`: 大概率能放下
- `tight`: 可能能放下，需要谨慎换行
- `overfull`: 大概率放不下
- `too_empty`: 空间需要更明确角色

主要内容 `overfull` 时必须在版式审批前处理，不能用不可读字号解决。

## 验证

```bash
python scripts/validate_contracts.py project <project_dir> --stage plan
python scripts/generate_layout_html.py <project_dir>
```
