# Documentation index

- `ARCHITECTURE.md`：当前可发布主版本的完整架构、状态机、合同与稳定性边界。
- `history/Template-Runtime-Simplification-Handoff.md`：模板运行时简化交接。
- `history/architecture-upgrade-20260717/`：逐文件架构审计、升级执行与验收材料。
- `history/one-shot-upgrade-vnext-20260717/`：单一 Agent 控制面升级规划、问题映射与回滚设计。
- `history/r2-upgrade-logs/`：R2 会话审计与修改测试记录。
- `history/run-analysis/`：完整运行日志、因果审计和效率分析。
- `history/2026-07-18-main-release/`：本次主版本修复、发布、回滚位置与验证结果。
- `history/legacy-planning/`：原仓库根 planning 包中的早期 MECE、模板提取、架构简化与升级材料。

`docs/` 只用于仓库维护和历史追溯。正常 Skill 调用不读取这些文件；运行时只由 `SKILL.md` 路由到 `references/` 和 task 明确列出的输入。
