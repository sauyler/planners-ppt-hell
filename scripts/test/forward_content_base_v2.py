#!/usr/bin/env python3
"""Real default-template/content_base forward with validator and PNG output."""

import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"


def run(*args):
    result = subprocess.run([sys.executable, *map(str, args)], cwd=SKILL, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def main():
    temp = Path(tempfile.mkdtemp(prefix="ppt-content-base-forward-"))
    try:
        project = temp / "project"
        source = temp / "source.md"
        source.write_text("# 非标准关系页\n\n监管变化、渠道摩擦与服务承诺彼此制约。", encoding="utf-8")
        run(SCRIPTS / "init_svg_project.py", project, "--source", source)
        run(SCRIPTS / "template" / "template_library.py", "apply", project,
            "--template-id", "planner-simple-default")
        internal = project / "_internal"
        content = {
            "project": "content-base-forward",
            "source_path": str(source),
            "pages": [{
                "page_key": "page_01",
                "action_title": "三种力量正在重写服务边界",
                "core_message": "监管、渠道与承诺不是标准图表关系，使用开放基础页。",
                "body_blocks": ["监管变化", "渠道摩擦", "服务承诺"],
                "speaker_notes": ["保留完整背景解释，导出时进入讲者备注。"],
            }],
        }
        (internal / "01_content" / "page_content.json").write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_path = internal / "00_project" / "page_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["pages"] = [{"page_key": "page_01", "batch_id": "batch_01",
                              "svg_path": "_internal/02_svg_source/page_01.svg",
                              "png_path": "_internal/03_png_preview/pages/page_01.png"}]
        manifest["batch_config"] = {"batch_01": {"pages": ["page_01"]}}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        layout = {"project": "content-base-forward", "pages": [{
            "page_key": "page_01", "layout_id": "L04", "template_layout_id": "content_base",
            "page_mode": "rational", "visual_density": "balanced", "grid": "single",
            "wireframe": [
                {"label": "title", "zone": "header", "x": 140, "y": 100, "w": 1600, "h": 120},
                {"label": "body", "zone": "body", "x": 140, "y": 270, "w": 1600, "h": 600},
            ],
            "copy_handling": {
                "final_on_slide": {"title": "三种力量正在重写服务边界", "body": ["监管变化 × 渠道摩擦 × 服务承诺"]},
                "kept_on_slide": ["监管变化", "渠道摩擦", "服务承诺"],
                "compression_rationale": [], "compressed": False,
                "moved_to_notes": ["完整背景解释保留在讲者备注。"],
            },
            "visual_asset_strategy": {"asset_need": "none"},
            "layout_reason": "没有专用模型精确匹配，按合同选择 content_base。",
        }]}
        layout_path = internal / "01_layout_plan" / "layout_plan.json"
        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
        run(SCRIPTS / "orchestrate" / "make_stage_task.py", project, "--step", "svg", "--batch", "batch_01")
        task = json.loads((internal / "00_project" / "tasks" / "svg_batch_01_task.json").read_text(encoding="utf-8"))
        canvases = [item for item in task["input_files"] if "/layout_canvases/" in item]
        if len(canvases) != 1 or not canvases[0].endswith("content_base.svg"):
            raise AssertionError(f"non-minimal canvas payload: {canvases}")
        run(SCRIPTS / "template" / "apply_fidelity_template.py", "--project", project,
            "--page-key", "page_01", "--layout-id", "content_base",
            "--title", "三种力量正在重写服务边界", "--body", "监管变化 × 渠道摩擦 × 服务承诺")
        svg_dir = internal / "02_svg_source"
        svg_root = ET.parse(svg_dir / "page_01.svg").getroot()
        positioned = {
            item.get("data-wireframe-label"): (item.get("x"), item.get("y"))
            for item in svg_root.iter() if item.get("data-wireframe-label")
        }
        if positioned != {"title": ("140.0", "100.0"), "body": ("140.0", "270.0")}:
            raise AssertionError(f"SVG copy ignored Layout Plan wireframe: {positioned}")
        validation = run(SCRIPTS / "validate_svg_layout.py", svg_dir,
            "--file", svg_dir / "page_01.svg", "--layout-plan", layout_path,
            "--fidelity-template", internal / "00_project" / "fidelity_template" / "template_registry.json")
        if json.loads(validation.stdout)["summary"]["errors"]:
            raise AssertionError(validation.stdout)
        preview = temp / "preview"
        run(SCRIPTS / "render_svg_png.py", svg_dir, preview)
        if not (preview / "pages" / "page_01.png").is_file():
            raise AssertionError("forward PNG missing")
        print(json.dumps({
            "status": "pass",
            "template_layout_id": "content_base",
            "task_canvas_inputs": canvases,
            "wireframe_positions": positioned,
            "svg": str(svg_dir / "page_01.svg"),
            "png": str(preview / "pages" / "page_01.png"),
            "validator_errors": 0,
        }, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(temp)


if __name__ == "__main__":
    main()
