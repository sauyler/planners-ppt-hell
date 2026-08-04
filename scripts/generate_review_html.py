"""
Generate 02_visual_review.html from page_manifest.json, validation, and self-review data.

Reads pages from page_manifest.json (the single source of truth for page ordering and paths),
validation results from validation_summary.json, and self-review from self_review.json.
Fails loudly when validation is missing or PNG paths are broken. Non-blocking
validator warnings are internal evidence for model self-review; the user-facing
page shows model-synthesized design suggestions instead of raw warning actions.

Usage:
  python generate_review_html.py <project_dir> [--batch BATCH_ID] [--output <path>]
  python generate_review_html.py <project_dir> --batch BATCH_ID --debug-show-failures
"""

import argparse
import json
import sys
from pathlib import Path

from review_policy import blocking_warning_issues

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>视觉审阅 — {project} — {batch_label}</title>
<style>
  :root{{--ink:#17202A;--muted:#6B7480;--soft:#EEF2F6;--paper:#FFFFFF;--line:#DDE4EC;--navy:#051C2C;--accent:#D46A00;--ok:#007A53;--danger:#E60012;--blue:#006BA6;--wash:#F7F9FC}}
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:linear-gradient(180deg,#E9EEF4 0,#F5F7FA 320px);color:var(--ink);line-height:1.58;letter-spacing:0}}
  .header{{background:rgba(5,28,44,.96);color:#FFF;padding:16px 30px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:10;box-shadow:0 10px 26px rgba(5,28,44,.16)}}
  .header h1{{font-size:23px;font-weight:850}}
  .status-bar{{display:flex;gap:12px;font-size:14px}}
  .status-bar .pass{{color:#8BC34A}} .status-bar .warn{{color:#FFC107}} .status-bar .fail{{color:#FF5252}}
  .workspace{{max-width:1620px;margin:0 auto;padding:22px 24px;display:grid;grid-template-columns:176px minmax(0,1fr);gap:18px;align-items:start}}
  .side-nav{{position:sticky;top:92px;background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:8px;padding:10px;box-shadow:0 14px 36px rgba(5,28,44,.08);backdrop-filter:blur(10px)}}
  .side-nav-title{{font-size:13px;font-weight:850;color:var(--muted);margin-bottom:10px}}
  .nav-list{{display:flex;flex-direction:column;gap:7px;max-height:calc(100vh - 138px);overflow:auto;padding-right:2px}}
  .nav-item{{display:grid;grid-template-columns:8px 1fr;align-items:center;gap:7px;padding:8px 9px;border-radius:7px;color:#46515E;text-decoration:none;font-size:12px;font-weight:800;background:#F5F7FA;border:1px solid transparent;transition:.16s ease}}
  .nav-item:hover,.nav-item.active{{background:#FFF7EB;border-color:#F0C48C;color:#8A4700;transform:translateX(2px)}}
  .nav-dot{{width:8px;height:8px;border-radius:50%;background:#007A53;flex:0 0 auto}}
  .nav-dot.warning{{background:#D46A00}}
  .container{{min-width:0}}
  .global-alert{{padding:14px 20px;border-radius:8px;margin-bottom:20px;font-size:15px;font-weight:850}}
  .global-alert.error{{background:#FFEBEE;color:#C62828;border:2px solid #E60012}}
  .global-alert.warning{{background:#FFF3E0;color:#D46A00;border:2px solid #D46A00}}
  .page-review{{background:var(--paper);border-radius:8px;margin-bottom:26px;box-shadow:0 18px 44px rgba(5,28,44,.08);overflow:hidden;border:1px solid var(--line)}}
  .page-review.fail{{border-left:5px solid #E60012}}
  .page-review.warning{{border-left:5px solid #D46A00}}
  .page-review.pass{{border-left:5px solid #007A53}}
  .page-head{{padding:18px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);flex-wrap:wrap;gap:8px;background:linear-gradient(180deg,#FFFFFF,#FAFBFD)}}
  .page-head h2{{font-size:22px;line-height:1.35;font-weight:900;max-width:1040px}}
  .page-meta{{font-size:13px;color:#8A929C;font-weight:800}}
  .page-body{{padding:22px 24px 24px}}
  .review-grid{{display:grid;grid-template-columns:minmax(720px,1.55fr) minmax(380px,.75fr);gap:24px;align-items:start}}
  .preview-panel{{position:sticky;top:104px}}
  .qa-panel{{min-width:0}}
  .preview-row{{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}}
  .preview-box{{flex:1;min-width:340px;max-width:100%}}
  .preview-box img{{width:100%;border:1px solid var(--line);border-radius:8px;background:#FAFAFA;box-shadow:0 18px 44px rgba(5,28,44,.10)}}
  .preview-box .vlabel{{font-size:12px;color:#999;margin-bottom:4px;font-weight:bold}}
  .grid-2col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
  @media(max-width:800px){{.grid-2col{{grid-template-columns:1fr}}}}
  .section-label{{font-size:13px;font-weight:900;color:#8A929C;margin-bottom:8px;letter-spacing:0;margin-top:14px}}
  .section-label:first-child{{margin-top:0}}
  .val-summary{{background:#F7F9FC;border-radius:8px;padding:13px 16px;margin-bottom:14px;font-size:15px;border:1px solid var(--line);font-weight:850}}
  .val-summary .status-pass{{color:#007A53}} .val-summary .status-warn{{color:#D46A00}} .val-summary .status-fail{{color:#E60012}}
  .required-fixes{{background:#FFEBEE;border:2px solid #E60012;border-radius:8px;padding:12px 16px;margin-bottom:16px}}
  .required-fixes .rf-title{{font-size:15px;font-weight:bold;color:#C62828;margin-bottom:6px}}
  .required-fixes .rf-subtitle{{font-size:12px;color:#999;margin-bottom:6px}}
  .required-fixes li{{font-size:14px;color:#C62828;margin-left:18px;margin-bottom:2px}}
  .self-review-status{{margin-bottom:16px;padding:10px 14px;border-radius:8px;font-size:14px}}
  .self-review-status.blocked{{background:#FFEBEE;color:#C62828;border:1px solid #E60012}}
  .self-review-status.revise{{background:#FFF3E0;color:#D46A00;border:1px solid #D46A00}}
  .self-review-status.pass{{background:#E8F5E9;color:#007A53;border:1px solid #007A53}}
  .self-review-status.human_review{{background:#E3F2FD;color:#006BA6;border:1px solid #006BA6}}
  .review-actions{{display:grid;gap:10px;margin-bottom:16px}}
  .review-action{{display:grid;grid-template-columns:22px 1fr;gap:12px;padding:14px 16px;background:#FFF;border:1px solid var(--line);border-radius:8px;cursor:pointer;transition:.16s ease}}
  .review-action:hover{{border-color:#007A53;background:#F2FBF7;transform:translateY(-1px)}}
  .review-action input{{width:22px;height:22px;accent-color:#007A53;margin-top:2px}}
  .action-title{{font-size:15px;font-weight:900;color:#26323F;margin-bottom:3px}}
  .action-desc{{font-size:13px;color:#66717E;line-height:1.45}}
  .action-meta{{font-size:12px;color:#9AA2AC;margin-top:5px;font-weight:800}}
  .action-source{{display:inline-block;border-radius:999px;padding:2px 8px;margin-right:6px;background:#EEF2F6;color:#66717E}}
  .accept-note{{background:#F7F9FC;border:1px solid var(--line);border-radius:8px;padding:10px 12px;color:#6B7480;font-size:13px;margin-bottom:14px}}
  .tech-details{{border:1px solid var(--line);border-radius:8px;background:#FFF;margin-bottom:14px}}
  .tech-details summary{{cursor:pointer;list-style:none;padding:13px 14px;font-weight:850;color:#66717E}}
  .tech-details summary::-webkit-details-marker{{display:none}}
  .tech-details ul{{padding:0 18px 14px 32px}}
  .tech-details li{{font-size:13px;color:#66717E;margin-bottom:4px}}
  .revision-notes{{margin-top:18px;background:#F7F9FC;border:1px solid var(--line);border-radius:8px;padding:14px 16px}}
  .revision-notes-title{{font-size:15px;font-weight:900;color:#26323F;margin-bottom:8px}}
  .revision-grid{{display:grid;gap:9px}}
  .revision-block{{background:#FFF;border:1px solid #E8ECF2;border-radius:8px;padding:10px 12px}}
  .revision-block strong{{display:block;font-size:13px;color:#7A8490;margin-bottom:4px}}
  .revision-block li{{font-size:13px;color:#46515E;margin-left:18px;margin-bottom:3px}}
  .suggestions{{display:grid;gap:10px;margin-bottom:18px}}
  .suggestions label{{display:flex;align-items:center;gap:12px;padding:15px 16px;font-size:16px;color:#39424E;cursor:pointer;background:#FFF;border:1px solid var(--line);border-radius:8px;min-height:58px;transition:.16s ease}}
  .suggestions label:hover{{border-color:#007A53;background:#F2FBF7;transform:translateY(-1px)}}
  .suggestions input{{width:22px;height:22px;accent-color:#007A53;flex:0 0 auto}}
  .feedback-text textarea{{width:100%;min-height:92px;border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:16px;font-family:inherit;resize:vertical;background:#FFF}}
  .action-zone{{position:sticky;bottom:14px;background:rgba(255,255,255,.94);border:1px solid var(--line);box-shadow:0 14px 34px rgba(5,28,44,.10);border-radius:8px;padding:14px;margin-top:10px;backdrop-filter:blur(10px)}}
  .approval-status{{padding:10px 12px;border:1px solid #D8DEE3;border-radius:7px;background:#F5F7F8;color:#6E7A84;font-size:12px;font-weight:800}}
  .approval-status.approved{{border-color:#BFDCCB;background:#F0F8F3;color:#08744F}}
  .submit-btn{{background:var(--danger);color:#FFF;border:none;padding:14px 40px;font-size:18px;font-weight:850;border-radius:8px;cursor:pointer;margin:0 6px;box-shadow:0 12px 28px rgba(230,0,18,.18)}}
  .submit-btn.green{{background:#007A53}}
  .toast{{position:fixed;top:20px;right:20px;background:#051C2C;color:#FFF;padding:14px 24px;border-radius:8px;font-size:15px;display:none;z-index:999}}
  .toast.show{{display:block}}
  .project-credit{{max-width:1620px;margin:0 auto 28px;padding:0 24px;text-align:center;color:#8A929C;font-size:13px;font-weight:800}}
  .project-credit a{{color:#59636F;text-decoration:none;border-bottom:1px solid #C8D0DA}}
  .missing-file{{background:#FFEBEE;color:#C62828;padding:8px 12px;border-radius:6px;font-size:13px;margin-bottom:8px;border:1px solid #E60012}}
  /* Compact visual review UI override. */
  body{{background:#EEF3F8;color:#182433}}
  .header{{background:#06131B;padding:20px 40px;display:grid;grid-template-columns:1fr auto;grid-template-areas:"title status" ". brand";align-items:center;gap:8px 18px;box-shadow:none;transition:padding .18s ease}}
  .header h1{{grid-area:title;font-size:24px}}
  .header .creator{{grid-area:brand;justify-self:end;display:flex;align-items:center;gap:9px;color:#DCE5EA;white-space:nowrap}}
  .creator-mark{{display:grid;place-items:center;width:30px;height:30px;border:1px solid rgba(255,255,255,.24);border-radius:8px;background:rgba(255,255,255,.06);color:#F0A05A;font:950 13px/1 ui-monospace,SFMono-Regular,Menlo,monospace}}
  .creator-copy{{display:grid;line-height:1.1}}.creator-copy strong{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#F5F7F8}}.creator-copy small{{margin-top:4px;font-size:10px;color:#7F8D97}}
  .status-bar{{grid-area:status;justify-self:end;align-self:center}}
  body.review-scrolled .header{{padding:10px 40px;grid-template-areas:"title status"}}
  body.review-scrolled .header .creator{{display:none}}
  body.review-scrolled .header h1{{font-size:21px}}
  .workspace{{max-width:none;padding:14px 18px 14px 0;grid-template-columns:104px minmax(0,1fr);gap:0}}
  .side-nav{{justify-self:center;top:92px;width:46px;padding:8px 5px;border-radius:9px;box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  body.review-scrolled .side-nav{{top:58px}}
  .side-nav-title{{display:none}}
  .nav-list{{counter-reset:batchNav;align-items:center;gap:8px;max-height:calc(100vh - 120px);padding:0;overflow:visible}}
  .nav-item{{counter-increment:batchNav;display:grid;grid-template-columns:1fr;place-items:center;width:32px;height:32px;padding:0;border-radius:999px;background:#F4F7FA;font-size:0;line-height:1}}
  .nav-item::before{{content:counter(batchNav);display:block;width:100%;height:32px;font-size:13px;font-weight:950;line-height:32px;text-align:center;transform:translateY(1px);color:#66717E}}
  .nav-item:hover,.nav-item.active{{transform:none;background:#FFF4E3;border-color:#F0C48C}}
  .nav-item:hover::before,.nav-item.active::before{{color:#D46A00}}
  .nav-dot{{display:none}}
  .page-review{{border-radius:9px;margin-bottom:18px;box-shadow:0 10px 26px rgba(5,28,44,.05)}}
  .page-review.fail,.page-review.warning,.page-review.pass{{border-left:1px solid var(--line)}}
  .page-head{{padding:18px 28px}}
  .page-head h2{{font-size:22px}}
  .page-body{{padding:18px 28px}}
  .review-grid{{grid-template-columns:minmax(760px,1.65fr) minmax(330px,.62fr);gap:22px}}
  .preview-panel{{top:96px}}
  .preview-box img{{box-shadow:none;border-color:#E6ECF3}}
  .val-summary,.accept-note,.review-action,.feedback-text textarea,details.self-review-status{{border-color:#E6ECF3}}
  .page-meta,.section-label{{font-size:12px}}
  .review-action{{padding:12px 14px}}
  .action-title{{font-size:14px}}
  .action-desc,.action-meta,.accept-note{{font-size:12px}}
  details.self-review-status{{padding:0;overflow:hidden}}
  details.self-review-status summary{{list-style:none;cursor:pointer;padding:11px 14px;font-weight:900}}
  details.self-review-status summary::-webkit-details-marker{{display:none}}
  .self-review-body{{padding:0 14px 12px;line-height:1.7;color:inherit}}
  .action-zone{{box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  .submit-btn{{min-width:210px;border-radius:10px;margin:0;padding:13px 28px;box-shadow:none}}
  .project-credit{{font-size:14px;padding-bottom:22px}}
  @media(max-width:1100px){{.workspace{{grid-template-columns:1fr;padding-left:18px}}.side-nav{{position:static;width:auto}}.nav-list{{flex-direction:row;overflow:auto}}.review-grid{{grid-template-columns:1fr}}.preview-panel{{position:static}}.header{{grid-template-columns:1fr;grid-template-areas:"title" "brand" "status"}}.header .creator,.status-bar{{justify-self:start;white-space:normal}}}}
  /* Visual proofing desk v2: compare one slide, make one decision. */
  body{{min-height:100vh;padding-bottom:74px;background:#E6EAED}}
  .header{{height:72px;padding:0 28px;grid-template-columns:auto 1fr auto;grid-template-areas:"title brand status";border-bottom:1px solid rgba(255,255,255,.09)}}
  .header h1{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;font-size:24px}}
  .header .creator{{justify-self:start;margin-left:18px}}
  .workspace{{height:calc(100vh - 72px - 74px);min-height:640px;padding:0;grid-template-columns:112px minmax(0,1fr);gap:0}}
  .side-nav{{position:relative;top:0;justify-self:stretch;width:auto;height:100%;padding:14px 10px;border:0;border-radius:0;background:#111B22;box-shadow:none;overflow:hidden}}
  .side-nav-title{{display:flex;justify-content:center;color:#71808B;padding:0 0 9px;font-size:10px;letter-spacing:.12em;text-transform:uppercase}}
  .nav-list{{display:flex;align-items:stretch;gap:7px;max-height:calc(100vh - 180px);overflow:auto;padding:0 3px;scrollbar-width:none}}
  .nav-list::-webkit-scrollbar,.qa-panel::-webkit-scrollbar,.preview-panel::-webkit-scrollbar{{display:none}}
  .nav-item{{counter-increment:none;position:relative;display:block;width:100%;height:auto;padding:5px;border:1px solid transparent;border-radius:7px;background:transparent;color:#AAB4BC}}
  .nav-item::before{{content:none}}
  .nav-item:hover,.nav-item.active{{background:#1E2A32;border-color:#34434E;transform:none;color:#FFF}}
  .nav-thumb{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:4px;background:#2A3740}}
  .nav-copy{{position:absolute;left:8px;top:8px;min-width:24px;padding:3px 5px;border-radius:4px;background:rgba(7,19,26,.78);color:#FFF;font:800 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden}}
  .nav-state{{position:absolute;right:8px;top:8px;width:8px;height:8px;border:1px solid rgba(255,255,255,.75);border-radius:999px;background:#64737D}}
  .nav-item.reviewed .nav-state{{background:#52B788}}
  .nav-item.changed .nav-state{{background:#F0A05A}}
  .nav-item.machine-fail{{border-color:rgba(233,92,98,.62)}}
  .container{{height:100%;padding:18px;overflow:hidden;background:#111B22}}
  .global-alert{{position:absolute;z-index:20;left:130px;right:18px;top:86px;margin:0}}
  .page-review{{display:none;height:100%;margin:0;border:0;border-radius:10px;box-shadow:0 18px 50px rgba(19,31,40,.12);overflow:hidden}}
  .page-review.active{{display:grid;grid-template-rows:auto minmax(0,1fr);animation:proofIn .2s ease both}}
  @keyframes proofIn{{from{{opacity:.35;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}
  .page-head{{padding:12px 20px;background:#FFF;border-bottom:1px solid #E5E9EC}}
  .page-head h2{{font-size:18px}}
  .page-body{{padding:0;min-height:0;overflow:hidden}}
  .review-grid{{height:100%;grid-template-columns:minmax(680px,1.55fr) minmax(340px,.63fr);gap:0}}
  .preview-panel{{position:relative;top:0;min-height:0;display:grid;place-items:center;padding:16px;overflow:hidden;background:#20292F}}
  .preview-row,.grid-2col{{width:100%;height:100%;margin:0;min-height:0}}
  .preview-box{{width:100%;height:100%;max-width:1160px;margin:0 auto;display:grid;place-items:center;min-height:0}}
  .preview-box img{{display:block;width:100%;height:100%;object-fit:contain;border:0;border-radius:4px;box-shadow:0 26px 70px rgba(0,0,0,.30)}}
  .annotation-stage{{position:relative;width:min(100%,calc((100vh - 190px)*16/9));max-height:100%;aspect-ratio:16/9;line-height:0;user-select:none}}
  .annotation-layer{{position:absolute;inset:0;z-index:5;pointer-events:none;cursor:crosshair}}
  .annotation-layer.annotating{{pointer-events:auto;background:rgba(255,142,43,.04);box-shadow:inset 0 0 0 2px #FF8E2B}}
  .annotation-rect{{position:absolute;border:2px solid #FF6A3D;background:rgba(255,106,61,.12);box-shadow:0 0 0 1px rgba(255,255,255,.9);border-radius:3px}}
  .annotation-rect::before{{content:attr(data-number);position:absolute;left:-2px;top:-22px;display:grid;place-items:center;min-width:22px;height:20px;padding:0 4px;border-radius:4px 4px 0 0;background:#FF6A3D;color:#FFF;font:800 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace}}
  .region-feedback{{margin:14px 0;padding:12px;border:1px solid #D8DEE3;border-radius:9px;background:#FFF8ED}}
  .region-feedback-head{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
  .region-feedback-head strong{{font-size:13px;color:#7A430D}}
  .region-btn{{padding:8px 11px;border:1px solid #D4832D;border-radius:7px;background:#FFF;color:#9A520A;font:800 12px/1 inherit;cursor:pointer}}
  .region-hint{{margin-top:7px;font-size:11px;line-height:1.5;color:#7A6856}}
  .region-item{{margin-top:9px;padding:9px;border:1px solid #EDC99D;border-radius:7px;background:#FFF}}
  .region-item label{{display:block;margin-bottom:5px;font-size:11px;font-weight:800;color:#9A520A}}
  .region-item textarea{{width:100%;min-height:58px;padding:8px;border:1px solid #D8DEE3;border-radius:6px;font:13px/1.5 inherit;resize:vertical}}
  .region-item-actions{{display:flex;justify-content:flex-end;margin-top:5px}}.region-delete{{border:0;background:transparent;color:#9A5B4C;cursor:pointer;font-size:11px}}
  .preview-panel>.section-label{{display:none}}
  .qa-panel{{min-height:0;padding:16px;overflow:auto;background:#FAFBFC;scrollbar-width:none;overscroll-behavior:contain}}
  .section-label{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7E8992}}
  .val-summary,.accept-note,.review-action,.feedback-text textarea,details.self-review-status{{border-color:#D8DEE3}}
  .action-zone{{position:relative;bottom:auto;margin-top:14px;background:#FFF;box-shadow:none}}
  .feedback-text textarea{{min-height:80px;font-size:14px}}
  .project-credit{{display:none}}
  .review-dock{{position:fixed;left:0;right:0;bottom:0;z-index:60;height:74px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px;padding:0 24px 0 136px;background:#07131A;color:#FFF;border-top:1px solid rgba(255,255,255,.08);box-shadow:0 -12px 34px rgba(7,19,26,.18)}}
  .dock-group{{display:flex;align-items:center;gap:8px}}.dock-group.end{{justify-content:flex-end}}
  .dock-btn{{height:40px;padding:0 16px;border:1px solid #35444E;border-radius:7px;background:#13232D;color:#DDE5EA;font:800 13px/1 inherit;cursor:pointer}}
  .dock-btn:hover{{border-color:#657681;background:#1B2D38}}
  .dock-btn.primary{{border-color:#4CB782;background:#1E8A5B;color:#FFF}}
  .dock-btn.warn{{border-color:#D08A46;background:#B86419;color:#FFF}}
  .dock-btn.danger{{border-color:#E95C62;background:#E60012;color:#FFF}}
  .dock-progress{{font:800 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:#93A1AB;letter-spacing:.08em}}
  .decision-sheet{{position:fixed;inset:0;z-index:100;display:none;place-items:center;padding:24px;background:rgba(7,19,26,.88);backdrop-filter:blur(10px)}}
  .decision-sheet.open{{display:grid}}
  .decision-card{{width:min(680px,calc(100vw - 48px));padding:24px;border-radius:12px;background:#FFF;box-shadow:0 30px 100px rgba(0,0,0,.34)}}
  .decision-card h2{{font-size:22px;margin-bottom:7px}}.decision-card p{{color:#65717A;font-size:13px;margin-bottom:15px}}
  .decision-card textarea{{width:100%;min-height:130px;padding:12px;border:1px solid #D8DEE3;border-radius:8px;font:14px/1.6 inherit;resize:vertical}}
  .decision-summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:15px 0}}
  .decision-summary div{{padding:12px;border:1px solid #E0E6EB;border-radius:8px;background:#F7F9FA;text-align:center;font-size:12px;color:#66717E}}
  .decision-summary strong{{display:block;font-size:22px;color:#1D2B34}}
  .sheet-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:16px;flex-wrap:wrap}}
  html,body{{height:100%;overflow:hidden}}body{{min-height:0!important;padding-bottom:0!important}}
  .completion{{position:fixed;inset:0;z-index:120;display:none;place-items:center;padding:24px;background:rgba(7,19,26,.86);backdrop-filter:blur(10px)}}
  .completion.open{{display:grid}}
  .completion-card{{width:min(560px,100%);padding:30px;border-radius:12px;background:#FFF;text-align:center;box-shadow:0 30px 100px rgba(0,0,0,.34)}}
  .completion-card h2{{font-family:inherit;font-size:27px;margin-bottom:8px}}.completion-card p{{color:#64717A;margin-bottom:18px}}
  @media(max-width:1100px){{.workspace{{grid-template-columns:92px minmax(0,1fr)}}.review-grid{{grid-template-columns:1fr}}.preview-panel,.qa-panel{{overflow:visible}}.container,.page-body{{overflow:auto}}.review-dock{{padding-left:116px}}}}
</style>
</head>
<body>
<div class="header">
  <h1>视觉审阅: {project} — {batch_label}</h1>
  <div class="creator"><span class="creator-mark">PH</span><span class="creator-copy"><strong>Planner's PPT Hell</strong><small>@阿祖不看TVC</small></span></div>
  <div class="status-bar">
    <span class="pass">页面: {count_pass}</span>
    <span class="warn">设计建议: {count_warn}</span>
    <span class="fail">阻断: {count_fail}</span>
  </div>
</div>
<div class="workspace">
  <aside class="side-nav">
    <div class="side-nav-title">批次导航</div>
    <nav class="nav-list" id="pageNav"></nav>
  </aside>
  <main class="container" id="container">{global_alerts}</main>
</div>
<div class="review-dock" aria-label="视觉审阅导航">
  <div class="dock-group"><button class="dock-btn" id="prevPage" type="button">← 上一页</button><button class="dock-btn" id="nextPage" type="button">下一页 →</button></div>
  <div class="dock-progress" id="dockProgress">01 / {page_count}</div>
  <div class="dock-group end"><button class="dock-btn warn" type="button" onclick="reviseCurrent()">标记修改</button><button class="dock-btn primary" type="button" onclick="approveCurrentAndNext()">批准当前页</button><button class="dock-btn danger" type="button" onclick="openReviewSubmit()">提交本轮审阅</button></div>
</div>
<div class="decision-sheet" id="reviewSubmitSheet" role="dialog" aria-modal="true"><div class="decision-card"><h2>提交本轮视觉审阅</h2><p>逐页决定和整套反馈在这里一次提交。已标记修改的页面不会被批量批准覆盖。</p><label for="globalFeedback" style="display:block;margin-bottom:7px;font-size:12px;font-weight:900;color:#53616B">整套统一反馈 <span style="font-weight:600;color:#98A2A9">· 可选</span></label><textarea id="globalFeedback" placeholder="只填写跨页面都适用的视觉要求；逐页问题请留在对应页面。"></textarea><div class="decision-summary" id="decisionSummary"></div><div class="sheet-actions"><button class="dock-btn" type="button" onclick="toggleSheet('reviewSubmitSheet',false)">继续审阅</button><button class="dock-btn" type="button" onclick="submitFeedback(false)">提交已有决定</button><button class="dock-btn primary" type="button" onclick="submitFeedback(true)">批准未处理页并提交</button></div></div></div>
<div class="toast" id="toast"></div>
<div class="completion" id="completion" role="dialog" aria-modal="true"><div class="completion-card"><h2>视觉反馈已保存</h2><p>请回到 Codex 问答框发送「已完成」，模型会读取逐页判断和整套反馈后继续。</p><button class="dock-btn primary" id="copyCompleted" type="button">复制「已完成」</button><button class="dock-btn" id="closeCompletion" type="button">继续查看</button></div></div>
<footer class="project-credit">
  Planner's PPT Hell © 2026 · 小红书 @阿祖不看 TVC · 网站 <a href="https://demyth.info" target="_blank" rel="noreferrer">demyth.info</a>
</footer>
<script>
var pages = {pages_json};
var validation = {validation_json};
var selfReview = {self_review_json};
var versions = {versions_json};
var revisionNotes = {revision_notes_json};
var batchId = "{batch_id}";
var pageBatchMap = {page_batch_json};
var hasSelfReview = {has_self_review};
var visionAvailable = {vision_available};
var visionUnavailableReason = {vision_unavailable_reason_json};
var hasValidation = {has_validation};
var activePageIndex = 0;
var pageDecisions = {{}};
var pageAnnotations = {{}};
var annotationModeIndex = null;

function escapeHtml(s) {{
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function assetUrl(path) {{
  if (!path) return '';
  if (location.protocol === 'file:' && path.indexOf('/_internal/') === 0) {{
    return path.slice(1);
  }}
  return path;
}}

var pageActionCache = {{}};

function warningActionSpec(issue) {{
  var code = issue.code || '';
  var msg = issue.message || '';
  var text = code + ' ' + msg;
  if (/FONT_TOO_SMALL|FONT_SIZE|MISSING_FONT|font-size/i.test(text)) {{
    return {{
      id:'font_readability',
      title:'小字或字体风险',
      desc:'提高小字号、减少次级说明，优先保证投影和 PPT 编辑后的可读性。'
    }};
  }}
  if (/TEXT_OVERFLOW_MAJOR/i.test(text)) {{
    return {{
      id:'text_overflow_major',
      title:'文字明显放不下',
      desc:'优先拆行、扩大容器或减少上屏文字；这是进入审阅前最值得修的文字容量问题。'
    }};
  }}
  if (/TEXT_CONTAINER_TIGHT|TEXT_BASELINE_ESTIMATE_DRIFT|OVERFLOW|贴边|overflow/i.test(text)) {{
    return {{
      id:'text_fit',
      title:'文字贴边或估算偏差',
      desc:'先看左侧 PNG 是否真的拥挤；若肉眼可接受，可不修，若显得紧再拆行或扩大容器。'
    }};
  }}
  if (/HIGH_TEXT_DENSITY|density|text elements/i.test(text)) {{
    return {{
      id:'reduce_density',
      title:'信息密度偏高',
      desc:'合并重复标签，删除非关键注释，保留主判断和关键证据。'
    }};
  }}
  if (/PALETTE|COLOR|Colors outside/i.test(text)) {{
    return {{
      id:'color_consistency',
      title:'颜色可能偏离规范',
      desc:'检查是否需要统一色板；如果这是品牌色覆盖，请在反馈中确认接受。'
    }};
  }}
  if (/SAFE_MARGIN|UNSAFE_MARGIN|bounds|outside/i.test(text)) {{
    return {{
      id:'safe_margin',
      title:'元素靠近边界',
      desc:'调整元素位置，避免导出或投影时显得拥挤、被裁切。'
    }};
  }}
  if (/TEXT_ANCHOR_MIDDLE_LONG|text-anchor/i.test(text)) {{
    return {{
      id:'long_center_text',
      title:'居中文本过长',
      desc:'改成左对齐或拆行，降低 PPT 编辑后跑版风险。'
    }};
  }}
  if (/same page_mode|same visual_density|rhythm/i.test(text)) {{
    return {{
      id:'deck_rhythm',
      title:'页面节奏重复',
      desc:'调整页面信息密度或视觉模式，避免连续页面观感过于相似。'
    }};
  }}
  if (/LARGE_EMPTY_REGION|LOW_MODULE_UTILIZATION|TABLE_READABILITY_RISK|VISUAL_WEIGHT|DENSITY_IMBALANCE/i.test(text)) {{
    return {{
      id:'layout_quality',
      title:'版面空间利用或视觉重心不稳',
      desc:'检查是否存在大块无功能空白、表格占位低效或上下左右重量失衡；优先改模块结构，不要只微调坐标。'
    }};
  }}
  return {{
    id:'review_warning',
    title:'其他可检查风险',
    desc:'存在非阻断质量提示，可人工检查页面细节后决定是否优化。'
  }};
}}

function buildReviewActions(suggestions) {{
  var actions = [];
  (suggestions || []).slice(0,3).forEach(function(sug, si) {{
    actions.push({{
      action_id: 'self_' + (sug.id || si),
      label: sug.text || '模型建议优化',
      description: sug.basis
        ? ('设计建议：' + String(sug.type || 'visual').toUpperCase() + ' · ' + String(sug.basis))
        : (sug.type ? ('设计建议：' + String(sug.type).toUpperCase()) : '设计建议'),
      source: 'self_review',
      source_index: si,
      source_codes: [],
      messages: [sug.text || '']
    }});
  }});
  return actions;
}}

function renderReviewActions(pageKey, idx, actions) {{
  pageActionCache[pageKey] = actions || [];
  if (!actions || !actions.length) {{
    return '<div class="accept-note">没有建议修改项。若页面效果可接受，可直接确认通过。</div>';
  }}
  var html = '<div class="review-actions">';
  actions.forEach(function(a, ai) {{
    var meta = '来源：模型综合视觉判断';
    html += '<label class="review-action">';
    html += '<input type="checkbox" name="action_'+idx+'" value="'+ai+'">';
    html += '<div><div class="action-title">'+escapeHtml(a.label)+'</div>';
    html += '<div class="action-desc">'+escapeHtml(a.description || '')+'</div>';
    html += '<div class="action-meta"><span class="action-source">'+escapeHtml(a.source || '')+'</span>'+escapeHtml(meta)+'</div>';
    html += '</div></label>';
  }});
  html += '</div><div class="accept-note">勾选表示“下一轮请修”。不勾选的设计建议视为本轮人工接受或暂不处理。</div>';
  return html;
}}

function renderRevisionNotes(pageKey) {{
  var notesRoot = revisionNotes || {{}};
  var pagesNotes = notesRoot.pages || notesRoot;
  var n = pagesNotes[pageKey];
  if (!n) return '';
  function block(title, arr) {{
    if (!arr || !arr.length) return '';
    var html = '<div class="revision-block"><strong>'+escapeHtml(title)+'</strong><ul>';
    arr.forEach(function(item) {{ html += '<li>'+escapeHtml(item)+'</li>'; }});
    html += '</ul></div>';
    return html;
  }}
  var body = '';
  body += block('上一轮用户要求', n.previous_feedback || n.user_requests);
  body += block('本轮已修改', n.changes_made);
  body += block('未改 / 保留原因', n.not_changed);
  body += block('仍需确认', n.remaining_risks);
  if (!body) return '';
  return '<div class="revision-notes"><div class="revision-notes-title">上一轮反馈与本轮修改</div><div class="revision-grid">'+body+'</div></div>';
}}

function pageHasBlockingIssues(pageKey) {{
  var v = (validation||{{}})[pageKey]||{{}};
  var issues = v.issues || [];
  var hasError = v.status === 'fail' || issues.some(function(i) {{ return i.severity === 'error'; }});
  var s = (selfReview||{{}})[pageKey]||{{}};
  var fixes = (s.required_fixes || []);
  return hasError || s.visual_status === 'blocked' || s.status === 'blocked' || fixes.length > 0;
}}

function statusLabel(v) {{
  return {{pass:'通过', warning:'警告', fail:'失败', unknown:'未知'}}[v] || v || '未知';
}}

function modeLabel(v) {{
  return {{rational:'理性页', emotional:'情绪页'}}[v] || v || '';
}}

function densityLabel(v) {{
  return {{dense:'高密度', balanced:'均衡', airy:'留白'}}[v] || v || '';
}}

function renderPages() {{
  var container = document.getElementById('container');
  var nav = document.getElementById('pageNav');

  if (!hasValidation) {{
    var alertDiv = document.createElement('div');
    alertDiv.className = 'global-alert error';
    alertDiv.textContent = '警告：validation_summary.json 缺失。所有页面校验结果未知，请先运行 validate_svg_layout.py。';
    container.appendChild(alertDiv);
  }}

  if (!hasSelfReview) {{
    var alertDiv2 = document.createElement('div');
    alertDiv2.className = 'global-alert warning';
    alertDiv2.textContent = '内部视觉闭环未完成：self_review.json 缺失。请用当前冻结任务恢复 SVG 阶段，不得以用户 Review 代替阶段自检。';
    container.appendChild(alertDiv2);
  }} else if (!visionAvailable) {{
    var alertDiv3 = document.createElement('div');
    alertDiv3.className = 'global-alert warning';
    alertDiv3.textContent = '内部视觉闭环未完成：当前页面仅用于调试。请用当前冻结任务恢复 SVG 阶段渲染，或应用有来源的外部视觉反馈。原因：' + (visionUnavailableReason || '未提供');
    container.appendChild(alertDiv3);
  }}

  pages.forEach(function(p, idx) {{
    var pageKey = p.page_key || ('page_' + String(idx+1).padStart(2,'0'));
    var v = (validation||{{}})[pageKey]||{{}};
    var s = (selfReview||{{}})[pageKey]||{{}};
    var vers = (versions||{{}})[pageKey]||[];

    var vStatus = v.status||'unknown';
    var srStatus = s.visual_status||s.status||(s.png_reviewed && !(s.unresolved_visual_warnings||[]).length ? 'pass' : 'not_reviewed');
    var hasDesignSuggestions = ((s||{{}}).suggestions||[]).length > 0;
    var hasRequiredFixes = ((s||{{}}).required_fixes||[]).length > 0;
    var borderClass = (vStatus === 'fail' || hasRequiredFixes || srStatus === 'blocked') ? 'fail' : (hasDesignSuggestions ? 'warning' : 'pass');

    var card = document.createElement('div');
    card.id = 'page-' + pageKey;
    card.className = 'page-review ' + borderClass + (idx===0 ? ' active' : '');
    card.dataset.pageIndex=idx;

    if (nav) {{
      var link = document.createElement('a');
      link.className = 'nav-item'+(borderClass==='fail'?' machine-fail':'');
      link.href = '#page-' + pageKey;
      link.dataset.pageIndex=idx;
      var thumb=p.png_path?'<img class="nav-thumb" src="'+assetUrl(p.png_path)+'" alt="">':'<span class="nav-thumb"></span>';
      link.title = String(idx+1).padStart(2,'0')+' · '+(p.page_title||pageKey);
      link.innerHTML = thumb+'<span class="nav-copy">'+String(idx+1).padStart(2,'0')+'</span><span class="nav-state"></span>';
      link.addEventListener('click',function(event){{event.preventDefault();setActivePage(idx);}});
      nav.appendChild(link);
    }}

    var html = '<div class="page-head"><h2>第'+(idx+1)+'页: '+escapeHtml(p.page_title||pageKey)+'</h2>';
    html += '<span class="page-meta">'+escapeHtml(pageKey);

    // Layout info from layout plan if available
    if (p.layout_id) html += ' | ' + escapeHtml(p.layout_id);
    if (p.page_mode) html += ' | ' + escapeHtml(modeLabel(p.page_mode));
    if (p.visual_density) html += ' | ' + escapeHtml(densityLabel(p.visual_density));
    html += '</span></div>';
    html += '<div class="page-body"><div class="review-grid">';

    // Preview first
    html += '<section class="preview-panel">';
    var pngPath = p.png_path;
    if (!pngPath) {{
      html += '<div class="missing-file">PNG 预览路径未在 page_manifest.json 中设置</div>';
    }} else {{
      if (vers.length >= 2) {{
        var latest = vers[vers.length-1];
        var prev = vers[vers.length-2];
        var versionBase = '_internal/05_review/versions/' + pageKey + '/';
        html += '<div class="section-label">版本对比</div><div class="grid-2col">';
        html += '<div class="preview-box"><div class="vlabel">v'+prev.version+' ('+prev.created_at+')</div><img src="'+assetUrl(versionBase+prev.png)+'" alt="v'+prev.version+'"></div>';
        html += '<div class="preview-box"><div class="vlabel">v'+latest.version+' ('+latest.created_at+') — 当前版本</div><div class="annotation-stage"><img src="'+assetUrl(versionBase+latest.png)+'" alt="v'+latest.version+'"><div class="annotation-layer" data-annotation-layer="'+idx+'"></div></div></div>';
        html += '</div>';
      }} else {{
        html += '<div class="section-label">预览</div><div class="preview-row"><div class="preview-box"><div class="annotation-stage"><img src="'+assetUrl(pngPath)+'" alt="页面预览"><div class="annotation-layer" data-annotation-layer="'+idx+'"></div></div></div></div>';
      }}
    }}
    html += '</section><section class="qa-panel">';

    // Internal check status. Non-blocking validator warnings are intentionally
    // not exposed as user-facing actions; the model should synthesize them into
    // design suggestions only when the PNG confirms a real issue.
    html += '<div class="section-label">内部检查</div>';
    if (vStatus === 'unknown') {{
      html += '<div class="missing-file">内部检查结果未知 — validation_summary.json 中未找到此页</div>';
    }} else {{
      html += '<div class="val-summary">';
      var visibleStatus = vStatus === 'fail' ? '发现阻断项' : '已完成';
      html += '<span class="status-'+(vStatus === 'fail' ? 'fail' : 'pass')+'">状态: '+escapeHtml(visibleStatus)+'</span>';
      var es = (v.summary||{{}}).errors||0;
      if (es) html += ' | 阻断: '+es;
      html += '</div>';
      var issues = v.issues || [];
      var errIssues = issues.filter(function(i) {{ return i.severity === 'error'; }});
      if (errIssues.length) {{
        html += '<div class="required-fixes"><div class="rf-title">必须修复项</div><ul>';
        errIssues.forEach(function(i) {{ html += '<li>'+escapeHtml(i.message)+'</li>'; }});
        html += '</ul></div>';
      }}
    }}

    // Self-review status
    html += '<div class="section-label">模型自检</div>';
    if (!visionAvailable) {{
      html += '<div class="self-review-status human_review">内部视觉闭环未完成；此调试页面不能代替 SVG 阶段的视觉修复。原因：'+escapeHtml(visionUnavailableReason || '未提供')+'</div>';
    }} else if (srStatus === 'not_reviewed') {{
      html += '<div class="self-review-status" style="background:#F5F7FA;color:#999;border:1px solid #E0E0E0">自检状态: 未完成</div>';
    }} else {{
      html += '<details class="self-review-status '+srStatus+'"><summary>自检状态: ' + srStatus.toUpperCase();
      if (s.confidence != null) html += ' | 置信度: ' + (s.confidence*100).toFixed(0) + '%';
      html += '</summary><div class="self-review-body">';
      if (s.layout_feedback) html += '<div>版式: ' + escapeHtml(s.layout_feedback) + '</div>';
      if (s.copy_feedback) html += '<div>文案: ' + escapeHtml(s.copy_feedback) + '</div>';
      if (s.visual_feedback) html += '<div>视觉: ' + escapeHtml(s.visual_feedback) + '</div>';
      if ((s.observations||[]).length) {{
        html += '<div style="margin-top:8px"><strong>PNG 观察</strong><ul>';
        s.observations.forEach(function(item) {{ html += '<li>'+escapeHtml(item)+'</li>'; }});
        html += '</ul></div>';
      }}
      if ((s.accepted_warnings||[]).length) html += '<div style="margin-top:8px;color:#66717E">已结合 PNG 接受 '+s.accepted_warnings.length+' 项非阻断风险</div>';
      html += '</div></details>';
    }}

    // Required fixes (blocking — shown BEFORE feedback controls)
    var fixes = (s||{{}}).required_fixes||[];
    if (fixes.length) {{
      html += '<div class="required-fixes"><div class="rf-title">阻断性问题（必须在PPT转换前解决）</div>';
      html += '<div class="rf-subtitle">以下 hard errors 不解决，当前页面不能进入审阅</div><ul>';
      fixes.forEach(function(f) {{ html += '<li>'+escapeHtml(f)+'</li>'; }});
      html += '</ul></div>';
    }}

    // User-facing design suggestions from model self-review only.
    var suggestions = (s||{{}}).suggestions||[];
    var reviewActions = buildReviewActions(suggestions);
    html += '<div class="section-label">设计建议（勾选表示下一轮请修改）</div>';
    html += renderReviewActions(pageKey, idx, reviewActions);

    // Region feedback: draw on the current slide, then describe the issue.
    html += '<div class="region-feedback"><div class="region-feedback-head"><strong>区域反馈</strong><button class="region-btn" type="button" onclick="beginAnnotation('+idx+')">框选页面问题</button></div>';
    html += '<div class="region-hint">在左侧页面上拖出框，然后说明这个位置要改什么。坐标会一起交给修改任务。</div><div data-region-list="'+idx+'"></div></div>';

    // Free-text feedback
    html += '<div class="action-zone"><div class="section-label">您的反馈</div><div class="feedback-text">';
    html += '<textarea name="feedback_'+idx+'" placeholder="对此页的反馈意见..."></textarea></div>';

    // Approval has one action surface: the bottom dock. Keep only hidden state here.
    html += '<input type="checkbox" name="approve_'+idx+'" value="1" hidden>';
    html += '<div class="approval-status" data-approval-status="'+idx+'">本页尚未批准 · 请使用底部“批准当前页”</div>';
    html += '</div>';
    html += '</section></div></div>'; // qa-panel, review-grid, page-body
    html += renderRevisionNotes(pageKey);
    card.innerHTML = html;
    container.appendChild(card);
  }});
  document.querySelectorAll('[name^="feedback_"]').forEach(function(input){{input.addEventListener('input',function(){{markVisualPageChanged(Number(input.name.split('_')[1]));}});}});
  document.querySelectorAll('[name^="action_"]').forEach(function(input){{input.addEventListener('change',function(){{markVisualPageChanged(Number(input.name.split('_')[1]));}});}});
  bindAnnotationLayers();
  var requestedKey=String(location.hash||'').replace(/^#page-/,'');
  var requestedIndex=pages.findIndex(function(item,index){{return (item.page_key||('page_'+String(index+1).padStart(2,'0')))===requestedKey;}});
  setActivePage(requestedIndex>=0?requestedIndex:0);
}}

function annotationList(index) {{
  if (!Array.isArray(pageAnnotations[index])) pageAnnotations[index]=[];
  return pageAnnotations[index];
}}

function markVisualPageChanged(index) {{
  pageDecisions[index]='revise';
  var approve=document.getElementsByName('approve_'+index)[0];
  if(approve) approve.checked=false;
  var nav=document.querySelector('.nav-item[data-page-index="'+index+'"]');
  if(nav){{nav.classList.add('changed');nav.classList.remove('reviewed');}}
  updateApprovalStatus(index);
}}

function updateApprovalStatus(index){{
  var approve=document.getElementsByName('approve_'+index)[0],status=document.querySelector('[data-approval-status="'+index+'"]');
  if(!status) return;
  var decision=pageDecisions[index]||'unreviewed',approved=decision==='approved';
  status.classList.toggle('approved',approved);
  status.textContent=approved?'本页已批准':(decision==='revise'?'本页已标记修改 · 将进入下一轮修订':'本页尚未处理');
}}

function pageHasVisualRequests(index){{
  var feedback=(document.getElementsByName('feedback_'+index)[0]||{{}}).value||'';
  var actions=Array.from(document.getElementsByName('action_'+index)||[]).some(function(item){{return item.checked;}});
  return Boolean(feedback.trim()||actions||annotationList(index).length);
}}

function refreshVisualDecision(index){{
  if(pageHasVisualRequests(index))pageDecisions[index]='revise';
  var nav=document.querySelector('.nav-item[data-page-index="'+index+'"]');
  if(nav){{nav.classList.toggle('changed',pageDecisions[index]==='revise');nav.classList.toggle('reviewed',pageDecisions[index]==='approved');}}
  var approve=document.getElementsByName('approve_'+index)[0];if(approve)approve.checked=pageDecisions[index]==='approved';updateApprovalStatus(index);
}}

function renderAnnotations(index) {{
  var layer=document.querySelector('[data-annotation-layer="'+index+'"]');
  if(!layer) return;
  layer.innerHTML=annotationList(index).map(function(item,i){{
    return '<div class="annotation-rect" data-number="'+(i+1)+'" style="left:'+(item.x*100)+'%;top:'+(item.y*100)+'%;width:'+(item.w*100)+'%;height:'+(item.h*100)+'%"></div>';
  }}).join('');
}}

function renderRegionFeedback(index, focusLast) {{
  var host=document.querySelector('[data-region-list="'+index+'"]');
  if(!host) return;
  var items=annotationList(index);
  host.innerHTML=items.map(function(item,i){{
    var region='x '+Math.round(item.x*100)+'% · y '+Math.round(item.y*100)+'% · '+Math.round(item.w*100)+'×'+Math.round(item.h*100)+'%';
    return '<div class="region-item"><label>标注 '+(i+1)+' · '+region+'</label><textarea data-annotation-text="'+index+':'+i+'" placeholder="说明这个位置的问题和期望修改…">'+escapeHtml(item.text||'')+'</textarea><div class="region-item-actions"><button class="region-delete" type="button" data-annotation-delete="'+index+':'+i+'">删除这个标注</button></div></div>';
  }}).join('');
  host.querySelectorAll('[data-annotation-text]').forEach(function(field){{field.addEventListener('input',function(){{var bits=field.dataset.annotationText.split(':').map(Number);annotationList(bits[0])[bits[1]].text=field.value;markVisualPageChanged(bits[0]);}});}});
  host.querySelectorAll('[data-annotation-delete]').forEach(function(button){{button.addEventListener('click',function(){{var bits=button.dataset.annotationDelete.split(':').map(Number);annotationList(bits[0]).splice(bits[1],1);renderAnnotations(bits[0]);renderRegionFeedback(bits[0],false);markVisualPageChanged(bits[0]);}});}});
  if(focusLast){{var fields=host.querySelectorAll('textarea');var field=fields[fields.length-1];if(field){{field.focus();field.scrollIntoView({{block:'nearest'}});}}}}
}}

function beginAnnotation(index) {{
  setActivePage(index);
  document.querySelectorAll('.annotation-layer').forEach(function(layer){{layer.classList.remove('annotating');}});
  var layer=document.querySelector('[data-annotation-layer="'+index+'"]');
  if(!layer) return;
  annotationModeIndex=index;
  layer.classList.add('annotating');
  toast.textContent='在页面上拖出要反馈的范围';toast.className='toast show';
  setTimeout(function(){{toast.className='toast';}},2200);
}}

function bindAnnotationLayers() {{
  document.querySelectorAll('[data-annotation-layer]').forEach(function(layer){{
    var start=null,draft=null,index=Number(layer.dataset.annotationLayer);
    function point(event){{var rect=layer.getBoundingClientRect();return {{x:Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))}};}}
    layer.addEventListener('pointerdown',function(event){{if(annotationModeIndex!==index)return;event.preventDefault();layer.setPointerCapture(event.pointerId);start=point(event);draft=document.createElement('div');draft.className='annotation-rect';draft.dataset.number=String(annotationList(index).length+1);layer.appendChild(draft);}});
    layer.addEventListener('pointermove',function(event){{if(!start||!draft)return;var p=point(event),x=Math.min(start.x,p.x),y=Math.min(start.y,p.y),w=Math.abs(p.x-start.x),h=Math.abs(p.y-start.y);draft.style.left=(x*100)+'%';draft.style.top=(y*100)+'%';draft.style.width=(w*100)+'%';draft.style.height=(h*100)+'%';}});
    layer.addEventListener('pointerup',function(event){{if(!start)return;var p=point(event),item={{x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(p.x-start.x),h:Math.abs(p.y-start.y),text:''}};start=null;draft=null;layer.classList.remove('annotating');annotationModeIndex=null;if(item.w<.015||item.h<.015){{renderAnnotations(index);return;}}annotationList(index).push(item);renderAnnotations(index);renderRegionFeedback(index,true);markVisualPageChanged(index);}});
    renderAnnotations(index);renderRegionFeedback(index,false);
  }});
}}

function decisionCounts(){{var counts={{approved:0,revise:0,unreviewed:0}};pages.forEach(function(_,idx){{counts[pageDecisions[idx]||'unreviewed']+=1;}});return counts;}}
function toggleSheet(id,open){{var sheet=document.getElementById(id);if(sheet)sheet.classList.toggle('open',Boolean(open));}}
function openReviewSubmit(){{var c=decisionCounts(),host=document.getElementById('decisionSummary');if(host)host.innerHTML='<div><strong>'+c.approved+'</strong>已批准</div><div><strong>'+c.revise+'</strong>待修改</div><div><strong>'+c.unreviewed+'</strong>未处理</div>';toggleSheet('reviewSubmitSheet',true);}}

function submitFeedback(approveRemaining) {{
  if(approveRemaining)pages.forEach(function(_,idx){{if((pageDecisions[idx]||'unreviewed')==='unreviewed'&&!pageHasBlockingIssues((pages[idx]||{{}}).page_key||('page_'+String(idx+1).padStart(2,'0'))))pageDecisions[idx]='approved';refreshVisualDecision(idx);}});
  var counts=decisionCounts();if(counts.approved+counts.revise===0){{toast.textContent='还没有任何逐页决定，不能提交空审阅。';toast.className='toast show';setTimeout(function(){{toast.className='toast';}},4000);return;}}
  var payload = {{phase:'visual_review', pages:{{}}, global_feedback:'', all_approved: false}};
  payload.global_feedback = (document.getElementById('globalFeedback')||{{}}).value||'';
  pages.forEach(function(p, idx) {{
    var pageKey = p.page_key || ('page_' + String(idx+1).padStart(2,'0'));
    var selectedActions = [];
    var selectedSuggestionIndexes = [];
    var actionCbs = document.getElementsByName('action_'+idx);
    actionCbs.forEach(function(cb) {{
      if (!cb.checked) return;
      var ai = parseInt(cb.value);
      var action = (pageActionCache[pageKey] || [])[ai];
      if (action) {{
        selectedActions.push(action);
        if (action.source === 'self_review' && action.source_index != null) {{
          selectedSuggestionIndexes.push(action.source_index);
        }}
      }}
    }});
    var annotations=annotationList(idx).map(function(item){{return {{x:Number(item.x.toFixed(4)),y:Number(item.y.toFixed(4)),w:Number(item.w.toFixed(4)),h:Number(item.h.toFixed(4)),text:String(item.text||'').trim()}};}});
    var incompleteAnnotation=annotations.some(function(item){{return !item.text;}});
    payload.pages[pageKey] = {{
      approved: pageDecisions[idx]==='approved' && annotations.length===0,
      decision: pageDecisions[idx]||'unreviewed',
      selected_suggestions: selectedSuggestionIndexes,
      selected_review_actions: selectedActions,
      custom_feedback: (document.getElementsByName('feedback_'+idx)[0]||{{}}).value||'',
      annotations: annotations,
      annotation_incomplete: incompleteAnnotation
    }};
  }});
  payload.all_approved = Object.values(payload.pages).every(function(p) {{ return p.approved; }});
  for (var pk in payload.pages) {{
    if (!Object.prototype.hasOwnProperty.call(payload.pages, pk)) continue;
    var pagePayload = payload.pages[pk];
    if (pagePayload.annotation_incomplete) {{
      toast.textContent = pk + ' 有尚未说明的区域标注。';
      toast.className = 'toast show';
      setTimeout(function(){{ toast.className='toast'; }}, 5000);
      return;
    }}
    delete pagePayload.annotation_incomplete;
    if (pagePayload.approved && pageHasBlockingIssues(pk)) {{
      toast.textContent = pk + ' 仍有阻断项，不能批准。请先修复。';
      toast.className = 'toast show';
      setTimeout(function(){{ toast.className='toast'; }}, 5000);
      return;
    }}
    if (pagePayload.approved && pagePayload.selected_review_actions && pagePayload.selected_review_actions.length) {{
      toast.textContent = pk + ' 已勾选修改建议。请先提交反馈，或取消勾选后再批准。';
      toast.className = 'toast show';
      setTimeout(function(){{ toast.className='toast'; }}, 5000);
      return;
    }}
  }}
  postPayload(payload);
}}

function postPayload(payload) {{
  var toast = document.getElementById('toast');
  fetch('/review-feedback', {{
    method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)
  }}).then(function(r) {{
    toast.textContent = r.ok ? '反馈已提交。' : '提交失败。审阅服务器是否在运行？';
    toast.className = 'toast show';
    if (r.ok) {{toggleSheet('reviewSubmitSheet',false);document.getElementById('completion').classList.add('open');}}
    setTimeout(function(){{ toast.className='toast'; }}, 4000);
  }}).catch(function() {{
    toast.textContent = '无法连接服务器。请先启动 review_server.py。';
    toast.className = 'toast show';
    setTimeout(function(){{ toast.className='toast'; }}, 5000);
  }});
}}

renderPages();

function setActivePage(index) {{
  activePageIndex=Math.max(0,Math.min(pages.length-1,Number(index)||0));
  document.querySelectorAll('.page-review').forEach(function(card){{card.classList.toggle('active',Number(card.dataset.pageIndex)===activePageIndex);}});
  document.querySelectorAll('.nav-item').forEach(function(item){{item.classList.toggle('active',Number(item.dataset.pageIndex)===activePageIndex);}});
  var progress=document.getElementById('dockProgress');
  if(progress) progress.textContent=String(activePageIndex+1).padStart(2,'0')+' / '+String(pages.length).padStart(2,'0');
  var activeNav=document.querySelector('.nav-item.active');if(activeNav) activeNav.scrollIntoView({{block:'nearest'}});
  var page=pages[activePageIndex]||{{}};var key=page.page_key||('page_'+String(activePageIndex+1).padStart(2,'0'));history.replaceState(null,'','#page-'+key);
  document.getElementById('prevPage').disabled=activePageIndex===0;
  document.getElementById('nextPage').disabled=activePageIndex===pages.length-1;
}}

function approveCurrentAndNext(){{
  var page=pages[activePageIndex]||{{}}, key=page.page_key||('page_'+String(activePageIndex+1).padStart(2,'0'));
  if(pageHasBlockingIssues(key)){{toast.textContent='当前页仍有阻断项，不能批准。';toast.className='toast show';setTimeout(function(){{toast.className='toast';}},3500);return;}}
  if(annotationList(activePageIndex).length){{toast.textContent='当前页已有区域反馈，请作为修改意见提交。';toast.className='toast show';setTimeout(function(){{toast.className='toast';}},3500);return;}}
  var actions=document.getElementsByName('action_'+activePageIndex);var selected=Array.from(actions).some(function(item){{return item.checked;}});
  if(selected){{toast.textContent='当前页已勾选修改建议，请取消勾选或作为修改意见提交。';toast.className='toast show';setTimeout(function(){{toast.className='toast';}},3500);return;}}
  pageDecisions[activePageIndex]='approved';refreshVisualDecision(activePageIndex);
  if(activePageIndex<pages.length-1) setActivePage(activePageIndex+1);
}}

function reviseCurrent(){{
  pageDecisions[activePageIndex]='revise';refreshVisualDecision(activePageIndex);
  beginAnnotation(activePageIndex);
}}
document.getElementById('prevPage').onclick=function(){{setActivePage(activePageIndex-1);}};
document.getElementById('nextPage').onclick=function(){{setActivePage(activePageIndex+1);}};
document.getElementById('copyCompleted').onclick=async function(){{try{{await navigator.clipboard.writeText('已完成');this.textContent='已复制';}}catch(error){{window.prompt('复制下面文字并发送给 Codex','已完成');}}}};
document.getElementById('closeCompletion').onclick=function(){{document.getElementById('completion').classList.remove('open');}};
document.addEventListener('keydown',function(event){{if(/textarea|input|select/i.test((event.target||{{}}).tagName||'')) return;if(event.key==='ArrowLeft') setActivePage(activePageIndex-1);if(event.key==='ArrowRight') setActivePage(activePageIndex+1);}});
</script>
</body>
</html>"""


def load_json(path):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None
    return None


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def to_url_path(path):
    if not path:
        return ""
    return "/" + str(path).lstrip("/")


def get_batch_pages(manifest, batch_id):
    batch_config = manifest.get("batch_config", {})
    if not isinstance(batch_config, dict):
        fail("page_manifest.json batch_config must be an object")
    if batch_id not in batch_config:
        fail(f"batch '{batch_id}' not found in page_manifest.json")

    batch = batch_config.get(batch_id)
    if not isinstance(batch, dict):
        fail(
            f"page_manifest.json batch_config.{batch_id} must be an object with "
            "'status' and 'pages'. List-style batches are not supported."
        )

    pages = batch.get("pages")
    if not isinstance(pages, list) or not pages:
        fail(f"page_manifest.json batch_config.{batch_id}.pages must be a non-empty list")
    return pages


def report_page_key(report, page_keys):
    filename = Path(report.get("file", "")).stem
    for pk in page_keys:
        if filename == pk or filename.startswith(pk):
            return pk
    return ""


def report_has_error(report):
    if report.get("status") == "fail":
        return True
    summary = report.get("summary", {})
    if isinstance(summary, dict) and summary.get("errors", 0):
        return True
    for issue in report.get("issues", []):
        if isinstance(issue, dict) and issue.get("severity") == "error":
            return True
    return False


def report_has_blocking_warning(report):
    return bool(blocking_warning_issues({"reports": [report]}))


def main():
    parser = argparse.ArgumentParser(
        description="Generate 02_visual_review.html from page_manifest, validation, and self-review data."
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--all", action="store_true", help="Render the complete deck in one review page (default)")
    parser.add_argument("--output", default="", help="Output HTML path (default: project root)")
    parser.add_argument("--allow-missing-validation", action="store_true",
                        help="Generate HTML even if validation_summary.json is missing (for debugging)")
    parser.add_argument("--debug-show-failures", action="store_true",
                        help="Generate HTML even when validation reports contain FAIL pages. Internal debugging only.")
    args = parser.parse_args()

    root = Path(args.project_dir)
    internal = root / "_internal"

    # Load manifest (the single source of truth for page ordering)
    manifest_data = load_json(internal / "00_project" / "page_manifest.json")
    if not manifest_data:
        fail("page_manifest.json not found or invalid")
    validation_data = load_json(internal / "04_validation" / "validation_summary.json")
    self_review_data = load_json(internal / "04_validation" / "self_review.json") or {}
    revision_notes_data = load_json(internal / "05_review" / "revision_notes.json") or {}

    has_validation = validation_data is not None
    has_self_review = bool(self_review_data)
    vision_available = self_review_data.get("vision_available", False) if has_self_review else False
    batch_ids = [bid for bid, batch in sorted(manifest_data.get("batch_config", {}).items()) if isinstance(batch, dict) and batch.get("pages")]
    batch_page_keys = [pk for bid in batch_ids for pk in get_batch_pages(manifest_data, bid)]
    if not batch_page_keys:
        fail("No pages are available for full-deck review")

    visual_status = self_review_data.get("visual_review_status") if has_self_review else None
    review_mode = self_review_data.get("review_mode", "") if has_self_review else ""
    pages_review = self_review_data.get("pages", {}) if has_self_review else {}
    external_source = str(self_review_data.get("external_feedback_source", "")).strip() if has_self_review else ""
    status_complete = visual_status in (None, "completed")
    page_evidence_complete = isinstance(pages_review, dict) and all(
        isinstance(pages_review.get(pk), dict)
        and not pages_review[pk].get("must_fix")
        and (
            (vision_available and pages_review[pk].get("png_reviewed") is True)
            or (
                not vision_available
                and review_mode in ("external_feedback", "mixed")
                and bool(external_source)
                and (pages_review[pk].get("external_feedback_applied") is True or pages_review[pk].get("png_reviewed") is True)
            )
        )
        for pk in batch_page_keys
    )
    visual_review_complete = bool(has_self_review and status_complete and page_evidence_complete)
    if not visual_review_complete and not args.allow_missing_validation:
        fail(
            "Visual closure is incomplete. Resume the SVG stage from the current frozen task to recover rendering, "
            "apply visual fixes, rerun validator/render, and clear must_fix. "
            "Use --allow-missing-validation only for internal debugging."
        )

    # Validation is REQUIRED
    if not has_validation and not args.allow_missing_validation:
        print("ERROR: validation_summary.json not found at _internal/04_validation/validation_summary.json", file=sys.stderr)
        print("Run validate_svg_layout.py first, or use --allow-missing-validation for debugging.", file=sys.stderr)
        sys.exit(1)

    # Build page list from manifest
    manifest_pages = manifest_data.get("pages", [])
    if not manifest_pages:
        fail("page_manifest.json has no pages.")

    manifest_by_key = {
        p.get("page_key"): p
        for p in manifest_pages
        if isinstance(p, dict) and p.get("page_key")
    }
    page_batch_map = {
        pk: bid for bid in batch_ids for pk in get_batch_pages(manifest_data, bid)
    }
    unknown_batch_pages = [pk for pk in batch_page_keys if pk not in manifest_by_key]
    if unknown_batch_pages:
        fail(f"Manifest batches reference page(s) not present in manifest pages: {unknown_batch_pages}")

    layout_data = load_json(internal / "01_layout_plan" / "layout_plan.json") or {}
    layout_by_key = {
        p.get("page_key"): p
        for p in layout_data.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }
    content_data = load_json(internal / "01_content" / "page_content.json") or {}
    content_by_key = {
        p.get("page_key"): p
        for p in content_data.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }

    pages = []
    missing_pngs = []
    for pk in batch_page_keys:
        p = manifest_by_key[pk]
        layout = layout_by_key.get(pk, {})
        content = content_by_key.get(pk, {})

        entry = {
            "page_key": pk,
            "page_title": content.get("action_title") or layout.get("page_title") or pk,
            "svg_path": to_url_path(p.get("svg_path", "")),
            "png_path": to_url_path(p.get("png_path", "")),
            "layout_id": layout.get("layout_id", ""),
            "page_mode": layout.get("page_mode", ""),
            "visual_density": layout.get("visual_density", ""),
        }

        # Check PNG path
        png_path = p.get("png_path", "")
        if not png_path:
            missing_pngs.append(f"{pk}: png_path not set in manifest")
        elif not (root / png_path).exists():
            missing_pngs.append(f"{pk}: PNG not found at {png_path}")

        pages.append(entry)

    if missing_pngs and not args.allow_missing_validation:
        print("ERROR: Missing PNG files:\n  " + "\n  ".join(missing_pngs), file=sys.stderr)
        print("Run render_svg_png.py first.", file=sys.stderr)
        sys.exit(1)

    # Build validation lookup by page_key from reports
    val_lookup = {}
    missing_validation_pages = []
    if has_validation:
        reports = validation_data.get("reports", [])
        for r in reports:
            pk = report_page_key(r, batch_page_keys)
            if pk:
                val_lookup[pk] = r
        missing_validation_pages = [pk for pk in batch_page_keys if pk not in val_lookup]

    if missing_validation_pages and not args.allow_missing_validation:
        fail("Missing validation report for page(s): " + ", ".join(missing_validation_pages))

    failed_validation_pages = [
        f"{pk}: {val_lookup[pk].get('summary', {}).get('errors', '?')} error(s)"
        for pk in batch_page_keys
        if pk in val_lookup and report_has_error(val_lookup[pk])
    ]
    if failed_validation_pages and not args.debug_show_failures:
        fail(
            "Validation failed for batch pages; fix SVG and rerun static validation "
            "before generating user review HTML. Failed page(s): "
            + "; ".join(failed_validation_pages)
            + ". Use --debug-show-failures only for internal QA."
        )

    blocking_warning_pages = [
        pk for pk in batch_page_keys
        if pk in val_lookup and report_has_blocking_warning(val_lookup[pk])
    ]
    if blocking_warning_pages and not args.debug_show_failures:
        fail(
            "Validation has blocking warning(s); fix SVG and rerun static validation "
            "before generating user review HTML. Blocked page(s): "
            + ", ".join(blocking_warning_pages)
            + ". Use --debug-show-failures only for internal QA."
        )

    # Build self-review lookup
    sr_lookup = self_review_data.get("pages", {}) if has_self_review else {}
    missing_self_review = [pk for pk in batch_page_keys if pk not in sr_lookup]
    if missing_self_review and not args.allow_missing_validation:
        fail("Missing self_review entry for page(s): " + ", ".join(missing_self_review))

    # Build versions index
    versions_dir = internal / "05_review" / "versions"
    versions_index = {}
    if versions_dir.exists():
        for page_dir in sorted(versions_dir.iterdir()):
            if page_dir.is_dir():
                history_path = page_dir / "history.json"
                if history_path.exists():
                    try:
                        versions_index[page_dir.name] = json.loads(history_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass

    # Compute user-facing counts. Validator warnings are internal; the header
    # shows page count, design-suggestion count, and hard blockers only.
    count_pass = len(batch_page_keys)
    count_warn = sum(
        len((sr_lookup.get(pk, {}) or {}).get("suggestions", []) or [])
        for pk in batch_page_keys
    )
    count_fail = sum(1 for v in val_lookup.values() if v.get("status") == "fail")
    count_fail += sum(
        1
        for pk in batch_page_keys
        if (sr_lookup.get(pk, {}) or {}).get("visual_status") == "blocked"
        or (sr_lookup.get(pk, {}) or {}).get("required_fixes")
    )

    # Global alerts
    global_alerts = ""
    if not has_validation:
        global_alerts = '<div class="global-alert error">validation_summary.json 缺失 — 所有页面校验结果未知。请先运行 validate_svg_layout.py。</div>'
    if not has_self_review:
        global_alerts += '<div class="global-alert warning">self_review.json 缺失 — 内部视觉闭环未完成，请用当前冻结任务恢复 SVG 阶段。</div>'
    elif not vision_available:
        reason = str(self_review_data.get("vision_unavailable_reason", "") or "未提供")
        if visual_review_complete:
            global_alerts += '<div class="global-alert warning">内部视觉闭环已通过有来源的外部反馈完成；用户 Review 仍只负责批准。来源：' + external_source.replace("&", "&amp;").replace("<", "&lt;") + '</div>'
        else:
            global_alerts += '<div class="global-alert warning">内部视觉闭环未完成；当前仅为调试输出。原因：' + reason.replace("&", "&amp;").replace("<", "&lt;") + '</div>'

    project = manifest_data.get("project", root.name) if manifest_data else root.name
    html = HTML_TEMPLATE.format(
        project=str(project).replace("&", "&amp;").replace("<", "&lt;"),
        batch_label="全套页面",
        batch_id="all",
        page_batch_json=json.dumps(page_batch_map, ensure_ascii=False),
        count_pass=count_pass,
        count_warn=count_warn,
        count_fail=count_fail,
        page_count=len(pages),
        pages_json=json.dumps(pages, ensure_ascii=False),
        validation_json=json.dumps(val_lookup, ensure_ascii=False),
        self_review_json=json.dumps(sr_lookup, ensure_ascii=False),
        versions_json=json.dumps(versions_index, ensure_ascii=False),
        revision_notes_json=json.dumps(revision_notes_data, ensure_ascii=False),
        has_self_review="true" if has_self_review else "false",
        vision_available="true" if visual_review_complete else "false",
        vision_unavailable_reason_json=json.dumps(self_review_data.get("vision_unavailable_reason", ""), ensure_ascii=False),
        has_validation="true" if has_validation else "false",
        global_alerts=global_alerts,
    )

    output_path = Path(args.output) if args.output else root / "02_visual_review.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Generated {output_path} ({len(pages)} pages)")

    # Report issues found
    if not has_validation:
        print("WARNING: Generated without validation data.", file=sys.stderr)
    if missing_pngs:
        print(f"WARNING: {len(missing_pngs)} missing PNG(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
