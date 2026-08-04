"""
Generate 01_layout_direction.html from page_content.json and layout_plan.json.

Reads complete copy and layout decisions, renders an interactive review page
where users can inspect full content, wireframes, and rationale before SVG generation.

Usage:
  python generate_layout_html.py <project_dir> [--output <path>]
"""

import argparse
import json
import sys
from pathlib import Path


def normalize_review_suggestions(value):
    """Make legacy suggestion strings safe to render without hiding the schema issue."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if isinstance(item, str) and item.strip()], ""
    if isinstance(value, str):
        normalized = [item.strip() for item in value.replace("；", ";").replace("\n", ";").split(";") if item.strip()]
        return normalized, "review_suggestions 应为字符串数组；已为本次审阅页兼容转换，需修复 layout_plan.json。"
    if value is None:
        return [], ""
    return [], "review_suggestions 类型无效；本次审阅页已忽略该字段，需修复 layout_plan.json。"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>版式方向审阅 — {project}</title>
<style>
  :root{{--ink:#17202A;--muted:#6B7480;--soft:#EEF2F6;--paper:#FFFFFF;--line:#DDE4EC;--navy:#051C2C;--accent:#D46A00;--ok:#007A53;--danger:#E60012;--blue:#006BA6;--wash:#F7F9FC}}
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:linear-gradient(180deg,#E9EEF4 0,#F5F7FA 320px);color:var(--ink);line-height:1.58;letter-spacing:0}}
  .header{{background:rgba(5,28,44,.96);color:#FFF;padding:16px 30px;position:sticky;top:0;z-index:10;box-shadow:0 10px 26px rgba(5,28,44,.16)}}
  .header h1{{font-size:23px;font-weight:850;letter-spacing:0}}
  .header .meta{{font-size:13px;opacity:.72;margin-top:3px}}
  .header .warning-banner{{background:#FFF3E0;color:#8A4700;padding:10px 14px;border-radius:8px;margin-top:10px;font-size:13px;font-weight:800;border:1px solid rgba(212,106,0,.28)}}
  .workspace{{max-width:1600px;margin:0 auto;padding:22px 24px;display:grid;grid-template-columns:116px minmax(0,1fr);gap:16px;align-items:start}}
  .side-nav{{position:sticky;top:92px;background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:8px;padding:8px;box-shadow:0 14px 36px rgba(5,28,44,.08);backdrop-filter:blur(10px)}}
  .side-nav-title{{font-size:12px;font-weight:850;color:var(--muted);margin-bottom:8px}}
  .nav-list{{display:flex;flex-direction:column;gap:7px;max-height:calc(100vh - 138px);overflow:auto;padding-right:2px}}
  .nav-item{{display:grid;grid-template-columns:7px 1fr;align-items:center;gap:6px;padding:7px 8px;border-radius:7px;color:#46515E;text-decoration:none;font-size:12px;font-weight:800;background:#F5F7FA;border:1px solid transparent;transition:.16s ease}}
  .nav-item:hover,.nav-item.active{{background:#FFF7EB;border-color:#F0C48C;color:#8A4700;transform:translateX(2px)}}
  .nav-dot{{width:8px;height:8px;border-radius:50%;background:var(--accent);flex:0 0 auto}}
  .container{{min-width:0}}
  .page-card{{background:var(--paper);border-radius:8px;margin-bottom:26px;box-shadow:0 18px 44px rgba(5,28,44,.08);overflow:hidden;border:1px solid var(--line)}}
  .page-card.error{{border-left:5px solid var(--danger)}}
  .page-card.warning{{border-left:5px solid var(--accent)}}
  .page-header{{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;background:linear-gradient(180deg,#FFFFFF,#FAFBFD)}}
  .page-header h2{{font-size:22px;line-height:1.35;font-weight:900;max-width:1000px}}
  .badges{{display:flex;gap:8px;flex-wrap:wrap}}
  .badge{{font-size:13px;padding:4px 12px;border-radius:12px;font-weight:bold}}
  .badge.rational{{background:#E3F2FD;color:#006BA6}}
  .badge.emotional{{background:#FFEBEE;color:#C62828}}
  .badge.dense{{background:#F5F7FA;color:#555}}
  .badge.balanced{{background:#E8F5E9;color:#007A53}}
  .badge.airy{{background:#FFF3E0;color:#D46A00}}
  .page-body{{padding:22px 24px 24px}}
  .layout-grid{{display:grid;grid-template-columns:minmax(520px,1.05fr) minmax(520px,.95fr);gap:24px;align-items:start}}
  .visual-panel{{position:sticky;top:104px}}
  .review-panel{{min-width:0}}
  .compact-card{{background:var(--wash);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:14px}}
  .copy-summary{{display:grid;gap:8px;background:#FFF;border-color:#DDE4EC}}
  .section-label{{font-size:13px;font-weight:900;color:#8A929C;margin-bottom:8px;letter-spacing:0;margin-top:16px}}
  .section-label:first-child{{margin-top:0}}
  .copy-blocks{{margin-bottom:16px}}
  .copy-blocks .action-title{{font-size:22px;font-weight:900;color:var(--ink);margin-bottom:10px;padding:12px 14px;background:#FFF7EB;border-left:4px solid var(--accent);border-radius:6px}}
  .copy-blocks .core-message{{font-size:16px;color:#4F5965;margin-bottom:12px;padding:10px 12px;background:#FFF;border:1px solid #E8ECF2;border-radius:6px;font-style:normal}}
  .on-slide-list{{display:grid;gap:7px;margin-top:2px}}
  .on-slide-item{{font-size:15px;color:#39424E;background:#FFF;border:1px solid #E8ECF2;border-radius:6px;padding:8px 10px}}
  .copy-rationale{{display:grid;gap:7px;margin-top:10px}}
  .copy-rationale-item{{font-size:14px;color:#4F5965;background:#F8FAFC;border:1px solid #E1E7EF;border-radius:6px;padding:8px 10px}}
  .copy-decision{{font-size:14px;color:#59636F;background:#F7F9FC;border:1px solid #E6EBF2;border-radius:8px;padding:10px 12px;margin-bottom:10px;line-height:1.65}}
  .notes-list{{display:grid;gap:7px;margin-top:10px}}
  .notes-item{{font-size:14px;color:#35536B;background:#F0F7FC;border:1px solid #CFE3F2;border-radius:6px;padding:8px 10px}}
  .copy-full{{max-height:520px;overflow:auto;background:#FFF;border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:14px}}
  .copy-full-title{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px;color:#59636F;font-size:13px;font-weight:900}}
  .copy-full-title span:last-child{{font-weight:700;color:#9AA2AC}}
  .copy-blocks .body-line{{font-size:15px;color:#4F5965;margin-bottom:7px;padding-left:16px;position:relative}}
  .copy-blocks .body-line::before{{content:'';position:absolute;left:0;top:.7em;width:5px;height:5px;border-radius:50%;background:var(--danger)}}
  .structured-block{{margin:10px 0;padding:10px 12px;background:#FFF;border:1px solid #E6ECF3;border-radius:8px}}
  .structured-block-title{{font-size:15px;font-weight:900;color:#26323F;margin-bottom:7px}}
  .structured-item{{padding:8px 0;border-top:1px solid #EFF3F7;color:#39424E;font-size:14px;line-height:1.65}}
  .structured-item:first-child{{border-top:0}}
  .structured-item strong{{color:#26323F}}
  .structured-item p{{margin-top:3px;color:#59636F}}
  .table-wrap{{overflow-x:auto;margin-bottom:12px}}
  .table-wrap table{{border-collapse:collapse;width:100%;font-size:14px}}
  .table-wrap th{{background:#051C2C;color:#FFF;padding:8px 12px;text-align:left;font-weight:bold}}
  .table-wrap td{{padding:8px 12px;border-bottom:1px solid #E0E0E0}}
  .table-wrap caption{{font-size:13px;color:#999;margin-bottom:6px;text-align:left}}
  .speaker-notes{{margin-bottom:16px}}
  .speaker-notes summary{{font-size:14px;color:#006BA6;cursor:pointer;font-weight:bold;padding:4px 0}}
  .speaker-notes .notes-content{{font-size:14px;color:#777;padding:8px 12px;background:#F5F7FA;border-radius:6px;margin-top:6px;font-style:italic}}
  .wireframe{{margin-bottom:16px;background:#FFF;border:1px solid var(--line);border-radius:8px;padding:14px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.7)}}
  .wireframe svg{{width:100%;height:auto;border:1px solid #D5DCE5;border-radius:6px;background:#FAFAFA;display:block}}
  .reason{{font-size:15px;color:#46515E;padding:12px 14px;background:#F7F9FC;border-radius:8px;margin-bottom:12px;border:1px solid #E8ECF2}}
  .asset-card{{font-size:15px;color:#46515E;padding:13px 14px;background:#FFF;border:1px solid #DDE4EC;border-radius:8px;margin-bottom:12px}}
  .asset-row{{display:grid;grid-template-columns:72px 1fr;gap:10px;padding:5px 0;border-bottom:1px solid #EEF2F6}}
  .asset-row:last-child{{border-bottom:none}}
  .asset-k{{font-weight:900;color:#7A8490}}
  .asset-v{{color:#26323F}}
  .asset-pill{{display:inline-block;padding:2px 9px;border-radius:999px;background:#E3F2FD;color:#006BA6;font-weight:900;font-size:12px;margin-right:6px}}
  .asset-pill.required{{background:#FFEBEE;color:#C62828}}
  .asset-pill.optional{{background:#FFF3E0;color:#D46A00}}
  .asset-pill.none{{background:#F5F7FA;color:#6B7480}}
  .asset-editor{{margin-top:12px;padding:12px;border:1px solid #DDE4EC;border-radius:8px;background:#F8FAFC}}
  .asset-preview{{display:grid;grid-template-columns:120px 1fr;gap:12px;align-items:start}}
  .asset-preview img{{width:120px;height:82px;object-fit:contain;background:#FFF;border:1px solid #DDE4EC;border-radius:6px}}
  .asset-preview select,.asset-preview input[type=file]{{width:100%;margin-top:7px;padding:8px;border:1px solid #C8D0DA;border-radius:6px;background:#FFF}}
  .asset-upload-status{{font-size:12px;color:#59636F;margin-top:6px}}
  .copy-handling{{margin-bottom:12px}}
  .copy-handling .ch-row{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px}}
  .copy-handling .ch-tag{{font-size:13px;padding:3px 10px;border-radius:8px;font-weight:bold}}
  .ch-tag.kept{{background:#E8F5E9;color:#007A53}}
  .ch-tag.compressed{{background:#FFF3E0;color:#D46A00}}
  .ch-tag.notes{{background:#E3F2FD;color:#006BA6}}
  .capacity-card{{background:#FFF;border:1px solid var(--line);border-radius:8px;padding:13px 14px;margin-bottom:14px}}
  .capacity-head{{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:8px}}
  .capacity-status{{font-size:12px;font-weight:900;border-radius:999px;padding:3px 9px;background:#E8F5E9;color:#007A53}}
  .capacity-status.tight{{background:#FFF3E0;color:#D46A00}}
  .capacity-status.overfull{{background:#FFEBEE;color:#C62828}}
  .capacity-status.too_empty{{background:#F5F7FA;color:#6B7480}}
  .capacity-summary{{font-size:13px;color:#59636F;margin-bottom:8px}}
  .capacity-region{{display:grid;grid-template-columns:1fr auto;gap:10px;border-top:1px solid #EEF2F6;padding:7px 0;font-size:13px;color:#46515E}}
  .capacity-region:first-of-type{{border-top:none}}
  .capacity-metric{{color:#8A929C;font-weight:800;white-space:nowrap}}
  .capacity-rec{{font-size:13px;color:#8A4700;background:#FFF8ED;border:1px solid #F0C48C;border-radius:6px;padding:8px 10px;margin-top:8px}}
  .risks{{margin-bottom:12px}}
  .risks li{{font-size:14px;color:#B35A00;margin-left:18px;margin-bottom:4px}}
  .suggestions{{margin-bottom:16px}}
  .suggestions{{display:grid;gap:10px;margin-bottom:18px}}
  .suggestions label{{display:flex;align-items:center;gap:12px;padding:15px 16px;font-size:16px;color:#39424E;cursor:pointer;background:#FFF;border:1px solid var(--line);border-radius:8px;min-height:58px;transition:.16s ease}}
  .suggestions input{{width:22px;height:22px;accent-color:#007A53;flex:0 0 auto}}
  .suggestions label:hover{{border-color:#007A53;background:#F2FBF7;transform:translateY(-1px)}}
  .feedback-text{{margin-bottom:16px}}
  .feedback-text textarea{{width:100%;min-height:88px;border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:16px;font-family:inherit;resize:vertical;background:#FFF}}
  .action-zone{{position:sticky;bottom:14px;background:rgba(255,255,255,.94);border:1px solid var(--line);box-shadow:0 14px 34px rgba(5,28,44,.10);border-radius:8px;padding:14px;margin-top:10px;backdrop-filter:blur(10px)}}
  .approval-status{{padding:9px 11px;border:1px solid #D8DEE3;border-radius:7px;background:#F5F7F8;color:#6E7A84;font-size:12px;font-weight:800}}
  .approval-status.approved{{border-color:#BFDCCB;background:#F0F8F3;color:#08744F}}
  .page-error{{background:#FFEBEE;color:#C62828;padding:12px 16px;border-radius:8px;font-size:14px;margin-bottom:16px;border:1px solid #E60012}}
  .submit-btn{{background:var(--danger);color:#FFF;border:none;padding:14px 42px;font-size:18px;font-weight:850;border-radius:8px;cursor:pointer;margin:0 6px;box-shadow:0 12px 28px rgba(230,0,18,.18)}}
  .submit-btn.green{{background:#007A53;box-shadow:0 12px 28px rgba(0,122,83,.18)}}
  .submit-btn:hover{{background:#C50010}}
  .toast{{position:fixed;top:20px;right:20px;background:#051C2C;color:#FFF;padding:14px 24px;border-radius:8px;font-size:15px;display:none;z-index:999}}
  .toast.show{{display:block}}
  .completion{{position:fixed;inset:0;background:rgba(5,28,44,.78);display:none;place-items:center;padding:24px;z-index:1000;backdrop-filter:blur(8px)}}
  .completion.open{{display:grid}}
  .completion-card{{width:min(600px,100%);background:#FFF;border-radius:12px;padding:32px;text-align:center;box-shadow:0 28px 90px rgba(0,0,0,.3)}}
  .completion-card h2{{font-size:28px;margin-bottom:10px}}.completion-card p{{color:#59636F;margin-bottom:18px}}
  .completion-card button{{border:1px solid #DDE4EC;border-radius:8px;padding:10px 15px;background:#FFF;cursor:pointer}}
  .completion-card button.primary{{background:#007A53;border-color:#007A53;color:#FFF;font-weight:850}}
  .project-credit{{max-width:1600px;margin:0 auto 28px;padding:0 24px;text-align:center;color:#8A929C;font-size:13px;font-weight:800}}
  .project-credit a{{color:#59636F;text-decoration:none;border-bottom:1px solid #C8D0DA}}
  .global-error{{background:#FFEBEE;border:2px solid #E60012;color:#C62828;padding:16px 24px;border-radius:12px;margin-bottom:20px;font-size:15px;font-weight:bold}}
  details.compact-details{{border:1px solid var(--line);border-radius:8px;background:#FFF;margin-bottom:14px}}
  details.compact-details summary{{list-style:none;cursor:pointer;padding:13px 16px;font-size:15px;font-weight:800;color:#59636F}}
  details.compact-details summary::-webkit-details-marker{{display:none}}
  details.compact-details .details-body{{padding:0 16px 16px}}
  /* Compact review UI override. Keep content intact; reduce chrome and visual noise. */
  body{{background:#EEF3F8;color:#182433}}
  .header{{background:#06131B;padding:20px 40px;display:grid;grid-template-columns:1fr auto;grid-template-areas:"title meta" ". brand";align-items:center;gap:8px 18px;box-shadow:none;transition:padding .18s ease}}
  .header h1{{grid-area:title;font-size:25px}}
  .header .meta{{grid-area:meta;justify-self:end;font-size:13px;color:#A9B4BF;opacity:1}}
  .header .creator{{grid-area:brand;justify-self:end;display:flex;align-items:center;gap:9px;color:#DCE5EA;white-space:nowrap}}
  .creator-mark{{display:grid;place-items:center;width:30px;height:30px;border:1px solid rgba(255,255,255,.24);border-radius:8px;background:rgba(255,255,255,.06);color:#F0A05A;font:950 13px/1 ui-monospace,SFMono-Regular,Menlo,monospace}}
  .creator-copy{{display:grid;line-height:1.1}}.creator-copy strong{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#F5F7F8}}.creator-copy small{{margin-top:4px;font-size:10px;color:#7F8D97}}
  body.review-scrolled .header{{padding:10px 40px;grid-template-areas:"title meta"}}
  body.review-scrolled .header .creator{{display:none}}
  body.review-scrolled .header h1{{font-size:21px}}
  .workspace{{max-width:none;padding:14px 18px 14px 0;grid-template-columns:104px minmax(0,1fr);gap:0}}
  .side-nav{{justify-self:center;top:92px;width:46px;padding:8px 5px;border-radius:9px;box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  body.review-scrolled .side-nav{{top:58px}}
  .side-nav-title{{display:none}}
  .nav-list{{counter-reset:pageNav;align-items:center;gap:8px;max-height:calc(100vh - 120px);padding:0;overflow:visible}}
  .nav-item{{counter-increment:pageNav;display:grid;grid-template-columns:1fr;place-items:center;width:32px;height:32px;padding:0;border-radius:999px;background:#F4F7FA;font-size:0;line-height:1}}
  .nav-item::before{{content:counter(pageNav);display:block;width:100%;height:32px;font-size:13px;font-weight:950;line-height:32px;text-align:center;transform:translateY(1px);color:#66717E}}
  .nav-item:hover,.nav-item.active{{transform:none;background:#FFF4E3;border-color:#F0C48C}}
  .nav-item:hover::before,.nav-item.active::before{{color:#D46A00}}
  .nav-dot{{display:none}}
  .page-card{{border-radius:9px;margin-bottom:18px;box-shadow:0 10px 26px rgba(5,28,44,.05)}}
  .page-card.error,.page-card.warning{{border-left:1px solid var(--line)}}
  .page-header{{padding:18px 28px}}
  .page-header h2{{font-size:24px}}
  .page-body{{padding:18px 28px}}
  .layout-grid{{grid-template-columns:minmax(520px,.95fr) minmax(520px,1fr);gap:22px}}
  .visual-panel{{top:96px}}
  .wireframe{{display:grid;place-items:center;padding:0;border-color:#E6ECF3;background:#FFFFFF;box-shadow:none}}
  .wireframe svg{{width:100%;margin:0 auto;border:0;background:#FFFFFF}}
  .asset-card{{border-color:#E8EDF3;box-shadow:none}}
  .copy-summary{{gap:10px;background:#F6F9FC}}
  .copy-decision{{font-size:13px;border-color:#E8EDF3;background:#FFFFFF}}
  .copy-blocks .action-title{{border-left:0;padding:14px 18px;border-radius:8px;margin-bottom:10px;font-size:19px}}
  .on-slide-combined,.copy-rationale-combined{{background:#FFF;border:1px solid #E6ECF3;border-radius:8px;padding:10px 14px;color:#39424E}}
  .combined-lead{{font-size:14px;color:#4F5965;margin-bottom:7px;line-height:1.65}}
  .combined-line{{font-size:14px;color:#39424E;border-top:1px solid #EFF3F7;padding:7px 0}}
  .combined-line:first-child{{border-top:0}}
  .copy-rationale-combined .combined-line{{color:#6A4309;border-top-color:#F6DEC0}}
  .action-zone{{box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  .submit-btn{{min-width:210px;border-radius:10px;margin:0;padding:13px 28px;box-shadow:none}}
  .project-credit{{font-size:14px;padding-bottom:22px}}
  @media(max-width:980px){{.workspace{{grid-template-columns:1fr;padding-left:18px}}.side-nav{{position:static;width:auto}}.nav-list{{flex-direction:row;overflow:auto}}.layout-grid{{grid-template-columns:1fr}}.visual-panel{{position:static}}.header{{grid-template-columns:1fr;grid-template-areas:"title" "meta" "brand"}}.header .meta,.header .creator{{justify-self:start;white-space:normal}}}}
  /* Review workbench v2: one decision surface at a time. */
  body{{min-height:100vh;padding-bottom:86px;background:#E7EBEF}}
  .header{{height:72px;padding:0 28px;grid-template-columns:auto 1fr auto;grid-template-areas:"title meta brand";border-bottom:1px solid rgba(255,255,255,.09)}}
  .header h1{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;font-size:25px;letter-spacing:.02em}}
  .header .meta{{justify-self:start;margin-left:18px;color:#8F9BA6}}
  .workspace{{height:calc(100vh - 72px - 74px);min-height:640px;padding:0;grid-template-columns:246px minmax(0,1fr);gap:0}}
  .side-nav{{position:relative;top:0;justify-self:stretch;width:auto;height:100%;padding:18px 14px;border:0;border-radius:0;background:#111B22;box-shadow:none;overflow:hidden}}
  .side-nav-title{{display:flex;color:#71808B;padding:0 8px 10px;font-size:11px;letter-spacing:.16em;text-transform:uppercase}}
  .nav-list{{display:flex;align-items:stretch;gap:6px;max-height:calc(100vh - 180px);overflow:auto;padding:0 3px;scrollbar-width:none}}
  .nav-list::-webkit-scrollbar,.asset-workspace-scroll::-webkit-scrollbar,.asset-tabs::-webkit-scrollbar{{display:none}}
  .nav-item{{counter-increment:none;display:grid;grid-template-columns:34px 1fr auto;width:100%;height:auto;min-height:50px;padding:8px 9px;border:1px solid transparent;border-radius:7px;background:transparent;color:#AAB4BC;font-size:12px;text-align:left;place-items:initial;line-height:1.25}}
  .nav-item::before{{content:none}}
  .nav-item:hover,.nav-item.active{{background:#1E2A32;border-color:#34434E;transform:none;color:#FFF}}
  .nav-page-no{{display:grid;place-items:center;width:28px;height:28px;border-radius:5px;background:#26343D;color:#F0A05A;font:800 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace}}
  .nav-copy{{min-width:0;display:flex;align-items:center;overflow:hidden}}
  .nav-title{{overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}}
  .nav-state{{width:8px;height:8px;margin-top:10px;border-radius:999px;background:#52616C}}
  .nav-item.reviewed .nav-state{{background:#52B788}}
  .nav-item.changed .nav-state{{background:#F0A05A}}
  .container{{height:100%;padding:18px;overflow:hidden;background:#111B22}}
  .page-card{{display:none;height:100%;margin:0;border:0;border-radius:10px;box-shadow:0 18px 50px rgba(19,31,40,.12);overflow:hidden}}
  .page-card.active{{display:grid;grid-template-rows:auto minmax(0,1fr);animation:pageIn .2s ease both}}
  @keyframes pageIn{{from{{opacity:.35;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}
  .page-header{{padding:13px 20px;background:#FFF;border-bottom:1px solid #E6EAED}}
  .page-header h2{{font-size:18px}}
  .page-body{{padding:0;min-height:0;overflow:hidden}}
  .layout-grid{{height:100%;min-height:0;grid-template-columns:minmax(620px,1.45fr) minmax(360px,.72fr);gap:0;align-items:stretch}}
  .visual-panel{{position:relative;top:0;min-height:0;padding:18px;overflow:auto;background:#F2F0EB;border-right:1px solid #DDE2E6}}
  .review-panel{{min-height:0;padding:18px;overflow:auto;background:#FAFBFC}}
  .section-label{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7F8A93}}
  .wireframe{{width:min(100%,900px);height:auto;aspect-ratio:16/9;margin:0 auto 14px;background:#101820;border:8px solid #101820;border-radius:8px;box-shadow:0 18px 42px rgba(16,24,32,.19);overflow:hidden}}
  .wireframe svg{{display:block;width:100%;height:100%;background:#FBFBF9}}
  .asset-card{{padding:0;background:transparent;border:0}}
  .asset-card>.asset-row{{display:none}}
  .asset-overview{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;padding:10px 12px;border:1px solid #E2E7EC;border-radius:8px;background:#F5F7F8}}
  .asset-overview strong{{font-size:13px;color:#26323F}}.asset-overview span{{font-size:11px;color:#72808A}}
  .asset-tabs{{display:flex;gap:8px;overflow-x:auto;padding:1px 1px 8px;scrollbar-width:thin}}
  .asset-tab{{flex:0 0 112px;display:grid;grid-template-rows:56px auto;gap:5px;padding:6px;border:1px solid #D8DEE3;border-radius:8px;background:#FFF;color:#59636F;text-align:left;cursor:pointer}}
  .asset-tab:hover,.asset-tab.active,.asset-tab.dragover{{border-color:#D46A00;background:#FFF8ED;box-shadow:0 0 0 2px rgba(212,106,0,.10)}}
  .asset-tab img,.asset-tab-placeholder{{display:grid;place-items:center;width:100%;height:56px;border-radius:5px;background:#E8ECEF;object-fit:cover;color:#78858E;font:900 16px/1 ui-monospace,SFMono-Regular,Menlo,monospace}}
  .asset-tab-label{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;font-weight:900}}
  .asset-tab-upload{{font-size:9px;color:#A45A12;white-space:nowrap}}
  .asset-editor{{display:none;margin:2px 0 0;padding:12px;background:#FFF;border:1px solid #D8DEE3;border-radius:9px}}
  .asset-editor.active{{display:block}}
  .asset-editor-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}}
  .asset-slot-name{{font-size:13px;font-weight:900;color:#28343C}}
  .asset-safe{{font-size:11px;color:#72808A}}
  .asset-preview{{display:grid;grid-template-columns:1fr;gap:10px;align-items:stretch}}
  .drop-zone{{position:relative;min-height:104px;display:grid;place-items:center;border:1.5px dashed #AAB6BF;border-radius:8px;background:#F4F6F7;overflow:hidden;cursor:pointer;transition:.15s ease}}
  .drop-zone:hover,.drop-zone.dragover{{border-color:#D46A00;background:#FFF7ED;box-shadow:inset 0 0 0 2px rgba(212,106,0,.08)}}
  .drop-zone img{{width:100%;height:180px;border:0;border-radius:0;background:#EDF0F2}}
  .drop-zone-copy{{position:absolute;inset:auto 10px 10px;display:flex;justify-content:center;padding:7px 10px;border-radius:6px;background:rgba(8,17,24,.82);color:#FFF;font-size:12px;backdrop-filter:blur(6px)}}
  .asset-file{{display:none}}
  .crop-options{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0}}
  .crop-option{{display:grid;grid-template-rows:70px auto;gap:6px;padding:6px;border:1px solid #D8DEE3;border-radius:8px;background:#FFF;cursor:pointer;transition:.15s ease}}
  .crop-option:hover,.crop-option.selected{{border-color:#D46A00;box-shadow:0 0 0 2px rgba(212,106,0,.11)}}
  .crop-option input{{position:absolute;opacity:0;pointer-events:none}}
  .crop-option-visual{{overflow:hidden;border-radius:5px;background:#E8ECEF}}
  .crop-option-visual img{{width:100%;height:100%;border:0;border-radius:0;background:#E8ECEF}}
  .crop-option-name{{font-size:11px;font-weight:900;color:#26323F}}
  .crop-option-note{{display:block;margin-top:1px;font-size:10px;line-height:1.3;color:#7A8790}}
  .asset-upload-status{{grid-column:1/-1;min-height:18px;margin-top:0;font-size:11px;color:#72808A}}
  .copy-summary{{padding:0;background:transparent;border:0}}
  .copy-blocks .action-title{{font-family:inherit;font-size:22px;background:#FFF4E8;color:#1F2B33}}
  .asset-empty-state{{position:relative;display:grid;grid-template-columns:44px 1fr auto;align-items:center;gap:12px;min-height:112px;padding:16px;border:1.5px dashed #A9B7C1;border-radius:10px;background:linear-gradient(135deg,#F8FAFB,#EEF3F5);color:#64737D;cursor:pointer;transition:.16s ease}}
  .asset-empty-state:hover,.asset-empty-state.dragover{{border-color:#D46A00;background:#FFF8EF;box-shadow:inset 0 0 0 2px rgba(212,106,0,.08)}}
  .asset-empty-state.compact{{min-height:72px;margin-top:10px;padding:11px 13px;grid-template-columns:34px 1fr auto}}.asset-empty-state.compact .asset-empty-icon{{width:34px;height:34px;border-radius:8px;font-size:17px}}
  .asset-empty-icon{{display:grid;place-items:center;width:44px;height:44px;border-radius:10px;background:#172731;color:#FFF;font-size:22px}}
  .asset-empty-copy strong{{display:block;color:#23313A;font-size:14px}}.asset-empty-copy span{{display:block;margin-top:3px;font-size:11px;line-height:1.5;color:#788690}}
  .asset-empty-action{{padding:8px 10px;border-radius:7px;background:#FFF;border:1px solid #D5DEE4;color:#A95309;font-size:11px;font-weight:900}}
  .action-zone{{position:relative;bottom:auto;margin-top:14px;padding:12px;background:#FFF;border-color:#D8DEE3;box-shadow:none}}
  .feedback-text textarea{{min-height:74px;font-size:14px}}
  .project-credit{{display:none}}
  .review-panel{{display:flex;flex-direction:column;height:100%;min-height:0;overflow:hidden;padding:0}}
  .asset-workspace-scroll{{min-height:0;overflow:auto;padding:18px 18px 8px;scrollbar-width:none;overscroll-behavior:contain}}
  .asset-overview{{display:flex;align-items:center;justify-content:space-between;gap:12px}}
  .asset-overview-copy{{display:flex;align-items:baseline;gap:9px;min-width:0}}
  .asset-new-note{{margin-top:8px;padding:10px 11px;border:1px solid #F0C48C;border-radius:7px;background:#FFF8ED;color:#7C470E;font-size:11px;line-height:1.55}}
  .asset-next-round{{display:grid;grid-template-columns:auto 1fr;gap:9px;margin-top:9px;padding:10px;border-radius:8px;background:#EAF5EF;border:1px solid #B9DCC9;color:#1E6548;font-size:11px;line-height:1.5}}
  .asset-next-round strong{{display:block;color:#15583D}}
  .asset-reset{{border:0;background:transparent;color:#8A5B45;font:800 11px/1 inherit;cursor:pointer}}
  .review-panel>.action-zone{{flex:0 0 auto;margin:0;padding:12px 18px 14px;border-width:1px 0 0;border-radius:0;background:#FFF;box-shadow:0 -10px 24px rgba(24,36,51,.07)}}
  .layout-details{{margin-top:12px;border:1px solid #D8DEE3;border-radius:8px;background:rgba(255,255,255,.78)}}
  .layout-details summary{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;cursor:pointer;font-size:12px;font-weight:900;color:#52616C}}
  .layout-details summary span{{font-size:10px;font-weight:700;color:#8A969F}}
  .layout-details-body{{display:grid;gap:10px;padding:0 13px 13px}}
  .layout-details .badges{{gap:6px}}.layout-details .badge{{font-size:10px;padding:3px 8px}}
  .layout-details .reason{{margin:0;padding:10px;font-size:12px;line-height:1.55}}
  .layout-details .suggestions{{margin:0;gap:6px}}
  .layout-details .suggestions label{{min-height:0;padding:9px 10px;font-size:12px}}
  .layout-details .suggestions input{{width:17px;height:17px}}
  .review-dock{{position:fixed;left:0;right:0;bottom:0;z-index:60;height:74px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px;padding:0 24px 0 270px;background:#07131A;color:#FFF;border-top:1px solid rgba(255,255,255,.08);box-shadow:0 -12px 34px rgba(7,19,26,.18)}}
  .dock-group{{display:flex;align-items:center;gap:8px}}.dock-group.end{{justify-content:flex-end}}
  .dock-btn{{height:40px;padding:0 16px;border:1px solid #35444E;border-radius:7px;background:#13232D;color:#DDE5EA;font:800 13px/1 inherit;cursor:pointer}}
  .dock-btn:hover{{border-color:#657681;background:#1B2D38}}
  .dock-btn.primary{{border-color:#4CB782;background:#1E8A5B;color:#FFF}}
  .dock-btn.warn{{border-color:#D08A46;background:#B86419;color:#FFF}}
  .dock-btn.danger{{border-color:#E95C62;background:#E60012;color:#FFF}}
  .dock-progress{{font:800 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:#93A1AB;letter-spacing:.08em}}
  .decision-sheet{{position:fixed;inset:0;z-index:100;display:none;place-items:center;padding:24px;background:rgba(7,19,26,.86);backdrop-filter:blur(10px)}}
  .decision-sheet.open{{display:grid}}
  .decision-card{{width:min(680px,calc(100vw - 48px));padding:24px;border-radius:12px;background:#FFF;box-shadow:0 30px 100px rgba(0,0,0,.34)}}
  .decision-card h2{{font-size:22px;margin-bottom:7px}}.decision-card p{{color:#65717A;font-size:13px;margin-bottom:15px}}
  .decision-card textarea{{width:100%;min-height:130px;padding:12px;border:1px solid #D8DEE3;border-radius:8px;font:14px/1.6 inherit;resize:vertical}}
  .decision-summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:15px 0}}
  .decision-summary div{{padding:12px;border:1px solid #E0E6EB;border-radius:8px;background:#F7F9FA;text-align:center;font-size:12px;color:#66717E}}
  .decision-summary strong{{display:block;font-size:22px;color:#1D2B34}}
  .sheet-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:16px;flex-wrap:wrap}}
  html,body{{height:100%;overflow:hidden}}body{{min-height:0!important;padding-bottom:0!important}}
  @media(max-width:1100px){{.workspace{{grid-template-columns:150px minmax(0,1fr)}}.layout-grid{{grid-template-columns:1fr}}.visual-panel,.review-panel{{overflow:visible}}.container,.page-body{{overflow:auto}}.review-dock{{padding-left:174px}}.nav-title{{display:none}}}}
</style>
</head>
<body>
<div class="header">
  <h1>版式方向审阅</h1>
  <div class="meta">项目: {project} | 页面数: {page_count}{server_note}</div>
  <div class="creator"><span class="creator-mark">PH</span><span class="creator-copy"><strong>Planner's PPT Hell</strong><small>@阿祖不看TVC</small></span></div>
  {header_warnings}
</div>
<div class="workspace">
  <aside class="side-nav">
    <div class="side-nav-title">页面导航</div>
    <nav class="nav-list" id="pageNav"></nav>
  </aside>
  <main class="container" id="container"></main>
</div>
<div class="review-dock" aria-label="版式审阅导航">
  <div class="dock-group"><button class="dock-btn" id="prevPage" type="button">← 上一页</button><button class="dock-btn" id="nextPage" type="button">下一页 →</button></div>
  <div class="dock-progress" id="dockProgress">01 / {page_count}</div>
  <div class="dock-group end"><button class="dock-btn warn" type="button" onclick="reviseCurrent()">标记修改</button><button class="dock-btn primary" type="button" onclick="approveCurrentAndNext()">批准当前页</button><button class="dock-btn danger" type="button" onclick="openReviewSubmit()">提交本轮审阅</button></div>
</div>
<div class="decision-sheet" id="reviewSubmitSheet" role="dialog" aria-modal="true"><div class="decision-card"><h2>提交本轮版式审阅</h2><p>逐页决定和整套反馈将在这里一次提交。新增图片会进入下一轮 Layout 重排，本页不会立即显示新槽位位置。</p><label for="globalFeedback" style="display:block;margin-bottom:7px;font-size:12px;font-weight:900;color:#53616B">整套统一反馈 <span style="font-weight:600;color:#98A2A9">· 可选</span></label><textarea id="globalFeedback" placeholder="只填写跨页面都适用的要求；逐页问题请留在对应页面。"></textarea><div class="decision-summary" id="decisionSummary"></div><div class="sheet-actions"><button class="dock-btn" type="button" onclick="toggleSheet('reviewSubmitSheet',false)">继续审阅</button><button class="dock-btn" type="button" onclick="submitFeedback(false)">提交已有决定</button><button class="dock-btn primary" type="button" onclick="submitFeedback(true)">批准未处理页并提交</button></div></div></div>
<div class="toast" id="toast"></div>
<div class="completion" id="completion" role="dialog" aria-modal="true">
  <div class="completion-card">
    <h2>版式反馈已保存</h2>
    <p>请回到 Codex 问答框发送「已完成」，模型会读取图片、裁剪选择和版式反馈后继续。</p>
    <button class="primary" id="copyCompleted">复制「已完成」</button>
    <button id="closeCompletion">继续查看页面</button>
  </div>
</div>
<footer class="project-credit">
  Planner's PPT Hell © 2026 · 小红书 @阿祖不看 TVC · 网站 <a href="https://demyth.info" target="_blank" rel="noreferrer">demyth.info</a>
</footer>
<script>
var pages = {pages_json};
var assetStates = {{}};
var pageDecisions = {{}};
var activePageIndex = 0;

function flattenPreviewText(value) {{
  if (value === null || value === undefined || typeof value === 'boolean') return [];
  if (typeof value === 'string' || typeof value === 'number') return [String(value)];
  if (Array.isArray(value)) return value.reduce(function(out,item){{return out.concat(flattenPreviewText(item));}},[]);
  if (typeof value === 'object') return Object.keys(value).reduce(function(out,key){{return out.concat(flattenPreviewText(value[key]));}},[]);
  return [];
}}

function anchorToPreserve(anchor, fit) {{
  var map={{top:'xMidYMin',bottom:'xMidYMax',left:'xMinYMid',right:'xMaxYMid',center:'xMidYMid'}};
  return (map[anchor]||'xMidYMid')+' '+(fit==='cover'?'slice':'meet');
}}

function previewVisualUnits(text) {{
  return Array.from(String(text||'')).reduce(function(total,ch){{return total+(ch===' '?0.3:(ch.charCodeAt(0)<128?0.56:1));}},0);
}}

function fitWireframeText(text, width, height, isTitle) {{
  var maxSize=isTitle?38:24,minSize=8,lineHeight=1.24,usableW=Math.max(20,width-44),usableH=Math.max(12,height);
  var paragraphs=String(text||'').split(/\n+/).filter(Boolean);
  for(var size=maxSize;size>=minSize;size-=1){{
    var charsPerLine=Math.max(1,Math.floor(usableW/(size*.76)));
    var lines=paragraphs.reduce(function(total,line){{return total+Math.max(1,Math.ceil(previewVisualUnits(line)/charsPerLine));}},0);
    if(lines*size*lineHeight<=usableH) return size;
  }}
  return minSize;
}}

function wireframeCopyForLabel(finalCopy, label, page) {{
  if(Object.prototype.hasOwnProperty.call(finalCopy,label)) return finalCopy[label];
  var key=String(label||'').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g,'');
  if(!key) return '';
  var aliases={{
    title:['title','actiontitle','header','heading','标题','主标题'],
    lead:['subtitle','coremessage','lead','intro','导语','副标题','核心观点'],
    body:['body','bodyblocks','items','list','points','keypoints','evidence','正文','要点','证据'],
    footer:['footer','footertakeaway','source','caption','imagecaption','页脚','来源','图注','结论']
  }};
  var group=Object.keys(aliases).find(function(name){{return aliases[name].some(function(alias){{return key===alias||key.indexOf(alias)>=0||alias.indexOf(key)>=0;}});}});
  var match=Object.keys(finalCopy).find(function(candidate){{var normalized=String(candidate).toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g,'');return group&&aliases[group].some(function(alias){{return normalized===alias;}});}});
  if(match) return finalCopy[match];
  return group==='title'?(finalCopy.title||page.action_title||''):'';
}}

function renderWireframeSVG(page, pageIndex) {{
  var zones = asArray(page.wireframe);
  if (!zones.length) return '<div class="page-error">缺少线框图数据 — 请重新生成 layout_plan.json</div>';
  var vbW = 1920, vbH = 1080;
  var colors = ['#EEF3F8','#F4F6F1','#FFF3E4','#F5EFF7','#EEF7F4','#F7F2EE'];
  var finalCopy=((page.copy_handling||{{}}).final_on_slide)||{{}};
  var assets=assetStates[pageIndex]||((page.visual_asset_strategy||{{}}).assets)||[];
  var rects = zones.map(function(r, i) {{
    var label = (r.label||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var fill = colors[i % colors.length];
    var assetIndex=assets.findIndex(function(a){{return String(a.slot_label||'')===String(r.label||'');}});
    if(assetIndex<0 && /image|photo|chart|visual|图|照片|素材/i.test(r.label||'')){{
      var visualSlot=zones.slice(0,i+1).filter(function(zone){{return /image|photo|chart|visual|图|照片|素材/i.test(zone.label||'');}}).length-1;
      assetIndex=visualSlot<assets.length?visualSlot:-1;
    }}
    if(assetIndex>=0 && assets[assetIndex] && assets[assetIndex].path){{
      var asset=assets[assetIndex], href='/'+String(asset.path).replace(/^\//,'');
      return '<rect x="'+r.x+'" y="'+r.y+'" width="'+r.w+'" height="'+r.h+'" fill="#E7EAEC" stroke="#B9C2C9" stroke-width="2" rx="10"/>'+
        '<image id="layout-image-'+pageIndex+'-'+assetIndex+'" href="'+escapeHtml(href)+'" x="'+r.x+'" y="'+r.y+'" width="'+r.w+'" height="'+r.h+'" preserveAspectRatio="'+anchorToPreserve(asset.crop_anchor,asset.fit)+'" clip-path="inset(0 round 10px)"/>'+
        '<rect x="'+(Number(r.x)+14)+'" y="'+(Number(r.y)+14)+'" width="'+Math.min(330,Math.max(150,label.length*29))+'" height="40" fill="#07131A" opacity=".78" rx="7"/>'+
        '<text x="'+(Number(r.x)+30)+'" y="'+(Number(r.y)+42)+'" font-family="PingFang SC,Microsoft YaHei,sans-serif" font-size="20" font-weight="700" fill="#FFFFFF">'+label+'</text>';
    }}
    var raw=wireframeCopyForLabel(finalCopy,r.label||'',page);
    var preview=flattenPreviewText(raw).join('\n');
    var regionH=Number(r.h),compact=regionH<100,labelBand=compact?23:46;
    var contentH=Math.max(12,regionH-labelBand-10),isTitle=/title|heading|标题/i.test(r.label||'');
    var textSize=fitWireframeText(preview,Number(r.w),contentH,isTitle);
    return '<rect x="'+r.x+'" y="'+r.y+'" width="'+r.w+'" height="'+r.h+'" fill="'+fill+'" stroke="#C9D2DC" stroke-width="2" rx="10"/>'+
      '<text x="'+(Number(r.x)+22)+'" y="'+(Number(r.y)+(compact?17:30))+'" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="'+(compact?12:15)+'" font-weight="700" fill="#88949D">'+label+'</text>'+
      (preview?'<foreignObject x="'+(Number(r.x)+22)+'" y="'+(Number(r.y)+labelBand)+'" width="'+Math.max(20,Number(r.w)-44)+'" height="'+contentH+'"><div xmlns="http://www.w3.org/1999/xhtml" data-fit-wireframe-text style="box-sizing:border-box;width:100%;height:100%;font-family:PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;font-size:'+textSize+'px;font-weight:'+(isTitle?'800':'500')+';line-height:1.24;color:#26323F;overflow:hidden;overflow-wrap:anywhere;white-space:pre-wrap">'+escapeHtml(preview)+'</div></foreignObject>':'');
  }});
  return '<svg width="960" height="540" viewBox="0 0 '+vbW+' '+vbH+'" xmlns="http://www.w3.org/2000/svg">'+
         '<rect width="1920" height="1080" fill="#FBFCFD"/>'+
         '<rect x="44" y="44" width="1832" height="992" fill="none" stroke="#E2E7EE" stroke-width="3" stroke-dasharray="12 12"/>'+
         rects.join('')+'</svg>';
}}

function modeLabel(v) {{
  return {{rational:'理性页', emotional:'情绪页'}}[v] || v || '?';
}}

function densityLabel(v) {{
  return {{dense:'高密度', balanced:'均衡', airy:'留白'}}[v] || v || '?';
}}

function escapeHtml(s) {{
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// Historical layout plans use both strings and arrays for descriptive fields.
// Normalize at the rendering boundary so one bad field cannot blank the page.
function asStringList(value, splitDelimited) {{
  if (Array.isArray(value)) return value.filter(function(item) {{ return typeof item === 'string' && item.trim(); }});
  if (typeof value === 'string' && value.trim()) {{
    return splitDelimited ? value.split(/[；;\n]/).map(function(item) {{ return item.trim(); }}).filter(Boolean) : [value.trim()];
  }}
  return [];
}}

function asArray(value) {{
  return Array.isArray(value) ? value : [];
}}

function cloneAsset(item, isNew) {{
  var asset=Object.assign({{}},item||{{}});
  asset.is_new=Boolean(isNew||asset.is_new);
  asset.operation=asset.is_new?'add':'replace';
  asset.fit=asset.fit||'contain';asset.crop_ratio=asset.crop_ratio||'original';asset.crop_anchor=asset.crop_anchor||'center';
  if(!asset._baseline) asset._baseline={{path:asset.path||'',sha256:asset.sha256||'',fit:asset.fit,crop_ratio:asset.crop_ratio,crop_anchor:asset.crop_anchor}};
  return asset;
}}

function assetChanged(asset) {{
  if(asset.is_new) return Boolean(asset.path);
  var b=asset._baseline||{{}};
  return (asset.path||'')!==(b.path||'')||(asset.sha256||'')!==(b.sha256||'')||asset.fit!==(b.fit||'contain')||asset.crop_ratio!==(b.crop_ratio||'original')||asset.crop_anchor!==(b.crop_anchor||'center');
}}

function renderVisualAssetStrategy(strategy, page, pageIndex) {{
  if (!strategy) {{
    return '<div class="page-error">缺少素材需求：请在版式计划中说明本页是否需要配图。</div>';
  }}
  var need = strategy.asset_need || 'unknown';
  var pillClass = ['required','optional','none'].indexOf(need) >= 0 ? need : '';
  var needText = need === 'none' ? '无' : (need === 'optional' ? '可选' : '有');
  var typeLabels = {{
    real_asset: '真实素材/截图/照片',
    data_visual: '数据图表/结构图',
    editable_schematic: '可编辑示意图',
    photo_placeholder: '图片占位',
    screenshot_placeholder: '截图占位',
    svg_background: 'SVG 背景',
    svg_illustration: 'SVG 插画',
    generated_image: '生成图片',
    chart: '图表',
    none: '不需要素材'
  }};
  var typeText = typeLabels[strategy.asset_type] || strategy.asset_type || '不需要素材';
  var html = '<div class="asset-card" data-asset-manager="'+pageIndex+'">';
  html += '<div class="asset-row"><div class="asset-k">配图</div><div class="asset-v"><span class="asset-pill '+pillClass+'">'+escapeHtml(needText)+'</span></div></div>';
  html += '<div class="asset-row"><div class="asset-k">类型</div><div class="asset-v">'+escapeHtml(typeText)+'</div></div>';
  if (strategy.prompt_or_source) html += '<div class="asset-row"><div class="asset-k">来源</div><div class="asset-v">'+escapeHtml(strategy.prompt_or_source)+'</div></div>';
  if (strategy.fallback_if_missing) html += '<div class="asset-row"><div class="asset-k">缺失时</div><div class="asset-v">'+escapeHtml(strategy.fallback_if_missing)+'</div></div>';
  var assets = assetStates[pageIndex] || (Array.isArray(strategy.assets) ? strategy.assets.map(function(item){{return cloneAsset(item,false);}}) : []);
  if (!assets.length && need !== 'none') {{
    var candidate = (page.wireframe||[]).find(function(zone){{return /image|photo|visual|asset|图片|照片|素材/i.test(zone.label||'');}});
    assets = [cloneAsset({{asset_id:'',path:'',slot_label:candidate ? candidate.label : ((page.wireframe||[])[0]||{{}}).label||'image',
      fit:'cover',crop_ratio:'16:9',crop_anchor:'center',crop_options:[
        {{label:'完整显示',fit:'contain',crop_ratio:'original',crop_anchor:'center',tradeoff:'保留全图，允许留白'}},
        {{label:'居中填满',fit:'cover',crop_ratio:'16:9',crop_anchor:'center',tradeoff:'填满区域，裁掉边缘'}}
      ]}},false)];
  }}
  assetStates[pageIndex] = assets;
  if (!assets.length) {{
    html += '<div class="asset-empty-state" tabindex="0" role="button" data-new-slot-drop="'+pageIndex+'"><span class="asset-empty-icon">＋</span><span class="asset-empty-copy"><strong>拖入图片，创建一个新槽位</strong><span>也可以点击选择或直接粘贴。上传后先提交本轮审阅，下一轮 Layout 才会显示图片放置结果。</span></span><span class="asset-empty-action">选择图片</span></div><input class="asset-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif" data-new-slot-upload="'+pageIndex+'"></div>';
    return html;
  }}
  html += '<div class="asset-overview"><div class="asset-overview-copy"><strong>'+assets.length+' 个图片槽位</strong><span>每个槽位可独立替换和裁剪</span></div></div>';
  html += '<div class="asset-tabs" role="tablist" aria-label="图片槽位">';
  assets.forEach(function(asset, assetIndex) {{
    var src=asset.path?('/'+String(asset.path).replace(/^\//,'')):'';
    var thumb=src?'<img src="'+escapeHtml(src)+'" data-asset-source="'+pageIndex+':'+assetIndex+'" alt="">':'<span class="asset-tab-placeholder">'+(assetIndex+1)+'</span>';
    html += '<button type="button" class="asset-tab'+(assetIndex===0?' active':'')+'" role="tab" aria-selected="'+(assetIndex===0?'true':'false')+'" data-asset-tab="'+pageIndex+':'+assetIndex+'" data-asset-drop-target="'+pageIndex+':'+assetIndex+'" onclick="switchAssetEditor('+pageIndex+','+assetIndex+')">'+thumb+'<span class="asset-tab-label">'+(assetIndex+1)+' · '+escapeHtml(asset.slot_label||('图片 '+(assetIndex+1)))+'</span><span class="asset-tab-upload">可拖图替换</span></button>';
  }});
  html += '</div>';
  assets.forEach(function(asset, assetIndex) {{
    var options = Array.isArray(asset.crop_options) && asset.crop_options.length ? asset.crop_options : [
      {{label:'完整显示',fit:'contain',crop_ratio:'original',crop_anchor:'center',tradeoff:'保留全图，允许留白'}},
      {{label:'居中填满',fit:'cover',crop_ratio:asset.crop_ratio||'16:9',crop_anchor:'center',tradeoff:'填满区域，裁掉边缘'}}
    ];
    asset.crop_options = options;
    var assetKey=pageIndex+':'+assetIndex;
    var src=asset.path?('/'+String(asset.path).replace(/^\//,'')):'';
    var livePreview=src?'<img src="'+escapeHtml(src)+'" alt="当前图片" data-asset-source="'+assetKey+'" style="object-fit:'+(asset.fit==='cover'?'cover':'contain')+';object-position:'+escapeHtml(asset.crop_anchor||'center')+'">':'<div class="asset-empty">将图片拖到这里</div>';
    html += '<div class="asset-editor'+(assetIndex===0?' active':'')+'" data-asset-editor="'+assetKey+'"><div class="asset-editor-head"><div class="asset-slot-name">'+(asset.is_new?'新增槽位':'图片位置')+' · '+escapeHtml(asset.slot_label||'未指定')+'</div><div><span class="asset-safe">锁定原始比例 · 禁止拉伸</span>　<button class="asset-reset" type="button" onclick="resetAssetSlot('+pageIndex+','+assetIndex+')">'+(asset.is_new?'移除':'重置')+'</button></div></div>';
    if(asset.is_new) html += '<div class="asset-new-note">这是新增图片，不是替换已有槽位。当前只确认图片与裁剪方式，页面左侧不会立即重排。</div><div class="asset-next-round" data-next-round="'+assetKey+'" style="display:'+(asset.path?'grid':'none')+'"><span>✓</span><span><strong>图片已就绪，等待下一轮 Layout</strong>点击底部“提交本轮审阅”；模型重排并生成新版后，你会在下一轮审阅看到图片槽位的位置和比例。</span></div>';
    html += '<div class="asset-preview"><div class="drop-zone" tabindex="0" role="button" data-drop-zone="'+assetKey+'">'+livePreview+'<span class="drop-zone-copy">拖拽、粘贴或点击替换图片</span></div>';
    html += '<input class="asset-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif" data-layout-upload="'+assetKey+'">';
    html += '<div class="crop-options" role="radiogroup" aria-label="图片显示方式">';
    options.forEach(function(option, optionIndex) {{
      var selected = option.fit===asset.fit && option.crop_ratio===asset.crop_ratio && option.crop_anchor===asset.crop_anchor;
      var optionImage=src?'<img src="'+escapeHtml(src)+'" data-asset-source="'+assetKey+'" style="object-fit:'+(option.fit==='cover'?'cover':'contain')+';object-position:'+escapeHtml(option.crop_anchor||'center')+'" alt="">':'<div class="asset-empty">待上传</div>';
      html += '<label class="crop-option'+(selected?' selected':'')+'"><input type="radio" name="crop_'+pageIndex+'_'+assetIndex+'" value="'+optionIndex+'" data-crop-select="'+assetKey+'"'+(selected?' checked':'')+'><span class="crop-option-visual">'+optionImage+'</span><span><span class="crop-option-name">'+escapeHtml(option.label)+'</span><span class="crop-option-note">'+escapeHtml(option.tradeoff||'')+'</span></span></label>';
    }});
    html += '</div><div class="asset-upload-status" data-upload-status="'+assetKey+'">选择结果会连同图片一起提交；改图后当前页自动转为待修改。</div></div></div>';
  }});
  html += '<div class="asset-empty-state compact" tabindex="0" role="button" data-new-slot-drop="'+pageIndex+'"><span class="asset-empty-icon">＋</span><span class="asset-empty-copy"><strong>再增加一张图片</strong><span>拖拽、粘贴或点击选择；将创建新的 Layout 槽位。</span></span><span class="asset-empty-action">新增槽位</span></div><input class="asset-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif" data-new-slot-upload="'+pageIndex+'">';
  html += '</div>';
  return html;
}}

function refreshAssetManager(pageIndex, activeIndex) {{
  var host=document.querySelector('[data-asset-manager="'+pageIndex+'"]');
  if(!host) return;
  var wrapper=document.createElement('div');wrapper.innerHTML=renderVisualAssetStrategy(pages[pageIndex].visual_asset_strategy||{{asset_need:'none'}},pages[pageIndex],pageIndex);
  host.replaceWith(wrapper.firstElementChild);bindAssetControls(document.querySelector('[data-asset-manager="'+pageIndex+'"]'));
  if((assetStates[pageIndex]||[]).length) switchAssetEditor(pageIndex,Math.max(0,Math.min(activeIndex||0,assetStates[pageIndex].length-1)));
}}

function addImageSlot(pageIndex, file) {{
  var assets=assetStates[pageIndex]||[];
  var serial=1,label='new_image_'+serial;
  while(assets.some(function(item){{return item.slot_label===label;}})){{serial+=1;label='new_image_'+serial;}}
  assets.push(cloneAsset({{asset_id:'',path:'',slot_label:label,fit:'contain',crop_ratio:'original',crop_anchor:'center',crop_options:[
    {{label:'完整显示',fit:'contain',crop_ratio:'original',crop_anchor:'center',tradeoff:'保留全图，允许留白'}},
    {{label:'居中填满 16:9',fit:'cover',crop_ratio:'16:9',crop_anchor:'center',tradeoff:'适合横图，裁掉上下边缘'}},
    {{label:'居中填满 4:3',fit:'cover',crop_ratio:'4:3',crop_anchor:'center',tradeoff:'更紧凑，裁掉左右边缘'}}
  ]}},true));
  assetStates[pageIndex]=assets;refreshAssetManager(pageIndex,assets.length-1);markPageChanged(pageIndex);
  var input=document.querySelector('[data-layout-upload="'+pageIndex+':'+(assets.length-1)+'"]');
  if(file&&input) uploadLayoutAsset(input,file);
}}

function resetAssetSlot(pageIndex, assetIndex) {{
  var assets=assetStates[pageIndex]||[],asset=assets[assetIndex];if(!asset)return;
  if(asset.is_new){{assets.splice(assetIndex,1);refreshAssetManager(pageIndex,Math.max(0,assetIndex-1));}}
  else{{var b=asset._baseline||{{}};asset.path=b.path||'';asset.sha256=b.sha256||'';asset.fit=b.fit||'contain';asset.crop_ratio=b.crop_ratio||'original';asset.crop_anchor=b.crop_anchor||'center';asset.uploaded=false;refreshAssetManager(pageIndex,assetIndex);}}
  refreshPageDecision(pageIndex);
}}

function renderPages() {{
  var container = document.getElementById('container');
  var nav = document.getElementById('pageNav');
  pages.forEach(function(p, idx) {{
    var card = document.createElement('div');
    var pageNo = idx + 1;
    var sourceNo = p.page_number;
    var anchor = 'page-' + pageNo;
    var hasError = !!p.error;
    var hasWarning = (!hasError && ((!p.wireframe || !p.wireframe.length) || !p.has_full_copy));
    card.id = anchor;
    card.className = 'page-card' + (idx===0 ? ' active' : '') + (hasError ? ' error' : (hasWarning ? ' warning' : ''));
    card.dataset.pageIndex=idx;

    if (nav) {{
      var link = document.createElement('a');
      link.className = 'nav-item';
      link.href = '#' + anchor;
      link.dataset.pageIndex=idx;
      link.innerHTML = '<span class="nav-page-no">' + String(pageNo).padStart(2,'0') + '</span><span class="nav-copy"><span class="nav-title">' + escapeHtml(p.action_title||p.page_title||('第'+pageNo+'页')) + '</span></span><span class="nav-state"></span>';
      link.addEventListener('click',function(event){{event.preventDefault();setActivePage(idx);}});
      nav.appendChild(link);
    }}

    var modeBadge = '<span class="badge ' + (p.page_mode||'') + '">' + escapeHtml(modeLabel(p.page_mode)) + '</span>';
    var densityBadge = '<span class="badge ' + (p.visual_density||'') + '">' + escapeHtml(densityLabel(p.visual_density)) + '</span>';

    var gridLabel = typeof p.grid === 'object' ? Object.keys(p.grid).map(function(k){{return k+': '+p.grid[k];}}).join(' · ') : (p.grid||'');
    var html = '<div class="page-header">';
    html += '<h2><span style="color:#D46A00;margin-right:8px">' + String(pageNo).padStart(2,'0') + '</span>' + escapeHtml(p.action_title||p.page_title||('page_' + String(pageNo).padStart(2,'0'))) + '</h2>';
    html += '</div>';

    html += '<div class="page-body"><div class="layout-grid">';
    if (p.error) html += '<div class="page-error">' + escapeHtml(p.error) + '</div>';
    if (p.review_suggestions_warning) html += '<div class="page-error" style="background:#FFF8ED;color:#8A4700;border-color:#F0C48C">' + escapeHtml(p.review_suggestions_warning) + '</div>';
    if (!p.has_full_copy && !p.error) html += '<div class="page-error">页面文案不完整：缺少 action_title、core_message 或 body_blocks。请检查 page_content.json。</div>';

    // Left: the approved 16:9 layout already carries the complete on-slide copy.
    html += '<section class="visual-panel">';
    html += '<div class="section-label">16:9 版式与上屏文案</div><div class="wireframe">';
    html += renderWireframeSVG(p, idx);
    html += '</div>';
    html += '<details class="layout-details"><summary>版式说明与工程信息 <span>默认隐藏 · 需要时展开</span></summary><div class="layout-details-body">';
    html += '<div class="badges">'+modeBadge+densityBadge;
    if (sourceNo && sourceNo !== pageNo) html += '<span class="badge" style="background:#F5F7FA;color:#59636F">源稿P'+escapeHtml(sourceNo)+'</span>';
    if (p.layout_id) html += '<span class="badge" style="background:#F5F7FA;color:#333">'+escapeHtml(p.layout_id)+'</span>';
    if (gridLabel) html += '<span class="badge" style="background:#F5F7FA;color:#333">'+escapeHtml(gridLabel)+'</span>';
    html += '</div>';
    if (p.layout_reason) html += '<div class="reason"><strong>版式理由：</strong>'+escapeHtml(p.layout_reason)+'</div>';
    var suggestions = asStringList(p.review_suggestions, true);
    if (suggestions.length) {{
      html += '<div class="suggestions">';
      suggestions.slice(0,3).forEach(function(s,si){{html += '<label><input type="checkbox" name="sugg_'+idx+'" value="'+si+'"> '+escapeHtml(s)+'</label>';}});
      html += '</div>';
    }}
    html += '</div></details>';
    html += '</section>';

    // Right: image slots and the decision controls. Copy is intentionally not duplicated here.
    html += '<section class="review-panel"><div class="asset-workspace-scroll">';
    html += '<div class="section-label">图片槽位与裁剪</div>';
    html += renderVisualAssetStrategy(p.visual_asset_strategy, p, idx);
    html += '</div><div class="action-zone"><div class="section-label">审批与反馈</div><div class="feedback-text">';
    html += '<textarea name="feedback_'+idx+'" placeholder="对此页版式的调整意见、顾虑或备注..."></textarea>';
    html += '</div>';
    html += '<input type="checkbox" name="approve_'+idx+'" value="1" hidden>';
    html += '<div class="approval-status" data-approval-status="'+idx+'">本页尚未批准 · 请使用底部“批准当前页”</div>';
    html += '</div>';
    html += '</section></div></div>'; // review-panel, layout-grid, page-body

    card.innerHTML = html;
    container.appendChild(card);
  }});
  bindAssetControls(document);
  document.querySelectorAll('[name^="feedback_"]').forEach(function(input){{input.addEventListener('input',function(){{markPageChanged(Number(input.name.split('_')[1]));}});}});
  document.querySelectorAll('[name^="sugg_"]').forEach(function(input){{input.addEventListener('change',function(){{markPageChanged(Number(input.name.split('_')[1]));}});}});
  var requested=(location.hash.match(/^#page-(\d+)$/)||[])[1];
  setActivePage(requested?Number(requested)-1:0);
}}

function bindAssetControls(scope) {{
  scope=scope||document;
  scope.querySelectorAll('[data-crop-select]').forEach(function(input) {{
    if(input.dataset.bound)return;input.dataset.bound='1';
    input.addEventListener('change', function() {{
      var bits=input.dataset.cropSelect.split(':').map(Number), asset=assetStates[bits[0]][bits[1]];
      var option=asset.crop_options[Number(input.value)];
      asset.fit=option.fit;asset.crop_ratio=option.crop_ratio;asset.crop_anchor=option.crop_anchor;
      document.querySelectorAll('[data-crop-select="'+input.dataset.cropSelect+'"]').forEach(function(item){{item.closest('.crop-option').classList.toggle('selected',item.checked);}});
      var svgImage=document.getElementById('layout-image-'+bits[0]+'-'+bits[1]);
      if(svgImage) svgImage.setAttribute('preserveAspectRatio',anchorToPreserve(asset.crop_anchor,asset.fit));
      markPageChanged(bits[0]);
    }});
  }});
  scope.querySelectorAll('[data-layout-upload]').forEach(function(input) {{
    if(input.dataset.bound)return;input.dataset.bound='1';
    input.addEventListener('change', function() {{
      if (input.files && input.files[0]) uploadLayoutAsset(input, input.files[0]);
    }});
  }});
  scope.querySelectorAll('[data-drop-zone]').forEach(function(zone){{
    if(zone.dataset.bound)return;zone.dataset.bound='1';
    var input=document.querySelector('[data-layout-upload="'+zone.dataset.dropZone+'"]');
    zone.addEventListener('click',function(){{if(input) input.click();}});
    zone.addEventListener('keydown',function(event){{if((event.key==='Enter'||event.key===' ')&&input){{event.preventDefault();input.click();}}}});
    ['dragenter','dragover'].forEach(function(name){{zone.addEventListener(name,function(event){{event.preventDefault();zone.classList.add('dragover');}});}});
    ['dragleave','drop'].forEach(function(name){{zone.addEventListener(name,function(event){{event.preventDefault();zone.classList.remove('dragover');}});}});
    zone.addEventListener('drop',function(event){{var file=event.dataTransfer&&event.dataTransfer.files&&event.dataTransfer.files[0];if(file&&input) uploadLayoutAsset(input,file);}});
  }});
  scope.querySelectorAll('[data-asset-drop-target]').forEach(function(tab){{
    if(tab.dataset.bound)return;tab.dataset.bound='1';
    var input=document.querySelector('[data-layout-upload="'+tab.dataset.assetDropTarget+'"]');
    ['dragenter','dragover'].forEach(function(name){{tab.addEventListener(name,function(event){{event.preventDefault();event.stopPropagation();tab.classList.add('dragover');}});}});
    ['dragleave','drop'].forEach(function(name){{tab.addEventListener(name,function(event){{event.preventDefault();event.stopPropagation();tab.classList.remove('dragover');}});}});
    tab.addEventListener('drop',function(event){{
      var file=event.dataTransfer&&event.dataTransfer.files&&event.dataTransfer.files[0];
      if(file&&input) uploadLayoutAsset(input,file);
    }});
  }});
  scope.querySelectorAll('[data-new-slot-upload]').forEach(function(input){{
    if(input.dataset.bound)return;input.dataset.bound='1';
    input.addEventListener('change',function(){{if(input.files&&input.files[0])addImageSlot(Number(input.dataset.newSlotUpload),input.files[0]);}});
  }});
  scope.querySelectorAll('[data-new-slot-drop]').forEach(function(zone){{
    if(zone.dataset.bound)return;zone.dataset.bound='1';
    var pageIndex=Number(zone.dataset.newSlotDrop),input=scope.querySelector('[data-new-slot-upload="'+pageIndex+'"]');
    zone.addEventListener('click',function(){{if(input)input.click();}});
    zone.addEventListener('keydown',function(event){{if((event.key==='Enter'||event.key===' ')&&input){{event.preventDefault();input.click();}}}});
    ['dragenter','dragover'].forEach(function(name){{zone.addEventListener(name,function(event){{event.preventDefault();zone.classList.add('dragover');}});}});
    ['dragleave','drop'].forEach(function(name){{zone.addEventListener(name,function(event){{event.preventDefault();zone.classList.remove('dragover');}});}});
    zone.addEventListener('drop',function(event){{var file=event.dataTransfer&&event.dataTransfer.files&&event.dataTransfer.files[0];if(file)addImageSlot(pageIndex,file);}});
  }});
}}

function switchAssetEditor(pageIndex, assetIndex) {{
  var prefix=pageIndex+':';
  document.querySelectorAll('[data-asset-tab^="'+prefix+'"]').forEach(function(tab){{
    var active=tab.dataset.assetTab===prefix+assetIndex;
    tab.classList.toggle('active',active);tab.setAttribute('aria-selected',active?'true':'false');
  }});
  document.querySelectorAll('[data-asset-editor^="'+prefix+'"]').forEach(function(editor){{
    editor.classList.toggle('active',editor.dataset.assetEditor===prefix+assetIndex);
  }});
}}

document.addEventListener('paste',function(event){{
  var item=Array.from((event.clipboardData&&event.clipboardData.items)||[]).find(function(entry){{return /^image\//.test(entry.type);}});
  if(!item) return;
  var input=document.querySelector('.page-card.active .asset-editor.active [data-layout-upload]');
  if(input){{event.preventDefault();uploadLayoutAsset(input,item.getAsFile());}}
  else{{event.preventDefault();addImageSlot(activePageIndex,item.getAsFile());}}
}});

function markPageChanged(pageIndex){{
  pageDecisions[pageIndex]='revise';
  var nav=document.querySelector('.nav-item[data-page-index="'+pageIndex+'"]');
  if(nav){{nav.classList.add('changed');nav.classList.remove('reviewed');}}
  var approve=document.getElementsByName('approve_'+pageIndex)[0];
  if(approve) approve.checked=false;
  updateApprovalStatus(pageIndex);
}}

function pageHasRequests(pageIndex){{
  var feedback=(document.getElementsByName('feedback_'+pageIndex)[0]||{{}}).value||'';
  var selected=Array.from(document.getElementsByName('sugg_'+pageIndex)||[]).some(function(item){{return item.checked;}});
  var changed=(assetStates[pageIndex]||[]).some(assetChanged);
  return Boolean(feedback.trim()||selected||changed);
}}

function refreshPageDecision(pageIndex){{
  if(pageHasRequests(pageIndex)) pageDecisions[pageIndex]='revise';
  else if(pageDecisions[pageIndex]==='revise') pageDecisions[pageIndex]='unreviewed';
  var nav=document.querySelector('.nav-item[data-page-index="'+pageIndex+'"]');
  if(nav){{nav.classList.toggle('changed',pageDecisions[pageIndex]==='revise');nav.classList.toggle('reviewed',pageDecisions[pageIndex]==='approved');}}
  var approve=document.getElementsByName('approve_'+pageIndex)[0];if(approve)approve.checked=pageDecisions[pageIndex]==='approved';
  updateApprovalStatus(pageIndex);
}}

function updateApprovalStatus(pageIndex){{
  var approve=document.getElementsByName('approve_'+pageIndex)[0];
  var status=document.querySelector('[data-approval-status="'+pageIndex+'"]');
  if(!status) return;
  var decision=pageDecisions[pageIndex]||'unreviewed',approved=decision==='approved';
  status.classList.toggle('approved',approved);
  status.textContent=approved?'本页已批准':(decision==='revise'?'本页已标记修改 · 将进入下一轮版式修订':'本页尚未处理');
}}

async function uploadLayoutAsset(input, file) {{
  var bits=input.dataset.layoutUpload.split(':').map(Number), page=pages[bits[0]], asset=assetStates[bits[0]][bits[1]];
  var status=document.querySelector('[data-upload-status="'+input.dataset.layoutUpload+'"]');
  status.textContent='正在上传 '+file.name+'…';
  var data=await new Promise(function(resolve,reject){{var reader=new FileReader();reader.onload=function(){{resolve(String(reader.result).split(',')[1]);}};reader.onerror=reject;reader.readAsDataURL(file);}});
  try {{
    var response=await fetch('/layout-asset',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
      page_key:page.page_key,slot_label:asset.slot_label,filename:file.name,mime:file.type,data_base64:data
    }})}});
    var result=await response.json();
    if(!response.ok) throw new Error(result.error||'上传失败');
    asset.path=result.path;asset.uploaded=true;asset.sha256=result.sha256;
    status.textContent='上传完成 · 已锁定原始比例。';
    document.querySelectorAll('[data-asset-source="'+input.dataset.layoutUpload+'"]').forEach(function(preview){{preview.src=result.url;}});
    var tab=document.querySelector('[data-asset-tab="'+input.dataset.layoutUpload+'"]');
    if(tab && !tab.querySelector('img')){{var placeholder=tab.querySelector('.asset-tab-placeholder');var image=document.createElement('img');image.src=result.url;image.alt='';image.dataset.assetSource=input.dataset.layoutUpload;if(placeholder)placeholder.replaceWith(image);else tab.prepend(image);}}
    var bits=input.dataset.layoutUpload.split(':').map(Number);
    var svgImage=document.getElementById('layout-image-'+bits[0]+'-'+bits[1]);
    if(svgImage) svgImage.setAttribute('href',result.url);
    var nextRound=document.querySelector('[data-next-round="'+input.dataset.layoutUpload+'"]');if(nextRound)nextRound.style.display='grid';
    markPageChanged(bits[0]);
  }} catch(error) {{ status.textContent='上传失败：'+error.message; }}
}}

function decisionCounts(){{
  var counts={{approved:0,revise:0,unreviewed:0}};pages.forEach(function(_,idx){{counts[pageDecisions[idx]||'unreviewed']+=1;}});return counts;
}}

function toggleSheet(id,open){{var sheet=document.getElementById(id);if(sheet)sheet.classList.toggle('open',Boolean(open));}}

function openReviewSubmit(){{
  var c=decisionCounts(),host=document.getElementById('decisionSummary');
  if(host)host.innerHTML='<div><strong>'+c.approved+'</strong>已批准</div><div><strong>'+c.revise+'</strong>待修改</div><div><strong>'+c.unreviewed+'</strong>未处理</div>';
  toggleSheet('reviewSubmitSheet',true);
}}

function submitFeedback(approveRemaining) {{
  if(approveRemaining) pages.forEach(function(_,idx){{if((pageDecisions[idx]||'unreviewed')==='unreviewed')pageDecisions[idx]='approved';refreshPageDecision(idx);}});
  var counts=decisionCounts();
  if(counts.approved+counts.revise===0){{toast.textContent='还没有任何逐页决定，不能提交空审阅。';toast.className='toast show';setTimeout(function(){{toast.className='toast';}},4000);return;}}
  var payload = {{phase:'layout_review',pages:{{}},global_feedback:(document.getElementById('globalFeedback')||{{}}).value||'',all_approved:false}};
  pages.forEach(function(p, idx) {{
    var pageKey = p.page_key || ('page_' + String(p.page_number||(idx+1)).padStart(2,'0'));
    var selected = [];
    var checkboxes = document.getElementsByName('sugg_'+idx);
    checkboxes.forEach(function(cb) {{ if (cb.checked) selected.push(parseInt(cb.value)); }});
    var customFeedback = (document.getElementsByName('feedback_'+idx)[0]||{{}}).value||'';
    var pageAssets=(assetStates[idx]||[]);
    payload.pages[pageKey] = {{
      selected_suggestions: selected,
      custom_feedback: customFeedback,
      approved: pageDecisions[idx]==='approved',
      decision: pageDecisions[idx]||'unreviewed',
      asset_uploads: pageAssets.filter(function(asset){{return !asset.is_new||Boolean(asset.path);}}).map(function(asset){{return {{
        asset_id:asset.asset_id||'',path:asset.path||'',sha256:asset.sha256||'',slot_label:asset.slot_label||'',
        fit:asset.fit||'contain',crop_ratio:asset.crop_ratio||'original',crop_anchor:asset.crop_anchor||'center',
        uploaded:asset.uploaded===true,changed:assetChanged(asset),is_new:asset.is_new===true,operation:asset.is_new?'add':'replace'
      }};}})
    }};
  }});
  payload.all_approved = Object.values(payload.pages).every(function(p) {{ return p.approved; }});
  fetch('/layout-feedback', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify(payload)
  }}).then(function(r) {{
    if (r.ok) {{
      toast.textContent = '反馈已提交。模型将根据反馈调整版式。';
      toast.className = 'toast show';
      toggleSheet('reviewSubmitSheet',false);document.getElementById('completion').classList.add('open');
    }} else {{
      toast.textContent = '提交失败。审阅服务器是否在运行？';
      toast.className = 'toast show';
      setTimeout(function(){{ toast.className='toast'; }}, 5000);
    }}
  }}).catch(function() {{
    toast.textContent = '无法连接服务器。请先启动 review_server.py。';
    toast.className = 'toast show';
    setTimeout(function(){{ toast.className='toast'; }}, 5000);
  }});
}}

renderPages();
document.getElementById('copyCompleted').onclick=async function(){{
  try{{await navigator.clipboard.writeText('已完成');this.textContent='已复制';}}catch(error){{window.prompt('复制下面的文字并发送给 Codex','已完成');}}
}};
document.getElementById('closeCompletion').onclick=function(){{document.getElementById('completion').classList.remove('open');}};

function setActivePage(index) {{
  activePageIndex=Math.max(0,Math.min(pages.length-1,Number(index)||0));
  document.querySelectorAll('.page-card').forEach(function(card){{card.classList.toggle('active',Number(card.dataset.pageIndex)===activePageIndex);}});
  document.querySelectorAll('.nav-item').forEach(function(item){{item.classList.toggle('active',Number(item.dataset.pageIndex)===activePageIndex);}});
  var progress=document.getElementById('dockProgress');
  if(progress) progress.textContent=String(activePageIndex+1).padStart(2,'0')+' / '+String(pages.length).padStart(2,'0');
  var activeNav=document.querySelector('.nav-item.active');
  if(activeNav) activeNav.scrollIntoView({{block:'nearest'}});
  history.replaceState(null,'','#page-'+(activePageIndex+1));
  document.getElementById('prevPage').disabled=activePageIndex===0;
  document.getElementById('nextPage').disabled=activePageIndex===pages.length-1;
  requestAnimationFrame(function(){{fitRenderedWireframeText(document.querySelector('.page-card.active'));}});
}}

function fitRenderedWireframeText(scope) {{
  if(!scope) return;
  scope.querySelectorAll('[data-fit-wireframe-text]').forEach(function(node){{
    var size=parseFloat(getComputedStyle(node).fontSize)||12;
    while(size>8 && (node.scrollHeight>node.clientHeight+1 || node.scrollWidth>node.clientWidth+1)){{
      size-=1;
      node.style.fontSize=size+'px';
    }}
  }});
}}

function approveCurrentAndNext(){{
  if(pageHasRequests(activePageIndex)){{toast.textContent='当前页已有图片或文字修改要求；请重置这些修改后再批准。';toast.className='toast show';setTimeout(function(){{toast.className='toast';}},3500);return;}}
  pageDecisions[activePageIndex]='approved';refreshPageDecision(activePageIndex);
  if(activePageIndex<pages.length-1) setActivePage(activePageIndex+1);
}}

function reviseCurrent(){{
  pageDecisions[activePageIndex]='revise';refreshPageDecision(activePageIndex);
  var field=document.getElementsByName('feedback_'+activePageIndex)[0];if(field)field.focus();
}}

document.getElementById('prevPage').onclick=function(){{setActivePage(activePageIndex-1);}};
document.getElementById('nextPage').onclick=function(){{setActivePage(activePageIndex+1);}};
document.addEventListener('keydown',function(event){{
  if(/textarea|input|select/i.test((event.target||{{}}).tagName||'')) return;
  if(event.key==='ArrowLeft') setActivePage(activePageIndex-1);
  if(event.key==='ArrowRight') setActivePage(activePageIndex+1);
}});
</script>
</body>
</html>"""


