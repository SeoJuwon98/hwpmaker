from __future__ import annotations

import uuid
from xml.etree import ElementTree as ET

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"

HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"


def append_xml(parent: ET.Element, tag: str, attrib: dict[str, str] | None = None, text: str | None = None) -> ET.Element:
    child = ET.SubElement(parent, tag, attrib or {})
    if text is not None:
        child.text = text
    return child


def random_id() -> str:
    return str(uuid.uuid4().int & 0xFFFFFFFF)


class ReportTextRun:
    def __init__(self, paragraph: "ReportParagraph", element: ET.Element) -> None:
        self.paragraph = paragraph
        self.element = element

    @property
    def char_pr_id_ref(self) -> str:
        return self.element.get("charPrIDRef", "0")

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int) -> None:
        self.element.set("charPrIDRef", str(value))

    def remove(self) -> None:
        self.paragraph.element.remove(self.element)


class ReportParagraph:
    def __init__(self, section: "ReportSection", element: ET.Element) -> None:
        self.section = section
        self.element = element

    @property
    def para_pr_id_ref(self) -> str:
        return self.element.get("paraPrIDRef", "0")

    @para_pr_id_ref.setter
    def para_pr_id_ref(self, value: str | int) -> None:
        self.element.set("paraPrIDRef", str(value))

    @property
    def style_id_ref(self) -> str:
        return self.element.get("styleIDRef", "0")

    @style_id_ref.setter
    def style_id_ref(self, value: str | int) -> None:
        self.element.set("styleIDRef", str(value))

    @property
    def char_pr_id_ref(self) -> str:
        run = self.element.find(f"{HP}run")
        return run.get("charPrIDRef", "0") if run is not None else "0"

    @char_pr_id_ref.setter
    def char_pr_id_ref(self, value: str | int) -> None:
        for run in self.element.findall(f"{HP}run"):
            run.set("charPrIDRef", str(value))

    @property
    def runs(self) -> list[ReportTextRun]:
        return [ReportTextRun(self, run) for run in self.element.findall(f"{HP}run")]

    def append_text(self, text: str, char_pr_id_ref: str | int = "0") -> ReportTextRun:
        run = append_xml(self.element, f"{HP}run", {"charPrIDRef": str(char_pr_id_ref)})
        append_xml(run, f"{HP}t", text=text)
        return ReportTextRun(self, run)


class ReportTableCell:
    def __init__(self, table: "ReportTable", element: ET.Element) -> None:
        self.table = table
        self.element = element

    @property
    def paragraphs(self) -> list[ReportParagraph]:
        sub_list = self.element.find(f"{HP}subList")
        if sub_list is None:
            return []
        return [ReportParagraph(self.table.section, para) for para in sub_list.findall(f"{HP}p")]

    def append_paragraph(
        self,
        text: str = "",
        *,
        para_pr_id_ref: str | int = "0",
        style_id_ref: str | int = "0",
        char_pr_id_ref: str | int = "0",
    ) -> ReportParagraph:
        sub_list = self.element.find(f"{HP}subList")
        if sub_list is None:
            sub_list = append_xml(
                self.element,
                f"{HP}subList",
                {
                    "id": "",
                    "textDirection": "HORIZONTAL",
                    "lineWrap": "BREAK",
                    "vertAlign": "CENTER",
                    "linkListIDRef": "0",
                    "linkListNextIDRef": "0",
                    "textWidth": "0",
                    "textHeight": "0",
                    "hasTextRef": "0",
                    "hasNumRef": "0",
                },
            )
        paragraph = build_paragraph_xml(
            text=text,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
        )
        sub_list.append(paragraph)
        return ReportParagraph(self.table.section, paragraph)

    @property
    def text(self) -> str:
        text_parts: list[str] = []
        for paragraph in self.paragraphs:
            for node in paragraph.element.findall(f".//{HP}t"):
                text_parts.append(node.text or "")
        return "".join(text_parts)

    @text.setter
    def text(self, value: str) -> None:
        paragraphs = self.paragraphs
        if paragraphs:
            paragraph = paragraphs[0]
            for run in list(paragraph.runs):
                run.remove()
            paragraph.append_text(value, char_pr_id_ref=paragraph.char_pr_id_ref)
            return
        self.append_paragraph(value)

    def set_size(self, *, width: int | None = None, height: int | None = None) -> None:
        cell_size = self.element.find(f"{HP}cellSz")
        if cell_size is None:
            cell_size = append_xml(self.element, f"{HP}cellSz", {"width": "0", "height": "0"})
        if width is not None:
            cell_size.set("width", str(width))
        if height is not None:
            cell_size.set("height", str(height))


class ReportTable:
    def __init__(self, section: "ReportSection", anchor_paragraph: ReportParagraph, element: ET.Element) -> None:
        self.section = section
        self.anchor_paragraph = anchor_paragraph
        self.element = element

    def cell(self, row: int, col: int) -> ReportTableCell:
        rows = self.element.findall(f"{HP}tr")
        return ReportTableCell(self, rows[row].findall(f"{HP}tc")[col])


class ReportSection:
    def __init__(self, root: ET.Element) -> None:
        self.root = root

    def touch(self) -> None:
        return None


