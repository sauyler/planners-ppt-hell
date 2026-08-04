# 04 — SVG Batch阶段

一个task只对应一个batch。只读取task的batch input、已选canvas、batch-scoped runtime、`style_system.md`、`svg_rules.md`和`svg_stage_contract.md`。

## 执行

1. 主Agent先告知用户即将启动的batch和执行者。若task的`source_asset_handoff.has_images=true`，同一交接必须明确列出本批图片数量、文件和Layout批准的fit/crop；不得只说“有素材”。Controller返回多个ready batches时，先生成该波次的全部冻结task，再按`min(3, 宿主可用槽位, ready batch数)`并行启动一次性SVG子Agent；每波上限3个是默认执行约束，不得保守改成逐batch串行等待。每个子Agent完成finalize后立即退出，子Agent之间不建立affinity、resume、中间通信或轮询。宿主不支持时，先告知用户再由主Agent串行执行。
2. 不手抄命令。原样执行task的`canvas_start_argv_by_page`，由脚本建立页面并把canvas相对图片路径重写为产出SVG可达路径。
3. 按`template_layout_id`和已生成页面执行已批准canvas。
4. 原样保留所有`data-template-lock`层；replace layer初始为空。
5. 只在replace layer内按已批准wireframe和`final_on_slide`绘制；每个非`background` wireframe区域必须在对应SVG元素或分组上写入相同的`data-wireframe-label`，作为结构执行追踪；读取batch-scoped Layout approval，不遗漏已批准的图表、图片占位和模型化要求。
   - 图片使用相对`href`，写`data-slot`与`data-wireframe-label`。
   - `fit=contain`使用`preserveAspectRatio="xMidYMid meet"`；`fit=cover`使用`preserveAspectRatio="<anchor> slice"`。禁止`preserveAspectRatio="none"`。
   - 图表避免依赖`rotate/skew/matrix`；饼图弧和折线路径在导出前必须跑转换回归。
6. 不重新选择canvas、不改文案、不跨batch写入。
7. 先原样运行task的validator argv与visual render argv，两项初检都完成前不得修图。
8. 查看batch PNG/contact sheet，把初次validator issues和视觉发现合成唯一`combined_findings`，最多集中返修一次；不得先根据valiator修一轮、再根据视觉自审修第二轮。
9. 修复后同时重跑validator与视觉检查，更新语义自审文件；没有视觉证据或仍有must_fix时停止。
10. 运行task返回的`finalize`。

流程分别记录`artifact_sha256`（SVG + validator）和`evidence_sha256`（self-review）。若仅更新`<batch>_self_review.json`而当前artifact与规范PNG均稳定，Controller进入`SVG_EVIDENCE_SEAL`，用一次`seal-ready-batches`批量封存所有ready batch的新证据；不重跑validator、不重新渲染，也不要求执行者逐batch重新finalize。

task不得包含完整profile、完整registry、提取证据、asset registry、`components.svg`或未选canvas。渲染权限失败先对原命令申请提权；仍阻断则记录在self-review并停止当前阶段，不能伪装完成。

一次性SVG子Agent是默认首选；多个写入范围完全不相交的冻结task默认并发。失败task由新的一次性执行者或主Agent串行重跑，无需恢复旧会话。
