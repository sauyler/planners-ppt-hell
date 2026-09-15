#!/usr/bin/env python3
"""SVG checks that protect PPT conversion and catch real defects — not design taste.

What stays, and why: things that break when the page becomes an editable PPT
(unsupported elements/attributes, images that are not real local files, stretched
bitmaps, tspan line breaks), plus defects that are wrong on any page regardless of
style (text overlapping text, elements off-canvas, an empty slide).

What was retired: the readability/density/composition heuristics
(font-size tiers, body-text floor at 20px, empty-region, module utilization,
canvas coverage, density imbalance, footer-zone, safe-margin, image-slot,
approved image ratios, the page_mode rhythm scan). They did not protect correctness;
they encoded one house style and pushed every deck toward sparse, uniform,
card-based pages — the opposite of a dense, designed proposal. Design judgement now
belongs to the model, which renders the page and looks at it.

The one retained size rule is a genuine readability floor, and it follows the page's
declared reading mode: a projected page ("讲") is read from the back of a room, a
document page ("读") is read up close.
"""
import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "template"))
from layout_canvas import locked_sha256  # noqa: E402

TEXT_RE = re.compile(r"\s+")
TRANSLATE_RE = re.compile(r"translate\(\s*([\d.eE+-]+)\s*[,\s]\s*([\d.eE+-]+)\s*\)")
SCALE_RE = re.compile(r"scale\(\s*([\d.eE+-]+)(?:\s*[,\s]\s*([\d.eE+-]+))?\s*\)")

CANVAS_W = 1920.0
CANVAS_H = 1080.0
MARGIN = 60.0
VALID_FONT_WEIGHTS = {"normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"}

# Reading mode drives the readability floor. 1 SVG px = 0.5 pt on a 13.333in slide,
# so 12px is 6pt (nothing is readable below this at any zoom) and 18px is 9pt.
MODE_FLOOR = {"讲": 18.0, "读": 12.0}
DEFAULT_MODE = "读"

PROHIBITED_ELEMENTS = ["foreignObject", "filter", "use", "style", "marker", "mask", "animate"]
PROHIBITED_ATTRIBUTES = [
    "stroke-dasharray", "textLength", "lengthAdjust",
    "marker-start", "marker-mid", "marker-end",
]
PROHIBITED_TRANSFORMS = ["rotate("]


# ── Helpers ──────────────────────────────────────────────────────

def parse_float(value, default=0.0):
    if value is None:
        return default
    cleaned = re.sub(r"[^\d.\-]", "", value)
    return float(cleaned) if cleaned else default


def parse_color(value):
    if not value or value == "none":
        return None
    v = value.strip().upper()
    if v.startswith("URL("):
        return None
    return v


def parse_transform(transform):
    dx, dy = 0.0, 0.0
    sx, sy = 1.0, 1.0
    m = TRANSLATE_RE.search(transform or "")
    if m:
        dx = float(m.group(1))
        dy = float(m.group(2))
    m = SCALE_RE.search(transform or "")
    if m:
        sx = float(m.group(1))
        sy = float(m.group(2)) if m.group(2) else sx
    return dx, dy, sx, sy


def get_accumulated_transform(node, parent_map):
    """Mirror native_svg_to_ppt.py's simplified transform model (translate/scale on <g>)."""
    ancestors = []
    current = node
    while current in parent_map:
        current = parent_map[current]
        ancestors.append(current)
    ancestors.reverse()
    dx, dy = 0.0, 0.0
    sx, sy = 1.0, 1.0
    for ancestor in ancestors:
        tx, ty, tsx, tsy = parse_transform(ancestor.get("transform", ""))
        dx += tx
        dy += ty
        sx *= tsx
        sy *= tsy
    return dx, dy, sx, sy


def build_parent_map(root):
    pm = {}
    for parent in root.iter():
        for child in parent:
            pm[child] = parent
    return pm


def estimate_text_width(content, font_size):
    w = 0.0
    for ch in content:
        w += font_size * (0.56 if ord(ch) < 128 else 0.92)
    return w


