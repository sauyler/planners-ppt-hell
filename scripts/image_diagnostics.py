"""Shared intrinsic image/slot measurements; fit warnings never veto a design."""
import base64
import io
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote_to_bytes


def number(value):
    match = re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?:px)?\s*', str(value or ''))
    result = float(match[1]) if match else None
    return result if result is not None and math.isfinite(result) else None


def dimensions(data):
    # Pillow reads metadata only; EXIF transpose matches browser-oriented dimensions.
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if image.getexif().get(274) in {5, 6, 7, 8}:
                width, height = height, width
            return width, height
    except (ImportError, OSError, ValueError):
        pass
    try:
        root = ET.fromstring(data)
        if root.tag.split('}')[-1] != 'svg':
            return None
        width, height = number(root.get('width')), number(root.get('height'))
        if width and height:
            return width, height
        box = [float(x) for x in re.split(r'[ ,]+', root.get('viewBox', '').strip())]
        if len(box) == 4 and all(math.isfinite(x) for x in box) and box[2] > 0 and box[3] > 0:
            return box[2], box[3]
    except (ET.ParseError, ValueError):
        pass
    return None


def image_frames(path):
    """Use href relative to this exact SVG; no filename or project-path guessing."""
    path = Path(path)
    root = ET.parse(path).getroot()
    result = []

    def visit(node, hidden=False):
        hidden = hidden or node.tag.split('}')[-1] in {'defs', 'clipPath', 'mask', 'pattern', 'symbol'}
        if node.tag.split('}')[-1] == 'image' and not hidden:
            href = node.get('href', node.get('{http://www.w3.org/1999/xlink}href', ''))
            slot = {key: number(node.get(key, '0' if key in {'x', 'y'} else '')) for key in ('x', 'y', 'width', 'height')}
            fit = 'slice' if 'slice' in node.get('preserveAspectRatio', '') else 'meet'
            row = {'element_id': node.get('data-workbench-id') or node.get('id') or f'image_{len(result)+1}',
                   'href': href.split(',', 1)[0] + ',<embedded>' if href.startswith('data:') else href, 'slot': slot, 'fit': fit, 'status': 'unmeasured', 'issues': []}
            result.append(row)
            try:
                if href.startswith('data:'):
                    header, payload = href.split(',', 1)
                    data = base64.b64decode(payload, validate=True) if ';base64' in header else unquote_to_bytes(payload)
                elif href and not re.match(r'^[a-zA-Z][\w+.-]*:|^#', href):
                    data = (path.parent / href).read_bytes()
                else:
                    raise ValueError('Image is not a local file or data URI')
                size = dimensions(data)
                if not size or min(size) <= 0:
                    raise ValueError('Image dimensions unavailable')
                row['source'] = {'width': size[0], 'height': size[1]}
                w, h = slot['width'], slot['height']
                if w is None or h is None or min(w, h) <= 0:
                    raise ValueError('Slot dimensions require positive numeric SVG units')
                if 'none' in node.get('preserveAspectRatio', '').split():
                    raise ValueError('Stretched image; meet/slice measurement does not apply')
                ratio = (w / h) / (size[0] / size[1])
                mismatch = max(ratio, 1 / ratio)
                fraction = 1 / mismatch
                row.update(status='measured', aspect_mismatch=round(mismatch, 4),
                           source_visible_fraction=round(fraction if fit == 'slice' else 1, 4),
                           slot_fill_fraction=round(fraction if fit == 'meet' else 1, 4))
                if fit == 'slice' and mismatch > 1.5:
                    row['issues'].append({'code': 'IMAGE_CROP_RISK', 'message': f'Slice retains about {fraction:.0%} of source area; inspect the subject.'})
                elif fit == 'meet' and fraction < .6:
                    row['issues'].append({'code': 'IMAGE_LOW_FILL', 'message': f'Meet fills about {fraction:.0%} of slot area; inspect intended whitespace.'})
            except (OSError, ValueError) as exc:
                row['reason'] = str(exc)
                row['issues'].append({'code': 'IMAGE_FIT_UNMEASURED', 'message': str(exc)})
        for child in node:
            visit(child, hidden)
    visit(root)
    return result
