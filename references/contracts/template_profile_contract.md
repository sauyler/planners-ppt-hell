# Template Profile Contract

`template_profile.json`由当前Agent在Template阶段根据全部模板渲染页提取。它描述视觉设计方向，不是XML分析、施工坐标或组件复刻清单。

开始前必须先查看 `template_visuals/contact_sheet.png`，再逐页查看 manifest 中的全部页面。`pages_reviewed` 必须与 visual manifest 的页面全集一致；缺页时不能标记完成。

## 必填结构

```json
{
  "source_files": [],
  "method": "visual_only",
  "pages_reviewed": [],
  "design_direction": {
    "overall_character": {"value": "", "evidence_pages": [], "confidence": "high|medium|low"},
    "color_roles": [
      {
        "role": "primary|accent|text-primary|background|accent-tertiary|surface|link|link-visited|text-secondary",
        "hex": "#CA172A",
        "source": "xml_parsed|visual_estimate|manual",
        "confidence": "high|medium|low",
        "note": ""
      }
    ],
    "type_hierarchy": [
      {
        "role": "cover_title|heading|subheading|body|caption",
        "font_family": "Microsoft YaHei",
        "font_size_px": 36,
        "font_weight": "bold|normal|light",
        "source": "xml_parsed|svg_measured|visual_estimate|manual",
        "confidence": "high|medium|low"
      }
    ],
    "title_entry": {},
    "grid_and_alignment": {},
    "spacing_and_density": {},
    "image_language": {},
    "chart_language": {},
    "component_language": {},
    "deck_rhythm": {},
    "reusable_motifs": [],
    "page_exceptions": []
  },
  "reusable_assets": [
    {
      "asset_id": "bg_01",
      "file": "image1.jpeg",
      "usage": "full_bleed_background|logo|decorative|content",
      "applies_to": {"page_types": ["cover"], "page_indices": [1]},
      "source_pages": [1],
      "display_geometry": {"x": 0.0, "y": 0.0, "width": 1280.0, "height": 720.0},
      "fit": "cover|contain|none",
      "source_canvas": "1280x720",
      "target_canvas": "1920x1080",
      "confidence": "high|medium|low"
    }
  ],
  "decoration_patterns": [
    {
      "pattern_id": "chapter_red_block",
      "name": "章节红色块",
      "applies_to": {"page_types": ["chapter_main"]},
      "elements": [
        {"type": "rect|line|circle|ellipse|path", "x": 160, "y": 200, "width": 960, "height": 200,
         "rx": 8, "fill": "#CA172A",
         "filter": "drop-shadow(0 4px 3.33px rgba(0,0,0,0.2))"}
      ],
      "parameters": {
        "suggested_scale": 1.0,
        "canvas_change_strategy": "scale_y|stretch_width|preserve|recalculate"
      },
      "confidence": "high|medium|low"
    }
  ],
  "usage_policy": {
    "mode": "extraction_audit_only",
    "note": "完整 profile 不进入 SVG task"
  },
  "limitations": [],
  "generated_at": ""
}
```

每项重要判断必须包含视觉证据页与置信度。`pages_reviewed` 必须覆盖 visual manifest 中全部页面。

禁止从PPT XML、主题字段、坐标统计或文件名直接推出视觉风格；这些信息只可作为候选证据。允许记录源资产的原始几何用于溯源和画布适配，但不得把源x/y、组件尺寸或单页成品转成Layout阶段的固定施工指令。

PPTX结构提取可在顶层`structural_extraction`保存XML色值、主题字体、位图和SVG测量的**候选证据**。它不是视觉结论：Template阶段必须逐页查看渲染图后，才可将确认过的色彩、字体、资产或装饰写入本合同的`design_direction`、`reusable_assets`与`decoration_patterns`。整页图片或含示例文字的图片不得作为可复用资产。

视觉审阅完成后，Template阶段还必须写`template_asset_registry.json`，记录候选资产的approved/rejected、角色、来源页和安全说明。Template阶段尚未生成内容页`page_key`，因此不得创建页级复用计划；页级模板选择由Layout阶段写入`layout_plan.json.template_layout_id`。

