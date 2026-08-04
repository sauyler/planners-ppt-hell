#!/usr/bin/env python3
"""Normalize Markdown or DOCX input and register every source image."""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((<[^>]+>|[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def image_size(data, suffix):
    """Return pixel dimensions for common web images without optional packages."""
    try:
        suffix = suffix.lower()
        if suffix == ".png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if suffix in {".gif"} and data[:6] in {b"GIF87a", b"GIF89a"}:
            return struct.unpack("<HH", data[6:10])
        if suffix in {".jpg", ".jpeg"} and data[:2] == b"\xff\xd8":
            index = 2
            while index + 9 < len(data):
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                index += 2
                if marker in {0xD8, 0xD9}:
                    continue
                length = struct.unpack(">H", data[index:index + 2])[0]
                if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    height, width = struct.unpack(">HH", data[index + 3:index + 7])
                    return width, height
                index += length
    except (IndexError, struct.error, ValueError):
        pass
    return None, None


class AssetWriter:
    def __init__(self, project_root, output_root):
        self.project_root = Path(project_root)
        self.output_root = Path(output_root)
        self.asset_dir = self.output_root / "assets"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.assets = []
        self.by_sha = {}

    def add(self, data, suffix, original_ref, alt="", source_kind="markdown", external=False):
        digest = sha256_bytes(data)
        if digest in self.by_sha:
            asset = self.by_sha[digest]
            asset.setdefault("occurrences", []).append({"original_ref": original_ref, "alt": alt})
            return asset
        suffix = suffix.lower() if suffix else ".bin"
        if suffix == ".jpeg":
            suffix = ".jpg"
        asset_id = f"asset_{len(self.assets) + 1:03d}"
        output = self.asset_dir / f"{asset_id}{suffix}"
        output.write_bytes(data)
        width, height = image_size(data, suffix)
        rel = output.relative_to(self.project_root).as_posix()
        asset = {
            "asset_id": asset_id,
            "source_kind": source_kind,
            "original_ref": original_ref,
            "normalized_path": rel,
            "mime_type": mimetypes.guess_type(output.name)[0] or "application/octet-stream",
            "sha256": digest,
            "width_px": width,
            "height_px": height,
            "aspect_ratio": round(width / height, 6) if width and height else None,
            "alt": alt,
            "external": external,
            "occurrences": [{"original_ref": original_ref, "alt": alt}],
        }
        self.assets.append(asset)
        self.by_sha[digest] = asset
        return asset

    def add_external(self, url, alt=""):
        asset_id = f"asset_{len(self.assets) + 1:03d}"
        asset = {
            "asset_id": asset_id,
            "source_kind": "markdown_external",
            "original_ref": url,
            "normalized_path": "",
            "mime_type": "",
            "sha256": "",
            "width_px": None,
            "height_px": None,
            "aspect_ratio": None,
            "alt": alt,
            "external": True,
            "occurrences": [{"original_ref": url, "alt": alt}],
        }
        self.assets.append(asset)
        return asset


def normalize_markdown(source, writer):
    text = source.read_text(encoding="utf-8")

    def replace(match):
        alt = match.group(1).strip()
        raw_ref = match.group(2).strip()
        ref = raw_ref[1:-1] if raw_ref.startswith("<") and raw_ref.endswith(">") else raw_ref
        if re.match(r"^(?:https?:)?//", ref):
            writer.add_external(ref, alt)
            return match.group(0)
        candidate = Path(ref).expanduser()
        if not candidate.is_absolute():
            candidate = (source.parent / candidate).resolve()
        if not candidate.is_file():
            raise ValueError(f"Markdown image is missing: {ref}")
        asset = writer.add(candidate.read_bytes(), candidate.suffix, ref, alt, "markdown")
        normalized = Path(asset["normalized_path"])
        rel = os.path.relpath(writer.project_root / normalized, writer.output_root).replace(os.sep, "/")
        return f"![{alt}]({rel})"

    return IMAGE_RE.sub(replace, text)


def docx_relationships(archive):
    root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    return {
        rel.attrib.get("Id"): rel.attrib.get("Target")
        for rel in root.findall(f"{{{PR_NS}}}Relationship")
    }


def normalize_docx(source, writer):
    lines = []
    with zipfile.ZipFile(source) as archive:
        rels = docx_relationships(archive)
        document = ET.fromstring(archive.read("word/document.xml"))
        body = document.find(f"{{{W_NS}}}body")
        if body is None:
            raise ValueError("DOCX has no document body")
        for paragraph in body.iterfind(f".//{{{W_NS}}}p"):
            style = paragraph.find(f"./{{{W_NS}}}pPr/{{{W_NS}}}pStyle")
            style_name = style.attrib.get(f"{{{W_NS}}}val", "") if style is not None else ""
            pieces = []
            for node in paragraph.iter():
                if node.tag == f"{{{W_NS}}}t" and node.text:
                    pieces.append(node.text)
                elif node.tag == f"{{{A_NS}}}blip":
                    rid = node.attrib.get(f"{{{R_NS}}}embed")
                    target = rels.get(rid, "")
                    member = f"word/{target}".replace("word/../", "")
                    if not target or member not in archive.namelist():
                        continue
                    data = archive.read(member)
                    doc_pr = paragraph.find(f".//{{{WP_NS}}}docPr")
                    alt = ""
                    if doc_pr is not None:
                        alt = doc_pr.attrib.get("descr") or doc_pr.attrib.get("name") or ""
                    asset = writer.add(data, Path(target).suffix, target, alt, "docx")
                    normalized = Path(asset["normalized_path"])
                    rel = os.path.relpath(writer.project_root / normalized, writer.output_root).replace(os.sep, "/")
                    pieces.append(f"\n\n![{alt}]({rel})\n\n")
            content = "".join(pieces).strip()
            if not content:
                continue
            heading = re.match(r"Heading\s*([1-6])", style_name, re.I)
            if heading:
                content = f"{'#' * int(heading.group(1))} {content}"
            elif style_name.lower() == "title":
                content = f"# {content}"
            lines.append(content)
    return "\n\n".join(lines).strip() + "\n"


def prepare_source_material(project_root, source, output_root=None):
    project_root = Path(project_root).resolve()
    source = Path(source).expanduser().resolve()
    output_root = Path(output_root) if output_root else project_root / "_internal" / "00_project" / "source"
    output_root.mkdir(parents=True, exist_ok=True)
    writer = AssetWriter(project_root, output_root)
    suffix = source.suffix.lower()
    if suffix in {".md", ".markdown"}:
        normalized = normalize_markdown(source, writer)
        source_type = "markdown"
    elif suffix == ".docx":
        normalized = normalize_docx(source, writer)
        source_type = "docx"
    elif suffix == ".doc":
        soffice = shutil.which("soffice")
        if not soffice:
            raise ValueError("Legacy .doc requires LibreOffice/soffice for loss-minimized conversion to DOCX.")
        with tempfile.TemporaryDirectory(prefix="ppt-hell-doc-") as temp:
            completed = subprocess.run(
                [soffice, "--headless", "--convert-to", "docx", "--outdir", temp, str(source)],
                capture_output=True,
                text=True,
            )
            converted = Path(temp) / f"{source.stem}.docx"
            if completed.returncode or not converted.is_file():
                details = (completed.stderr or completed.stdout or "").strip()
                raise ValueError(f"Could not convert legacy .doc to DOCX: {details}")
            normalized = normalize_docx(converted, writer)
        source_type = "doc"
    else:
        raise ValueError("Source must be Markdown (.md/.markdown) or Word (.doc/.docx).")

    normalized_path = output_root / "source.md"
    normalized_path.write_text(normalized, encoding="utf-8")
    manifest = {
        "schema": "planners-ppt-hell.source-assets.v1",
        "source_type": source_type,
        "original_source": str(source),
        "normalized_source": normalized_path.relative_to(project_root).as_posix(),
        "has_images": bool(writer.assets),
        "image_count": len(writer.assets),
        "assets": writer.assets,
    }
    manifest_path = output_root / "source_assets.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Normalize Markdown/DOCX and extract source images.")
    parser.add_argument("project_dir")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-root", default="")
    args = parser.parse_args()
    root = Path(args.project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    output_root = Path(args.output_root).expanduser().resolve() if args.output_root else None
    try:
        manifest = prepare_source_material(root, args.source, output_root)
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
