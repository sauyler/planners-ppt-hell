"""Advisory SVG text comparison against confirmed page_content, never a fact audit."""
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or ''))


def manuscript_text(value):
    value = re.sub(r'!\[[^\]]*\]\([^\n]*?\)', '', str(value or ''))
    value = re.sub(r'\[([^\]]+)\]\([^\n]*?\)', r'\1', value)
    value = re.sub(r'(?m)^\s{0,3}#{1,6}\s+', '', value)
    value = re.sub(r'(\*\*|__)(.+?)\1', r'\2', value)
    value = re.sub(r'(?<!\w)([*_])(.+?)\1(?!\w)', r'\2', value)
    return value.replace('`', '')


def audit_copy(root, document, page, svg_path, route):
    baseline = Path(root) / '_internal/01_content/page_content.json'
    result = {'status': 'unchecked', 'baseline': str(baseline), 'page_key': page['page_key'],
              'issues': [], 'suspect_text': [], 'structural_text': [],
              'scope': 'SVG text additions only; excludes raster text, omissions and factual accuracy'}
    if page.get('copy_confirmed') is not True:
        result['reason'] = 'Current page title/content are not marked copy_confirmed.'
        return result
    manifest_path = Path(root) / '_internal/00_project/page_manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    binding = manifest.get('visual_plan', {}) if route == 'video' else manifest.get('input_binding', {}).get('upstream', {}).get('deliverable', {})
    source_path = binding.get('path') or document.get('source_path')
    expected = binding.get('sha256') or document.get('source_sha256')
    if source_path and expected:
        source = Path(source_path)
        if not source.is_absolute():
            source = Path(root) / source
        try:
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError('Source changed; refresh confirmed page content before comparing.')
        except (OSError, ValueError) as exc:
            result['reason'] = str(exc)
            return result
        result['source'] = str(source)
    # Video titles may be scene names. Only screen content is authorized for that route.
    fields = [page.get('content', '')]
    if route == 'slides':
        fields.insert(0, page.get('title', ''))
    allowed = normalized('\n'.join(manuscript_text(x) for x in fields))
    result['baseline_sha256'] = hashlib.sha256(allowed.encode()).hexdigest()
    tree = ET.parse(svg_path).getroot()
    runs = []
    def visit(node, hidden=False):
        tag = node.tag.split('}')[-1]
        hidden = hidden or tag in {'defs', 'clipPath', 'mask', 'pattern', 'symbol', 'metadata', 'title', 'desc'}
        hidden = hidden or node.get('display') == 'none' or bool(re.search(r'display\s*:\s*none', node.get('style', '')))
        if tag == 'text' and not hidden:
            text = ''.join(node.itertext())
            value = normalized(text)
            if value:
                runs.append((node.get('data-workbench-id') or node.get('id'), text, value))
            return
        for child in node:
            visit(child, hidden)
    visit(tree)
    for identity, text, value in runs:
        entry = {'element_id': identity, 'text': text}
        if re.fullmatch(r'(?:\d{1,2}[.)、]?|[•·●○▪■□→←↑↓↔—–─|/]+)', value):
            result['structural_text'].append(entry)
        elif value not in allowed:
            result['suspect_text'].append(entry)
    result['status'] = 'warning' if result['suspect_text'] else 'matched'
    if result['suspect_text']:
        result['issues'] = [{'code': 'COPY_NOT_IN_BASELINE', 'message': 'SVG contains text not found in the confirmed page copy; review additions or authorized revisions.'}]
    return result
