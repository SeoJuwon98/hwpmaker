from __future__ import annotations

import re

from app.models.hwp_document import (
    BodyBlock,
    BulletBlock,
    DividerBlock,
    DocumentMeta,
    HeadingBlock,
    HwpBlock,
    HwpDocument,
    NoteBlock,
    OrderedBulletBlock,
    PageBreakBlock,
    TableBlock,
)

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_YAML_FIELD_RE = re.compile(r"^(\w+)\s*:\s*(.+)$", re.MULTILINE)

# Heading patterns
_H1_RE = re.compile(r"^#\s+(.+)$")
_H2_RE = re.compile(r"^##\s+(.+)$")
_H3_RE = re.compile(r"^###\s+(.+)$")

_HEADING_DECOR_RE = re.compile(r"^[□■◆◇▶►\s]+")
_HEADING_BRACKET_RE = re.compile(r"^\[(.+)\]$")


def _clean_heading(text: str) -> str:
    text = _HEADING_DECOR_RE.sub("", text).strip()
    m = _HEADING_BRACKET_RE.match(text)
    if m:
        text = m.group(1).strip()
    return text

# Bullet patterns
_BULLET_DEPTH0_RE = re.compile(r"^[○◎]\s+(.+)$")
_BULLET_DEPTH0_BARE_RE = re.compile(r"^-\s+(.+)$")    # indent 없는 - → 최상위
_BULLET_DEPTH0_NUM_RE = re.compile(r"^(?:\d+[.)]\s*|\(\d+\)\s*)(.+)$")  # 1. or (1)
_BULLET_DEPTH1_RE = re.compile(r"^ {2,}(-)\s+(.+)$")    # 2+ 공백 + -
_BULLET_DEPTH2_RE = re.compile(r"^ {4,}([·∙•-])\s+(.+)$")

# Ordered bullet (가나다라...) pattern
_GANA = "가나다라마바사아자차카타파하"
_ORDERED_BULLET_RE = re.compile(rf"^( {{2,}})?([{_GANA}])[.)]\s+(.+)$")

# Note pattern
_NOTE_RE = re.compile(r"^※\s*(.+)$")

# Table row pattern
_TABLE_ROW_RE = re.compile(r"^\|.+\|$")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-|:]+\|$")

# Divider / page break
_DIVIDER_RE = re.compile(r"^---\s*$")
_PAGEBREAK_RE = re.compile(r"^<!--\s*pagebreak\s*-->$", re.IGNORECASE)

_BACKTICK_RE = re.compile(r"`+")
_CODE_BLOCK_RE = re.compile(r"^```")


def _strip_backticks(text: str) -> str:
    return _BACKTICK_RE.sub("", text)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    fields = {m.group(1): m.group(2).strip() for m in _YAML_FIELD_RE.finditer(match.group(1))}
    rest = text[match.end():]
    return fields, rest


def _parse_table_block(lines: list[str], start: int) -> tuple[TableBlock | None, int]:
    """lines[start]부터 테이블을 파싱. (block, next_line_index) 반환."""
    i = start
    if i >= len(lines) or not _TABLE_ROW_RE.match(lines[i]):
        return None, start

    def _split_row(line: str) -> list[str]:
        cells = line.strip("|").split("|")
        return [c.strip() for c in cells]

    header_row = _split_row(lines[i])
    i += 1

    # separator 행
    if i < len(lines) and _TABLE_SEP_RE.match(lines[i]):
        i += 1
        headers = header_row
    else:
        headers = []
        i = start + 1  # no sep → no header, re-read from next line

    rows: list[list[str]] = []
    while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
        rows.append(_split_row(lines[i]))
        i += 1

    if not headers and not rows:
        return None, start + 1

    # 모든 행의 셀 수를 column_count에 맞게 정규화
    # 헤더가 있으면 헤더 기준, 없으면 최대 행 기준
    if headers:
        column_count = len(headers)
    else:
        column_count = max((len(r) for r in rows), default=0)
    for row in rows:
        if len(row) < column_count:
            row.extend([""] * (column_count - len(row)))
        elif len(row) > column_count:
            del row[column_count:]

    return TableBlock(headers=headers, rows=rows), i


