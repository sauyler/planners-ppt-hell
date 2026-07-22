# 04 — SVG Batch阶段

一个task只对应一个batch。只读取task的batch input、已选canvas、batch-scoped runtime、`style_system.md`、`svg_rules.md`和`svg_stage_contract.md`。

## 执行

1. 主Agent先告知用户即将启动的batch和执行者。宿主支持子Agent时，每个batch启动一个一次性SVG子Agent；完成finalize后立即退出。不得建立affinity、resume、中间通信或轮询。宿主不支持时，先告知用户再由主Agent串行执行。
2. 不手抄命令。原样执行task的`canvas_start_argv_by_page`，由脚本建立页面并把canvas相对图片路径重写为产出SVG可达路径。
3. 按`template_layout_id`和已生成页面执行已批准canvas。
4. 原样保留所有`data-template-lock`层；replace layer初始为空。
5. 只在replace layer内按已批准wireframe和`final_on_slide`绘制；每个非`background` wireframe区域必须在对应SVG元素或分组上写入相同的`data-wireframe-label`，作为结构执行追踪；读取batch-scoped Layout approval，不遗漏已批准的图表、图片占位和模型化要求。
6. 不重新选择canvas、不改文案、不跨batch写入。
7. 原样运行task的validator argv和render argv。
8. 查看batch PNG/contact sheet，把视觉发现与validator issues合成一份修复清单，最多集中返修一次。
9. 更新语义自审文件；没有视觉证据或仍有must_fix时停止。
10. 运行task返回的`finalize`。

task不得包含完整profile、完整registry、提取证据、asset registry、`components.svg`或未选canvas。渲染权限失败先对原命令申请提权；仍阻断则记录在self-review并停止当前阶段，不能伪装完成。

一次性SVG子Agent是默认首选；多个写入范围完全不相交的冻结task可并发。失败task由新的一次性执行者或主Agent串行重跑，无需恢复旧会话。
