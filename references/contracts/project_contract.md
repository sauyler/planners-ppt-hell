# 机器接口

这些文件只服务真实消费者，不是设计思考问卷。

| 文件 | 写者 → 消费者 | 最小职责 |
|---|---|---|
| source/source_assets.json | 素材脚本 → 底稿、检查 | 资产 ID、路径、源上下文 |
| page_content.json | 模型 → 索引、制作、notes 导出 | project、pages[{page_key,mode?,title,content,source_assets?,notes?}]、unused_assets? |
| design_direction.md | 模型 → 跨页制作、版本检查 | 这套页面共同视觉决定：网格与纵向步长、层级角色、色彩角色、跨页锚点、节奏 |
| page_manifest.json | Controller → Server、渲染 | v5 版本、页序与路径、每页 mode、模板模式 |
| 每页 validation JSON | check → inspect、Review | 实际输入版本、PNG hash、技术报告 |
| inspections.json | inspect → Review | render token、具体观察、must_fix |
| snapshot.json | Review 生成器 → Server | HTML、页面及PNG版本、实际图片集合 |
| feedback.json | Server → 创作、导出 | 页级决定、区域、资产修改、全部反馈 items 与 provenance |
| resolutions.json | resolve → Review | 反馈 ID 与实际解决说明 |
| export.json | Controller → 完成状态 | PPTX 与页面版本、实际渲染检查证据 |

page_key 为稳定的字母开头标识，后续为字母数字、短横线或下划线；顺序由 pages 数组确定。不是连续页码，也不是 batch ID。

`mode` 是每页的读法声明，只接受 `讲` 或 `读`；缺失按 `读` 处理。它唯一影响的技术量是字号下限（`讲` ≥18px，`读` ≥12px），其余是设计判断的输入。它**不是**布局类型、密度或视觉风格枚举。

模型直接写底稿、方向与 SVG，其余通过命令写。Controller 计算时间和 hash。脚本能证明文件一致、缺图与技术错误，**不能**证明视觉检查真实发生、设计是否成立或商业判断是否正确——样式类启发式已从校验器移除，那部分判断归模型看图与人审。
