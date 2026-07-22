#!/usr/bin/env python3
"""Reference SVG-stage adapter: instantiate a selected fidelity layout."""

import argparse
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def main():
    parser = argparse.ArgumentParser(description="Instantiate reviewed fidelity components into one SVG")
    parser.add_argument("--project", required=True)
    parser.add_argument("--page-key", required=True)
    parser.add_argument("--layout-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--layout-plan", default="")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    registry = json.loads((root / "_internal/00_project/fidelity_template/template_registry.json").read_text(encoding="utf-8"))
    layout = registry["layouts"].get(args.layout_id)
    if layout is None:
        raise ValueError(f"unknown fidelity layout: {args.layout_id}")
    canvas_file = layout.get("canvas_file")
    if not canvas_file:
        raise ValueError(f"fidelity layout has no executable SVG canvas: {args.layout_id}")
    canvas = root / "_internal/00_project/fidelity_template" / canvas_file
    if not canvas.is_file():
        raise ValueError(f"fidelity layout canvas is missing: {canvas}")
    tree = ET.parse(canvas)
    svg_root = tree.getroot()
    destination = root / "_internal/02_svg_source" / f"{args.page_key}.svg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    for image in list(svg_root.iter(f"{{{SVG_NS}}}image")) + list(svg_root.iter("image")):
        for attribute in ("href", "{http://www.w3.org/1999/xlink}href"):
            value = str(image.get(attribute, "")).strip()
            if not value or value.startswith(("data:", "http://", "https://", "/", "#")):
                continue
            source_asset = (canvas.parent / value).resolve()
            image.set(attribute, Path(os.path.relpath(source_asset, destination.parent)).as_posix())
    svg_root.set("data-fidelity-template", "v2")
    svg_root.set("data-layout-id", args.layout_id)
    svg_root.set("data-page-key", args.page_key)
    content_layer = next((node for node in svg_root.iter() if node.get("data-template-content-layer") == "replace"), None)
    if content_layer is None:
        raise ValueError(f"fidelity layout canvas has no replaceable content layer: {canvas}")
    content_layer.clear()
    content_layer.set("data-template-content-layer", "replace")
    layout_plan_path = Path(args.layout_plan).resolve() if args.layout_plan else root / "_internal/01_layout_plan/layout_plan.json"
    layout_plan = json.loads(layout_plan_path.read_text(encoding="utf-8"))
    page_plan = next((page for page in layout_plan.get("pages", []) if page.get("page_key") == args.page_key), None)
    if page_plan is None:
        raise ValueError(f"layout plan has no page: {args.page_key}")
    if page_plan.get("template_layout_id") != args.layout_id:
        raise ValueError(
            f"layout plan/template canvas mismatch: {page_plan.get('template_layout_id')!r} != {args.layout_id!r}"
        )
    wireframe = page_plan.get("wireframe")
    if not isinstance(wireframe, list) or not wireframe:
        raise ValueError(f"layout plan wireframe is empty: {args.page_key}")

    def region(label, fallback_zone):
        return next((item for item in wireframe if str(item.get("label", "")).lower() == label), None) or next(
            (item for item in wireframe if str(item.get("zone", "")).lower() == fallback_zone), None
        )

    title_region = region("title", "header")
    body_region = region("body", "body")
    if title_region is None or (args.body and body_region is None):
        raise ValueError(f"layout plan wireframe lacks required title/body regions: {args.page_key}")

    def position(item):
        try:
            return str(float(item["x"])), str(float(item["y"]))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"wireframe region has invalid x/y: {item}")

    title_x, title_y = position(title_region)
    title = ET.SubElement(content_layer, f"{{{SVG_NS}}}text", {
        "x": title_x, "y": title_y, "font-family": "PingFang SC", "font-size": "56",
        "font-weight": "bold", "fill": "#1F1F1F", "dominant-baseline": "hanging",
        "data-wireframe-label": "title",
    })
    title.text = args.title
    if args.body:
        body_x, body_y = position(body_region)
        body = ET.SubElement(content_layer, f"{{{SVG_NS}}}text", {
            "x": body_x, "y": body_y, "font-family": "PingFang SC", "font-size": "28", "fill": "#555555",
            "dominant-baseline": "hanging", "data-wireframe-label": "body",
        })
        body.text = args.body
    svg_root.insert(0, ET.Comment(
        f' page_key="{args.page_key}" data-layout="{args.layout_id}" page_mode="rational" '
        'visual_density="balanced" reason="Approved SVG layout canvas was used before content." '
    ))
    tree.write(destination, encoding="unicode", xml_declaration=False)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    print(destination)


if __name__ == "__main__":
    main()
