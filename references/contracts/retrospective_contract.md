# 复盘合同

定义 PPT 导出完成后的复盘产物。复盘只提出候选默认设置和流程观察，不自动改 Skill、不自动写 memory。

## 输出文件

| 文件 | 作用 |
|------|------|
| `_internal/07_retrospective/run_summary.json` | 运行统计摘要 |
| `_internal/07_retrospective/default_suggestions.md` | 给用户看的候选建议 |
| `_internal/07_retrospective/memory_candidates.json` | 机器可读的候选默认设置 |

## run_summary.json 最小结构

```json
{
  "project": "Q1 Product Review",
  "analyzed_at": "2026-07-09T16:00:00Z",
  "total_pages": 3,
  "batches": 1,
  "flow_summary": {
    "states_visited": ["CONTENT", "PLAN", "DRAFT", "REVIEW", "EXPORT"]
  },
  "layout_summary": {
    "pages_approved": 3,
    "pages_rejected": 0
  },
  "validation_summary": {
    "total_warnings": 2,
    "total_errors": 0,
    "common_warnings": [{"code": "TEXT_CONTAINER_TIGHT", "count": 2}]
  },
  "repair_summary": {
    "rounds": 1,
    "pages_repaired": ["page_03"]
  },
  "template_summary": {
    "used": false,
    "confidence": "N/A"
  }
}
```

## memory_candidates.json 最小结构

```json
{
  "requires_user_confirmation": true,
  "confirmation_required_before": "任何写回 SKILL.md、references 或 memory 的操作",
  "generated_at": "2026-07-09T16:00:00Z",
  "candidates": [
    {
      "field": "batch_size",
      "current": 3,
      "suggested": 2,
      "reason": "每批 3 页导致单页修复时间过长"
    }
  ],
  "summary": "本次运行共产生 1 条候选建议，请确认后手动应用。",
  "safe_to_apply_automatically": [],
  "needs_user_review": []
}
```

## 硬规则

1. `requires_user_confirmation` 必须为 `true`。
2. `safe_to_apply_automatically` 默认必须为空。
3. 每条候选建议必须包含 `current`、`suggested`、`reason`。
4. 复盘可以建议默认设置变化，但不得自动修改 `SKILL.md`、references、脚本或用户 memory。
5. 复盘不替代 batch learning；经验传递只通过用户确认后的显式修改发生。
