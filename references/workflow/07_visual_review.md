# Full-deck Visual Review

Visual Review 一次加载整份 deck，但用单页校样台逐页决策，不逐 batch 生成独立长页。

## Review 前提

- 全部 batch Worker已完成。
- 全部页面 SVG 与 PNG 存在。
- 每个 batch 实际运行 validator，hard errors 为零。
- 每个 batch 已完成视觉闭环：Worker实际查看 PNG，或同一 Worker已应用有来源的外部视觉反馈。
- 所有视觉发现已驱动 SVG 修复并重新通过 validator 与渲染复查；不存在未解决的 `must_fix`。
- 权限或沙箱失败仍处于恢复中时不得生成用户Review；停止当前stage，让用户选择宿主渲染或提供该batch的PNG。

## 页面内容

- 全 deck contact sheet 与每页大图
- 页面顺序与 batch 归属
- validator warnings
- Worker视觉证据、实际修改与已接受风险摘要
- 页面级反馈与批准
- 全局反馈
- 全量批准

交互上，左侧缩略图轨只显示页面缩略图、页码和状态点，不重复页面标题；中间只显示当前页大图或前后版本对比；右侧只保留阻断、模型建议、区域反馈、用户反馈和通过决定。用户点击“框选页面问题”后在当前页拖出矩形，紧接着填写该位置的问题；保存为`annotations[]`的归一化`x/y/w/h`与文字，修订task必须将其转为`scope=page_region`的必做反馈。底部固定导航支持上一页、下一页、标记修改、批准当前页和提交本轮审阅。

反馈只写`_internal/05_review/feedback.json`，并绑定当前HTML与PNG hash。Controller不代替用户批准。

导航使用人工三态：未处理、批准、修改。机器PASS与自检完成只能显示在检查区，不能把导航标绿。底栏“标记修改/批准当前页”是页级动作；唯一的“提交本轮审阅”层同时承载可选整套反馈、决策统计和提交方式，可提交已有决定或只批准未处理页后提交，不能覆盖已标记修改页。

生成revision task前先做确定性修复层路由：单个标注覆盖幻灯片40%以上，或文字明确包含整页、整体、版式、布局、结构、重排、换版、重新设计等意图时，返回Layout revision并重新人工审阅；其余局部视觉问题才留在SVG层。只有当前HTML与PNG provenance仍匹配的反馈可以触发revision。

## Reject

Controller将页面反馈映射到受影响batch并生成冻结revision task。修订完成后重新生成全deck review，不生成局部review页面。
