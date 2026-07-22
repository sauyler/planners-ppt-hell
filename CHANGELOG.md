# Changelog

## 2026-07-18 — current main release

- 支持启动时明确选择默认模板、上传提取新模板或无模板。
- 新模板逐 Layout 审阅：通过、舍弃、返修；保留单独反馈、整体反馈和模板命名。
- Template canvas 只固定视觉身份与页面边界，replace layer 保持为空。
- Layout 独占结构、最终文案、wireframe 与 canvas 选择；无精确匹配时使用 `content_base`。
- SVG task 缩减为当前 batch 的已选 canvas、最小运行时、批准文案与 wireframe。
- 移除持久 Parent/Worker 会话编排；Template、Content、Layout 由当前 Agent 串行执行，SVG batch 只保留一次性并发能力。
- 返修任务改用冻结的旧产物快照，消除输入/输出同路径导致的 stale 循环。
- 阶段完成绑定当前 task hash 和当前输出 hash；重复 SVG finalize 在证据仍有效时幂等返回。
- 增加 wireframe 结构执行追踪，但不新增视觉质量判断或强化视觉流程门禁。

