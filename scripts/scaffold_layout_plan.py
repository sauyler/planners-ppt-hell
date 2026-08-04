#!/usr/bin/env python3
"""Create a deterministic, deliberately incomplete Layout Plan scaffold.

The scaffold removes repetitive JSON assembly. It is not an approved design:
the contract validator rejects ``scaffold_status: incomplete`` until the Layout
agent has reviewed every page and marked the top-level and page-level statuses
``completed``.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path


INTERNAL = "_internal"


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    json.loads(payload)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def flatten(value):
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        return [text for item in value for text in flatten(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in flatten(item)]
    return []


def body_lines(page):
    lines = []
    for block in page.get("body_blocks", []) or []:
        if isinstance(block, dict):
            lines.extend(flatten(block.get("content", block.get("text", block.get("items", [])))))
        else:
            lines.extend(flatten(block))
    return lines


def source_asset_records(page, asset_manifest):
    registry = {
        str(item.get("asset_id", "")): item
        for item in asset_manifest.get("assets", [])
        if isinstance(item, dict) and item.get("asset_id")
    }
    records = []
    for item in page.get("source_assets", []) or []:
        if isinstance(item, str):
            item = {"asset_id": item}
        if not isinstance(item, dict):
            continue
        merged = dict(registry.get(str(item.get("asset_id", "")), {}))
        merged.update(item)
        path = str(merged.get("normalized_path") or merged.get("path") or "").strip()
        if path:
            merged["path"] = path
            records.append(merged)
    return records


def crop_options():
    return [
        {"label": "完整显示", "fit": "contain", "crop_ratio": "original", "crop_anchor": "center", "tradeoff": "保留全图，允许留白"},
        {"label": "居中填满", "fit": "cover", "crop_ratio": "16:9", "crop_anchor": "center", "tradeoff": "填满槽位，裁掉边缘"},
    ]


def page_scaffold(page, asset_manifest, fidelity_registry):
    title = str(page.get("action_title", "")).strip()
    lead = str(page.get("core_message", "")).strip()
    items = body_lines(page)
    assets = source_asset_records(page, asset_manifest)
    wireframe = [
        {"label": "title", "x": 120, "y": 60, "w": 1680, "h": 120, "zone": "header"},
    ]
    if assets:
        wireframe.extend([
            {"label": "lead", "x": 120, "y": 220, "w": 760, "h": 150, "zone": "body"},
            {"label": "items", "x": 120, "y": 400, "w": 760, "h": 560, "zone": "body"},
        ])
        image_height = max(120, int(740 / max(1, len(assets))))
        for index, _ in enumerate(assets):
            wireframe.append({
                "label": f"image_{index + 1}", "x": 940,
                "y": 220 + index * image_height, "w": 860,
                "h": image_height - 20, "zone": "body",
            })
    else:
        wireframe.extend([
            {"label": "lead", "x": 120, "y": 220, "w": 1680, "h": 160, "zone": "body"},
            {"label": "items", "x": 120, "y": 410, "w": 1680, "h": 550, "zone": "body"},
        ])
    final_copy = {"title": title, "lead": lead, "items": items or [lead]}
    visual_assets = []
    for index, asset in enumerate(assets):
        visual_assets.append({
            "asset_id": str(asset.get("asset_id", "")),
            "path": asset["path"],
            "slot_label": f"image_{index + 1}",
            "fit": "contain", "crop_ratio": "original", "crop_anchor": "center",
            "crop_options": crop_options(),
        })
    output = {
        "page_key": page.get("page_key"),
        "scaffold_status": "incomplete",
        "layout_id": "L00",
        "page_mode": "rational",
        "visual_density": "balanced",
        "grid": {"columns": 2 if assets else 1, "rows": max(3, len(assets) + 2)},
        "wireframe": wireframe,
        "copy_handling": {
            "final_on_slide": final_copy,
            "kept_on_slide": [text for text in [title, lead, *items] if text],
            "compression_rationale": ["Scaffold only: review and replace this with the actual Layout copy decision."],
            "compressed": False,
            "moved_to_notes": [],
        },
        "visual_asset_strategy": {
            "asset_need": "required" if assets else "none",
            "asset_type": "real_asset" if assets else "none",
            "placement": "main_right" if assets else "none",
            "reason": "Scaffold only: review the image role and placement." if assets else "Scaffold only: confirm that this page needs no image.",
            **({"assets": visual_assets} if assets else {}),
        },
        "layout_reason": "Scaffold only: replace with the page-specific reading path and spatial rationale.",
        "review_suggestions": [],
    }
    if "content_base" in fidelity_registry.get("layouts", {}):
        output["template_layout_id"] = "content_base"
    return output


def build(project_dir):
    root = Path(project_dir).resolve()
    internal = root / INTERNAL
    content = load_json(internal / "01_content" / "page_content.json", {})
    assets = load_json(internal / "00_project" / "source" / "source_assets.json", {})
    registry = load_json(internal / "00_project" / "fidelity_template" / "template_registry.json", {})
    pages = content.get("pages", []) if isinstance(content, dict) else []
    if not pages:
        raise SystemExit("page_content.json has no pages")
    return {
        "project": content.get("project", ""),
        "scaffold_status": "incomplete",
        "scaffold_instruction": "Review every page, replace scaffold judgments, then set top-level and every page scaffold_status to completed.",
        "pages": [page_scaffold(page, assets, registry) for page in pages],
    }


def main():
    parser = argparse.ArgumentParser(description="Create an incomplete deterministic Layout Plan scaffold")
    parser.add_argument("project_dir")
    parser.add_argument("--output", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    output = Path(args.output).resolve() if args.output else root / INTERNAL / "01_layout_plan" / "layout_plan.json"
    if output.exists() and not args.force:
        print(f"Kept existing {output}")
        return
    atomic_write(output, build(root))
    print(f"Generated incomplete Layout scaffold: {output}")


if __name__ == "__main__":
    main()
