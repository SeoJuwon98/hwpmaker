from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass
class DocumentMeta:
    title: str
    organization: str = ""
    date_label: str = ""
    subtitle: str = ""
    cover_image: bytes | None = None
    cover_image_format: str = "png"


@dataclass
class HeadingBlock:
    level: int  # 1=# (Ⅰ.), 2=## (□), 3=### (1)
    text: str


@dataclass
class BulletBlock:
    depth: int  # 0=○, 1=-, 2=·
    text: str
    marker: str | None = None


@dataclass
class NoteBlock:
    text: str  # ※ 주석


@dataclass
class BodyBlock:
    text: str  # 일반 문단


@dataclass
class PageBreakBlock:
    pass


@dataclass
class DividerBlock:
    pass


@dataclass
class TableBlock:
    headers: list[str]
    rows: list[list[str]]  # ^^ = 위 셀과 병합 (세로)
    title: str = ""


@dataclass
class OrderedBulletBlock:
    marker: str  # 가, 나, 다, ...
    text: str
    depth: int = 0  # 0=최상위, 1=하위


HwpBlock = Union[
    HeadingBlock, BulletBlock, OrderedBulletBlock, NoteBlock, BodyBlock,
    PageBreakBlock, DividerBlock, TableBlock,
]


@dataclass
class HwpDocument:
    meta: DocumentMeta
    blocks: list[HwpBlock] = field(default_factory=list)
