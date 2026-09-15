"""One actual-page review, with image editing and versioned regional feedback."""
import json
import uuid
from pathlib import Path
from project_state import *

def generate(root):
    c=content(root);v=versions(root);old=review_snapshot(root);allowed=approvals(root)
    snap={'review_id':uuid.uuid4().hex,'versions':v,'order':list(v),'png_hashes':{k:sha(root/PNG/(k+'.png')) for k in v},
        'assets':{k:images(root,root/SVG/(k+'.svg')) for k in v}}
    data={'project':c.get('project',''),'review_id':snap['review_id'],'pages':[]}
    for p in c['pages']:
        k=p['page_key'];previous=root/REVIEW/'versions'/f'{k}-{old.get("versions",{}).get(k,"")}.png'
        data['pages'].append({'key':k,'title':p['title'],'png':f'/{PNG}/{k}.png?v={v[k]}','assets':snap['assets'][k],
            'previous':'/'+previous.relative_to(root).as_posix() if previous.exists() else '',
            'decision': 'approved' if allowed.get(k,{}).get('decision')=='approved' else 'pending'})
    template=(Path(__file__).resolve().parents[1]/'assets/review/review.html').read_text()
    html=template.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
    (root/'02_visual_review.html').write_text(html,encoding='utf-8')
    snap['html_sha256']=sha(root/'02_visual_review.html');write(root/REVIEW/'snapshot.json',snap)
    return snap