def estimate_text_box(node, parent_map):
    """Estimated ink box. Honors text-anchor, so centred/right-aligned text is not
    reported as overflowing the right margin or colliding with a neighbour."""
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    x = (parse_float(node.get("x")) + dx) * sx
    y = (parse_float(node.get("y")) + dy) * sy
    font_size = parse_float(node.get("font-size"), 24.0) * min(sx, sy)
    content = TEXT_RE.sub(" ", "".join(node.itertext())).strip()
    w = estimate_text_width(content, font_size) if content else 0.0
    h = font_size * 1.18
    anchor = (node.get("text-anchor") or "start").strip()
    if anchor == "middle":
        x -= w / 2.0
    elif anchor == "end":
        x -= w
    return (x, y - font_size, w, h)


def rect_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        (parse_float(node.get("x")) + dx) * sx,
        (parse_float(node.get("y")) + dy) * sy,
        parse_float(node.get("width")) * sx,
        parse_float(node.get("height")) * sy,
    )


def image_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        (parse_float(node.get("x")) + dx) * sx,
        (parse_float(node.get("y")) + dy) * sy,
        parse_float(node.get("width")) * sx,
        parse_float(node.get("height")) * sy,
    )


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and by < ay + ah and by + bh > ay


def outside_safe_margin(box, margin=MARGIN):
    x, y, w, h = box
    return x < margin or y < margin or x + w > CANVAS_W - margin or y + h > CANVAS_H - margin


def box_to_dict(box):
    return {"x": round(box[0], 1), "y": round(box[1], 1), "w": round(box[2], 1), "h": round(box[3], 1)}


def text_content(node):
    return TEXT_RE.sub(" ", "".join(node.itertext())).strip()


def is_full_canvas_rect(box):
    x, y, w, h = box
    return x <= 5 and y <= 5 and w >= CANVAS_W * 0.95 and h >= CANVAS_H * 0.95


def issue(severity, code, message, target=None, detail=None, hint=None):
    i = {"severity": severity, "code": code, "message": message}
    if target:
        i["target"] = target
    if detail:
        i["detail"] = detail
    if hint:
        i["hint"] = hint
    return i


# ── Fidelity template component checks (only in the strict-template branch) ──

def fidelity_component_node_errors(component, node):
    """Validate a v2 fidelity instance beyond the presence of its ID."""
    errors = []
    geometry = component.get("geometry", {})
    preset = component.get("shape", {}).get("preset")
    expected_tag = "image" if component.get("source_kind") == "asset" else {
        "roundRect": "rect", "rect": "rect", "ellipse": "ellipse", "line": "line",
    }.get(preset, "rect")
    actual_tag = node.tag.rsplit("}", 1)[-1]
    component_id = component.get("component_id", "")
    if actual_tag != expected_tag:
        return [("FIDELITY_COMPONENT_TYPE_MISMATCH",
                 f"Template component {component_id} must be <{expected_tag}>, got <{actual_tag}>")]

    if expected_tag in {"rect", "image"}:
        actual_geometry = {key: parse_float(node.get(key)) for key in ("x", "y", "width", "height")}
        expected_geometry = {key: float(geometry.get(key, 0)) for key in actual_geometry}
        positive = actual_geometry["width"] > 0 and actual_geometry["height"] > 0
    elif expected_tag == "ellipse":
        actual_geometry = {key: parse_float(node.get(key)) for key in ("cx", "cy", "rx", "ry")}
        expected_geometry = {
            "cx": float(geometry.get("x", 0)) + float(geometry.get("width", 0)) / 2,
            "cy": float(geometry.get("y", 0)) + float(geometry.get("height", 0)) / 2,
            "rx": float(geometry.get("width", 0)) / 2,
            "ry": float(geometry.get("height", 0)) / 2,
        }
        positive = actual_geometry["rx"] > 0 and actual_geometry["ry"] > 0
    else:
        actual_geometry = {key: parse_float(node.get(key)) for key in ("x1", "y1", "x2", "y2")}
        expected_geometry = {
            "x1": float(geometry.get("x", 0)), "y1": float(geometry.get("y", 0)),
            "x2": float(geometry.get("x", 0)) + float(geometry.get("width", 0)),
            "y2": float(geometry.get("y", 0)) + float(geometry.get("height", 0)),
        }
        positive = math.hypot(actual_geometry["x2"] - actual_geometry["x1"],
                              actual_geometry["y2"] - actual_geometry["y1"]) > 0
    if not positive:
        errors.append(("FIDELITY_COMPONENT_EMPTY", f"Template component {component_id} has zero visual geometry"))
    if component.get("geometry_policy", "fixed") == "fixed":
        mismatched = [key for key in expected_geometry if abs(actual_geometry[key] - expected_geometry[key]) > 3.0]
        if mismatched:
            errors.append(("FIDELITY_COMPONENT_GEOMETRY_MISMATCH",
                           f"Template component {component_id} changed fixed geometry: {', '.join(mismatched)}"))

    if expected_tag != "image":
        style = component.get("style", {})
        for key in ("fill", "stroke"):
            expected = parse_color(style.get(key))
            if expected and parse_color(node.get(key)) != expected:
                errors.append(("FIDELITY_COMPONENT_STYLE_MISMATCH",
                               f"Template component {component_id} changed {key}: expected {expected}"))
        expected_width = float(style.get("stroke_width") or 0)
        if expected_width and abs(parse_float(node.get("stroke-width")) - expected_width) > 1.0:
            errors.append(("FIDELITY_COMPONENT_STYLE_MISMATCH",
                           f"Template component {component_id} changed stroke-width"))
    return errors