`template_asset_registry.reviewed_source_ids` 必须与 `structural_extraction.assets[].asset_id` 和 `structural_extraction.native_shapes[].candidate_id` 的全集完全一致。即使候选明显无效，也必须明确列为 rejected；不得以“未提及”代替审阅。图片、placeholder、chart 和文本框不得混入 `native_shapes`；线条候选必须保留 stroke、stroke_width 和方向证据。

人工模板审阅的主对象是由 fidelity registry 组装的逐 layout 完整页面抽象 SVG，不是候选表格或 contact sheet。批准凭证必须覆盖 registry 的全部 layout，且与当前审阅 HTML 和源模板渲染图 hash 绑定。

在人工审阅前，Template阶段必须先完成源页与canvas PNG的视觉闭环，写入`template_canvas_self_review.json`。视觉闭环必须识别重复元素、真实页型、字体层级、卡片/强调语言和关键位置，并根据渲染结果返修canvas。只有元素清单、通用占位框或无法从源页识别的layout必须判定为不可用。Controller必须验证全页覆盖、逐layout结论、未解决must-fix和全部证据hash。

当用户选择**fidelity模板复用**时，Template阶段还须写`template_worker_result.json`：先生成`content_base`，其required components只能表达跨页稳定身份且必须非空；再从结构候选中批准经全页视觉审阅确认的组件，并为每个可用layout明确`required_components`/`optional_components`。随后运行`build_fidelity_template.py`生成单一registry、`components.svg`和逐layout canvas。审阅页和SVG阶段必须共用这些canvas；SVG阶段只替换content layer，不得凭视觉近似重画locked layer。

一个`source_id`只能定义一个fidelity component。`geometry_override`仅用于小幅纠偏，必须提供`override_reason`；不得把一个源形状改造成另一种组件。含文字的源形状必须声明`text_handling: strip`。Builder统一把源画布坐标缩放到1920×1080，模型不得手工完成坐标换算。

Fidelity模式没有任何可安全批准的组件或任一layout的`required_components`为空时不得静默退化；Controller必须阻断并让用户选择继续修订、改为reference模式或更换模板。

Template阶段输出完成后不能直接进入Layout。必须生成模板人工审阅页：每个具体Layout独立提供“通过/舍弃/返修”和单独反馈框；整体只提供“提交批次反馈”“全部通过”、整体反馈与模板命名。“全部通过”必须先把全部Layout设为通过。只有所有Layout明确通过、模板名非空且当前证据hash一致时，Controller才能发布；舍弃或返修均进入Template revision，其中被舍弃的非基础Layout从单一registry/canvas集合移除，`content_base`若被舍弃则必须重建而不能缺失。模型不得直接写模板库。

Layout与SVG阶段将其作为项目设计方向，不能用它覆盖用户brief、已批准layout、`style_system.md`或`svg_rules.md`。

### 字段说明

- **color_roles[].source**: `visual_estimate` 为看图估计；`manual` 为人工指定；`xml_parsed` 只可在视觉确认其与渲染图一致后使用。XML 本身不是 MUST 级约束。
- **type_hierarchy[].source**: `svg_measured` 表示字号从 SVG 渲染测量；`visual_estimate` 看图估计；`manual` 人工指定；`xml_parsed` 必须有页面视觉证据佐证。
- **reusable_assets**: 仅包含由Template阶段视觉确认可安全复用的位图资产。`usage`标明角色，`fit`只能为等比裁剪`cover`、完整显示`contain`或不强制适配`none`；禁止`stretch`。`applies_to`标明适用页。
- **decoration_patterns**: 跨页重复的装饰形状（来自 SVG 分析），`elements` 为 SVG 元素描述，`parameters.canvas_change_strategy` 标明画布变化时的适配方式。
- **usage_policy.mode**: 只记录模板提取审计。完整 profile 不进入 SVG task，也不得覆盖 Layout 的结构、wireframe 或文案。

> 强制优先级：XML/PPTX 结构提取产物始终只是审计候选，不能自行成为 SVG 施工约束。
