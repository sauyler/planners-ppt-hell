#!/usr/bin/env python3
"""Build and verify reusable SVG layout canvases for template-driven pages."""

import hashlib
import html
import json
import re
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def component_markup(component):
    geometry = component["geometry"]
    kind = component["source_kind"]
    attrs = f'data-template-component="{component["component_id"]}" data-template-origin="{component["origin"]}"'
    if kind == "asset":
        return (f'<image {attrs} x="{geometry["x"]}" y="{geometry["y"]}" '
                f'width="{geometry["width"]}" height="{geometry["height"]}" '
                f'href="../../template_media/{component["file"]}" data-slot="template_background"/>')
    style = component.get("style", {})
    fill = style.get("fill") or "none"
    stroke = style.get("stroke") or "none"
    stroke_width = float(style.get("stroke_width") or 0)
    if component.get("shape", {}).get("preset") == "line":
        return (f'<line {attrs} x1="{geometry["x"]}" y1="{geometry["y"]}" '
                f'x2="{geometry["x"] + geometry["width"]}" y2="{geometry["y"] + geometry["height"]}" '
                f'stroke="{stroke if stroke != "none" else fill}" stroke-width="{max(stroke_width, 1):.2f}"/>')
    if component.get("shape", {}).get("preset") == "roundRect":
        radius = min(geometry["width"], geometry["height"]) * 0.18
        return (f'<rect {attrs} x="{geometry["x"]}" y="{geometry["y"]}" '
                f'width="{geometry["width"]}" height="{geometry["height"]}" rx="{radius:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>')
    if component.get("shape", {}).get("preset") == "ellipse":
        return (f'<ellipse {attrs} cx="{geometry["x"] + geometry["width"] / 2:.1f}" '
                f'cy="{geometry["y"] + geometry["height"] / 2:.1f}" '
                f'rx="{geometry["width"] / 2:.1f}" ry="{geometry["height"] / 2:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>')
    return (f'<rect {attrs} x="{geometry["x"]}" y="{geometry["y"]}" '
            f'width="{geometry["width"]}" height="{geometry["height"]}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>')


def build_layout_canvas(layout_id, layout, component_map):
    ids = list(dict.fromkeys(layout.get("required_components", [])))
    components = [component_map[cid] for cid in ids if cid in component_map]
    backgrounds = [item for item in components if item.get("placement") == "background"]
    foregrounds = [item for item in components if item.get("placement") != "background"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080" '
            f'data-layout-id="{html.escape(layout_id, quote=True)}" data-template-canvas-version="1">'
            '<g data-template-lock="background">'
            '<rect width="1920" height="1080" fill="#F7F8FA"/>'
            + ''.join(component_markup(item) for item in backgrounds)
            + '</g><g data-template-content-layer="replace">'
            + ''
            + '</g><g data-template-lock="foreground">'
            + ''.join(component_markup(item) for item in foregrounds)
            + '</g></svg>')


def _canonical_node(node):
    attrs = ''.join(f' {key}={json.dumps(value, ensure_ascii=False)}' for key, value in sorted(node.attrib.items()))
    text = (node.text or "").strip()
    children = ''.join(_canonical_node(child) for child in list(node))
    return f'<{node.tag}{attrs}>{text}{children}</{node.tag}>'


def locked_sha256(svg_or_path):
    value = Path(svg_or_path).read_text(encoding="utf-8") if isinstance(svg_or_path, Path) else str(svg_or_path)
    root = ET.fromstring(value)
    locked = [node for node in root.iter() if node.get("data-template-lock")]
    canonical = ''.join(_canonical_node(node) for node in locked)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_layout_filename(layout_id):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(layout_id)).strip("_")
    return f"{value or 'layout'}.svg"


def ensure_layout_canvases(registry, fidelity_dir):
    """Write the canonical canvases and bind their lock hashes into the registry."""
    fidelity_dir = Path(fidelity_dir)
    canvas_dir = fidelity_dir / "layout_canvases"
    canvas_dir.mkdir(parents=True, exist_ok=True)
    component_map = {item["component_id"]: item for item in registry.get("components", [])}
    expected = set()
    for layout_id, layout in registry.get("layouts", {}).items():
        filename = safe_layout_filename(layout_id)
        expected.add(filename)
        svg = build_layout_canvas(layout_id, layout, component_map)
        path = canvas_dir / filename
        path.write_text(svg + "\n", encoding="utf-8")
        layout["canvas_file"] = f"layout_canvases/{filename}"
        layout["locked_sha256"] = locked_sha256(svg)
    for stale in canvas_dir.glob("*.svg"):
        if stale.name not in expected:
            stale.unlink()
    return registry


def registry_canvases_ready(registry, fidelity_dir):
    layouts = registry.get("layouts", {}) if isinstance(registry, dict) else {}
    if not layouts:
        return False
    fidelity_dir = Path(fidelity_dir)
    for layout in layouts.values():
        canvas_file = layout.get("canvas_file", "")
        expected = layout.get("locked_sha256", "")
        path = fidelity_dir / canvas_file if canvas_file else None
        if not path or not path.is_file() or not expected or locked_sha256(path) != expected:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate executable SVG layout canvases from a fidelity registry")
    parser.add_argument("registry")
    args = parser.parse_args()
    registry_path = Path(args.registry).resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    ensure_layout_canvases(registry, registry_path.parent)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(registry_path.parent / "layout_canvases")


if __name__ == "__main__":
    main()
