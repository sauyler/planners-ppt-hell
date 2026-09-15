# 开始与恢复

目标：把机械准备交给工具，让模型获得可继续制作的材料与当前状态。
在 Skill 根目录运行，项目路径使用绝对路径；使用已具备 requirements.txt 依赖的 Python。

```bash
python scripts/init_svg_project.py <project> --source <source.md|source.doc|source.docx>
python scripts/orchestrate/ppt_pipeline.py <project> next --json
```

初始化原子复制源文及本地图片。已有项目只运行 next；旧版项目不能在原地混用新控制器，继续使用归档旧 Skill 完成，或在新目录从材料重新开始并人工核对旧反馈。

next 给出 CONTENT、CREATE、VISUAL_REVIEW、EXPORT、EXPORT_VERIFY 或 COMPLETE。这是恢复提示，不把模型拆成只能读白名单的小执行器：可以回看原文、图片、相邻页面和整套方向。

## 两次必问，别的都别问

读完材料、写完内容底稿后，**一次性**把这两件问清：

1. **视觉来源** — 自主设计／用模板库里的模板／给一份视觉参考／新建严格品牌模板。四条路线的命令、产物与完成标准见 `01_template_intake.md`。
   **不要静默默认自主设计。** 库里有一个内置模板，用户可能手上有参考成品或自己的品牌 PPTX——这三件事都会显著改变成品，而它们都不会自己冒出来。
2. **图片** — 这套需不需要配图、要什么类型、大概哪几页、是否已有现成资产。见 `02_content_stage.md`。

用户已经明确说了的就直接执行，不重复问。除此之外只在导入异常、源资料缺失或影响商业结论的歧义上询问。

完成标准：源文可读，图片路径有效，**视觉来源已确认**，内容任务或恢复动作明确。素材存在和 Schema 合法不能证明内容已被理解。
