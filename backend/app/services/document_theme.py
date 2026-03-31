from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParagraphStyleRefs:
    para_pr_id_ref: str
    char_pr_id_ref: str
    style_id_ref: str = "0"


@dataclass(frozen=True)
class DocumentTheme:
    header_template_path: Path
    paragraph_styles: dict[str, ParagraphStyleRefs]
    bold_char_pr_map: dict[str, str]
    char_pr_color_patches: dict[str, str]
    table_border_fills: dict[str, str]
    cover_table_host_para_pr_id: str = "0"


def get_default_document_theme() -> DocumentTheme:
    root_dir = Path(__file__).resolve().parents[3]
    return DocumentTheme(
        header_template_path=root_dir / "template" / "header.xml",
        paragraph_styles={
            "cover_title": ParagraphStyleRefs(para_pr_id_ref="70", char_pr_id_ref="75"),
            "cover_org_hy": ParagraphStyleRefs(para_pr_id_ref="70", char_pr_id_ref="461"),
            "cover_org": ParagraphStyleRefs(para_pr_id_ref="24", char_pr_id_ref="76"),
            "cover_subtitle": ParagraphStyleRefs(para_pr_id_ref="24", char_pr_id_ref="18"),
            "cover_meta_label": ParagraphStyleRefs(para_pr_id_ref="61", char_pr_id_ref="18"),
            "cover_meta_value": ParagraphStyleRefs(para_pr_id_ref="24", char_pr_id_ref="30"),
            "cover_caption": ParagraphStyleRefs(para_pr_id_ref="60", char_pr_id_ref="30"),
            "toc_title": ParagraphStyleRefs(para_pr_id_ref="19", char_pr_id_ref="13", style_id_ref="14"),
            "toc_item": ParagraphStyleRefs(para_pr_id_ref="20", char_pr_id_ref="14", style_id_ref="15"),
            "section_title": ParagraphStyleRefs(para_pr_id_ref="61", char_pr_id_ref="18"),
            "section_line": ParagraphStyleRefs(para_pr_id_ref="325", char_pr_id_ref="6"),
            "section_big": ParagraphStyleRefs(para_pr_id_ref="24", char_pr_id_ref="83"),
            "section_line_end": ParagraphStyleRefs(para_pr_id_ref="107", char_pr_id_ref="6"),
            "h2": ParagraphStyleRefs(para_pr_id_ref="27", char_pr_id_ref="18"),
            "h2_num": ParagraphStyleRefs(para_pr_id_ref="414", char_pr_id_ref="462"),
            "h3": ParagraphStyleRefs(para_pr_id_ref="100", char_pr_id_ref="112"),
            "h3_spaced": ParagraphStyleRefs(para_pr_id_ref="415", char_pr_id_ref="112"),
            "h3_shifted": ParagraphStyleRefs(para_pr_id_ref="419", char_pr_id_ref="112"),
            "h3_shifted_spaced": ParagraphStyleRefs(para_pr_id_ref="420", char_pr_id_ref="112"),
            "body": ParagraphStyleRefs(para_pr_id_ref="264", char_pr_id_ref="58"),
            "body_spaced": ParagraphStyleRefs(para_pr_id_ref="400", char_pr_id_ref="58"),
            "bullet": ParagraphStyleRefs(para_pr_id_ref="21", char_pr_id_ref="465"),
            "bullet_1": ParagraphStyleRefs(para_pr_id_ref="22", char_pr_id_ref="465"),
            "bullet_2": ParagraphStyleRefs(para_pr_id_ref="12", char_pr_id_ref="465"),
            "bullet_h3": ParagraphStyleRefs(para_pr_id_ref="421", char_pr_id_ref="465"),
            "bullet_1_h3": ParagraphStyleRefs(para_pr_id_ref="422", char_pr_id_ref="465"),
            "bullet_2_h3": ParagraphStyleRefs(para_pr_id_ref="423", char_pr_id_ref="465"),
            "ordered_bullet_first": ParagraphStyleRefs(para_pr_id_ref="416", char_pr_id_ref="465"),
            "ordered_bullet_1_first": ParagraphStyleRefs(para_pr_id_ref="417", char_pr_id_ref="465"),
            "ordered_bullet_2_first": ParagraphStyleRefs(para_pr_id_ref="418", char_pr_id_ref="465"),
            "ordered_bullet_h3_first": ParagraphStyleRefs(para_pr_id_ref="424", char_pr_id_ref="465"),
            "ordered_bullet_1_h3_first": ParagraphStyleRefs(para_pr_id_ref="425", char_pr_id_ref="465"),
            "ordered_bullet_2_h3_first": ParagraphStyleRefs(para_pr_id_ref="426", char_pr_id_ref="465"),
            "note": ParagraphStyleRefs(para_pr_id_ref="161", char_pr_id_ref="219"),
            "owner": ParagraphStyleRefs(para_pr_id_ref="212", char_pr_id_ref="30"),
            "table_title": ParagraphStyleRefs(para_pr_id_ref="325", char_pr_id_ref="83"),
            "table_header": ParagraphStyleRefs(para_pr_id_ref="60", char_pr_id_ref="460"),
            "table_cell": ParagraphStyleRefs(para_pr_id_ref="60", char_pr_id_ref="91"),
        },
        bold_char_pr_map={
            "58": "404",
            "30": "404",
            "465": "466",
            "91": "463",
            "460": "464",
        },
        char_pr_color_patches={
            "404": "#000000",
        },
        table_border_fills={
            "cover": "28",
            "cover_bg": "1",
            "header": "45",
            "body": "38",
            "h1_cell": "175",
        },
    )
