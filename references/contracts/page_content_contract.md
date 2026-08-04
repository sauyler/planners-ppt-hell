# Page Content 合同

`page_content.json`是页面文案的完整来源。Content阶段保留含义和可追溯性；Layout阶段决定哪些内容上屏。

## 路径

```text
_internal/01_content/page_content.json
```

## 必要形状

| 字段 | 规则 |
|---|---|
| `project` | 项目名 |
| `pages` | 非空、有序页面列表 |
| `pages[].page_key` | 唯一页面 id，格式 `page_01`，连续递增 |
| `pages[].action_title` | 非空判断句，不是栏目标签 |
| `pages[].core_message` | 1-3 句页面核心含义 |
| `pages[].body_blocks` | 非空，保留正文信息 |

可选字段：`source_path`、`generated_at`、`source_page_id`、`source_title`、`tables`、`speaker_notes`、`source_excerpt`、`source_assets`。

源材料含图片时，相关页面的`source_assets`必须为数组，每项至少包含：

- `asset_id`：匹配`_internal/00_project/source/source_assets.json`
- `role_candidate`：该图在内容中的证据/案例/产品/人物/场景作用
- `source_context`：图片在原稿附近的标题、段落或说明
- 可选`caption`、`alt`

Content只保持图片归属和语义，不决定裁剪或最终槽位。
`source_assets.json`中的每个`asset_id`都必须分配到至少一个页面；不能因暂时不确定是否上屏而遗漏。是否最终上屏由Layout决定。

`source_excerpt` 有源文案时应保存该页完整来源，不是短摘录。

## 文案规则

允许：

- 将源材料拆成稳定页序。
- 将源标题整理为更适合 PPT 的 `action_title`。
- 将正文结构化为段落、列表、KPI、引用或表格。
- 将背景解释和讲稿提示放入 `speaker_notes`。
- 修正明显标点、空格、重复标题。

禁止：

- 改事实、数字、品牌名、日期、来源、案例或限定条件。
- 添加源文案没有支持的结论。
- 因为担心放不下而删正文。
- 合并不同论点导致不可追溯。
- 删除风险、保留意见、不确定性或反例。

## 强规则

- `page_key` 是唯一页面标识。
- 不使用 `page`、`page_number`、`page_id`、`layout` 作为页面标识。
- `body_blocks` 保留完整内容；上屏删减只能记录在 `layout_plan.json.copy_handling`。
- 文案太长时先完整保留，PLAN 再决定压缩、移入 notes、改 layout 或拆页。

## 验证

```bash
python scripts/validate_contracts.py project <project_dir> --stage content
```
