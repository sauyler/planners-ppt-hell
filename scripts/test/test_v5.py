"""v5 behavioral regressions. Synthetic approvals are isolated test fixtures only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'orchestrate'))
from project_state import *
from ppt_pipeline import next_action, make_review, resolve, export
from review_feedback import save_feedback
from validate_svg_layout import validate_file
S=Path(__file__).resolve().parents[1]

class V5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'project'
        src=Path(self.tmp.name)/'source.md';src.write_text('# Demo\nEvidence 42% with qualification.\n')
        subprocess.run([sys.executable,str(S/'init_svg_project.py'),str(self.root),'--source',str(src)],check=True,capture_output=True)
        write(self.root/CONTENT,{'project':'Test','pages':[{'page_key':k,'title':k,'content':'42% with qualification','source_assets':[]} for k in ['alpha','omega']]})
        sync(self.root)
        for k in ['alpha','omega']:self.svg(k)
        self.seal()
    def tearDown(self):self.tmp.cleanup()
    def svg(self,k,text='Evidence'):
        (self.root/SVG/(k+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="#FFFFFF"/><text x="120" y="180" font-size="48" font-family="Arial" fill="#111111">'+text+'</text></svg>')
    def seal(self):
        ins={}
        for k,v in versions(self.root).items():
            png=self.root/PNG/(k+'.png');png.parent.mkdir(parents=True,exist_ok=True);Image.new('RGB',(192,108),'white').save(png)
            rec={'version':v,'errors':0,'png_sha256':sha(png),'validator':{}}
            write(self.root/VALIDATION/(k+'.json'),rec);ins[k]={'render_token':digest(rec),'note':'Synthetic test fixture','first_glance':'fixture focal element','design_check':'fixture rule check','must_fix':False}
        write(self.root/VALIDATION/'inspections.json',ins)
    def payload(self):
        snap=make_review(self.root)
        return {'review_id':snap['review_id'],'pages':{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in snap['versions']},'overall_feedback':''}
    def test_no_layout_or_batch_gate(self):
        m=manifest(self.root);self.assertNotIn('batch_size',m);self.assertFalse((self.root/'_internal/01_layout_plan').exists());self.assertEqual(next_action(self.root)['state'],'VISUAL_REVIEW')
    def test_stable_ids_reorder_without_renumber(self):
        c=content(self.root);c['pages'].reverse();write(self.root/CONTENT,c);self.assertEqual(sync(self.root)['pages'][0]['page_key'],'omega')
    def test_old_projects_rejected_explicitly(self):
        m=manifest(self.root);m['version']='4.0';write(self.root/PROJECT/'page_manifest.json',m)
        with self.assertRaisesRegex(ValueError,'older workflow'):manifest(self.root)
    def test_metadata_not_required_for_editable_svg(self):
        r=validate_file(self.root/SVG/'alpha.svg');self.assertFalse(any('METADATA' in x['code'] or 'LAYOUT' in x['code'] for x in r['issues']))
    def test_unapproved_export_blocked(self):
        with self.assertRaisesRegex(ValueError,'human review'):export(self.root)
    def test_human_approval_bound_to_actual_version(self):
        p=self.payload();save_feedback(self.root,p,'synthetic-test');self.assertTrue(approved(self.root));self.svg('alpha','Changed');self.assertFalse(approved(self.root))
    def test_stale_browser_submission_rejected(self):
        p=self.payload();self.svg('alpha','Changed');self.seal();make_review(self.root)
        with self.assertRaisesRegex(ValueError,'stale'):save_feedback(self.root,p,'synthetic-test')
    def test_unchanged_page_retains_approval(self):
        save_feedback(self.root,self.payload(),'synthetic-test');self.svg('alpha','Changed');self.seal();self.assertEqual(set(approvals(self.root)),{'omega'})
    def test_png_tamper_invalidates_approval(self):
        save_feedback(self.root,self.payload(),'synthetic-test');Image.new('RGB',(192,108),'red').save(self.root/PNG/'alpha.png');self.assertFalse(approved(self.root))
    def test_source_change_invalidates_review(self):
        save_feedback(self.root,self.payload(),'synthetic-test');(self.root/PROJECT/'source/source.md').write_text('New facts');self.assertFalse(approved(self.root))
    def test_html_change_invalidates_approval(self):
        save_feedback(self.root,self.payload(),'synthetic-test');p=self.root/'02_visual_review.html';p.write_text(p.read_text()+'<!-- changed -->');self.assertFalse(approved(self.root))
    def test_feedback_overrides_approved(self):
        p=self.payload();p['pages']['alpha']['feedback']='Rearrange the whole page';save_feedback(self.root,p,'synthetic-test');f=read(self.root/REVIEW/'feedback.json');self.assertEqual(f['pages']['alpha']['decision'],'revise');self.assertEqual(next_action(self.root)['state'],'CREATE')
    def test_feedback_needs_actual_change_to_resolve(self):
        p=self.payload();p['pages']['alpha']['feedback']='Change';save_feedback(self.root,p,'synthetic-test');fid=read(self.root/REVIEW/'feedback.json')['items'][0]['id']
        with self.assertRaisesRegex(ValueError,'changed artifact'):resolve(self.root,fid,'Done')
        self.svg('alpha','Changed');resolve(self.root,fid,'Changed headline');self.seal();make_review(self.root)
    def test_feedback_all_items_block_review(self):
        p=self.payload();p['pages']['alpha']['feedback']='Change';p['pages']['omega']['feedback']='Change';save_feedback(self.root,p,'synthetic-test')
        with self.assertRaisesRegex(ValueError,'every submitted'):make_review(self.root)
    def test_region_bounds_validated(self):
        p=self.payload();p['pages']['alpha']['annotations']=[{'x':.9,'y':0,'w':.5,'h':.2,'text':'Fix'}]
        with self.assertRaisesRegex(ValueError,'inside'):save_feedback(self.root,p,'synthetic-test')
    def test_upload_path_traversal_blocked(self):
        p=self.payload();p['pages']['alpha']['assets']=[{'asset_key':'new','operation':'add','path':'../source.md','fit':'contain','ratio':'original','anchor':'center'}]
        with self.assertRaisesRegex(ValueError,'outside'):save_feedback(self.root,p,'synthetic-test')
    def test_new_image_reaches_creation_feedback(self):
        p=self.payload();image=self.root/REVIEW/'uploads/alpha/test.png';image.parent.mkdir(parents=True);Image.new('RGB',(20,20),'blue').save(image)
        p['pages']['alpha']['assets']=[{'asset_key':'new','operation':'add','path':image.relative_to(self.root).as_posix(),'fit':'cover','ratio':'5:4','anchor':'top'}]
        save_feedback(self.root,p,'synthetic-test');f=read(self.root/REVIEW/'feedback.json');self.assertEqual(f['items'][0]['assets'][0]['ratio'],'5:4')
    def test_source_assets_must_be_accounted_for(self):
        write(self.root/PROJECT/'source/source_assets.json',{'assets':[{'asset_id':'asset_001'}]})
        with self.assertRaisesRegex(ValueError,'not accounted'):content(self.root)
    def test_missing_image_and_stretch_rejected(self):
        svg=self.root/SVG/'alpha.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="missing.png"/></svg>')
        with self.assertRaisesRegex(ValueError,'Missing image'):images(self.root,svg)
    def test_check_cache_evidence_token_changes_on_new_version(self):
        old=read(self.root/VALIDATION/'alpha.json');self.svg('alpha','New');self.seal();self.assertNotEqual(digest(old),digest(read(self.root/VALIDATION/'alpha.json')))

if __name__=='__main__':unittest.main()
