# 内容输入与核查时机

## Bypage 成品

接收 Bypage、委派资料整理或恢复这条链路时，读取 planners-bypage 的 references/content-handoff.md。复用同一项目记忆与 canonical source_index、正式稿、audit、feedback、资产清单和制作快照的原路径；不在 PPT Hell 另造第二份权威索引或把本地派生稿冒充正式稿。
Bypage 生产包由上游脚本产生，本侧程序导入：

```bash
python scripts/import_bypage.py <project> --production <bypage-production.json>
```

该命令为新项目检查原稿、审计与反馈的绑定以及页序和资产指纹。已有项目继续原工作台，不能拿旧生产包覆盖用户修改。
Production Notes 的图片路径先相对原交付稿定位，再映射本地登记资产；保留 Bypage 页号、来源 ID、资产 ID 与 canonical 文件绑定。本地 page_content / source_assets 都是制作派生文件。

同时承接原项目记忆中的方法采用记录和已确认论证关系。出现新的表达组织问题时可读取并调用 `planners-method-wiki`，只发展适用的画面或论证表达；方法查询不另建来源索引、不重复事实核查，也不重新决定策略。

## 事实核查的时机

上游有效 audit 只覆盖它实际绑定的 Bypage 原稿；没有内容变化时沿用，不重复建立 source index 或伪造一份已核查 PPT。
模型或用户改数字、主体、时间、单位、来源、关键限定或证据，先对照原索引回源，用 planners-fact-check 的现有契约核查受影响内容；保留结果与核查范围。压缩措辞也检查是否改变命题。缺来源明确报告，不把“未核查”写成“通过”。
新页面版本与输出快照保留变化事实；content_delta / changed_needs_check 不自动沿用原 audit 为改版背书。必要核查在把改版内容作为事实交付前完成；技术 export 不承担事实批准。

## 直接材料与内容展开

Bypage 是已有生产包的适配入口，不是使用本 Skill 的前置条件。用户提供材料、逐页稿或需求时，可先整理成 Markdown，再用 `--source` 初始化并填写 page_content。多源研究或需要完整来源审阅时可调用 Bypage；已有完整内容无需重跑上游。
直接整理也需实际阅读材料和图片，保留来源与未解决问题。没有上游审计就报告实际核查范围，不伪造生产包或审核通过。复杂内容不足以开始设计时，先完成必要的内容整理。

## 页面身份与图片

每页有稳定 page_key、title、content、notes、source_assets，可选 mode 为“讲”或“读”（默认读）。新页使用新 ID；现有工作台页序以 store order 为准，不能只改底稿数组冒充已保存页序。
图片用途开局一次确认。源图被使用或在 unused_assets 写原因；视频包图按契约适配，未被引用的图片点名报错，不删除作者素材来过检查。

## 视频输入

--assets + --plan 初始化直接适配上游 visual-plan，screen_id 原样作为 page_key；上屏内容与不宜上屏的理解信息分别进 content / notes。没有 visual-plan 时用 `--source <上屏稿.md> --route video` 直接制作；这是独立画面输入，未绑定口播与录音，不要求先运行其他 Skill。见 [视频路线](03_video_route.md)。
