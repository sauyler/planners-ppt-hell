#!/usr/bin/env python3
"""项目画幅的唯一解析入口；缺省常量仅用于旧项目和示例。

项目选择存于 page_manifest.json.canvas；快照冻结该值。
模板、校验与输出消费该选择，不各自决定画幅。
"""

# ── 画幅本体 ──
FRAME_LABEL = "16:9"
FRAME_W = 1920.0
FRAME_H = 1080.0
FRAME_W_INT = int(FRAME_W)
FRAME_H_INT = int(FRAME_H)
FRAME_VIEWBOX = f"0 0 {FRAME_W_INT} {FRAME_H_INT}"
FRAME_SIZE_ATTRS = f'width="{FRAME_W_INT}" height="{FRAME_H_INT}"'

# 画布 px → 幻灯片 pt 的换算：1920px 对应 13.333in 宽，所以 1px = 0.5pt。
# 见 references/domain/svg_rules.md。
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5
SVG_PX_TO_PT = SLIDE_W_IN * 72 / FRAME_W

# ── 画幅派生的版式度量 ──
# 下面这些数字只在当前画幅下有意义，所以和画幅放在一起：改画幅时必须一起复核。
FULL_BLEED_W = 1780.0    # 达到这个尺寸的矩形算整页底／满版块，不计入等面积容器
FULL_BLEED_H = 1040.0
CONTAINER_MIN_W = 200.0  # 小于这个尺寸的矩形不算容器
CONTAINER_MIN_H = 120.0
BODY_TEXT_MAX_Y = 1000.0  # y 超过它的 text 归页脚／页码，不计入正文底部
FOOTER_RULE_Y = 986.0     # 页脚规则的基线位置；正文底部与它之差就是底部空档
SMALL_TEXT_MAX_PX = 22.0  # 不超过它的字号算小字，参与跨页基线统计


from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Canvas:
    width: int = FRAME_W_INT
    height: int = FRAME_H_INT

    def __post_init__(self):
        for value in (self.width, self.height):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("Canvas width and height must be positive integers")

    @property
    def viewbox(self):
        return f"0 0 {self.width} {self.height}"

    def as_dict(self):
        return {"width": self.width, "height": self.height}


def frame_from_manifest(manifest):
    value = manifest.get("canvas")
    if value is None:
        return Canvas()
    if not isinstance(value, dict) or set(value) != {"width", "height"}:
        raise ValueError("canvas must contain width and height")
    return Canvas(**value)


def project_frame(root):
    path = Path(root) / "_internal/00_project/page_manifest.json" if root else None
    return frame_from_manifest(json.loads(path.read_text())) if path and path.is_file() else Canvas()


def svg_frame(path):
    """Read the dimensions already declared by an SVG, including frozen artifacts."""
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    values = [float(root.get(name, default)) for name, default in (("width", FRAME_W), ("height", FRAME_H))]
    if any(not value.is_integer() for value in values):
        raise ValueError("SVG canvas dimensions must be integer pixels")
    return Canvas(*(int(value) for value in values))
