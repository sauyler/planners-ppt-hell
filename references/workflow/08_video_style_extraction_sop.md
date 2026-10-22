# 视频模板提取：视觉与可动画结构

使用 [共同提取流程](01_template_intake.md) 与 [模板定义](../contracts/template_package.md)。这里仅补充视频出口，不从某个现有主题推导所有视频的颜色、留白、页数或装饰配额。

## 视频参考与迁移验证

实际查看静态参考；动态参考还需查看关键状态与运动过程，分清静态视觉身份和时间上的表现。动态效果不能仅凭封面图宣称已经还原。
用当前上屏内容试做代表画面，保留可定位的元素、复合分组和出现步骤。有 visual-plan 时继承 screen ID 与脚本绑定；直接输入时保留本项目身份，不伪造录音绑定。
人物位置、字幕区域、透明背景等读当前项目选择。字段定义只读 Video Craft 的 `references/composition-facts-contract.md`；元素与动效接口只读其 `references/svg-animation-contract.md`。本 Skill 生产结构，Craft 实现动画与合成。
查看静态 PNG 后，将候选交 Craft 验证所选动画的真实播放与合成；尚未完成时把验证范围写清，不能用静态看图替代。参考中的新动作若现有引擎不支持，作为 Craft 能力需求处理，不在这里另造动作词表。

## 保存与复用

视频风格的共享数值与风格登记由**本 Skill 自己维护**：风格文档（`references/domain/video_style_*.md`，当前为 `video_style_editorial_archive.md`）持有数值与用法，参考图及静态试做保存在本 Skill 的 `assets/video_style_references/<id>/`。不向 Video Craft 注册风格，也不读取它的主题库；Craft 只消费成品画面与它的动画契约。制作说明引用本 Skill 的风格数值与动作接口，描述样张用途和变化方式。
迁移验证通过后再审阅当前候选；风格文档变更依本 Skill 的维护流程执行。只为当前项目使用参考时不必先写成风格文档。**注册到别的 Skill 已取消**：跨 Skill 的正式修改与发布统一在候选验证完成后进行。
