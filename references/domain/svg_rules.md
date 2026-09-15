# SVG 与可编辑 PPT 兼容

模型负责画面判断，技术规则用于防止渲染和转换事故。使用 1920×1080、viewBox="0 0 1920 1080"，同套保持一致。

**单位换算（写死在这里，别每次重算）**：画布 1920px 对应 13.333in 宽的幻灯片，所以 **1 SVG px = 0.5pt**。32px = 16pt，48px = 24pt，96px = 48pt。字号下限按页面 `mode` 判：`讲` 页 ≥18px（9pt），`读` 页 ≥12px（6pt）。

## 基础表达

使用 rect、line、circle、ellipse、polygon、path、text、image 及少量 g。文字显式写 x、y、font-family、font-size、font-weight、fill；深色背景文字不要依赖组继承颜色。中文长句显式换行，每行独立 text，预留足够行距。

禁用转换器不能可靠处理的 foreignObject、filter、use、style、marker、mask、animate，以及 stroke-dasharray、textLength、lengthAdjust 和 marker-*。使用显式属性，不依赖 CSS。避免 rotate、skew、matrix；简单 translate / scale 也要核对转换结果。渐变、clipPath 和复杂 path 必须跑实际转换验证。用几何箭头替代 marker，不能把标签藏进图片。

标题、正文、图表数据标签和来源都是可编辑 text；图形以原生 SVG 表达。无需额外写布局类型、密度或设计理由 metadata。

## 纵向构造

页内纵向位置从 `design_direction.md` 里定下的**一条纵向步长**导出，而不是先摆元素再让它们看起来齐（中文的字面方块天然构成这种步长，见 `style_system.md` 规则 13）。跨页重复的元素——页眉、页脚、页码、栏目名——各页使用**同一组坐标**，让它们落在同一条水平线上。

中西文混排会打断纯方块网格，这是正常的；要稳定的是**行的对齐关系**（段首、段末、栏目起点），不是让每个字符落在网格上。

## 图片

```xml
<image href="../00_project/source/assets/asset_001.png"
       x="100" y="220" width="900" height="600"
       data-asset-key="evidence" preserveAspectRatio="xMidYMid meet"/>
```

使用项目内文件，完整显示用 meet，填满用 slice，可用 xMin/xMid/xMax 与 YMin/YMid/YMax 选择焦点。禁止 none 拉伸。`data-asset-key` 用于最终审阅中的换图与裁剪；全页位置以实际 SVG 为准。

## 技术检查与视觉判断

check 只保留两类检查：**转成 PPT 会坏**的（画布契约、禁用元素与属性、图片必须是真实存在的项目内文件且不得拉伸、tspan 换行、文字缺 fill 或 font-weight 非法、元素出画布），和**在任何风格下都是缺陷**的（文字压文字、空页）。它**不再**评价密度、字号档位、容器选择、留白多少或配色——那些是设计决定，由你看渲染图判断。

因此：技术报告干净不等于页面好看。实际查看每页 PNG 大图，按 `style_system.md` 的五个自检问题核对。`OUTSIDE_SAFE_MARGIN` 这类 info 级提示只是提醒（满版出血是正当的设计手法），不要为消除提示改设计。

遇到容量不足，重排、断行、拆页、调整内容与 notes，不以不断缩字解决。关键事实、来源和限定条件仍受保护。修订后检查新渲染；只要有实质进展就继续，不限制一次修复。

严格模板下保留 data-template-lock 层、required components、data-layout-id 和 data-template-content-layer="replace"。指定 canvas 从脚本实例化；检查锁层与真实资产，不能用近似重绘冒充复用。

SVG 显示正确不证明 PPTX 正确。圆弧、折线、图片裁剪、字体和透明度在最终 PPTX 渲染中再次核对。
