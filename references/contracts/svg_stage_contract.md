# SVG Stage Contract

一个task对应一个batch，写入范围与其他batch不相交。

## 输出

- `_internal/02_svg_source/<page_key>.svg`
- `_internal/04_validation/batches/<batch_id>.json`，必须由task validator argv生成
- `_internal/04_validation/batches/<batch_id>_self_review.json`

## Hard规则

- 页集合必须与task完全一致。
- SVG尺寸、技术限制、文字可读性和图片路径必须通过validator。
- 所有`<image>`必须保持宽高比：`preserveAspectRatio`只能使用`meet`或`slice`，不得为`none`。`slice`按Layout批准锚点裁剪；转换为PPT后不得拉伸。
- Fidelity页`data-layout-id`匹配Layout Plan；从task已选canvas开始。
- Fidelity页必须先原样执行`canvas_start_argv_by_page`，不手抄路径。所有本地`<image href>`必须从产出SVG所在目录可解析；绝对路径和丢失图片是硬错误。
- locked layer通过hash校验，required components完整；只修改空replace layer。
- validation每页`input_sha256`匹配当前SVG。
- 自审覆盖每页，记录`png_reviewed:true`或有来源的`external_feedback_applied:true`；`must_fix`为空。
- 自审必须记录合并质检闭环：初次validator与初次视觉检查先后完成，`combined_findings`同时收录两类结果，`repair_passes`只能为0或1，并在修复后重检两者。

建议自审最小结构：

```json
{
  "visual_review_status": "completed",
  "review_mode": "model_vision",
  "vision_available": true,
  "render_attempts": [],
  "combined_quality_gate": {
    "initial_validator_checked": true,
    "initial_visual_checked": true,
    "combined_findings": [],
    "repair_passes": 0,
    "final_validator_rechecked": true,
    "final_visual_rechecked": true
  },
  "pages": {
    "page_01": {
      "png_reviewed": true,
      "must_fix": [],
      "should_fix": [],
      "accepted_risks": []
    }
  }
}
```

模型不写result、hash、timestamp或完成状态。`finalize-stage`分别封存`artifact_sha256`（SVG与validator）和`evidence_sha256`（self-review）。仅evidence变化时，Controller必须用批量`seal-ready-batches`复核，不得让artifact失效或重复渲染。

图表页还必须通过`native_svg_to_ppt.py`的转换回归：饼图椭圆弧、折线/面积路径和嵌套`translate/scale`在PPT中不得相对SVG预览发生明显错位。
## Wireframe execution trace

For every approved Layout Plan wireframe region whose `zone` is not `background`, the corresponding SVG element or group must carry `data-wireframe-label="<exact label>"`. This is a structural trace only: it does not prescribe geometry or visual quality. The validator reports all missing labels for a page as one repair item.