# ── Per-file validation ──────────────────────────────────────────

def validate_file(path, page_mode=DEFAULT_MODE, margin=MARGIN, quick_mode=False):
    content = Path(path).read_text(encoding="utf-8-sig")
    root = ET.fromstring(content)
    parent_map = build_parent_map(root)

    errors, warnings, infos = [], [], []
    E = lambda code, msg, **kw: errors.append(issue("error", code, msg, **kw))
    W = lambda code, msg, **kw: warnings.append(issue("warning", code, msg, **kw))
    I = lambda code, msg, **kw: infos.append(issue("info", code, msg, **kw))

    # ── Canvas contract ──
    if root.get("width") != "1920" or root.get("height") != "1080":
        E("INVALID_CANVAS_SIZE", 'SVG root must use width="1920" and height="1080"', target="svg_root")
    if root.get("viewBox") != "0 0 1920 1080":
        E("INVALID_VIEWBOX", 'SVG root must use viewBox="0 0 1920 1080"', target="svg_root")

    # ── SVG → PPT compatibility ──
    for el_name in PROHIBITED_ELEMENTS:
        if f"<{el_name}".lower() in content.lower():
            E(f"PROHIBITED_{el_name.upper()}", f"SVG uses <{el_name}> — unsupported in PPT conversion",
              target="svg_structure")
    for attr in PROHIBITED_ATTRIBUTES:
        if attr.lower() in content.lower():
            E(f"PROHIBITED_{attr.replace('-', '_').upper()}",
              f"SVG uses {attr} — unsupported in PPT conversion", target="svg_structure")
    for tf in PROHIBITED_TRANSFORMS:
        if tf.lower() in content.lower():
            E("PROHIBITED_TRANSFORM", f"SVG uses transform with {tf} — unsupported in PPT conversion",
              target="svg_structure")

    # ── Images must be real local project files, never stretched ──
    image_nodes = list(root.findall(".//{http://www.w3.org/2000/svg}image")) or list(root.findall(".//image"))
    for idx, node in enumerate(image_nodes, 1):
        href = (node.get("href") or node.get("{http://www.w3.org/1999/xlink}href") or "").strip()
        if not href or href.startswith(("data:", "http://", "https://", "#")):
            continue
        if Path(href).is_absolute():
            E("ABSOLUTE_IMAGE_PATH", f"Image href must be portable and relative: {href}", target=f"image_{idx}")
        elif not (Path(path).parent / href).resolve().is_file():
            E("MISSING_IMAGE_FILE", f"Image href does not resolve from the SVG: {href}", target=f"image_{idx}")
        preserve = (node.get("preserveAspectRatio") or "xMidYMid meet").strip()
        if preserve == "none" or not re.search(r"\b(meet|slice)\b", preserve):
            E("IMAGE_ASPECT_DISTORTION",
              "Image must use preserveAspectRatio with meet or slice; 'none' stretches the bitmap",
              target=f"image_{idx}")

    # ── tspan line breaks break the PPT text parser ──
    tspans = re.findall(r"<tspan\b[^>]*>", content, re.I)
    if any("dy=" in t.lower() for t in tspans):
        E("TSPAN_LINEBREAK",
          "SVG uses <tspan> with dy for line breaks — causes PPT parse errors; use separate <text> elements",
          target="svg_structure")

    # ── Text: explicit fill / family / weight ──
    text_nodes = list(root.findall(".//{http://www.w3.org/2000/svg}text")) or list(root.findall(".//text"))
    font_families, font_sizes = [], []
    for idx, node in enumerate(text_nodes, 1):
        tid = f"text_{idx}"
        snippet = "".join(node.itertext()).strip()[:40]
        if node.get("fill") is None:
            E("MISSING_FILL", f"<text> missing explicit fill: '{snippet}…'", target=tid)
        if node.get("font-family") is None:
            W("MISSING_FONT_FAMILY", f"<text> missing explicit font-family: '{snippet}…'", target=tid)
        else:
            font_families.append(node.get("font-family").strip())
        fw = (node.get("font-weight") or "").strip()
        if fw and fw not in VALID_FONT_WEIGHTS:
            E("INVALID_FONT_WEIGHT", f"font-weight '{fw}' is not a valid value", target=tid)
        fs = parse_float(node.get("font-size"), 0)
        if fs > 0:
            font_sizes.append(fs)

    # ── Readability floor, per declared reading mode ──
    floor = MODE_FLOOR.get(page_mode, MODE_FLOOR[DEFAULT_MODE])
    for idx, node in enumerate(text_nodes, 1):
        fs = parse_float(node.get("font-size"), 0)
        if 0 < fs < floor:
            snippet = "".join(node.itertext()).strip()[:30]
            E("TEXT_BELOW_READABILITY_FLOOR",
              f"font-size {fs:.0f}px is below the {page_mode} floor of {floor:.0f}px "
              f"(≈{floor * 0.5:.0f}pt): '{snippet}…'",
              target=f"text_{idx}",
              hint="Raise the size, or declare this page as a 读 page if it is meant to be read up close.")

    # ── Text overlapping text: wrong on any page, any style ──
    if not quick_mode:
        text_boxes = []
        for idx, node in enumerate(text_nodes, 1):
            tbox = estimate_text_box(node, parent_map)
            if tbox[2] > 0:
                text_boxes.append((f"text_{idx}", tbox, "".join(node.itertext())[:30]))
        for i in range(len(text_boxes)):
            for j in range(i + 1, len(text_boxes)):
                tid_a, box_a, txt_a = text_boxes[i]
                tid_b, box_b, txt_b = text_boxes[j]
                if not intersects(box_a, box_b):
                    continue
                overlap_x = min(box_a[0] + box_a[2], box_b[0] + box_b[2]) - max(box_a[0], box_b[0])
                overlap_y = min(box_a[1] + box_a[3], box_b[1] + box_b[3]) - max(box_a[1], box_b[1])
                if overlap_x > 5 and overlap_y > 5:
                    W("TEXT_OVERLAP",
                      f"Text elements overlap: '{txt_a}…' and '{txt_b}…'",
                      target=tid_a,
                      detail=f"overlaps {tid_b} ({overlap_x:.0f}x{overlap_y:.0f}px)",
                      hint="Estimated boxes are approximate — confirm on the rendered PNG before rewriting the page.")

        # ── Safe margin: advisory only (full-bleed art direction is legitimate) ──
        for idx, node in enumerate(text_nodes, 1):
            tbox = estimate_text_box(node, parent_map)
            if tbox[2] > 0 and outside_safe_margin(tbox, margin):
                I("OUTSIDE_SAFE_MARGIN",
                  f"Text sits outside the {margin:.0f}px safe margin — verify on the PNG",
                  target=f"text_{idx}", detail=box_to_dict(tbox))

    # ── Nothing may leave the canvas ──
    for rect_node in (root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect")):
        rbox = rect_box(rect_node, parent_map)
        if rbox[2] > 0 and rbox[3] > 0:
            x, y, w, h = rbox
            if x + w > CANVAS_W + 5 or y + h > CANVAS_H + 5 or x < -5 or y < -5:
                E("ELEMENT_OUTSIDE_CANVAS",
                  f"<rect> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas "
                  f"{CANVAS_W:.0f}x{CANVAS_H:.0f}",
                  target="svg_structure", detail=box_to_dict(rbox))
    for img_node in image_nodes:
        ibox = image_box(img_node, parent_map)
        if ibox[2] > 0 and ibox[3] > 0:
            x, y, w, h = ibox
            if x + w > CANVAS_W + 5 or y + h > CANVAS_H + 5 or x < -5 or y < -5:
                E("IMAGE_OUTSIDE_CANVAS",
                  f"<image> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas",
                  target="svg_structure", detail=box_to_dict(ibox))

    # ── Empty / near-empty slide ──
    visible = sum(len(nodes) for nodes in (
        text_nodes,
        root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect"),
        image_nodes,
        root.findall(".//{http://www.w3.org/2000/svg}circle") or root.findall(".//circle"),
        root.findall(".//{http://www.w3.org/2000/svg}line") or root.findall(".//line"),
        root.findall(".//{http://www.w3.org/2000/svg}path") or root.findall(".//path"),
        root.findall(".//{http://www.w3.org/2000/svg}polygon") or root.findall(".//polygon"),
    ))
    if visible < 3:
        W("EMPTY_SLIDE", f"Page has only {visible} visible element(s) — appears empty or near-empty",
          target="svg_structure")

    all_issues = errors + warnings + infos
    if errors:
        status = "fail"
    elif warnings:
        status = "warning"
    else:
        status = "pass"
    return {
        "file": str(path),
        "page_mode": page_mode,
        "status": status,
        "summary": {"errors": len(errors), "warnings": len(warnings), "infos": len(infos)},
        "issues": all_issues,
    }


def select_svg_files(svg_path, manifest_data=None):
    if svg_path.is_file():
        return [svg_path]
    if not manifest_data:
        return sorted(svg_path.glob("*.svg"))
    return [svg_path / (p["page_key"] + ".svg") for p in manifest_data.get("pages", [])]


def main():
    parser = argparse.ArgumentParser(
        description="SVG → PPT conversion checks and real layout defects. No design-style heuristics."
    )
    parser.add_argument("svg_dir", help="Directory containing SVG files")
    parser.add_argument("--margin", type=float, default=MARGIN, help=f"Advisory safe margin in px (default: {MARGIN})")
    parser.add_argument("--output", default="", help="Output JSON path (default: stdout)")
    parser.add_argument("--file", default="", help="Single SVG file to validate (alternative to svg_dir)")
    parser.add_argument("--page-mode", default=DEFAULT_MODE, choices=sorted(MODE_FLOOR),
                        help="Reading mode for this page: 讲 (projected) or 读 (read up close)")
    parser.add_argument("--fidelity-template", default="", help="Optional reviewed fidelity template_registry.json")
    parser.add_argument("--self-check", action="store_true",
                        help="Skip text-overlap estimation; only hard conversion errors")
    args = parser.parse_args()

    if args.file:
        svg_path = Path(args.file)
        if not svg_path.is_file() or svg_path.suffix.lower() != ".svg":
            print(json.dumps({"status": "fail", "summary": {"errors": 1, "warnings": 0, "infos": 0},
                              "reports": [{"file": str(svg_path), "status": "fail",
                                           "issues": [issue("error", "INVALID_SVG_FILE",
                                                            f"Not a valid SVG file: {svg_path}")]}]},
                             ensure_ascii=False, indent=2))
            return 1
        svg_files, manifest_data = [svg_path], None
    else:
        svg_path = Path(args.svg_dir)
        svg_files = select_svg_files(svg_path, None)

    if not svg_files:
        print(json.dumps({"status": "fail", "summary": {"errors": 1, "warnings": 0, "infos": 0},
                          "reports": [{"file": str(svg_path), "status": "fail",
                                       "issues": [issue("error", "NO_SVG_FILES", "No SVG files found")]}]},
                         ensure_ascii=False, indent=2))
        return 1

    reports = [validate_file(f, page_mode=args.page_mode, margin=args.margin, quick_mode=args.self_check)
               for f in svg_files]

    if args.fidelity_template:
        try:
            fidelity_path = Path(args.fidelity_template).resolve()
            template = json.loads(fidelity_path.read_text(encoding="utf-8"))
            layouts = template.get("layouts", {})
            component_map = {item.get("component_id"): item for item in template.get("components", [])
                             if isinstance(item, dict)}
            strict_components = template.get("schema") == "planner.fidelity-template.v2"

            def fail(report, code, message, page_key):
                report["issues"].append(issue("error", code, message, target=page_key))
                report["summary"]["errors"] += 1
                report["status"] = "fail"

            for report in reports:
                page_key = Path(report["file"]).stem
                root = ET.parse(report["file"]).getroot()
                layout_id = root.attrib.get("data-layout-id", "")
                if not layout_id:
                    fail(report, "FIDELITY_LAYOUT_NOT_DECLARED",
                         "SVG does not declare data-layout-id", page_key)
                    continue
                layout = layouts.get(layout_id)
                if layout is None:
                    fail(report, "UNKNOWN_FIDELITY_LAYOUT",
                         f"SVG declares an unknown fidelity layout: {layout_id}", page_key)
                    continue
                canvas_file = layout.get("canvas_file", "")
                if strict_components and not canvas_file:
                    fail(report, "FIDELITY_CANVAS_NOT_BOUND",
                         f"Layout {layout_id} does not declare canvas_file", page_key)
                elif canvas_file:
                    canvas_path = fidelity_path.parent / canvas_file
                    if not canvas_path.is_file():
                        fail(report, "FIDELITY_CANVAS_MISSING",
                             f"Layout canvas is missing: {canvas_file}", page_key)
                    else:
                        expected_lock = layout.get("locked_sha256", "")
                        canvas_lock = locked_sha256(canvas_path)
                        page_lock = locked_sha256(Path(report["file"]))
                        if not expected_lock or canvas_lock != expected_lock:
                            fail(report, "FIDELITY_CANVAS_INTEGRITY_ERROR",
                                 f"Layout canvas lock hash is stale for {layout_id}", page_key)
                        elif page_lock != expected_lock:
                            fail(report, "FIDELITY_LOCKED_LAYER_MISMATCH",
                                 f"SVG changed the locked layer of canvas {layout_id}", page_key)
                used_nodes = {}
                for node in root.iter():
                    component_id = node.attrib.get("data-template-component")
                    if component_id:
                        used_nodes.setdefault(component_id, []).append(node)
                used = set(used_nodes)
                for component_id in sorted(used - set(component_map)):
                    fail(report, "UNKNOWN_FIDELITY_COMPONENT",
                         f"SVG uses unknown template component {component_id}", page_key)
                for component_id in layout.get("required_components", []):
                    if component_id not in used:
                        fail(report, "REQUIRED_FIDELITY_COMPONENT_MISSING",
                             f"Layout {layout_id} requires template component {component_id}", page_key)
                if strict_components:
                    for component_id, nodes in used_nodes.items():
                        component = component_map.get(component_id)
                        if not component:
                            continue
                        if component.get("geometry_policy", "fixed") == "fixed" and len(nodes) != 1:
                            fail(report, "FIDELITY_FIXED_COMPONENT_DUPLICATED",
                                 f"Fixed template component {component_id} must appear exactly once", page_key)
                        for node in nodes:
                            for code, message in fidelity_component_node_errors(component, node):
                                fail(report, code, message, page_key)
        except Exception as exc:
            reports[-1]["issues"].append(issue("error", "INVALID_FIDELITY_TEMPLATE", str(exc),
                                              target="fidelity_template"))
            reports[-1]["summary"]["errors"] += 1
            reports[-1]["status"] = "fail"

    total_errors = sum(r["summary"]["errors"] for r in reports)
    total_warnings = sum(r["summary"]["warnings"] for r in reports)
    total_infos = sum(r["summary"]["infos"] for r in reports)
    agg_status = "fail" if total_errors else ("warning" if total_warnings else "pass")

    summary = {
        "status": agg_status,
        "summary": {"errors": total_errors, "warnings": total_warnings, "infos": total_infos},
        "reports": reports,
    }

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
