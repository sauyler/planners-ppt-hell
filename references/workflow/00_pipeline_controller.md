# 00 — Pipeline Controller

Controller是唯一状态机和机器元数据写者。当前Agent执行它返回的当前阶段，不扮演另一个管理Agent，也不与常驻子Agent通信。

## 启动

```bash
python scripts/init_svg_project.py <project_dir> --source <source.md|source.doc|source.docx>
python scripts/orchestrate/ppt_pipeline.py <project_dir> next --json
```

已有项目只运行`next`。禁止重复初始化。

初始化会把源文稿规范化为`_internal/00_project/source/source.md`，并把Markdown/DOCX中的本地图片复制到项目资产目录、写入`source_assets.json`。任何阶段task声明`source_asset_handoff.has_images=true`时，执行者交接必须明说图片存在，不能只交接文案。

## 执行动作

`next`返回以下之一：

- `do.user_question`：只向用户展示模板选择。
- `do.actions`：顺序运行确定性脚本。
- `do.stage`：运行`prepare`生成task，当前Agent读取task并写语义输出，最后运行`finalize`。
- Review：启动健康Server并等待用户显式提交。
- Export：由Controller严格缺图导出。

每个stage只读取task的`input_files`、只写`output_files`。模型不写时间、hash、状态或result。`finalize-stage`一次验证所有输入、输出、合同、hard gate和视觉证据；失败一次返回完整issues。

task必须携带可直接执行的`finalize_argv`。用户Review生成与`finalize-stage`共用`review_policy.py`中的同一阻断告警集合，不能出现“审阅页拒绝但finalize通过”的双重门禁。Layout人工批准绑定HTML和`layout_plan.json` hash；Visual批准绑定HTML和PNG hash。

## 顺序

Template（仅新模板）→ Content → Layout → SVG batches。Template、Content、Layout固定串行。SVG Controller一次交出全部ready task，执行者必须默认按每波最多3个batch并发（同时受宿主可用槽位限制）；不得保守改为逐batch串行。每个batch优先交给一个明确提示用户的一次性子Agent；只有宿主不支持子Agent时，先告知用户再由当前Agent串行降级。并发执行者不通信、不恢复、不保存身份。

## 人审

- Template：每个具体Layout独立选择“通过/舍弃/返修”并可填写单独反馈；整体区只有“提交批次反馈”和“全部通过”。“全部通过”必须把每个Layout明确设为通过后再提交，不能绕过逐Layout审计。
- Layout：全deck结构、final copy、wireframe和容量。
- Visual：全deck PNG。

Controller和模型均不得写批准。revision由Review Server反馈快照生成，不依赖旧会话。
Controller启动任一审阅后必须验证Server健康并直接打开对应页面。打开失败即阻断并返回诊断，不把URL当作完成结果。

## 日志

`flow_events.jsonl`自动记录pipeline command、stage完成/失败、命令、duration、issues和hash。不要另建空的主Agent日志作为完成条件。

## 完成

只有三道当前人审通过、所有hard gate通过且PPTX与当前SVG hashes一致时为COMPLETE。
