# 03 — Layout阶段

只读取task列出的Content、可信模板方向、单一registry、`layout_taxonomy.md`和`layout_plan_contract.md`。

Layout独占：最终上屏文案、内容关系、`layout_id`、wireframe、素材角色、容量和`template_layout_id`。

Controller在初始Layout前必须先运行`scaffold_layout_plan.py`生成页数、page key、基础文案和图片槽均已对齐的确定性scaffold。模型只在这份JSON上做逐页判断，禁止手写整套数组或临时编写Python生成器重建文件。完成后将顶层和每页`scaffold_status`设为`completed`；任一为`incomplete`都会被contract阻断。

## 图片布局

- 先核对Content的`source_assets`和项目`source_assets.json`；现有图片优先作为真实证据，不得退化成通用占位。
- 每张上屏图片绑定`asset_id/path`与一个明确的wireframe `slot_label`。
- 给用户可比较的裁剪方案：至少`完整显示（contain，不裁剪）`、`填满区域（cover，居中裁剪）`；主体明显偏离中心时再提供`填满区域（cover，焦点锚定）`。只保留真实有差异的2–3项。
- Layout最终选择`fit=contain|cover`、`crop_ratio=original|16:9|4:3|1:1|3:4`和`crop_anchor=center|top|bottom|left|right`。不得使用stretch，不得通过同时改宽高扭曲原图。
- Layout Review右侧按`slot_label`展示所有图片槽；一页多图时用缩略图tab切换，缩略图tab本身也是拖拽上传目标，每个槽位独立上传、裁剪、预览和交接。除替换既有槽位外，必须始终提供可拖拽、点击或粘贴的“新增图片槽”投放区：新条目使用唯一`slot_label`、`is_new:true`、`operation:add`，上传成功后才进入提交载荷。页面必须明确提示“当前只确认图片与裁剪；提交本轮审阅后由下一轮Layout创建槽位和重排”，不得暗示当前wireframe会即时变化。
- 图片/裁剪改动是相对审阅页加载基线计算的状态，不是永久事件标记。既有槽位重置或新增槽位移除后必须解除待修改状态，不能形成批准死锁。
- Review每次只把一页放在主工作台，左侧页面轨显示顺序与状态；不把全deck纵向堆叠成长页。
- 图片槽同时支持拖拽、点击和剪贴板图片；裁剪选项必须用当前真实图片和目标槽位呈现可比较预览，不用纯文字下拉框。
- 审阅页只在左侧16:9 wireframe内展示最终上屏文案，文字按槽位容量自适应字号并在浏览器实测溢出后继续缩小，不再于右侧重复一份。右侧上部只放图片槽与裁剪，审批与反馈固定在右侧底部且不得被全局底栏遮挡。版式ID、密度、网格、理由与建议放在左侧wireframe下方的默认收起说明中；原稿和备注不占用主审阅区。导航色只表达人工状态；底部只用一个“提交本轮审阅”打开同时包含整套反馈与提交确认的统一层。

## Canvas选择

- 只有内容关系与专用canvas精确一致时才选择专用canvas。
- 没有精确匹配时必须选择`content_base`；禁止最近模型fallback。
- 选择必须存在于当前单一registry。

## Wireframe

- 为每个上屏区写明确x/y/w/h、zone和label。
- `copy_handling.final_on_slide`必须能映射到wireframe区域。
- 需要移入notes或拆页时明确记录，不让SVG阶段重新做内容取舍。
- 全deck检查节奏、密度和重复构图。
- 图片框比例必须与所选`crop_ratio`一致；`contain`可以留白，`cover`可以裁剪但不能变形。

## 完成

只写`layout_plan.json`。revision时必须逐条落实`constraints.required_feedback_items`，并在顶层`feedback_resolution`中写明每条的实际改动；不得只修最显眼的一条。运行task返回的`finalize`；Controller会一次运行反馈集合、contract、capacity和HTML生成。任何未落实反馈、overfull、未知canvas、缺失区域或文案映射错误会在同一issue列表返回。不要写机器元数据、feedback或SVG。
