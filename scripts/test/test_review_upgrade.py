#!/usr/bin/env python3

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "orchestrate"))

from review_policy import blocking_warning_issues, layout_reroute_pages  # noqa: E402
from review_server import validate_layout_feedback_assets  # noqa: E402
from orchestrate.ppt_pipeline import review_artifact_current  # noqa: E402


class ReviewUpgradeTests(unittest.TestCase):
    def test_blocking_warning_policy_is_single_source(self):
        report = {"reports": [{"file": "page_01.svg", "issues": [
            {"severity": "warning", "code": "TEXT_OVERFLOW_MAJOR", "message": "overflow"},
            {"severity": "warning", "code": "PALETTE", "message": "palette"},
        ]}]}
        self.assertEqual([item["code"] for item in blocking_warning_issues(report)], ["TEXT_OVERFLOW_MAJOR"])

    def test_visual_feedback_routes_structure_to_layout(self):
        feedback = {"pages": {
            "page_01": {"approved": False, "custom_feedback": "这一页版式整体重排"},
            "page_02": {"approved": False, "custom_feedback": "图例字号加大"},
            "page_03": {"approved": False, "annotations": [{"x": 0, "y": 0, "w": .8, "h": .6, "text": "重做"}]},
        }}
        self.assertEqual(layout_reroute_pages(feedback), ["page_01", "page_03"])

    def test_new_image_slot_is_additive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "_internal" / "01_layout_plan"
            plan_dir.mkdir(parents=True)
            (plan_dir / "layout_plan.json").write_text(json.dumps({"pages": [{
                "page_key": "page_01", "visual_asset_strategy": {"assets": [{"slot_label": "hero"}]}
            }]}), encoding="utf-8")
            asset = root / "_internal" / "00_project" / "review_assets" / "page_01" / "extra.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"png")
            data = {"pages": {"page_01": {"asset_uploads": [
                {"slot_label": "hero", "fit": "contain", "crop_ratio": "original", "crop_anchor": "center", "changed": False},
                {"slot_label": "new_image_1", "fit": "cover", "crop_ratio": "16:9", "crop_anchor": "center",
                 "changed": True, "is_new": True, "operation": "add", "path": str(asset.relative_to(root))},
            ]}}}
            self.assertEqual(validate_layout_feedback_assets(root, data, {"page_01"}), "")
            data["pages"]["page_01"]["asset_uploads"][1].pop("operation")
            self.assertIn("operation=add", validate_layout_feedback_assets(root, data, {"page_01"}))

    def test_layout_approval_binds_plan_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "01_layout_direction.html"
            plan = root / "_internal" / "01_layout_plan" / "layout_plan.json"
            plan.parent.mkdir(parents=True)
            html.write_text("review", encoding="utf-8")
            plan.write_text("{}", encoding="utf-8")
            import hashlib
            digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            data = {"provenance": {"source": "review_server", "route": "/layout-feedback", "session_id": "s",
                    "html_sha256": digest(html), "layout_plan_sha256": digest(plan)}}
            self.assertTrue(review_artifact_current(root, data, "/layout-feedback"))
            plan.write_text('{"changed":true}', encoding="utf-8")
            self.assertFalse(review_artifact_current(root, data, "/layout-feedback"))


if __name__ == "__main__":
    unittest.main()
