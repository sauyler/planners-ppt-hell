#!/usr/bin/env python3
"""Generate the read-only, per-layout template review page."""

import argparse
import html
import json
from pathlib import Path


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def inline_canvas(path):
    text = path.read_text(encoding="utf-8")
    return (text.replace('href="../../template_media/', 'href="/_internal/00_project/template_media/')
                .replace("href='../../template_media/", "href='/_internal/00_project/template_media/")
                .replace('xlink:href="../../template_media/', 'xlink:href="/_internal/00_project/template_media/')
                .replace("xlink:href='../../template_media/", "xlink:href='/_internal/00_project/template_media/"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    project = root / "_internal" / "00_project"
    registry = load(project / "fidelity_template" / "template_registry.json")
    profile = load(project / "template_profile.json")
    assets = load(project / "template_asset_registry.json")
    reviews = load(project / "template_canvas_self_review.json")
    visual_manifest = load(project / "template_visuals" / "visual_manifest.json")
    if not profile or not assets or not registry.get("layouts"):
        raise SystemExit("template review requires profile, asset registry, and fidelity registry")

    component_map = {x.get("component_id"): x for x in registry.get("components", []) if isinstance(x, dict)}
    page_images = {int(x["page"]): x.get("image", f"page_{int(x['page']):03d}.png")
                   for x in visual_manifest.get("pages", []) if isinstance(x, dict) and x.get("page")}
    cards = []
    layout_ids = list(registry["layouts"])
    for index, layout_id in enumerate(layout_ids, 1):
        layout = registry["layouts"][layout_id]
        canvas = project / "fidelity_template" / str(layout.get("canvas_file", ""))
        if not canvas.is_file():
            raise SystemExit(f"missing Builder canvas: {canvas}")
        ids = list(dict.fromkeys(layout.get("required_components", []) + layout.get("optional_components", [])))
        source_pages = {p for cid in ids for p in (
            component_map.get(cid, {}).get("source_pages") or [component_map.get(cid, {}).get("source_page")]
        ) if p}
        review = reviews.get("layouts", {}).get(layout_id, {})
        for ref in review.get("compared_source_pages", []):
            digits = "".join(ch for ch in str(ref) if ch.isdigit())
            if digits:
                source_pages.add(int(digits))
        evidence = "".join(
            f'<figure><img src="/_internal/00_project/template_visuals/{esc(page_images.get(p, f"page_{p:03d}.png"))}"><figcaption>源模板 P{p}</figcaption></figure>'
            for p in sorted(source_pages)[:6]
        ) or '<p class="muted">无源页映射；请对照 contact sheet。</p>'
        usage = "默认开放内容页" if layout_id == "content_base" else (
            "仅在内容关系精确匹配时使用" if layout_id.startswith(("content_", "data_", "two_column_", "process_", "funnel_", "compare_"))
            else "核心功能页")
        cards.append(f'''<article class="card"><header><h2>{index}. {esc(layout_id)}</h2><span>{usage}</span></header>
<div class="compare"><section class="canvas">{inline_canvas(canvas)}</section><section><h3>源模板证据</h3><div class="thumbs">{evidence}</div>
<p><b>Required:</b> {esc(", ".join(layout.get("required_components", [])))}</p><p><b>Optional:</b> {esc(", ".join(layout.get("optional_components", [])))}</p></section></div>
<div class="decision"><fieldset data-decision="{esc(layout_id)}"><legend>此 Layout 如何处理？</legend>
<label class="choice pass"><input type="radio" name="decision-{index}" value="pass"><span>通过</span></label>
<label class="choice discard"><input type="radio" name="decision-{index}" value="discard"><span>舍弃</span></label>
<label class="choice revise"><input type="radio" name="decision-{index}" value="revise"><span>返修</span></label></fieldset>
<textarea data-feedback="{esc(layout_id)}" placeholder="此 Layout 的单独反馈；选择返修时请说明要改什么"></textarea></div></article>''')

    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>模板人工审阅</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#182433;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}.top{{position:sticky;top:0;z-index:4;background:#06131b;color:#fff;padding:18px 30px}}main{{max-width:1680px;margin:auto;padding:24px}}.summary,.card,.global{{background:#fff;border:1px solid #dce4ec;border-radius:12px;margin-bottom:22px;overflow:hidden}}.summary,.global{{padding:20px}}header{{padding:15px 22px;border-bottom:1px solid #e5eaf0;display:flex;justify-content:space-between}}.compare{{display:grid;grid-template-columns:1.25fr .75fr;gap:22px;padding:22px}}.canvas svg,.thumbs img{{display:block;width:100%;height:auto;border:1px solid #d7dee7}}.thumbs{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}figure{{margin:0}}figcaption,.muted{{color:#697582;font-size:13px}}.decision{{padding:0 22px 22px;display:grid;grid-template-columns:360px 1fr;gap:15px}}fieldset{{border:1px solid #cfd8e2;border-radius:9px;padding:12px;display:flex;gap:8px;align-items:center}}legend{{font-weight:700}}textarea,input,button{{font:inherit}}textarea{{width:100%;min-height:88px;padding:10px}}.choice input{{position:absolute;opacity:0;pointer-events:none}}.choice span{{display:inline-block;padding:10px 18px;border:1px solid #bcc7d3;border-radius:8px;background:#fff;font-weight:800;cursor:pointer}}.choice.pass input:checked+span{{background:#087a51;color:#fff;border-color:#087a51}}.choice.discard input:checked+span{{background:#3e4854;color:#fff;border-color:#3e4854}}.choice.revise input:checked+span{{background:#a44a12;color:#fff;border-color:#a44a12}}.global input{{width:100%;padding:10px;margin-bottom:10px}}.actions{{position:sticky;bottom:0;z-index:5;background:#eef3f8ee;padding:15px;text-align:center;border-top:1px solid #d4dde6}}button{{padding:12px 22px;border:0;border-radius:8px;color:#fff;background:#27506f;font-weight:800;cursor:pointer}}button.approve{{background:#087a51}}@media(max-width:1000px){{.compare,.decision{{grid-template-columns:1fr}}fieldset{{flex-wrap:wrap}}}}</style></head><body>
<div class="top"><b>模板提取人工审阅</b> · 每个 Layout 分别决定通过 / 舍弃 / 返修</div><main><section class="summary"><h1>先看生产 canvas，再对照源模板</h1><p>通过会保留该 Layout；舍弃会在返修阶段删除该 Layout；返修必须留下具体意见。“全部通过”会自动把每个 Layout 设为通过并提交。</p><img style="max-width:100%" src="/_internal/00_project/template_visuals/contact_sheet.png"></section>
{''.join(cards)}
<section class="global"><h2>整体反馈与模板命名</h2><input id="templateName" placeholder="模板名称（全部 Layout 通过时必填）"><textarea id="overall" placeholder="整体反馈（可选）"></textarea></section></main>
<div class="actions"><button onclick="submitFeedback('submit_batch')">提交批次反馈</button> <button class="approve" onclick="approveAll()">全部通过</button><p id="status"></p></div>
<script>const layoutIds={json.dumps(layout_ids, ensure_ascii=False)};
function approveAll(){{for(const id of layoutIds){{document.querySelector('[data-decision="'+id+'"] input[value="pass"]').checked=true;}}submitFeedback('approve_all');}}
async function submitFeedback(submissionAction){{
 const status=document.getElementById('status'), layouts={{}};let allPass=true,missing=false,revisionWithoutFeedback=false;
 const templateName=document.getElementById('templateName').value.trim(),overall=document.getElementById('overall').value.trim();
 for(const id of layoutIds){{const box=document.querySelector('[data-decision="'+id+'"]');const choice=box.querySelector('input:checked')?.value||'';const feedback=document.querySelector('[data-feedback="'+id+'"]').value.trim();if(!choice)missing=true;if(choice!=='pass')allPass=false;if(choice==='revise'&&!feedback&&!overall)revisionWithoutFeedback=true;layouts[id]={{approved:choice==='pass',decision:choice,custom_feedback:feedback}};}}
 if(missing){{status.textContent='请先为每个 Layout 选择通过、舍弃或返修。';return;}}
 if(revisionWithoutFeedback){{status.textContent='选择返修的 Layout 需要填写单独或整体反馈。';return;}}
 if(allPass&&!templateName){{status.textContent='全部 Layout 通过时必须填写模板名称。';return;}}
 const response=await fetch('/template-feedback',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{submission_action:submissionAction,approved:allPass,all_approved:allPass,template_name:templateName,overall_feedback:overall,layouts}})}});
 const result=await response.json();status.textContent=response.ok?'反馈已保存；请回到 Codex 问答框发送「已完成」。':(result.error||'提交失败');
 if(response.ok) window.alert('模板反馈已保存。请回到 Codex 问答框发送「已完成」，模型会继续处理。');
}}
</script></body></html>'''
    out = root / "00_template_review.html"
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