def load_json(path):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def build_page_data(content_data, layout_data, capacity_data=None, fail_on_missing_copy=True, fail_on_missing_wireframe=True):
    """Merge content and layout data into per-page render objects."""
    pages = []
    global_errors = []

    content_pages = content_data.get("pages", []) if content_data else []
    layout_pages = layout_data.get("pages", []) if layout_data else []

    # Build lookup from layout by page_key
    layout_by_key = {}
    for lp in layout_pages:
        pk = lp.get("page_key")
        if pk:
            layout_by_key[pk] = lp

    for i, cp in enumerate(content_pages):
        pk = cp.get("page_key", f"page_{i+1:02d}")
        lp = layout_by_key.get(pk, {})

        page = {
            "page_key": pk,
            "page_number": i + 1,
            "page_title": cp.get("source_title") or lp.get("source_page_id") or pk,
        }

        # Content fields from page_content.json
        page["action_title"] = cp.get("action_title", "")
        page["core_message"] = cp.get("core_message", "")
        page["body_blocks"] = cp.get("body_blocks", [])
        page["tables"] = cp.get("tables", [])
        page["speaker_notes"] = cp.get("speaker_notes", "")
        page["source_excerpt"] = cp.get("source_excerpt", "")
        page["has_full_copy"] = bool(
            page["action_title"].strip()
            and page["core_message"].strip()
            and page["body_blocks"]
        )

        # Layout fields from layout_plan.json
        page["page_mode"] = lp.get("page_mode", "")
        page["visual_density"] = lp.get("visual_density", "")
        page["layout_id"] = lp.get("layout_id", "")
        page["layout_usage"] = lp.get("layout_usage", "")
        page["design_judgment"] = lp.get("design_judgment", {})
        page["why_this_layout"] = lp.get("why_this_layout", "")
        page["why_not_other_layouts"] = lp.get("why_not_other_layouts", "")
        page["adaptation_note"] = lp.get("adaptation_note", "")
        page["anti_laziness_check"] = lp.get("anti_laziness_check", "")
        page["grid"] = lp.get("grid", "")
        page["wireframe"] = lp.get("wireframe", [])
        page["layout_reason"] = lp.get("layout_reason", "")
        page["copy_handling"] = lp.get("copy_handling")
        page["capacity"] = ((capacity_data or {}).get("pages", {}) or {}).get(pk)
        page["visual_asset_strategy"] = lp.get("visual_asset_strategy")
        page["design_risks"] = lp.get("design_risks", [])
        page["review_suggestions"], suggestions_warning = normalize_review_suggestions(
            lp.get("review_suggestions", [])
        )
        if suggestions_warning:
            page["review_suggestions_warning"] = suggestions_warning

        # Validation errors
        errors = []
        if fail_on_missing_copy and not page["has_full_copy"]:
            errors.append(f"页面文案不完整（缺少 action_title、core_message 或 body_blocks）")
        if fail_on_missing_wireframe and not page["wireframe"]:
            errors.append(f"缺少线框图（wireframe 为空）")
        if not page["layout_reason"].strip():
            errors.append(f"版式计划不完整（缺少 layout_reason）")
        ch = page.get("copy_handling")
        if not isinstance(ch, dict):
            errors.append("缺少文案处理方案（copy_handling）")
        else:
            final_copy = ch.get("final_on_slide")
            # Auto-wrap string-type final_on_slide (common LLM error)
            if isinstance(final_copy, str) and final_copy.strip():
                final_copy = {"body": [final_copy.strip()]}
                ch["final_on_slide"] = final_copy
                page.setdefault("review_suggestions_warning", "")
                page["review_suggestions_warning"] = (
                    "final_on_slide 应为对象；已自动包装为 {body: [文案]}。请修复 layout_plan.json。"
                )
            if not isinstance(final_copy, dict):
                errors.append("缺少最终上屏文案（copy_handling.final_on_slide）")
            else:
                if not str(final_copy.get("title", "")).strip():
                    errors.append("最终上屏文案缺少标题（final_on_slide.title）")
                def has_visible(value):
                    if value is None or isinstance(value, bool):
                        return False
                    if isinstance(value, (str, int, float)):
                        return bool(str(value).strip())
                    if isinstance(value, list):
                        return any(has_visible(item) for item in value)
                    if isinstance(value, dict):
                        return any(has_visible(item) for item in value.values())
                    return False
                if not any(has_visible(value) for key, value in final_copy.items() if key != "title"):
                    errors.append("最终上屏文案除标题外没有可见内容")
            rationale = ch.get("compression_rationale", [])
            # Auto-wrap string-type compression_rationale (common LLM error)
            if isinstance(rationale, str) and rationale.strip():
                rationale = [rationale.strip()]
                ch["compression_rationale"] = rationale
            if not isinstance(rationale, list) or not any(str(x).strip() for x in rationale):
                errors.append("缺少文案处理原则（copy_handling.compression_rationale）")
        vas = page.get("visual_asset_strategy")
        if not isinstance(vas, dict):
            errors.append("缺少素材需求（visual_asset_strategy）")
        else:
            required_vas_fields = ["asset_need", "asset_type", "placement", "reason"]
            missing_vas = [f for f in required_vas_fields if not str(vas.get(f, "")).strip()]
            if missing_vas:
                errors.append(f"素材需求缺少字段：{', '.join(missing_vas)}")

        if errors:
            page["error"] = "；".join(errors)
            global_errors.append(f"{pk}: {page['error']}")

        pages.append(page)

    return pages, global_errors


