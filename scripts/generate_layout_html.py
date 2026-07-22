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
  .suggestions input,.approve-row input{{width:22px;height:22px;accent-color:#007A53;flex:0 0 auto}}
  .suggestions label:hover{{border-color:#007A53;background:#F2FBF7;transform:translateY(-1px)}}
  .feedback-text{{margin-bottom:16px}}
  .feedback-text textarea{{width:100%;min-height:88px;border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:16px;font-family:inherit;resize:vertical;background:#FFF}}
  .action-zone{{position:sticky;bottom:14px;background:rgba(255,255,255,.94);border:1px solid var(--line);box-shadow:0 14px 34px rgba(5,28,44,.10);border-radius:8px;padding:14px;margin-top:10px;backdrop-filter:blur(10px)}}
  .approve-row{{display:flex;align-items:center;gap:12px;padding:14px 16px;font-size:16px;color:#26323F;background:#F7FBF8;border:1px solid #CFE8D8;border-radius:8px;font-weight:850}}
  .page-error{{background:#FFEBEE;color:#C62828;padding:12px 16px;border-radius:8px;font-size:14px;margin-bottom:16px;border:1px solid #E60012}}
  .submit-area{{text-align:center;padding:20px 0 40px}}
  .submit-btn{{background:var(--danger);color:#FFF;border:none;padding:14px 42px;font-size:18px;font-weight:850;border-radius:8px;cursor:pointer;margin:0 6px;box-shadow:0 12px 28px rgba(230,0,18,.18)}}
  .submit-btn.green{{background:#007A53;box-shadow:0 12px 28px rgba(0,122,83,.18)}}
  .submit-btn:hover{{background:#C50010}}
  .toast{{position:fixed;top:20px;right:20px;background:#051C2C;color:#FFF;padding:14px 24px;border-radius:8px;font-size:15px;display:none;z-index:999}}
  .toast.show{{display:block}}
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
  .header .creator{{grid-area:brand;justify-self:end;font-size:15px;font-weight:900;color:#FFFFFF;white-space:nowrap}}
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
  .approve-row{{cursor:pointer}}
  .action-zone{{box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  .submit-area{{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:12px;padding:28px 0 34px;background:linear-gradient(180deg,#EEF3F8,#F7F9FC)}}
  .submit-btn{{min-width:210px;border-radius:10px;margin:0;padding:13px 28px;box-shadow:none}}
  .submit-area div,.submit-area p{{flex-basis:100%;text-align:center}}
  .project-credit{{font-size:14px;padding-bottom:22px}}
  @media(max-width:980px){{.workspace{{grid-template-columns:1fr;padding-left:18px}}.side-nav{{position:static;width:auto}}.nav-list{{flex-direction:row;overflow:auto}}.layout-grid{{grid-template-columns:1fr}}.visual-panel{{position:static}}.header{{grid-template-columns:1fr;grid-template-areas:"title" "meta" "brand"}}.header .meta,.header .creator{{justify-self:start;white-space:normal}}}}
</style>
</head>
<body>
<div class="header">
  <h1>版式方向审阅</h1>
  <div class="meta">项目: {project} | 页面数: {page_count}{server_note}</div>
  <div class="creator">小红书 @阿祖不看 TVC</div>
  {header_warnings}
</div>
<div class="workspace">
  <aside class="side-nav">
    <div class="side-nav-title">页面导航</div>
    <nav class="nav-list" id="pageNav"></nav>
  </aside>
  <main class="container" id="container"></main>
</div>
<div class="submit-area">
  <button class="submit-btn green" onclick="submitFeedback()">提交全部调整意见</button>
  <button class="submit-btn" onclick="approveAll()">全部通过并继续</button>
  <div style="margin-top:12px">
    <!-- approval key removed — structural constraints prevent model from skipping review -->
  </div>
  <p style="margin-top:12px;font-size:14px;color:#999">请使用本地审阅服务器提交反馈，不要直接打开 file:// HTML。</p>
</div>
<div class="toast" id="toast"></div>
<footer class="project-credit">
  Planner's PPT Hell © 2026 · 小红书 @阿祖不看 TVC · 网站 <a href="https://demyth.info" target="_blank" rel="noreferrer">demyth.info</a>
</footer>
<script>
var pages = {pages_json};

function renderWireframeSVG(wireframe) {{
  var zones = asArray(wireframe);
  if (!zones.length) return '<div class="page-error">缺少线框图数据 — 请重新生成 layout_plan.json</div>';
  var vbW = 1920, vbH = 1080;
  var colors = ['#EEF3F8','#F4F6F1','#FFF3E4','#F5EFF7','#EEF7F4','#F7F2EE'];
  var rects = zones.map(function(r, i) {{
    var label = (r.label||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    var fill = colors[i % colors.length];
    var labelX = Number(r.x) + 20;
    var labelY = Number(r.y) + 42;
    return '<rect x="'+r.x+'" y="'+r.y+'" width="'+r.w+'" height="'+r.h+'" fill="'+fill+'" stroke="#C9D2DC" stroke-width="2" rx="10"/>'+
           '<rect x="'+(Number(r.x)+16)+'" y="'+(Number(r.y)+16)+'" width="'+Math.min(360, Math.max(160, label.length * 34))+'" height="42" fill="#FFFFFF" opacity=".86" rx="8"/>'+
           '<text x="'+labelX+'" y="'+labelY+'" font-family="PingFang SC,Microsoft YaHei,SimHei,sans-serif" font-size="24" font-weight="700" fill="#7B858F">'+label+'</text>';
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

function renderBodyBlock(block) {{
  if (!block) return '';
  if (block.type === 'bullet_list' && Array.isArray(block.items)) {{
    return block.items.map(function(item) {{
      return '<div class="body-line">'+escapeHtml(item)+'</div>';
    }}).join('');
  }}
  if ((block.type === 'paragraph' || block.type === 'quote') && block.text) {{
    return '<div class="body-line">'+escapeHtml(block.text)+'</div>';
  }}
  if (block.type === 'numbered_list' && Array.isArray(block.items)) {{
    return block.items.map(function(item, i) {{
      return '<div class="body-line">'+(i+1)+'. '+escapeHtml(item)+'</div>';
    }}).join('');
  }}
  if (block.type === 'kpi_set' && Array.isArray(block.items)) {{
    return block.items.map(function(item) {{
      return '<div class="body-line" style="font-size:18px;font-weight:bold;color:#333">'+escapeHtml(item)+'</div>';
    }}).join('');
  }}
  return '';
}}

function renderFinalBlock(block) {{
  if (!block) return '';
  if (block.type === 'table') {{
    var headers = block.columns || block.headers || [];
    return '<div class="structured-block">' +
      (block.title ? '<div class="structured-block-title">' + escapeHtml(block.title) + '</div>' : '') +
      renderTable({{headers: headers, rows: block.rows || [], caption: block.caption || ''}}) +
      '</div>';
  }}
  if (block.type === 'list' && Array.isArray(block.items)) {{
    var html = '<div class="structured-block">' + (block.title ? '<div class="structured-block-title">' + escapeHtml(block.title) + '</div>' : '');
    block.items.forEach(function(item) {{
      if (item && typeof item === 'object') {{
        html += '<div class="structured-item"><strong>' + escapeHtml(item.title || '') + '</strong>' +
          (item.body ? '<p>' + escapeHtml(item.body) + '</p>' : '') + '</div>';
      }} else {{
        html += '<div class="structured-item">' + escapeHtml(item) + '</div>';
      }}
    }});
    return html + '</div>';
  }}
  return renderBodyBlock(block);
}}

function renderTable(table) {{
  if (!table) return '';
  var html = '<div class="table-wrap">';
  if (table.caption) html += '<caption>'+escapeHtml(table.caption)+'</caption>';
  html += '<table>';
  if (Array.isArray(table.headers) && table.headers.length) {{
    html += '<thead><tr>';
    table.headers.forEach(function(h) {{ html += '<th>'+escapeHtml(h)+'</th>'; }});
    html += '</tr></thead>';
  }}
  if (Array.isArray(table.rows) && table.rows.length) {{
    html += '<tbody>';
    table.rows.forEach(function(row) {{
      html += '<tr>';
      asArray(row).forEach(function(cell) {{ html += '<td>'+escapeHtml(cell)+'</td>'; }});
      html += '</tr>';
    }});
    html += '</tbody>';
  }}
  html += '</table></div>';
  return html;
}}

function renderVisualAssetStrategy(strategy) {{
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
  var html = '<div class="asset-card">';
  html += '<div class="asset-row"><div class="asset-k">配图</div><div class="asset-v"><span class="asset-pill '+pillClass+'">'+escapeHtml(needText)+'</span></div></div>';
  html += '<div class="asset-row"><div class="asset-k">类型</div><div class="asset-v">'+escapeHtml(typeText)+'</div></div>';
  if (strategy.prompt_or_source) html += '<div class="asset-row"><div class="asset-k">来源</div><div class="asset-v">'+escapeHtml(strategy.prompt_or_source)+'</div></div>';
  if (strategy.fallback_if_missing) html += '<div class="asset-row"><div class="asset-k">缺失时</div><div class="asset-v">'+escapeHtml(strategy.fallback_if_missing)+'</div></div>';
  html += '</div>';
  return html;
}}

function renderSemanticValue(label, value) {{
  if (value === null || value === undefined || typeof value === 'boolean') return '';
  var title = label ? '<div class="structured-block-title">'+escapeHtml(label.replace(/_/g, ' '))+'</div>' : '';
  if (typeof value === 'string' || typeof value === 'number') {{
    return '<div class="structured-block">'+title+'<div class="structured-item">'+escapeHtml(value)+'</div></div>';
  }}
  if (Array.isArray(value)) {{
    if (!value.length) return '';
    var objectRows = value.every(function(item) {{ return item && typeof item === 'object' && !Array.isArray(item); }});
    if (objectRows) {{
      var headers = Object.keys(value[0]);
      var rows = value.map(function(item) {{ return headers.map(function(key) {{
        var cell=item[key]; return typeof cell === 'object' ? JSON.stringify(cell) : String(cell ?? '');
      }}); }});
      return '<div class="structured-block">'+title+renderTable({{headers:headers,rows:rows}})+'</div>';
    }}
    return '<div class="structured-block">'+title+value.map(function(item) {{
      return '<div class="structured-item">'+escapeHtml(item)+'</div>';
    }}).join('')+'</div>';
  }}
  if (typeof value === 'object') {{
    var inner = Object.keys(value).map(function(key) {{ return renderSemanticValue(key, value[key]); }}).join('');
    return '<div class="structured-block">'+title+inner+'</div>';
  }}
  return '';
}}

function renderOnSlideCopy(p) {{
  var html = '<div class="copy-blocks copy-summary compact-card">';
  var ch = p.copy_handling || {{}};
  var finalCopy = ch.final_on_slide || {{}};
  var title = finalCopy.title || p.action_title || '';
  var subtitle = finalCopy.subtitle || p.core_message || '';
  var moved = asStringList(ch.moved_to_notes, false);
  var compressed = asStringList(ch.compressed, false);
  var decisionBits = [];
  if (title) decisionBits.push('记住这一句: ' + title);
  if (compressed.length) decisionBits.push('压缩/合并 ' + compressed.length + ' 项说明');
  if (moved.length) decisionBits.push('移入备注 ' + moved.length + ' 项');
  if (decisionBits.length) {{
    html += '<div class="copy-decision">' + escapeHtml(decisionBits.join(' · ')) + '</div>';
  }}
  if (title) html += '<div class="action-title">' + escapeHtml(title) + '</div>';

  var body = [];
  var structuredBlocks = Array.isArray(finalCopy.body_blocks) ? finalCopy.body_blocks : [];
  if (structuredBlocks.length) {{
    html += '<div class="on-slide-combined structured-copy">';
    if (subtitle) html += '<div class="combined-lead">' + escapeHtml(subtitle) + '</div>';
    structuredBlocks.forEach(function(block) {{ html += renderFinalBlock(block); }});
    html += '</div>';
  }} else if (Array.isArray(finalCopy.body)) {{
    body = finalCopy.body;
  }} else if (typeof finalCopy.body === 'string' && finalCopy.body.trim()) {{
    body = [finalCopy.body];
  }}
  var semanticHtml = '';
  if (!body.length && !structuredBlocks.length) {{
    semanticHtml = Object.keys(finalCopy).filter(function(key) {{
      return ['title','subtitle','core_message','body','body_blocks','footer_takeaway'].indexOf(key) < 0;
    }}).map(function(key) {{ return renderSemanticValue(key, finalCopy[key]); }}).join('');
    if (!semanticHtml) {{
      body = asStringList(ch.kept_on_slide, false).filter(function(s) {{
        var v = String(s || '').toLowerCase();
        return v && v !== 'action_title' && v !== 'core_message';
      }});
    }}
  }}
  if (semanticHtml) html += '<div class="on-slide-combined structured-copy">'+semanticHtml+'</div>';
  if (!structuredBlocks.length && (subtitle || body.length)) {{
    html += '<div class="on-slide-combined">';
    if (subtitle) html += '<div class="combined-lead">' + escapeHtml(subtitle) + '</div>';
    body.forEach(function(s) {{
      html += '<div class="combined-line">' + escapeHtml(s) + '</div>';
    }});
    html += '</div>';
  }}
  if (finalCopy.footer_takeaway) {{
    html += '<div class="on-slide-item" style="margin-top:8px;font-weight:850;border-color:#F0C48C;background:#FFF8ED">' + escapeHtml(finalCopy.footer_takeaway) + '</div>';
  }}
  var rationale = asStringList(ch.compression_rationale, false);
  if (rationale.length) {{
    html += '<div class="section-label" style="margin-top:14px">文案处理原则</div><div class="copy-rationale-combined">';
    rationale.forEach(function(s) {{ html += '<div class="combined-line">' + escapeHtml(s) + '</div>'; }});
    html += '</div>';
  }}
  if (compressed.length) {{
    html += '<div class="section-label" style="margin-top:14px">精简/合并</div><div class="copy-rationale-combined">';
    compressed.forEach(function(s) {{ html += '<div class="combined-line">' + escapeHtml(s) + '</div>'; }});
    html += '</div>';
  }}
  if (moved.length) {{
    html += '<div class="section-label" style="margin-top:14px">移入备注</div><div class="notes-list">';
    moved.forEach(function(s) {{ html += '<div class="notes-item">' + escapeHtml(s) + '</div>'; }});
    html += '</div>';
  }}
  html += '</div>';
  return html;
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
    card.className = 'page-card' + (hasError ? ' error' : (hasWarning ? ' warning' : ''));

    if (nav) {{
      var link = document.createElement('a');
      link.className = 'nav-item';
      link.href = '#' + anchor;
      link.innerHTML = '<span class="nav-dot"></span><span>第' + pageNo + '页</span>';
      nav.appendChild(link);
    }}

    var modeBadge = '<span class="badge ' + (p.page_mode||'') + '">' + escapeHtml(modeLabel(p.page_mode)) + '</span>';
    var densityBadge = '<span class="badge ' + (p.visual_density||'') + '">' + escapeHtml(densityLabel(p.visual_density)) + '</span>';

    var html = '<div class="page-header">';
    html += '<h2>第' + pageNo + '页: ' + escapeHtml(p.page_title||('page_' + String(pageNo).padStart(2,'0'))) + '</h2>';
    html += '<div class="badges">' + modeBadge + densityBadge;
    if (sourceNo && sourceNo !== pageNo) html += '<span class="badge" style="background:#F5F7FA;color:#59636F">源稿P' + escapeHtml(sourceNo) + '</span>';
    if (p.layout_id) html += '<span class="badge" style="background:#F5F7FA;color:#333">' + escapeHtml(p.layout_id) + '</span>';
    if (p.grid) {{
      var gridLabel = typeof p.grid === 'object' ? Object.keys(p.grid).map(function(k){{return k+': '+p.grid[k];}}).join(' · ') : p.grid;
      html += '<span class="badge" style="background:#F5F7FA;color:#333">' + escapeHtml(gridLabel) + '</span>';
    }}
    html += '</div></div>';

    html += '<div class="page-body"><div class="layout-grid">';
    if (p.error) html += '<div class="page-error">' + escapeHtml(p.error) + '</div>';
    if (p.review_suggestions_warning) html += '<div class="page-error" style="background:#FFF8ED;color:#8A4700;border-color:#F0C48C">' + escapeHtml(p.review_suggestions_warning) + '</div>';
    if (!p.has_full_copy && !p.error) html += '<div class="page-error">页面文案不完整：缺少 action_title、core_message 或 body_blocks。请检查 page_content.json。</div>';

    // Visual decision first
    html += '<section class="visual-panel">';
    html += '<div class="section-label">空间线框图</div><div class="wireframe">';
    html += renderWireframeSVG(p.wireframe);
    html += '</div>';
    html += '<div class="section-label">素材需求</div>';
    html += renderVisualAssetStrategy(p.visual_asset_strategy);

    // Never trust historical data to match the latest contract. Python
    // normalizes new output; this protects already-generated project JSON.
    var suggestions = asStringList(p.review_suggestions, true);
    if (suggestions.length) {{
      html += '<div class="section-label">改进建议（勾选即采纳）</div><div class="suggestions">';
      var shown = suggestions.slice(0, 3);
      shown.forEach(function(s, si) {{
        html += '<label><input type="checkbox" name="sugg_'+idx+'" value="' + si + '"> ' + escapeHtml(s) + '</label>';
      }});
      html += '</div>';
    }}

    html += '<div class="action-zone"><div class="section-label">您的反馈</div><div class="feedback-text">';
    html += '<textarea name="feedback_'+idx+'" placeholder="对此页版式的调整意见、顾虑或备注..."></textarea>';
    html += '</div>';
    html += '<label class="approve-row"><input type="checkbox" name="approve_'+idx+'" value="1"> <strong>确认此页版式</strong></label>';
    html += '</div>';
    html += '</section>';

    html += '<section class="review-panel">';
    html += '<div class="section-label">最终上屏文案</div>';
    html += renderOnSlideCopy(p);

    html += '<details class="compact-details"><summary>原始完整文稿（默认收起）</summary><div class="details-body">';
    html += '<div class="copy-full"><div class="copy-full-title"><span>用于对照最终上屏文案是否过度简化</span><span>可滚动</span></div><div class="copy-blocks">';
    if (p.source_excerpt) {{
      html += '<pre style="white-space:pre-wrap;font-family:inherit;font-size:15px;color:#4F5965;line-height:1.7">' + escapeHtml(p.source_excerpt) + '</pre>';
    }} else {{
      html += '<div class="body-line">未提供原始完整文稿；下方显示结构化正文。</div>';
    }}
    if (Array.isArray(p.body_blocks) && p.body_blocks.length) {{
      if (p.source_excerpt) html += '<div class="section-label" style="margin-top:14px">结构化正文</div>';
      p.body_blocks.forEach(function(block) {{ html += renderBodyBlock(block); }});
    }}
    if (Array.isArray(p.tables) && p.tables.length) {{
      html += '<div class="section-label" style="margin-top:12px">表格数据</div>';
      p.tables.forEach(function(t) {{ html += renderTable(t); }});
    }}
    html += '</div></div></div></details>';

    // Speaker notes (collapsible)
    if (p.speaker_notes) {{
      html += '<details class="compact-details"><summary>演讲者备注</summary>';
      html += '<div class="details-body notes-content">' + escapeHtml(p.speaker_notes) + '</div></details>';
    }}
    html += '</section></div></div>'; // review-panel, layout-grid, page-body

    card.innerHTML = html;
    container.appendChild(card);
  }});
}}

function submitFeedback() {{
  var payload = {{pages:{{}}, all_approved: false}};
  pages.forEach(function(p, idx) {{
    var pageKey = p.page_key || ('page_' + String(p.page_number||(idx+1)).padStart(2,'0'));
    var selected = [];
    var checkboxes = document.getElementsByName('sugg_'+idx);
    checkboxes.forEach(function(cb) {{ if (cb.checked) selected.push(parseInt(cb.value)); }});
    var customFeedback = (document.getElementsByName('feedback_'+idx)[0]||{{}}).value||'';
    var approved = (document.getElementsByName('approve_'+idx)[0]||{{}}).checked||false;
    payload.pages[pageKey] = {{
      selected_suggestions: selected,
      custom_feedback: customFeedback,
      approved: approved
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
      setTimeout(function(){{ toast.className='toast'; }}, 3000);
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

function approveAll() {{
  pages.forEach(function(p, idx) {{
    var cb = document.getElementsByName('approve_'+idx)[0];
    if (cb) cb.checked = true;
  }});
  submitFeedback();
}}

renderPages();

function updateHeaderCompactState() {{
  document.body.classList.toggle('review-scrolled', window.scrollY > 24);
}}
updateHeaderCompactState();
window.addEventListener('scroll', updateHeaderCompactState, {{passive:true}});

var observer = new IntersectionObserver(function(entries) {{
  entries.forEach(function(entry) {{
    if (!entry.isIntersecting) return;
    document.querySelectorAll('.nav-item').forEach(function(a) {{ a.classList.remove('active'); }});
    var active = document.querySelector('.nav-item[href="#'+entry.target.id+'"]');
    if (active) active.classList.add('active');
  }});
}}, {{rootMargin:'-35% 0px -55% 0px', threshold:0}});
document.querySelectorAll('.page-card').forEach(function(card) {{ observer.observe(card); }});
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
