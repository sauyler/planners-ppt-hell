"""SVG 页内 `<style>` / `:root` 变量展开 —— 审阅工作台与 PPT 转换共用这一份实现。

同一个 SVG 文件有两个消费方：审阅工作台（内联进 HTML 预览）与 PPT 转换器。
两边曾经各写一套：转换器会把 `.class` 规则和 `var(--token)` 展开成字面属性，
工作台则直接拒绝任何 `<style>`。同一条文档承诺（`svg_rules.md` §2「双出口原生支持」）
于是在必经的审阅路径上失效。这里把展开逻辑收成唯一实现，两边都 import 它。

对外只有两个动作：
  · `inline_svg_styles_and_vars(root)` —— 把规则、`style=""`、`var(--…)` 落到元素属性上；
  · `strip_style_elements(root)` —— 展开之后把 `<style>` 节点摘掉，避免它跟着内联进宿主页面，
    把规则泄漏到别的页或宿主自身。
"""

import re

_XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_STYLE_ELEMENT_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CSS_VAR_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*([^()]*))?\)")


def _css_declarations(text):
    declarations = {}
    for piece in str(text or "").split(";"):
        if ":" not in piece:
            continue
        prop, value = piece.split(":", 1)
        prop = prop.strip()
        if not prop.startswith("--"):
            prop = prop.lower()
        value = value.strip()
        if prop and value:
            declarations[prop] = value
    return declarations


def _resolve_var_string(value, custom_props):
    """Expand var(--token, fallback) references up to 10 levels deep."""
    if not value or "var(" not in str(value):
        return value
    resolved = str(value)
    for _ in range(10):
        if "var(" not in resolved:
            break
        changed = False

        def _repl(match):
            nonlocal changed
            token = match.group(1)
            fallback = match.group(2)
            if token in custom_props:
                changed = True
                return custom_props[token]
            if fallback is not None and fallback.strip():
                changed = True
                return fallback.strip()
            return match.group(0)

        resolved = _CSS_VAR_RE.sub(_repl, resolved)
        if not changed:
            break
    return resolved


def _simple_compound_matches(node, compound):
    """Check if a single selector compound (e.g. 'text.title#hero' or '.card' or ':root') matches node."""
    if compound in (":root", "svg"):
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
        return tag == "svg"
    tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
    node_id = (node.attrib.get("id") or "").strip()
    node_classes = set((node.attrib.get("class") or "").split())

    # Extract tag if present at start
    m_tag = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)", compound)
    if m_tag and m_tag.group(1) != tag:
        return False
    for m_id in re.findall(r"#([A-Za-z_][-\w]*)", compound):
        if m_id != node_id:
            return False
    for m_cls in re.findall(r"\.([A-Za-z_][-\w]*)", compound):
        if m_cls not in node_classes:
            return False
    return bool(m_tag or "#" in compound or "." in compound)


def _selector_matches_node(node, parent_map, compounds):
    """Match descendant selector compounds from right to left."""
    current = node
    for index, compound in enumerate(reversed(compounds)):
        if index == 0:
            if not _simple_compound_matches(current, compound):
                return False
        else:
            while current is not None and not _simple_compound_matches(current, compound):
                current = parent_map.get(current)
            if current is None:
                return False
        current = parent_map.get(current)
    return True


def inline_svg_styles_and_vars(root, raw_svg_text=None):
    """Expand inline <style> rules, inline style='' attributes, and :root CSS variables (var(--...))
    directly onto SVG DOM element attributes before PPT conversion.
    """
    style_blocks = []
    if raw_svg_text:
        style_blocks.extend(_STYLE_ELEMENT_RE.findall(_XML_COMMENT_RE.sub("", raw_svg_text)))
    for node in root.iter():
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
        if tag == "style":
            txt = "".join(node.itertext())
            if txt and txt not in style_blocks:
                style_blocks.append(txt)

    rules = []
    custom_props = {}

    for block in style_blocks:
        clean_block = _CSS_COMMENT_RE.sub("", block)
        for match in _CSS_RULE_RE.finditer(clean_block):
            decls = _css_declarations(match.group(2))
            if not decls:
                continue
            for k, v in decls.items():
                if k.startswith("--"):
                    custom_props[k] = v
            selectors = []
            for part in match.group(1).split(","):
                compounds = [c.strip() for c in part.strip().split() if c.strip()]
                if compounds:
                    selectors.append(compounds)
            if selectors:
                rules.append((selectors, decls))

    for node in root.iter():
        for k, v in _css_declarations(node.attrib.get("style")).items():
            if k.startswith("--"):
                custom_props[k] = v

    # Resolve transitive var(--...) inside custom_props
    for _ in range(10):
        changed = False
        for k, v in list(custom_props.items()):
            new_v = _resolve_var_string(v, custom_props)
            if new_v != v:
                custom_props[k] = new_v
                changed = True
        if not changed:
            break

    parent_map = {child: parent for parent in root.iter() for child in parent}

    for node in root.iter():
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
        if tag == "style":
            continue

        # 1. Apply matched <style> rules (if attribute not explicitly set on element)
        if rules:
            matched_props = {}
            for selectors, decls in rules:
                if any(_selector_matches_node(node, parent_map, comp) for comp in selectors):
                    for k, v in decls.items():
                        if not k.startswith("--"):
                            matched_props[k] = v
            for k, v in matched_props.items():
                if k not in node.attrib:
                    node.set(k, v)

        # 2. Apply inline style="..." declarations (overrides element attributes)
        inline_decls = _css_declarations(node.attrib.get("style"))
        for k, v in inline_decls.items():
            if not k.startswith("--"):
                node.set(k, v)

        # 3. Expand var(--...) across all attributes on node
        for attr_k, attr_v in list(node.attrib.items()):
            if "var(" in str(attr_v):
                node.set(attr_k, _resolve_var_string(attr_v, custom_props))

    return custom_props


def strip_style_elements(root):
    """摘掉所有 `<style>` 节点，返回摘掉的个数。

    只在 `inline_svg_styles_and_vars` 之后调用：此时规则已经落到元素属性上，
    留着 `<style>` 只会让内联进宿主文档的 CSS 互相污染。
    """
    removed = 0
    for parent in list(root.iter()):
        for child in list(parent):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "style":
                parent.remove(child)
                removed += 1
    return removed


UNRESOLVED_VAR = re.compile(r"var\(")


def expand_for_inline(root, raw_svg_text=None):
    """审阅工作台入口：展开 → 摘 style → 复查没有残留的 `var(`。

    残留的 `var(--x)` 意味着页内引用了没定义的 token；浏览器会静默丢掉这条声明，
    页面看着「突然没颜色了」。这里让它当场报错，并点名是哪个元素的哪个属性。
    """
    inline_svg_styles_and_vars(root, raw_svg_text=raw_svg_text)
    strip_style_elements(root)
    leftovers = []
    for node in root.iter():
        for key, value in node.attrib.items():
            if UNRESOLVED_VAR.search(str(value)):
                leftovers.append((node.tag.split("}")[-1], node.get("id") or "", key, value))
    if leftovers:
        detail = ", ".join(f"<{tag} id={i or '-'}> {k}={v!r}" for tag, i, k, v in leftovers[:5])
        raise ValueError(f"undefined CSS variable left after expansion: {detail}")