def main():
    parser = argparse.ArgumentParser(
        description="Generate 01_layout_direction.html from page_content.json and layout_plan.json."
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--output", default="", help="Output HTML path (default: project root)")
    parser.add_argument("--fail-on-missing-copy", action="store_true", default=True,
                        help="Fail if any page is missing full copy (default: true)")
    parser.add_argument("--no-fail-on-missing-copy", action="store_true",
                        help="Do not fail on missing copy")
    parser.add_argument("--fail-on-missing-wireframe", action="store_true", default=True,
                        help="Fail if any page is missing wireframe (default: true)")
    parser.add_argument("--no-fail-on-missing-wireframe", action="store_true",
                        help="Do not fail on missing wireframe")
    parser.add_argument("--allow-degraded", action="store_true",
                        help="Write HTML even when errors exist (debug mode — degraded HTML may be misleading)")
    args = parser.parse_args()

    fail_on_copy = args.fail_on_missing_copy and not args.no_fail_on_missing_copy
    fail_on_wf = args.fail_on_missing_wireframe and not args.no_fail_on_missing_wireframe
    strict_mode = fail_on_copy or fail_on_wf

    root = Path(args.project_dir)
    internal = root / "_internal"

    content_data = load_json(internal / "01_content" / "page_content.json")
    layout_data = load_json(internal / "01_layout_plan" / "layout_plan.json")
    capacity_data = load_json(internal / "01_layout_plan" / "layout_capacity_report.json") or {}

    if not content_data:
        print("ERROR: page_content.json not found or invalid.", file=sys.stderr)
        sys.exit(1)
    if not layout_data:
        print("ERROR: layout_plan.json not found or invalid.", file=sys.stderr)
        sys.exit(1)

    pages, global_errors = build_page_data(content_data, layout_data, capacity_data, fail_on_copy, fail_on_wf)

    # In strict mode, exit before writing HTML if errors exist
    if global_errors and strict_mode and not args.allow_degraded:
        print("ERROR: Refusing to generate layout HTML with errors:", file=sys.stderr)
        for e in global_errors:
            print(f"  - {e}", file=sys.stderr)
        print("Fix the issues above or use --allow-degraded to force HTML output.", file=sys.stderr)

        # Write structured error file for parent/preflight diagnostics
        from datetime import datetime, timezone
        error_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strict_mode": True,
            "allow_degraded": False,
            "errors": global_errors,
            "html_written": False,
            "next_action": "Fix layout_plan.json/page_content.json, then rerun generate_layout_html.py.",
        }
        layout_errors_path = internal / "01_layout_plan" / "layout_html_errors.json"
        layout_errors_path.parent.mkdir(parents=True, exist_ok=True)
        layout_errors_path.write_text(json.dumps(error_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Structured errors written to: {layout_errors_path}", file=sys.stderr)
        sys.exit(1)

    project = content_data.get("project", root.name)
    header_warnings = ""

    if global_errors:
        error_list = "".join(f"<div>{e}</div>" for e in global_errors)
        header_warnings = f'<div class="warning-banner">检测到以下问题：{error_list}</div>'

    server_note = ""
    html = HTML_TEMPLATE.format(
        project=str(project).replace("&", "&amp;").replace("<", "&lt;"),
        page_count=len(pages),
        pages_json=json.dumps(pages, ensure_ascii=False),
        header_warnings=header_warnings,
        server_note=server_note,
    )

    output_path = Path(args.output) if args.output else root / "01_layout_direction.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Generated {output_path} ({len(pages)} pages)")

    if global_errors:
        print(f"WARNING: {len(global_errors)} page(s) have issues — generated degraded HTML.", file=sys.stderr)
        # Write degraded status for parent/preflight awareness
        from datetime import datetime, timezone
        degraded_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strict_mode": strict_mode,
            "allow_degraded": True,
            "degraded": True,
            "html_written": True,
            "errors": global_errors,
            "next_action": "HTML generated in degraded mode. Review errors in layout_html_errors.json, fix, and regenerate.",
        }
        layout_errors_path = internal / "01_layout_plan" / "layout_html_errors.json"
        layout_errors_path.parent.mkdir(parents=True, exist_ok=True)
        layout_errors_path.write_text(json.dumps(degraded_data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
