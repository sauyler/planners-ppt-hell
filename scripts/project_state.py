"""Mechanical project state: content, assets, render evidence and versioned review."""
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

PROJECT = '_internal/00_project'
CONTENT = '_internal/01_content/page_content.json'
REVIEW = '_internal/05_review'
VALIDATION = '_internal/04_validation'
SVG = '_internal/02_svg_source'
PNG = '_internal/03_png_preview/pages'

def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

def write(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def local(root, rel):
    root = Path(root).resolve(); p = (root / rel).resolve()
    if p == root or root not in p.parents: raise ValueError('path outside project: '+str(rel))
    return p

def event(root, kind, **details):
    p = root / PROJECT / 'flow_events.jsonl'
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'type':kind,'details':details},ensure_ascii=False)+'\n')

def manifest(root):
    m = read(root / PROJECT / 'page_manifest.json', {})
    if m.get('version') != '5.0':
        raise ValueError('This project uses an older workflow. Finish with the archived Skill or migrate into a new v5 project; no in-place resume.')
    return m

def content(root):
    data = read(root / CONTENT, {})
    pages = data.get('pages', [])
    if not isinstance(pages, list) or not pages: raise ValueError('Write the lightweight page_content.json first.')
    seen = set(); used = set()
    source = read(root / PROJECT / 'source/source_assets.json', {})
    available = {a['asset_id'] for a in source.get('assets', [])}
    for p in pages:
        k = p.get('page_key', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', k) or k in seen: raise ValueError('Each page needs a unique stable page_key: '+k)
        seen.add(k)
        if not str(p.get('title','')).strip() or not str(p.get('content','')).strip(): raise ValueError(k+': title and content required')
        mode = p.get('mode')
        if mode is not None and mode not in ('讲','读'): raise ValueError(k+': mode must be 讲 or 读')
        refs = p.get('source_assets', [])
        if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs): raise ValueError(k+': source_assets must contain asset IDs')
        used.update(refs)
    excluded = data.get('unused_assets', {})
    if not isinstance(excluded,dict) or any(not str(v).strip() for v in excluded.values()): raise ValueError('unused_assets maps asset ID to a reason')
    if used - available or set(excluded)-available: raise ValueError('unknown source asset IDs')
    if available - used - set(excluded): raise ValueError('Source assets not accounted for: '+', '.join(sorted(available-used-set(excluded))))
    return data

def sync(root):
    m = manifest(root); c = content(root)
    m['project'] = c.get('project','')
    m['pages'] = [{'page_key':p['page_key'],'title':p['title'],'mode':p.get('mode') or '读','svg_path':f'{SVG}/{p["page_key"]}.svg','png_path':f'{PNG}/{p["page_key"]}.png'} for p in c['pages']]
    write(root / PROJECT / 'page_manifest.json',m)
    return m

def images(root, svg):
    root=Path(root).resolve()
    result=[]
    for i,node in enumerate(ET.parse(svg).getroot().iter()):
        if node.tag.split('}')[-1] != 'image': continue
        href = node.get('href',node.get('{http://www.w3.org/1999/xlink}href',''))
        if not href or href.startswith(('data:','http:','https:','#')): raise ValueError('Use local project image files: '+href[:60])
        p = local(root, str((Path(svg).parent / href).resolve()))
        if not p.is_file(): raise ValueError('Missing image: '+str(p))
        if node.get('preserveAspectRatio') == 'none': raise ValueError('Image stretching is prohibited')
        key = node.get('data-asset-key') or node.get('id') or f'image_{i}'
        result.append({'asset_key':key,'path':p.relative_to(root).as_posix(),'sha256':sha(p),'width':float(node.get('width',1)),'height':float(node.get('height',1)), 'fit':'cover' if 'slice' in node.get('preserveAspectRatio','') else 'contain'})
    if len({x['asset_key'] for x in result}) != len(result): raise ValueError('Duplicate image asset key')
    return result

def page_version(root, p):
    svg = root / SVG / (p['page_key']+'.svg')
    m = manifest(root)
    source = read(root / PROJECT / 'source/source_assets.json', {})
    assets = {a['asset_id']:a for a in source.get('assets',[])}
    dependencies = {aid:sha(local(root,assets[aid]['normalized_path'])) for aid in p.get('source_assets',[])}
    direction = root / '_internal/01_content/design_direction.md'
    template = root / PROJECT / 'fidelity_template'
    return digest({'page':p,'svg':sha(svg),'images':images(root,svg),'source_assets':dependencies,
        'source':sha(root / PROJECT / 'source/source.md'),'direction':sha(direction) if direction.exists() else '',
        'mode':m.get('template_intake'), 'template':{str(f.relative_to(template)):sha(f) for f in sorted(template.rglob('*')) if f.is_file()} if m.get('template_intake',{}).get('mode')=='fidelity' else {}})

def versions(root):
    return {p['page_key']:page_version(root,p) for p in content(root)['pages']}

