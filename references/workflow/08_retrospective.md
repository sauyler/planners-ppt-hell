# 08 — Retrospective 参考

## 触发条件
Retrospective 是导出完成后的显式可选命令；当前主状态机不会自动派发。

## 工作流程
1. Controller运行`scripts/retrospective/analyze_run.py <project_dir>`
2. 脚本收集并分析：
   - flow_events.jsonl（状态转换轨迹）
   - layout_feedback.json（版式审批偏好）
   - visual feedback（视觉反馈偏好）
   - validation_summary.json（常见 warning/error）
   - repair loop history（修复成本）
   - template_profile.json（模板使用情况）
3. 输出三个文件：
   - `_internal/07_retrospective/run_summary.json`
   - `_internal/07_retrospective/default_suggestions.md`
   - `_internal/07_retrospective/memory_candidates.json`

## 核心约束
- **必须用户确认后才写回**：`memory_candidates.json` 包含 `requires_user_confirmation: true`
- **不自动修改 Skill**：脚本不得自动修改 SKILL.md、references 或用户 memory
- **safe_to_apply_automatically 默认为空**：除非用户明确允许

## 分析产出示例
- 用户偏好的版式方向（常批准/常拒绝的 layout_id）
- 常见 SVG warning 和修复建议
- batch size 建议
- 规则升级/降级建议
