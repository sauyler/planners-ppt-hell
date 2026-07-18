# Page Manifest Contract

`page_manifest.json`是Controller独占的稳定项目索引，不保存模型会话、阶段结果或第二状态机。

```json
{
  "project": "项目名",
  "template_intake": {
    "status": "pending|provided|none",
    "mode": "reference|fidelity|none",
    "origin": "extraction|library|none",
    "source_files": []
  },
  "batch_size": 3,
  "pages": [],
  "batch_config": {}
}
```

Content finalize按页序写`pages`和`batch_config`。每页只含`page_key`、`batch_id`、`svg_path`、`png_path`。模板发布可写`library_template_id`或`published_template_id`。

不允许`execution.mode`、Agent ID、affinity、timestamp freshness或手写workflow state。状态从task、机器events、语义产物、validator和当前人工证据派生。
