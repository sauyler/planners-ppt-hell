# Full-deck Visual Review

Visual Review 一次展示整份 deck，不逐 batch 审阅。

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

反馈只写`_internal/05_review/feedback.json`，并绑定当前HTML与PNG hash。Controller不代替用户批准。

## Reject

Controller将页面反馈映射到受影响batch并生成冻结revision task。修订完成后重新生成全deck review，不生成局部review页面。
