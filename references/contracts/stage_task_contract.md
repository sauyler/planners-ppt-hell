# Stage Task Contract

Task由`make_stage_task.py`原子生成，是当前阶段唯一输入快照。

必填：`task_id`、`task_sha256`、`step`、`project_dir`、`reference_root`、`contract`、`input_files`、`input_hashes`、`output_files`、`executor`、`constraints`、`finalize_argv`。

- `input_files`与`input_hashes`键集合必须完全相同。
- 相对reference以`reference_root`解析；项目产物以`project_dir`解析。
- 模型只读取声明输入、只写声明输出；不得写hash、timestamp、状态、manifest、events或feedback。
- revision task必须包含Review Server反馈快照和`revision_feedback_sha256`。
- 阶段完成只由`finalize_stage.py`写入`stage_completed`事件。
- 执行者必须原样运行`finalize_argv`，不得自行拼接finalize命令。SVG task同时记录创建时的`layout_plan_sha256`；Layout变化后旧task自动失效并重新生成。
- Task只携带当前阶段必要上下文，不携带架构文档、其他阶段方法、对话记录或导出实现。