def build_paragraph_xml(
    *,
    text: str,
    para_pr_id_ref: str | int,
    style_id_ref: str | int,
    char_pr_id_ref: str | int,
    include_run: bool = True,
    extra_attrs: dict[str, str] | None = None,
    run_attributes: dict[str, str] | None = None,
) -> ET.Element:
    attrs = {
        "id": random_id(),
        "paraPrIDRef": str(para_pr_id_ref),
        "styleIDRef": str(style_id_ref),
        "pageBreak": "0",
        "columnBreak": "0",
        "merged": "0",
    }
    if extra_attrs:
        attrs.update({key: str(value) for key, value in extra_attrs.items()})
    paragraph = ET.Element(f"{HP}p", attrs)
    if include_run:
        run_attrs = {"charPrIDRef": str(char_pr_id_ref)}
        if run_attributes:
            run_attrs.update({key: str(value) for key, value in run_attributes.items()})
        run = append_xml(paragraph, f"{HP}run", run_attrs)
        append_xml(run, f"{HP}t", text=text)
    return paragraph


def build_default_section_xml() -> ET.Element:
    root = ET.Element(f"{HS}sec")
    first_para = ET.SubElement(
        root,
        f"{HP}p",
        {
            "id": random_id(),
            "paraPrIDRef": "0",
            "styleIDRef": "0",
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    run = append_xml(first_para, f"{HP}run", {"charPrIDRef": "0"})
    sec_pr = append_xml(
        run,
        f"{HP}secPr",
        {
            "id": "",
            "textDirection": "HORIZONTAL",
            "spaceColumns": "1134",
            "tabStop": "8000",
            "tabStopVal": "4000",
            "tabStopUnit": "HWPUNIT",
            "outlineShapeIDRef": "1",
            "memoShapeIDRef": "0",
            "textVerticalWidthHead": "0",
            "masterPageCnt": "0",
        },
    )
    append_xml(sec_pr, f"{HP}grid", {"lineGrid": "0", "charGrid": "0", "wonggojiFormat": "0"})
    append_xml(sec_pr, f"{HP}startNum", {"pageStartsOn": "BOTH", "page": "0", "pic": "0", "tbl": "0", "equation": "0"})
    append_xml(
        sec_pr,
        f"{HP}visibility",
        {
            "hideFirstHeader": "0",
            "hideFirstFooter": "0",
            "hideFirstMasterPage": "0",
            "border": "SHOW_ALL",
            "fill": "SHOW_ALL",
            "hideFirstPageNum": "0",
            "hideFirstEmptyLine": "0",
            "showLineNumber": "0",
        },
    )
    append_xml(sec_pr, f"{HP}lineNumberShape", {"restartType": "0", "countBy": "0", "distance": "0", "startNumber": "0"})
    page_pr = append_xml(
        sec_pr,
        f"{HP}pagePr",
        {"landscape": "WIDELY", "width": "59528", "height": "84186", "gutterType": "LEFT_ONLY"},
    )
    append_xml(page_pr, f"{HP}margin", {"header": "4252", "footer": "4252", "gutter": "0", "left": "8504", "right": "8504", "top": "5668", "bottom": "4252"})
    foot_note = append_xml(sec_pr, f"{HP}footNotePr")
    append_xml(foot_note, f"{HP}autoNumFormat", {"type": "DIGIT", "userChar": "", "prefixChar": "", "suffixChar": ")", "supscript": "0"})
    append_xml(foot_note, f"{HP}noteLine", {"length": "-1", "type": "SOLID", "width": "0.12 mm", "color": "#000000"})
    append_xml(foot_note, f"{HP}noteSpacing", {"betweenNotes": "283", "belowLine": "567", "aboveLine": "850"})
    append_xml(foot_note, f"{HP}numbering", {"type": "CONTINUOUS", "newNum": "1"})
    append_xml(foot_note, f"{HP}placement", {"place": "EACH_COLUMN", "beneathText": "0"})
    end_note = append_xml(sec_pr, f"{HP}endNotePr")
    append_xml(end_note, f"{HP}autoNumFormat", {"type": "DIGIT", "userChar": "", "prefixChar": "", "suffixChar": ")", "supscript": "0"})
    append_xml(end_note, f"{HP}noteLine", {"length": "14692344", "type": "SOLID", "width": "0.12 mm", "color": "#000000"})
    append_xml(end_note, f"{HP}noteSpacing", {"betweenNotes": "0", "belowLine": "567", "aboveLine": "850"})
    append_xml(end_note, f"{HP}numbering", {"type": "CONTINUOUS", "newNum": "1"})
    append_xml(end_note, f"{HP}placement", {"place": "END_OF_DOCUMENT", "beneathText": "0"})
    for fill_type in ("BOTH", "EVEN", "ODD"):
        page_border = append_xml(
            sec_pr,
            f"{HP}pageBorderFill",
            {
                "type": fill_type,
                "borderFillIDRef": "1",
                "textBorder": "PAPER",
                "headerInside": "0",
                "footerInside": "0",
                "fillArea": "PAPER",
            },
        )
        append_xml(page_border, f"{HP}offset", {"left": "1417", "right": "1417", "top": "1417", "bottom": "1417"})
    ctrl = append_xml(run, f"{HP}ctrl")
    append_xml(ctrl, f"{HP}colPr", {"id": "", "type": "NEWSPAPER", "layout": "LEFT", "colCount": "1", "sameSz": "1", "sameGap": "0"})
    blank_run = append_xml(first_para, f"{HP}run", {"charPrIDRef": "0"})
    append_xml(blank_run, f"{HP}t", text="")
    line_seg_array = append_xml(first_para, f"{HP}linesegarray")
    append_xml(
        line_seg_array,
        f"{HP}lineseg",
        {
            "textpos": "0",
            "vertpos": "0",
            "vertsize": "1000",
            "textheight": "1000",
            "baseline": "850",
            "spacing": "600",
            "horzpos": "0",
            "horzsize": "42520",
            "flags": "393216",
        },
    )
    return root