def _parse_blocks(lines: list[str]) -> list[HwpBlock]:
    blocks: list[HwpBlock] = []
    i = 0
    prev_blank = False

    while i < len(lines):
        line = lines[i]

        if _CODE_BLOCK_RE.match(line.strip()):
            # 닫는 ``` 를 미리 탐색; 없으면 여는 줄만 스킵하고 나머지는 일반 텍스트로 처리
            close_idx = None
            for j in range(i + 1, len(lines)):
                if _CODE_BLOCK_RE.match(lines[j].strip()):
                    close_idx = j
                    break
            if close_idx is not None:
                i = close_idx + 1
            else:
                i += 1  # 여는 ``` 줄만 스킵
            prev_blank = False
            continue

        # --- blank line
        if not line.strip():
            prev_blank = True
            i += 1
            continue

        # --- page break
        if _PAGEBREAK_RE.match(line):
            blocks.append(PageBreakBlock())
            prev_blank = False
            i += 1
            continue

        # --- table
        if _TABLE_ROW_RE.match(line):
            table_block, i = _parse_table_block(lines, i)
            if table_block is not None:
                blocks.append(table_block)
            prev_blank = False
            continue

        # --- divider (standalone ---, not front matter)
        if _DIVIDER_RE.match(line):
            blocks.append(DividerBlock())
            prev_blank = False
            i += 1
            continue

        # --- headings (order: h3 before h2 before h1)
        m = _H3_RE.match(line)
        if m:
            blocks.append(HeadingBlock(level=3, text=_clean_heading(m.group(1))))
            prev_blank = False
            i += 1
            continue

        m = _H2_RE.match(line)
        if m:
            blocks.append(HeadingBlock(level=2, text=_clean_heading(m.group(1))))
            prev_blank = False
            i += 1
            continue

        m = _H1_RE.match(line)
        if m:
            blocks.append(HeadingBlock(level=1, text=_clean_heading(m.group(1))))
            prev_blank = False
            i += 1
            continue

        # --- ordered bullets (가나다라...)
        m = _ORDERED_BULLET_RE.match(line)
        if m:
            depth = 1 if m.group(1) else 0
            blocks.append(OrderedBulletBlock(marker=m.group(2), text=m.group(3).strip(), depth=depth))
            prev_blank = False
            i += 1
            continue

        # --- bullets
        m = _BULLET_DEPTH2_RE.match(line)
        if m:
            blocks.append(BulletBlock(depth=2, text=m.group(2).strip(), marker=m.group(1)))
            prev_blank = False
            i += 1
            continue

        m = _BULLET_DEPTH1_RE.match(line)
        if m:
            blocks.append(BulletBlock(depth=1, text=m.group(2).strip(), marker=m.group(1)))
            prev_blank = False
            i += 1
            continue

        m = _BULLET_DEPTH0_RE.match(line)
        if m:
            blocks.append(BulletBlock(depth=0, text=m.group(1).strip()))
            prev_blank = False
            i += 1
            continue

        m = _BULLET_DEPTH0_BARE_RE.match(line)
        if m:
            blocks.append(BulletBlock(depth=0, text=m.group(1).strip()))
            prev_blank = False
            i += 1
            continue

        m = _BULLET_DEPTH0_NUM_RE.match(line)
        if m:
            blocks.append(BulletBlock(depth=0, text=m.group(1).strip()))
            prev_blank = False
            i += 1
            continue

        # --- note
        m = _NOTE_RE.match(line)
        if m:
            blocks.append(NoteBlock(text=m.group(1).strip()))
            prev_blank = False
            i += 1
            continue

        # --- body / continuation
        stripped = _strip_backticks(line.strip())
        if not prev_blank and blocks and isinstance(blocks[-1], (BulletBlock, OrderedBulletBlock, BodyBlock)):
            blocks[-1].text += " " + stripped
        else:
            blocks.append(BodyBlock(text=stripped))
        prev_blank = False
        i += 1

    return blocks


def parse(md_text: str, title: str = "", organization: str = "", cover_image: bytes | None = None, cover_image_format: str = "png") -> HwpDocument:
    fm, body = _parse_front_matter(md_text)

    meta = DocumentMeta(
        title=fm.get("title", title) or title,
        organization=fm.get("organization", organization) or organization,
        date_label=fm.get("date", fm.get("date_label", "")),
        subtitle=fm.get("subtitle", ""),
        cover_image=cover_image,
        cover_image_format=cover_image_format,
    )

    raw_lines = body.splitlines()
    return HwpDocument(meta=meta, blocks=_parse_blocks(raw_lines))
