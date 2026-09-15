#!/usr/bin/env python3
"""v5: material → lightweight content → create/check → human review → export."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_state import *
SCRIPTS=Path(__file__).resolve().parents[1]

def run(*args, env=None):
    p=subprocess.run([sys.executable,*map(str,args)],capture_output=True,text=True,env=env)
    if p.returncode: raise ValueError(p.stderr.strip() or p.stdout.strip() or 'Command failed')
    return p.stdout

def check(root, keys):
    m=sync(root); pages=content(root)['pages']; selected=keys or [p['page_key'] for p in pages]
    if set(selected)-{p['page_key'] for p in pages}: raise ValueError('Unknown page key')
    results=[]
    for p in pages:
        k=p['page_key']
        if k not in selected: continue
        try:
            v=page_version(root,p)
            if rendered(root,k,v):
                rec=read(root/VALIDATION/(k+'.json'),{})
                results.append({'page':k,'status':'unchanged','render_token':digest(rec),
                                'issues':rec.get('validator',{})}); continue
            svg=root/SVG/(k+'.svg'); report=root/VALIDATION/(k+'-validator.json')
            argv=[sys.executable,str(SCRIPTS/'validate_svg_layout.py'),str(svg.parent),'--file',str(svg),
                  '--output',str(report),'--page-mode',p.get('mode') or '读']
            if m.get('template_intake',{}).get('mode')=='fidelity': argv+=['--fidelity-template',str(root/PROJECT/'fidelity_template/template_registry.json')]
            val=subprocess.run(argv,capture_output=True,text=True)
            data=read(report,{})
            # Render even when the initial validator reports issues: fix one combined list.
            from render_svg_png import PLAYWRIGHT_SNIPPET
            png=root/PNG/(k+'.png')
            old=read(root/VALIDATION/(k+'.json'),{})
            if png.exists() and old.get('version'):
                oldpath=root/REVIEW/'versions'/f'{k}-{old["version"]}.png'
                oldpath.parent.mkdir(parents=True,exist_ok=True)
                import shutil
                shutil.copy2(png,oldpath)
            run('-c',PLAYWRIGHT_SNIPPET,root/PNG,svg)
            if page_version(root,p)!=v: raise ValueError('Page changed during rendering; rerun check')
            rec={'version':v,'errors':data.get('summary',{}).get('errors',1) if not val.returncode else max(1,data.get('summary',{}).get('errors',1)),
                'png_sha256':sha(png),'validator':data}
            write(root/VALIDATION/(k+'.json'),rec)
            results.append({'page':k,'status':'pass' if rec['errors']==0 else 'fix','render_token':digest(rec),'png':str(png),'issues':data})
        except (ValueError,OSError,ET.ParseError) as e: results.append({'page':k,'status':'blocked','error':str(e)})
    # Read-only measurements for the model's own design self-check. Facts, never pass/fail.
    obs=design_observations_deck(root,[r['page'] for r in results if r.get('page')])
    for r in results:
        if r.get('page') in obs: r['design']=obs[r['page']]
    from render_svg_png import make_contact_sheet
    files=[root/PNG/(p['page_key']+'.png') for p in pages if (root/PNG/(p['page_key']+'.png')).exists()]
    if files: make_contact_sheet(files,root/'_internal/03_png_preview/full_deck_contact_sheet.png')
    event(root,'check',pages=selected)
    return results

def inspect(root,k,token,note,first_glance,design_check,must_fix):
    ps={p['page_key']:p for p in content(root)['pages']}
    if k not in ps: raise ValueError('Unknown page')
    rec=read(root/VALIDATION/(k+'.json'),{})
    if digest(rec)!=token or not rendered(root,k,page_version(root,ps[k])): raise ValueError('Stale render token: rerun check and inspect the current PNG')
    if not note.strip(): raise ValueError('Record concrete visual findings after viewing PNG')
    if not first_glance.strip(): raise ValueError('Name the one element the eye lands on first (--first-glance)')
    if not design_check.strip(): raise ValueError('State which design rules you checked against and any violation found (--design-check)')
    records=read(root/VALIDATION/'inspections.json',{})
    records[k]={'render_token':token,'note':note,'first_glance':first_glance,
                'design_check':design_check,'must_fix':must_fix}
    write(root/VALIDATION/'inspections.json',records)
    return {'page':k,'inspected':not must_fix}

def resolve(root,feedback_id,note):
    f=read(root/REVIEW/'feedback.json',{})
    pending=f.get('items',[]); item=next((i for i in pending if i['id']==feedback_id),None)
    if not item or not note.strip(): raise ValueError('Known feedback ID and concrete resolution note required')
    current=versions(root)
    affected=item.get('pages',list(current))
    if all(current.get(k)==f.get('pages',{}).get(k,{}).get('version') for k in affected):
        raise ValueError('Feedback resolution requires a changed artifact; clarify with user if no change is appropriate')
    resolutions=read(root/REVIEW/'resolutions.json',{})
    resolutions[feedback_id]={'note':note,'versions':{k:current.get(k) for k in affected}}
    write(root/REVIEW/'resolutions.json',resolutions)
    return {'resolved':feedback_id}

def unresolved(root):
    f=read(root/REVIEW/'feedback.json',{}); resolutions=read(root/REVIEW/'resolutions.json',{})
    return [i for i in f.get('items',[]) if i['id'] not in resolutions]

def make_review(root):
    sync(root); v=versions(root)
    bad=[k for k,x in v.items() if not inspected(root,k,x)]
    if bad: raise ValueError('View and inspect current PNGs after check: '+', '.join(bad))
    if unresolved(root): raise ValueError('Resolve every submitted feedback item: '+json.dumps(unresolved(root),ensure_ascii=False))
    if review_current(root): return review_snapshot(root)
    from generate_review_html import generate
    return generate(root)

def server(root, route='review'):
    meta=read(root/PROJECT/'review_server.json',{})
    def healthy(meta):
        try:
            with urllib.request.urlopen(meta['health_url'],timeout=2) as r: d=json.load(r)
            return d.get('project_dir')==str(root) and d.get('session_id')==meta.get('session_id')
        except (OSError,KeyError,ValueError): return False
    if not healthy(meta):
        log=root/PROJECT/'review_server.log'
        with log.open('a') as f:
            subprocess.Popen([sys.executable,str(SCRIPTS/'review_server.py'),str(root)],stdout=f,stderr=f,start_new_session=True)
        for _ in range(30):
            time.sleep(.1); meta=read(root/PROJECT/'review_server.json',{})
            if healthy(meta): break
        else: raise ValueError('Review server failed: '+str(log))
    url=f'http://127.0.0.1:{meta["port"]}/{route}'
    if not webbrowser.open(url): raise ValueError('Could not open review in browser: '+url)
    return {'url':url,'status':'awaiting_user'}

def export(root):
    # 导出不再要求"整套人工审阅已批准"。审阅仍是一个正常步骤，但它不再是导出的前置门：
    # 强制人类点到最后一页才允许导出，拦不住也救不了——没审完就导出，人还是会回来改。
    # 真正该保证的是导出质量（描边、越界、图片），那由转换器与 exporter 回归测试负责。
    sync(root)
    v=versions(root); target=root/'final_deck.pptx'; old=read(root/PROJECT/'export.json',{})
    if target.exists() and old.get('versions')==v and old.get('pptx_sha256')==sha(target): return old
    c=content(root); notes={p['page_key']+'.svg':p.get('notes','') for p in c['pages']}
    write(root/PROJECT/'speaker_notes.json',notes)
    env=dict(os.environ,SMART_SVG_EXPORT_APPROVED_BY_PIPELINE='1')
    run(SCRIPTS/'native_svg_to_ppt.py',*[root/SVG/(k+'.svg') for k in v],'-o',target,'--auto-size','--match-aspect','--strict-missing-images','--notes',root/PROJECT/'speaker_notes.json','--report',root/VALIDATION/'conversion.json',env=env)
    from pptx import Presentation
    prs=Presentation(target)
    if len(prs.slides)!=len(v): raise ValueError('Export page count differs')
    rec={'versions':v,'pptx_sha256':sha(target),'page_count':len(v),'visual_verification':'pending'}
    write(root/PROJECT/'export.json',rec); event(root,'export',**rec)
    return rec

def export_inspect(root,note,preview):
    rec=read(root/PROJECT/'export.json',{})
    if rec.get('versions')!=versions(root) or rec.get('pptx_sha256')!=sha(root/'final_deck.pptx'): raise ValueError('Export evidence is stale')
    if not note.strip() or not preview: raise ValueError('Provide actual PPTX-rendered preview files and visual findings')
    files=[local(root,p) for p in preview]
    if len(files)!=len(rec['versions']) or len(set(files))!=len(files): raise ValueError('Provide one distinct PPTX-rendered PNG/JPEG per slide')
    from PIL import Image
    for image in files:
        if image.suffix.lower() not in {'.png','.jpg','.jpeg'}: raise ValueError('Use actual raster PPTX previews')
        with Image.open(image) as im: im.verify()
    rec.update(visual_verification='inspected',note=note,preview_hashes={str(p.relative_to(root)):sha(p) for p in files})
    write(root/PROJECT/'export.json',rec)
    return rec

def next_action(root):
    manifest(root)
    try: m=sync(root)
    except ValueError as e: return {'state':'CONTENT','instruction':str(e),'stage':str(SCRIPTS.parent/'references/workflow/02_content_stage.md')}
    if unresolved(root): return {'state':'CREATE','feedback':unresolved(root),'instruction':'Implement feedback in the same creation stage, then record resolutions.'}
    try: v=versions(root)
    except (ValueError,OSError,ET.ParseError) as e: return {'state':'CREATE','instruction':str(e),'stage':str(SCRIPTS.parent/'references/workflow/04_svg_stage.md')}
    pending=[k for k,x in v.items() if not inspected(root,k,x)]
    if pending:return {'state':'CREATE','pages':pending,'instruction':'Create or revise, run check, view PNGs, and inspect using returned render tokens.'}
    if not approved(root): return {'state':'VISUAL_REVIEW','instruction':'Run review; user submits the whole deck in the browser.'}
    out=read(root/PROJECT/'export.json',{})
    if out.get('versions')!=v or not (root/'final_deck.pptx').is_file() or out.get('pptx_sha256')!=sha(root/'final_deck.pptx'): return {'state':'EXPORT','instruction':'Run export, then inspect the rendered PPTX.'}
    if out.get('visual_verification')!='inspected' or len(out.get('preview_hashes',{}))!=len(v) or any(not local(root,p).is_file() or sha(local(root,p))!=h for p,h in out.get('preview_hashes',{}).items()): return {'state':'EXPORT_VERIFY','instruction':'Render final PPTX, inspect all pages, then export-inspect. Report unavailable rendering explicitly; do not mark complete.'}
    return {'state':'COMPLETE','pptx':str(root/'final_deck.pptx')}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project_dir');sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('next').add_argument('--json',action='store_true')
    c=sub.add_parser('check');c.add_argument('--pages',nargs='+')
    c=sub.add_parser('inspect');c.add_argument('--page',required=True);c.add_argument('--render-token',required=True);c.add_argument('--note',required=True);c.add_argument('--first-glance',required=True);c.add_argument('--design-check',required=True);c.add_argument('--must-fix',action='store_true')
    c=sub.add_parser('resolve');c.add_argument('--feedback-id',required=True);c.add_argument('--note',required=True)
    sub.add_parser('review');sub.add_parser('export');sub.add_parser('template-review')
    c=sub.add_parser('export-inspect');c.add_argument('--note',required=True);c.add_argument('--previews',nargs='+',required=True)
    c=sub.add_parser('template');c.add_argument('--mode',choices=['autonomous','reference','fidelity'],required=True);c.add_argument('--template-id');c.add_argument('--reference')
    a=p.parse_args();root=Path(a.project_dir).expanduser().resolve()
    try:
        if a.command=='next':result=next_action(root)
        elif a.command=='check':result=check(root,a.pages)
        elif a.command=='inspect':result=inspect(root,a.page,a.render_token,a.note,a.first_glance,a.design_check,a.must_fix)
        elif a.command=='resolve':result=resolve(root,a.feedback_id,a.note)
        elif a.command=='review':make_review(root);result=server(root)
        elif a.command=='export':result=export(root)
        elif a.command=='export-inspect':result=export_inspect(root,a.note,a.previews)
        elif a.command=='template-review':run(SCRIPTS/'generate_template_review_html.py',root);result=server(root,'template')
        elif a.command=='template':
            m=manifest(root)
            if a.template_id:
                if a.mode!='fidelity':raise ValueError('Library templates require fidelity mode')
                run(SCRIPTS/'template/template_library.py','apply',root,'--template-id',a.template_id)
            if a.mode=='reference':
                if not a.reference:raise ValueError('Reference mode needs --reference <pptx|pdf|image|dir> so the reference pages are actually rendered before design_direction.md is written')
                run(SCRIPTS/'template/prepare_visual_references.py',a.reference,'--project',root)
            m['template_intake']={'mode':a.mode,'template_id':a.template_id};write(root/PROJECT/'page_manifest.json',m);result=m['template_intake']
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if a.command=='check' and any(x['status'] in {'blocked','fix'} for x in result):raise SystemExit(1)
    except (ValueError,OSError,ET.ParseError) as e:print(json.dumps({'error':str(e)},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
