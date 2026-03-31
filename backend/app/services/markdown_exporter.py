from __future__ import annotations

import re
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from xml.etree import ElementTree as ET

from app.core.logger import get_logger

logger = get_logger("api.exporter")

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
from app.services.document_theme import DocumentTheme, ParagraphStyleRefs, get_default_document_theme
from app.services.report_hwpx import ReportHwpxBuilder, ReportSection

# ── 섹션 구분선 ────────────────────────────────────────────────────
_SECTION_LINE = "━" * 25

_BULLET_STYLE: dict[int, str] = {
    0: "bullet",
    1: "bullet_1",
    2: "bullet_2",
}

_NOTE_STYLE = "note"
_BODY_STYLE = "body_spaced"

# 불릿 기호 (depth → 접두어)
_BULLET_PREFIX: dict[int, str] = {
    0: "○ ",
    1: "- ",
    2: "· ",
}

class MarkdownExporter:
    """HwpDocument(마크다운 파서 결과)를 HWPX로 렌더링."""

    _CONTENT_HPF_PATH = "Contents/content.hpf"
    _SECTION_0_PATH = "Contents/section0.xml"
    _HP_NS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    _TABLE_MAX_WIDTH = 42000
    _TABLE_COL_MIN_WIDTH = 4500
    _TABLE_DEFAULT_ROW_HEIGHT = 3000

    def __init__(self, theme: DocumentTheme | None = None) -> None:
        self.theme = theme or get_default_document_theme()
        self._header_template_path = self.theme.header_template_path

    def export_markdown(self, *, target_path: Path, document: HwpDocument) -> None:
        hwpx_document = ReportHwpxBuilder(header_template_path=self._header_template_path)
        target_section = hwpx_document.sections[0]

        self._render_md_cover(hwpx_document, target_section, document.meta)

        self._h1_count = 0
        self._shifted_h3_context = False
        blocks = document.blocks
        for i, block in enumerate(blocks):
            if isinstance(block, HeadingBlock):
                if block.level == 3:
                    self._shifted_h3_context = True
                elif block.level <= 2:
                    self._shifted_h3_context = False
            prev_block = blocks[i - 1] if i > 0 else None
            next_block = blocks[i + 1] if i < len(blocks) - 1 else None
            self._render_block(hwpx_document, target_section, block, prev_block, next_block)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        hwpx_document.write(str(target_path), validate=True)
        self._compact_cover_secpr(target_path)
        self._inject_reference_header(target_path, document.meta.title)

    # ── cover ────────────────────────────────────────────────────────

    def _render_md_cover(self, hwpx_document: ReportHwpxBuilder, section: ReportSection, meta: DocumentMeta) -> None:
        _W = 42000
        _NO_BORDER = self.theme.table_border_fills["cover_bg"]  # fill id=1, 테두리/배경 없음

        # 고정 높이 구성 (A4 콘텐츠 높이 65762 기준)
        # 순서: 제목 → 여백 → 이미지 → 여백 → 기관명
        _TITLE_H   = 15000   # ~53mm
        _SPACER1_H = 10000   # ~35mm
        _IMG_H     = 13000   # ~46mm
        _SPACER2_H = 13762   # ~49mm
        _META_H    = 14000   # ~49mm  (항상 하단 고정)

        # 표지 전체를 1컬럼 5행 테이블로 구성
        cover_tbl = self._add_cover_table(
            hwpx_document, section, rows=5, cols=1, width=_W, border_fill_id_ref=_NO_BORDER
        )
        self._set_table_inner_margin(cover_tbl, 0, 0, 0, 0)

        def _blank_cell(row: int, height: int):
            cell = cover_tbl.cell(row, 0)
            cell.set_size(width=_W, height=height)
            cell.element.set("borderFillIDRef", _NO_BORDER)
            return cell

        # ── Row 0: 제목 + 부제목 ──────────────────────────────────────
        title_cell = _blank_cell(0, _TITLE_H)
        self._set_cell_para(title_cell, meta.title, "cover_title", first=True)
        if meta.subtitle:
            self._set_cell_para(title_cell, meta.subtitle, "cover_subtitle", first=False)

        # ── Row 1: 여백 ───────────────────────────────────────────────
        _blank_cell(1, _SPACER1_H)

        # ── Row 2: 이미지 (없으면 빈 셀 유지, 높이 동일) ─────────────
        img_cell = _blank_cell(2, _IMG_H)
        if meta.cover_image:
            item_id, img_w, img_h = self._embed_cover_image(
                hwpx_document, meta.cover_image, meta.cover_image_format
            )
            if item_id:
                disp_w, disp_h = self._fit_image(_W // 2, _IMG_H, img_w, img_h)
                img_para = img_cell.paragraphs[0] if img_cell.paragraphs else img_cell.append_paragraph("")
                img_para.para_pr_id_ref = "24"  # CENTER 정렬
                self._insert_cover_pic(img_para, item_id, disp_w, disp_h)

        # ── Row 3: 여백 ───────────────────────────────────────────────
        _blank_cell(3, _SPACER2_H)

        # ── Row 4: 기관명 / 날짜 — HY헤드라인M 30pt 중앙 정렬 (고정 위치) ─
        meta_cell = _blank_cell(4, _META_H)
        refs = self.theme.paragraph_styles["cover_org_hy"]
        items = [t for t in [meta.date_label, meta.organization] if t]
        if items:
            # 첫 번째 항목: 셀 기본 단락 재사용 (_set_cell_text가 run 스타일까지 적용)
            self._set_cell_text(meta_cell, items[0], "cover_org_hy", _NO_BORDER)
        for text in items[1:]:
            # 추가 항목: 새 단락 추가 후 스타일 직접 주입
            p2 = meta_cell.append_paragraph(
                "", para_pr_id_ref=refs.para_pr_id_ref, char_pr_id_ref=refs.char_pr_id_ref
            )
            self._apply_paragraph_refs(p2, refs)
            for run in list(p2.runs):
                run.remove()
            p2.append_text(text, char_pr_id_ref=refs.char_pr_id_ref)

        # pageBreak는 첫 H1 테이블 단락에 걸어서 처리 (빈 줄 방지)

    def _set_cell_para(self, cell, text: str, slot_name: str, *, first: bool) -> None:
        """셀 안에 스타일이 적용된 단락을 추가. first=True면 기존 첫 단락을 재사용."""
        refs = self.theme.paragraph_styles[slot_name]
        if first:
            paras = cell.paragraphs
            para = paras[0] if paras else cell.append_paragraph(
                "", para_pr_id_ref=refs.para_pr_id_ref, char_pr_id_ref=refs.char_pr_id_ref
            )
            para.para_pr_id_ref = refs.para_pr_id_ref
            para.style_id_ref = refs.style_id_ref
            para.char_pr_id_ref = refs.char_pr_id_ref
            for run in list(para.runs):
                run.remove()
        else:
            para = cell.append_paragraph(
                "", para_pr_id_ref=refs.para_pr_id_ref, char_pr_id_ref=refs.char_pr_id_ref
            )
        para.append_text(text, char_pr_id_ref=refs.char_pr_id_ref)

    @staticmethod
    def _read_image_size(data: bytes) -> tuple[int, int]:
        """PIL 없이 PNG/JPEG 헤더에서 픽셀 크기 읽기."""
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(data))
            return img.size
        except Exception:
            pass
        # PNG: 시그니처 8바이트 후 IHDR 청크 (너비4 높이4)
        if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
            import struct
            w, h = struct.unpack('>II', data[16:24])
            return w, h
        # JPEG: SOF 마커에서 높이/너비 파싱
        if data[:2] == b'\xff\xd8' and len(data) > 4:
            import struct
            i = 2
            while i < len(data) - 8:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2):  # SOF0/SOF1/SOF2
                    h, w = struct.unpack('>HH', data[i + 5:i + 9])
                    return w, h
                i += 2 + seg_len
        return 0, 0

    def _embed_cover_image(self, hwpx_document: ReportHwpxBuilder, image_data: bytes, image_format: str) -> tuple[str | None, int, int]:
        """이미지를 embed하고 (manifest_item_id, pixel_w, pixel_h) 반환."""
        img_w, img_h = self._read_image_size(image_data)

        try:
            image_index = len(hwpx_document.binary_assets) + 1
            manifest_id = hwpx_document.register_binary_asset(image_data, image_format, asset_id=f"image{image_index}")
            return manifest_id, img_w, img_h
        except Exception as e:
            logger.error_with_exception("커버 이미지 임베드 실패", e)
            return None, 0, 0

    def _add_cover_table(
        self,
        hwpx_document: ReportHwpxBuilder,
        section: ReportSection,
        *,
        rows: int,
        cols: int,
        width: int,
        border_fill_id_ref: str,
    ):
        return hwpx_document.create_table(
            rows,
            cols,
            section=section,
            width=width,
            border_fill_id_ref=border_fill_id_ref,
            para_pr_id_ref=self.theme.cover_table_host_para_pr_id,
            style_id_ref="0",
            char_pr_id_ref="0",
        )

    @staticmethod
    def _fit_image(box_w: int, box_h: int, img_w: int, img_h: int) -> tuple[int, int]:
        """비율 유지하면서 box 안에 맞는 (disp_w, disp_h) 반환 (HWPUNIT)."""
        if img_w <= 0 or img_h <= 0:
            return box_w, box_h * 2 // 3
        ratio = img_w / img_h
        if box_w / box_h >= ratio:
            # 높이 기준
            disp_h = box_h
            disp_w = int(disp_h * ratio)
        else:
            # 너비 기준
            disp_w = box_w
            disp_h = int(disp_w / ratio)
        return disp_w, disp_h

    def _insert_cover_pic(self, paragraph, item_id: str, width: int, height: int) -> None:
        _HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
        _HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

        def _sub(parent, tag, attrib=None):
            child = parent.makeelement(tag, attrib or {})
            parent.append(child)
            return child

        pic_id = str(uuid4().int & 0xFFFFFFFF)
        inst_id = str(uuid4().int & 0xFFFFFFFF)

        run_el = _sub(paragraph.element, f"{_HP}run", {"charPrIDRef": "0"})
        pic = _sub(run_el, f"{_HP}pic", {
            "id": pic_id, "zOrder": "25", "numberingType": "PICTURE",
            "textWrap": "TOP_AND_BOTTOM", "textFlow": "BOTH_SIDES",
            "lock": "0", "dropcapstyle": "None", "href": "", "groupLevel": "0",
            "instid": inst_id, "reverse": "0",
        })
        _sub(pic, f"{_HP}offset", {"x": "0", "y": "0"})
        _sub(pic, f"{_HP}orgSz", {"width": str(width), "height": str(height)})
        _sub(pic, f"{_HP}curSz", {"width": str(width), "height": str(height)})
        _sub(pic, f"{_HP}flip", {"horizontal": "0", "vertical": "0"})
        _sub(pic, f"{_HP}rotationInfo", {
            "angle": "0", "centerX": str(width // 2), "centerY": str(height // 2), "rotateimage": "1",
        })
        ri = _sub(pic, f"{_HP}renderingInfo")
        _sub(ri, f"{_HC}transMatrix", {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"})
        _sub(ri, f"{_HC}scaMatrix", {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"})
        _sub(ri, f"{_HC}rotMatrix", {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"})
        _sub(pic, f"{_HC}img", {
            "binaryItemIDRef": item_id, "bright": "0", "contrast": "0", "effect": "REAL_PIC", "alpha": "0",
        })
        img_rect = _sub(pic, f"{_HP}imgRect")
        _sub(img_rect, f"{_HC}pt0", {"x": "0", "y": "0"})
        _sub(img_rect, f"{_HC}pt1", {"x": str(width), "y": "0"})
        _sub(img_rect, f"{_HC}pt2", {"x": str(width), "y": str(height)})
        _sub(img_rect, f"{_HC}pt3", {"x": "0", "y": str(height)})
        _sub(pic, f"{_HP}imgClip", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
        _sub(pic, f"{_HP}inMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
        _sub(pic, f"{_HP}imgDim", {"dimwidth": "0", "dimheight": "0"})
        _sub(pic, f"{_HP}effects")
        _sub(pic, f"{_HP}sz", {
            "width": str(width), "height": str(height),
            "widthRelTo": "ABSOLUTE", "heightRelTo": "ABSOLUTE", "protect": "0",
        })
        _sub(pic, f"{_HP}pos", {
            "treatAsChar": "1", "affectLSpacing": "0", "flowWithText": "1",
            "allowOverlap": "1", "holdAnchorAndSO": "0",
            "vertRelTo": "PARA", "horzRelTo": "PARA",
            "vertAlign": "TOP", "horzAlign": "LEFT",
            "vertOffset": "0", "horzOffset": "0",
        })
        _sub(pic, f"{_HP}outMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
        paragraph.section.touch()

    # ── block dispatch ───────────────────────────────────────────────

    def _render_block(self, hwpx_document: ReportHwpxBuilder, section: ReportSection, block: HwpBlock, prev_block=None, next_block=None) -> None:
        if isinstance(block, HeadingBlock):
            self._render_heading(hwpx_document, section, block, prev_block=prev_block)
        elif isinstance(block, BulletBlock):
            next_is_h3 = isinstance(next_block, HeadingBlock) and next_block.level == 3
            is_last = not isinstance(next_block, (BulletBlock, OrderedBulletBlock, BodyBlock)) and not next_is_h3
            self._render_bullet(hwpx_document, section, block, is_last=is_last)
        elif isinstance(block, OrderedBulletBlock):
            next_is_h3 = isinstance(next_block, HeadingBlock) and next_block.level == 3
            is_last = not isinstance(next_block, (BulletBlock, OrderedBulletBlock, BodyBlock)) and not next_is_h3
            is_first = not isinstance(prev_block, OrderedBulletBlock) or prev_block.depth != block.depth
            self._render_ordered_bullet(hwpx_document, section, block, is_first=is_first, is_last=is_last)
        elif isinstance(block, NoteBlock):
            self._add_styled_paragraph(hwpx_document, section, f"※ {block.text}", _NOTE_STYLE)
        elif isinstance(block, BodyBlock):
            self._add_styled_paragraph(hwpx_document, section, block.text, _BODY_STYLE)
        elif isinstance(block, TableBlock):
            self._render_md_table(hwpx_document, section, block)
        elif isinstance(block, DividerBlock):
            self._add_styled_paragraph(hwpx_document, section, "", "body")
        elif isinstance(block, PageBreakBlock):
            para = self._add_styled_paragraph(hwpx_document, section, "", "body")
            if para is not None:
                para.element.set("pageBreak", "1")

    def _render_heading(self, hwpx_document: ReportHwpxBuilder, section: ReportSection, block: HeadingBlock, prev_block=None) -> None:
        if block.level == 1:
            self._h1_count += 1
            h1_fill = self.theme.table_border_fills["h1_cell"]
            no_border = self.theme.table_border_fills["cover_bg"]
            # TABLE fill = no_border, CELL fill = h1_fill (위아래 선 + 연한 배경)
            tbl = hwpx_document.create_table(
                1, 1,
                section=section,
                width=self._TABLE_MAX_WIDTH,
                border_fill_id_ref=no_border,
                para_pr_id_ref="0",
                style_id_ref="0",
                char_pr_id_ref="0",
            )
            tbl.anchor_paragraph.element.set("pageBreak", "1")
            self._set_table_inner_margin(tbl, 1000, 1000, 700, 700)
            self._set_cell_text(tbl.cell(0, 0), block.text, "section_big", h1_fill)
        elif block.level == 2:
            # 번호체계(1. 2. 등)로 시작하면 □ 생략 + 검은색 스타일
            if re.match(r"\d+\.", block.text):
                style = "h2_num"
                display = block.text
            else:
                style = "h2"
                display = f"□ {block.text}"
            self._add_styled_paragraph(hwpx_document, section, display, style)
        else:
            # Normalize multi-level numbering:
            # - "1.1.1. 제목" -> "1.1.1 제목" (remove delimiter dot before text)
            # - "1.1.1제목"  -> "1.1.1 제목" (insert missing space)
            h3_text = re.sub(r'^(\d+(?:\.\d+)+)\.\s*', r'\1 ', block.text)
            # - "1.1.1. ·제목" -> "1.1.1 제목" (remove accidental bullet marker)
            h3_text = re.sub(r'^(\d+(?:\.\d+)+)\s+[·∙•]\s*', r'\1 ', h3_text)
            h3_text = re.sub(r'^(\d+(?:\.\d+)+)([^\s])', r'\1 \2', h3_text)
            prev_is_heading = isinstance(prev_block, HeadingBlock) and prev_block.level <= 2
            if self._uses_shifted_h3_styles():
                h3_style = "h3_shifted" if prev_is_heading else "h3_shifted_spaced"
            else:
                h3_style = "h3" if prev_is_heading else "h3_spaced"
            self._add_styled_paragraph(hwpx_document, section, h3_text, h3_style)

    def _render_ordered_bullet(
        self,
        hwpx_document: ReportHwpxBuilder,
        section: ReportSection,
        block: OrderedBulletBlock,
        is_first: bool = False,
        is_last: bool = False,
    ) -> None:
        if is_first:
            style = self._ordered_bullet_style_for(block.depth)
        else:
            style = self._bullet_style_for(block.depth)
        self._add_styled_paragraph(hwpx_document, section, f"{block.marker}. {block.text}", style)

    def _render_bullet(self, hwpx_document: ReportHwpxBuilder, section: ReportSection, block: BulletBlock, is_last: bool = False) -> None:
        marker_prefix = {
            "-": "- ",
            "·": "· ",
            "∙": "· ",
            "•": "· ",
        }.get((block.marker or "").strip())
        prefix = marker_prefix or _BULLET_PREFIX.get(block.depth, "○ ")
        style = self._bullet_style_for(block.depth)
        self._add_styled_paragraph(hwpx_document, section, f"{prefix}{block.text}", style)

    def _uses_shifted_h3_styles(self) -> bool:
        return getattr(self, "_shifted_h3_context", False)

    def _bullet_style_for(self, depth: int) -> str:
        if self._uses_shifted_h3_styles():
            return {
                0: "bullet_h3",
                1: "bullet_1_h3",
                2: "bullet_2_h3",
            }.get(depth, "bullet_h3")
        return _BULLET_STYLE.get(depth, "bullet")

    def _ordered_bullet_style_for(self, depth: int) -> str:
        if self._uses_shifted_h3_styles():
            return {
                0: "ordered_bullet_h3_first",
                1: "ordered_bullet_1_h3_first",
                2: "ordered_bullet_2_h3_first",
            }.get(depth, "ordered_bullet_h3_first")
        return {
            0: "ordered_bullet_first",
            1: "ordered_bullet_1_first",
            2: "ordered_bullet_2_first",
        }.get(depth, "ordered_bullet_first")

    def _render_md_table(self, hwpx_document: ReportHwpxBuilder, section: ReportSection, block: TableBlock) -> None:
        if block.title:
            self._add_styled_paragraph(hwpx_document, section, block.title, "table_title")

        headers = [self._normalize_line(h) for h in block.headers]
        rows = [[self._normalize_line(c) for c in row] for row in block.rows]

        column_count = max(len(headers), max((len(r) for r in rows), default=0))
        if column_count == 0:
            return

        col_widths, table_width = self._calc_col_widths(headers, rows, column_count)
        row_count = len(rows) + (1 if headers else 0)
        hwpx_table = hwpx_document.create_table(
            max(row_count, 1),
            column_count,
            section=section,
            width=table_width,
            height=max(row_count, 1) * self._TABLE_DEFAULT_ROW_HEIGHT,
            border_fill_id_ref=self.theme.table_border_fills["body"],
        )

        # 컬럼 너비 및 셀 내부 여백 설정
        self._set_table_inner_margin(hwpx_table)
        for r in range(max(row_count, 1)):
            for c, w in enumerate(col_widths):
                hwpx_table.cell(r, c).set_size(width=w)

        current_row = 0
        if headers:
            for col_i, header in enumerate(headers):
                self._set_cell_text(
                    hwpx_table.cell(current_row, col_i),
                    header,
                    "table_header",
                    self.theme.table_border_fills["header"],
                )
            current_row += 1

        for row in rows:
            for col_i in range(column_count):
                value = row[col_i] if col_i < len(row) else ""
                display = "" if value == "^^" else value
                self._set_cell_text(
                    hwpx_table.cell(current_row, col_i),
                    display,
                    "table_cell",
                    self.theme.table_border_fills["body"],
                )
            current_row += 1

    def _add_styled_paragraph(self, document, section, text: str, slot_name: str):
        refs = self.theme.paragraph_styles[slot_name]
        segments = self._parse_bold_segments(text)
        has_bold = any(is_bold for _, is_bold in segments)

        if not has_bold:
            paragraph = document.create_paragraph(
                text,
                section=section,
                para_pr_id_ref=refs.para_pr_id_ref,
                style_id_ref=refs.style_id_ref,
                char_pr_id_ref=refs.char_pr_id_ref,
            )
            self._apply_paragraph_refs(paragraph, refs)
            return paragraph

        paragraph = document.create_paragraph(
            "",
            section=section,
            para_pr_id_ref=refs.para_pr_id_ref,
            style_id_ref=refs.style_id_ref,
            char_pr_id_ref=refs.char_pr_id_ref,
        )

        for run in list(paragraph.runs):
            run.remove()

        bold_char_pr = self.theme.bold_char_pr_map.get(refs.char_pr_id_ref, refs.char_pr_id_ref)
        for segment_text, is_bold in segments:
            if not segment_text:
                continue
            char_pr = bold_char_pr if is_bold else refs.char_pr_id_ref
            paragraph.append_text(segment_text, char_pr_id_ref=char_pr)
        return paragraph

    def _set_cell_text(self, cell, text: str, slot_name: str, border_fill_id_ref: str) -> None:
        refs = self.theme.paragraph_styles[slot_name]
        segments = self._parse_bold_segments(text)
        plain_text = "".join(t for t, _ in segments)
        cell.text = plain_text
        cell.element.set("borderFillIDRef", border_fill_id_ref)
        paragraphs = cell.paragraphs
        if not paragraphs:
            paragraph = cell.append_paragraph(
                plain_text,
                para_pr_id_ref=refs.para_pr_id_ref,
                style_id_ref=refs.style_id_ref,
                char_pr_id_ref=refs.char_pr_id_ref,
            )
        else:
            paragraph = paragraphs[0]
            paragraph.para_pr_id_ref = refs.para_pr_id_ref
            paragraph.style_id_ref = refs.style_id_ref
            paragraph.char_pr_id_ref = refs.char_pr_id_ref
        self._apply_paragraph_refs(paragraph, refs)

        has_bold = any(is_bold for _, is_bold in segments)
        if has_bold:
            for run in list(paragraph.runs):
                run.remove()
            bold_char_pr = self.theme.bold_char_pr_map.get(refs.char_pr_id_ref, refs.char_pr_id_ref)
            for seg_text, is_bold in segments:
                if not seg_text:
                    continue
                char_pr = bold_char_pr if is_bold else refs.char_pr_id_ref
                paragraph.append_text(seg_text, char_pr_id_ref=char_pr)

    def _apply_paragraph_refs(self, paragraph, refs: ParagraphStyleRefs) -> None:
        paragraph.para_pr_id_ref = refs.para_pr_id_ref
        paragraph.style_id_ref = refs.style_id_ref
        paragraph.char_pr_id_ref = refs.char_pr_id_ref
        for run in paragraph.runs:
            run.char_pr_id_ref = refs.char_pr_id_ref

    def _inject_reference_header(self, target_path: Path, title: str) -> None:
        if not self.theme.header_template_path.exists():
            return

        template_bytes = self.theme.header_template_path.read_bytes()
        template_bytes = self._patch_header_char_colors(template_bytes)
        title = self._normalize_line(title)
        with NamedTemporaryFile(delete=False, suffix=".hwpx", dir=target_path.parent) as tmp_file:
            temp_path = Path(tmp_file.name)

        try:
            with zipfile.ZipFile(target_path, "r") as source_zip, zipfile.ZipFile(temp_path, "w") as target_zip:
                # 원본 header.xml에서 binDataList 추출 (이미지 임베드 정보 보존)
                source_header = source_zip.read("Contents/header.xml").decode("utf-8")
                bin_data_list = self._extract_bin_data_list(source_header)

                for info in source_zip.infolist():
                    data = source_zip.read(info.filename)
                    if info.filename == "Contents/header.xml":
                        header_text = template_bytes.decode("utf-8")
                        if bin_data_list:
                            header_text = header_text.replace("</hh:head>", bin_data_list + "</hh:head>")
                        data = header_text.encode("utf-8")
                    elif info.filename == self._CONTENT_HPF_PATH:
                        data = self._update_content_hpf_title(data, title)
                    target_zip.writestr(info, data)
            temp_path.replace(target_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _compact_cover_secpr(self, target_path: Path) -> None:
        with NamedTemporaryFile(delete=False, suffix=".hwpx", dir=target_path.parent) as tmp_file:
            temp_path = Path(tmp_file.name)

        try:
            with zipfile.ZipFile(target_path, "r") as source_zip, zipfile.ZipFile(temp_path, "w") as target_zip:
                for info in source_zip.infolist():
                    data = source_zip.read(info.filename)
                    if info.filename == self._SECTION_0_PATH:
                        data = self._move_secpr_to_first_cover_table(data)
                    target_zip.writestr(info, data)
            temp_path.replace(target_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _move_secpr_to_first_cover_table(self, section_bytes: bytes) -> bytes:
        root = ET.fromstring(section_bytes)
        paragraphs = root.findall(f"./{self._HP_NS}p")
        if len(paragraphs) < 2:
            return section_bytes

        first_para = paragraphs[0]
        second_para = paragraphs[1]
        first_run = first_para.find(f"./{self._HP_NS}run")
        second_run = second_para.find(f"./{self._HP_NS}run")
        if first_run is None or second_run is None:
            return section_bytes

        sec_pr = first_run.find(f"./{self._HP_NS}secPr")
        first_text = "".join(node.text or "" for node in first_para.findall(f".//{self._HP_NS}t")).strip()
        if sec_pr is None or first_text:
            return section_bytes

        first_run.remove(sec_pr)
        second_run.insert(0, sec_pr)
        root.remove(first_para)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _extract_bin_data_list(header_xml: str) -> str:
        """header.xml에서 hh:binDataList 블록을 추출해 문자열로 반환."""
        match = re.search(r"<hh:binDataList[^>]*>.*?</hh:binDataList>", header_xml, re.DOTALL)
        return match.group(0) if match else ""

    def _patch_header_char_colors(self, header_bytes: bytes) -> bytes:
        _HH_NS = "{http://www.hancom.co.kr/hwpml/2011/head}"
        root = ET.fromstring(header_bytes)
        for cp in root.iter(f"{_HH_NS}charPr"):
            cp_id = cp.get("id", "")
            if cp_id in self.theme.char_pr_color_patches:
                cp.set("textColor", self.theme.char_pr_color_patches[cp_id])
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _update_content_hpf_title(self, content_hpf_bytes: bytes, title: str) -> bytes:
        root = ET.fromstring(content_hpf_bytes)
        namespace = {"opf": "http://www.idpf.org/2007/opf"}
        title_node = root.find(".//opf:metadata/opf:title", namespace)
        if title_node is not None and title:
            title_node.text = title

        for item in root.iter():
            if not item.tag.endswith("item"):
                continue
            href = item.get("href", "")
            if href.startswith("BinData/"):
                item.set("isEmbeded", "1")

        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _parse_bold_segments(text: str) -> list[tuple[str, bool]]:
        segments: list[tuple[str, bool]] = []
        last_end = 0
        for match in re.finditer(r"\*\*(.+?)\*\*", text):
            if match.start() > last_end:
                segments.append((text[last_end:match.start()], False))
            segments.append((match.group(1), True))
            last_end = match.end()
        if last_end < len(text):
            segments.append((text[last_end:], False))
        if not segments:
            segments.append((text, False))
        return segments

    def _set_table_inner_margin(self, table, left: int = 600, right: int = 600, top: int = 300, bottom: int = 300) -> None:
        inmargin = table.element.find(f"{self._HP_NS}inMargin")
        if inmargin is not None:
            inmargin.set("left", str(left))
            inmargin.set("right", str(right))
            inmargin.set("top", str(top))
            inmargin.set("bottom", str(bottom))

    @staticmethod
    def _visual_width(text: str) -> int:
        """한글·CJK 문자는 2, 나머지는 1로 계산하여 시각적 너비 근사."""
        w = 0
        for ch in text:
            cp = ord(ch)
            if (0xAC00 <= cp <= 0xD7A3        # 한글 음절
                or 0x3000 <= cp <= 0x303F      # CJK 기호
                or 0x4E00 <= cp <= 0x9FFF      # CJK 통합 한자
                or 0xF900 <= cp <= 0xFAFF      # CJK 호환 한자
                or 0xFF01 <= cp <= 0xFF60      # 전각 영숫자
                or 0x1100 <= cp <= 0x11FF      # 한글 자모
                or 0x3130 <= cp <= 0x318F):    # 한글 호환 자모
                w += 2
            else:
                w += 1
        return w

    def _calc_col_widths(self, headers: list[str], rows: list[list[str]], column_count: int) -> tuple[list[int], int]:
        col_max_lens = [0] * column_count
        for col_i, header in enumerate(headers):
            if col_i < column_count:
                col_max_lens[col_i] = max(col_max_lens[col_i], self._visual_width(header))
        for row in rows:
            for col_i, cell in enumerate(row):
                if col_i < column_count:
                    col_max_lens[col_i] = max(col_max_lens[col_i], self._visual_width(cell))

        total_chars = sum(col_max_lens) or column_count
        col_widths = [max(1, round(length / total_chars * self._TABLE_MAX_WIDTH)) for length in col_max_lens]

        for index in range(column_count - 1):
            if col_widths[index] < self._TABLE_COL_MIN_WIDTH:
                col_widths[index] = self._TABLE_COL_MIN_WIDTH
        col_widths[-1] = max(self._TABLE_COL_MIN_WIDTH, self._TABLE_MAX_WIDTH - sum(col_widths[:-1]))

        return col_widths, sum(col_widths)

    def _normalize_line(self, line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return ""
        return re.sub(r"\s+", " ", stripped)