def rendered(root, k, version):
    rec = read(root / VALIDATION / (k+'.json'), {})
    png = root / PNG / (k+'.png')
    return bool(rec.get('version')==version and rec.get('errors')==0 and png.is_file() and rec.get('png_sha256')==sha(png))

def inspected(root,k,version):
    rec=read(root / VALIDATION / (k+'.json'),{})
    ins=read(root / VALIDATION / 'inspections.json',{}).get(k,{})
    return (rendered(root,k,version) and ins.get('render_token')==digest(rec)
            and all(str(ins.get(f,'')).strip() for f in ('note','first_glance','design_check'))
            and not ins.get('must_fix'))


def design_observations(root, page_key):
    """Read-only measurements for the model's own design self-check.

    Facts about the page, not judgements: no pass/fail, no thresholds. They exist so
    the self-check in style_system.md can be done against numbers instead of memory.
    """
    svg = root / SVG / (page_key + '.svg')
    if not svg.is_file():
        return {}
    root_el = ET.parse(svg).getroot()

    def tag(n):
        return n.tag.split('}')[-1]

    def num(n, attr):
        try:
            return float(n.get(attr, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    texts = [n for n in root_el.iter() if tag(n) == 'text']
    rects = [n for n in root_el.iter() if tag(n) == 'rect']

    sizes = sorted({round(num(n, 'font-size')) for n in texts if num(n, 'font-size') > 0})
    scale_ratio = round(sizes[-1] / sizes[0], 2) if len(sizes) > 1 else None

    groups = {}
    for n in rects:
        w, h = num(n, 'width'), num(n, 'height')
        if w >= 200 and h >= 120 and not (w >= 1780 and h >= 1040):
            groups[(round(w), round(h))] = groups.get((round(w), round(h)), 0) + 1
    equal_containers = [f'{w}x{h}×{c}' for (w, h), c in sorted(groups.items()) if c >= 2]

    body = [n for n in texts if num(n, 'y') < 1000]
    lowest = round(max((num(n, 'y') + num(n, 'font-size') * 0.2) for n in body), 1) if body else None
    void = round(986.0 - lowest, 1) if lowest is not None else None

    # Include footer text too: the footer/folio baselines are themselves cross-page anchors.
    small = sorted({round(num(n, 'y')) for n in texts if 0 < num(n, 'font-size') <= 22})
    return {
        'type_tiers': sizes,
        'scale_ratio': scale_ratio,
        'equal_containers': equal_containers,
        'lowest_content_bottom': lowest,
        'gap_to_footer_rule': void,
        'small_text_baselines': small,
    }


def design_observations_deck(root, page_keys):
    """Per-page observations plus which small-text baselines are shared across pages."""
    obs = {k: design_observations(root, k) for k in page_keys}
    seen = {}
    for o in obs.values():
        for y in o.get('small_text_baselines', []):
            seen[y] = seen.get(y, 0) + 1
    for o in obs.values():
        o['shared_small_baselines'] = sorted(y for y in o.get('small_text_baselines', []) if seen.get(y, 0) > 1)
    return obs


def review_snapshot(root):
    return read(root / REVIEW / 'snapshot.json',{})

def review_current(root):
    try:
        snap=review_snapshot(root); v=versions(root)
        return bool(snap and snap.get('versions')==v and snap.get('order')==list(v) and
            all(inspected(root,k,x) for k,x in v.items()) and
            snap.get('png_hashes')=={k:sha(root/PNG/(k+'.png')) for k in v} and
            snap.get('html_sha256')==sha(root/'02_visual_review.html'))
    except (OSError,ValueError,ET.ParseError): return False

def approvals(root):
    """Per-page approval survives only while its exact content and rendered image remain unchanged."""
    f=read(root/REVIEW/'feedback.json',{})
    if f.get('provenance',{}).get('source')!='review_server': return {}
    result={}
    for p in content(root)['pages']:
        k=p['page_key']; item=f.get('pages',{}).get(k,{})
        try: v=page_version(root,p)
        except (OSError,ValueError): continue
        if item.get('version')==v and (root/PNG/(k+'.png')).is_file() and item.get('png_sha256')==sha(root/PNG/(k+'.png')) and inspected(root,k,v): result[k]=item
    return result

def approved(root):
    if not review_current(root): return False
    s=review_snapshot(root); f=read(root/REVIEW/'feedback.json',{})
    return f.get('review_id')==s.get('review_id') and not f.get('overall_feedback','').strip() and all(x.get('decision')=='approved' for x in approvals(root).values()) and len(approvals(root))==len(s['versions'])


def template_version(root):
    base=root/PROJECT
    paths=[base/'fidelity_template',base/'template_visuals',base/'template_media']
    files=[f for p in paths for f in p.rglob('*') if f.is_file()]
    files += [base/n for n in ('template_profile.json','template_asset_registry.json','template_canvas_self_review.json','template_worker_result.json') if (base/n).is_file()]
    return digest({str(f.relative_to(root)):sha(f) for f in files})
