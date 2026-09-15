"""Validate human feedback against the exact page shown; one revision destination."""
import math
import re
import uuid
from project_state import *

def save_feedback(root,data,session):
    root=Path(root).resolve()
    snapshot=review_snapshot(root)
    if data.get('review_id')!=snapshot.get('review_id') or not review_current(root): raise ValueError('Review is stale. Reload the current review; decisions were not saved.')
    supplied=data.get('pages',{})
    if not isinstance(supplied,dict) or set(supplied)!=set(snapshot['versions']): raise ValueError('Feedback must cover the exact page set')
    result={}; items=[]
    overall=str(data.get('overall_feedback','')).strip()
    for k,x in supplied.items():
        if not isinstance(x,dict):raise ValueError('Invalid page feedback')
        decision=x.get('decision')
        if decision not in {'pending','approved','revise'}:raise ValueError('Invalid decision')
        note=str(x.get('feedback','')).strip();ann=x.get('annotations',[]);assets=x.get('assets',[])
        if not isinstance(ann,list) or not isinstance(assets,list):raise ValueError('Invalid annotations/assets')
        for a in ann:
            if not isinstance(a,dict):raise ValueError('Invalid region')
            nums=[a.get(n) for n in ('x','y','w','h')]
            if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in nums):raise ValueError('Invalid region coordinates')
            xx,y,w,h=nums
            if min(xx,y)<0 or min(w,h)<=0 or xx+w>1.00001 or y+h>1.00001 or not str(a.get('text','')).strip(): raise ValueError('Region must be inside page and have feedback')
        used=set();declared={a['asset_key'] for a in snapshot['assets'][k]}
        for a in assets:
            key=a.get('asset_key','');op=a.get('operation')
            if not key or key in used or op not in {'add','replace','crop'}:raise ValueError('Unique asset keys and valid operations required')
            used.add(key)
            if op=='add' and key in declared or op!='add' and key not in declared:raise ValueError('Asset operation does not match displayed image')
            path=local(root,a.get('path',''))
            permitted={i['path'] for i in snapshot['assets'][k]}
            upload_base=root/REVIEW/'uploads'/k
            if str(path.relative_to(root)) not in permitted and upload_base not in path.parents:raise ValueError('Asset must be displayed or uploaded for this page')
            if not path.is_file() or a.get('fit') not in {'contain','cover'}:raise ValueError('Missing image or invalid fit')
            if not re.fullmatch(r'(original|[1-9]\d*:[1-9]\d*)',str(a.get('ratio',''))):raise ValueError('Use original or W:H ratio')
            if a.get('anchor') not in {'center','top','bottom','left','right'}:raise ValueError('Invalid anchor')
            a['sha256']=sha(path)
        if note or ann or assets:decision='revise'
        if decision=='revise' and not (note or ann or assets or overall):raise ValueError('Describe the requested change')
        result[k]={'decision':decision,'feedback':note,'annotations':ann,'assets':assets,'version':snapshot['versions'][k],'png_sha256':snapshot['png_hashes'][k]}
        if decision=='revise':items.append({'id':uuid.uuid4().hex,'pages':[k],'feedback':note,'annotations':ann,'assets':assets})
    if overall:items.append({'id':uuid.uuid4().hex,'pages':list(result),'feedback':overall})
    feedback={'review_id':snapshot['review_id'],'pages':result,'overall_feedback':overall,'items':items,
        'provenance':{'source':'review_server','session_id':session,'html_sha256':snapshot['html_sha256'],'submitted_at':datetime.now(timezone.utc).isoformat()}}
    write(root/REVIEW/'feedback.json',feedback);event(root,'visual_feedback_submitted',review_id=snapshot['review_id'])
    return {'status':'ok','message':'反馈已保存；请回到 Codex 问答框发送「已完成」。'}
