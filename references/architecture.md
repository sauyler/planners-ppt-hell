# Planner's PPT Hell vNext architecture

本文件只供维护者读取，不进入阶段task。

## 分层

- `ppt_pipeline.py`是唯一控制面：派生状态、生成当前动作、启动审阅、发布模板和导出。
- `make_stage_task.py`生成不可变阶段快照与输入hash。
- `finalize_stage.py`是唯一阶段完成写者：验证输入/输出/合同/视觉证据，机器生成时间、hash、issues和`stage_completed`事件。
- 当前主Agent串行完成Template、Content和Layout。SVG每个batch首选一个一次性子Agent；子Agent只有冻结task的生产职责，没有持久会话身份、affinity或状态职责。主Agent在启动前告知用户；宿主不支持时告知后串行回退。
- Review Server是唯一人工反馈写者。

## 单一事实源

| 问题 | 权威 |
|---|---|
| 项目状态与运行时间 | `flow_events.jsonl`机器事件 |
| 页面完整事实 | `page_content.json` |
| 源文稿与图片资产 | `_internal/00_project/source/source.md`与`source_assets.json` |
| 上屏文案、结构、wireframe、素材角色和canvas选择 | 已批准`layout_plan.json` |
| 模板视觉身份与页面边界 | 单一`template_registry.json`和已批准canvas |
| 人工决定 | Server写入且hash绑定的feedback JSON |

Layout Review Server可把用户上传图片写入`_internal/01_layout_plan/uploads/`，并只通过`layout_feedback.json`把路径、slot和裁剪决定交给Layout revision。上传不是第二asset registry。

不保存`agent_result.json`、Agent ID、affinity、parallel/serial状态或对话式恢复信息。

## 状态机

```text
PROJECT_MISSING → TEMPLATE_INTAKE
→ TEMPLATE_RENDER_REQUIRED / TEMPLATE / TEMPLATE_REVIEW / TEMPLATE_REVISION / TEMPLATE_PUBLISH
→ CONTENT → LAYOUT → LAYOUT_REVIEW
→ SVG_BATCH_BUILD → VISUAL_REVIEW → EXPORT → COMPLETE
```

每次`next`只返回当前状态的一个执行单元。Template、Content、Layout不并行。SVG按batch使用一次性子Agent是默认行为；多个写集不相交的冻结task可并发。返修时旧Layout Plan、模板产物和SVG必须复制到task inputs快照，实时产物路径只作为输出，禁止输入/输出同路径。

## 阶段完成

模型不声明完成。`finalize-stage`必须同时验证：task hash、所有input hash、所有声明输出、阶段contract、hard validator和视觉闭环；一次返回全部issues。成功才追加`stage_completed`及当前output/feedback hashes。Controller判断完成时再次绑定当前task hash和当前输出hash。revision只靠冻结feedback/旧产物snapshot，不依赖旧会话。相同SVG task与产物已完成且PNG证据仍在时，finalize幂等返回，不重复渲染或追加事件。

## 模板运行时

Template canvas只固定身份与边界，replace layer为空。Layout精确选择专用canvas；无精确匹配时选择`content_base`。SVG task只包含batch-scoped runtime、已选canvas、最终文案、wireframe和最小style。完整profile、提取证据、asset registry、`components.svg`和未选canvas禁止进入。每个非background wireframe区域以同名`data-wireframe-label`记录结构执行，不扩展为几何或视觉质量门禁。

## 人工门禁

- Template：每Layout通过/舍弃/返修 + 单独反馈；整体区只有提交批次反馈/全部通过 + 整体反馈 + 模板名。
- Layout：全deck结构、final copy、wireframe、容量，以及图片上传/替换和非变形裁剪选择。
- Visual：全deck PNG审阅。

批准绑定当前HTML及相关PNG/SVG/registry。任何证据变化使旧批准失效。Controller和模型均不得写批准。

## 维护规则

- 一个状态机、一个registry、一个review写入路径、一个stage issue模型。
- hard validators只防可确定性事故；启发式建议为warning。
- 失败一次聚合；返修保持集中且有界，不把validator拆成逐字段循环。
- 旧机制被替代后直接删除，不保留fallback或备份目录。
- 运行日志自动生成；不依赖Agent另写聊天日志。
