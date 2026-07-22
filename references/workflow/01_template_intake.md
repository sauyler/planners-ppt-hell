# 01 — Template选择与提取

初始化后必须让用户选择：推荐默认模板、已有本地模板、新提取或无模板。必须显示Controller问题并等待用户新回复；初始请求中已附PPTX/PDF/图片路径只表示文件可用，不构成“提取新模板”的同意。未经新回复不得调用`confirm-template`，不开始Content。已有模板直接应用人工批准包；只有新模板进入本阶段。

## 视觉证据

- PPTX由宿主演示文稿能力渲染为有序逐页PNG；PDF/图片同样形成有序视觉manifest。
- 程序结构提取只提供候选，不能直接宣布视觉风格或可复用组件。
- 当前Agent必须查看contact sheet和所有源页。

## 模板抽象

Template只固定视觉身份和页面边界：背景、跨页重复装饰、品牌元素、页眉页脚、安全区域、核心功能页和可选专用页型。内容区结构、标题/正文坐标和文案由Layout决定。

Fidelity模式必须：

1. 建立`content_base`；无精确语义匹配时供Layout默认选择。
2. 只从真实源页证据建立cover/contents/chapter/closing和可选专用canvas。
3. 每个canvas有locked层和唯一、可见元素为空的replace layer。
4. required components非空且只表达必须保留的视觉身份。
5. 运行task给定builder/render命令。
6. 对照源图和canvas PNG；通用灰框、错误缩放、只有零散元素、缺少模板身份或凭taxonomy臆造的layout必须返修或判不可用。
7. 最多一次集中返修，仍有must_fix就停止。
8. 写`template_canvas_self_review.json`，由visual gate绑定当前源PNG、canvas SVG/PNG和contact sheet hashes。

## 人工审阅

- 每个Layout：通过 / 舍弃 / 返修 + 独立反馈框。
- 整体区：只有“提交批次反馈”和“全部通过”，另保留整体反馈与模板名。
- 点击“全部通过”自动将所有Layout选为通过并提交；要求模板名非空且全部证据新鲜。
- 任一Layout返修时，该Layout或整体反馈必须可执行。任一Layout舍弃或返修都生成冻结revision task：舍弃项从registry/canvas删除，返修项按反馈修复。`content_base`如被舍弃，必须在同一revision重建可用的`content_base`。

只有Review Server写反馈。Controller只在当前批准后发布模板库；任何产物变化都必须重新审阅。

## 运行时边界

完整profile、结构提取证据、asset registry、`components.svg`和未选canvas只用于提取/审计，不进入SVG task。专用canvas只有Layout精确选择后才进入对应batch。
