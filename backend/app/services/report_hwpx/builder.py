from __future__ import annotations

from pathlib import Path

from app.services.report_hwpx.archive import BinaryAsset, validate_report_archive, write_report_archive
from app.services.report_hwpx.dom import ReportParagraph, ReportSection, ReportTable, build_default_section_xml, build_paragraph_xml, append_xml, HP


class ReportHwpxBuilder:
    def __init__(self, *, header_template_path: Path) -> None:
        self.header_template_path = header_template_path
        self._section_xml = build_default_section_xml()
        self.sections = [ReportSection(self._section_xml)]
        self._assets: list[BinaryAsset] = []

    @property
    def binary_assets(self) -> list[BinaryAsset]:
        return list(self._assets)

    def create_paragraph(
        self,
        text: str = "",
        *,
        section: ReportSection | None = None,
        section_index: int | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        include_run: bool = True,
        **extra_attrs: str,
    ) -> ReportParagraph:
        target_section = section or self.sections[section_index or 0]
        paragraph_xml = build_paragraph_xml(
            text=text,
            para_pr_id_ref=para_pr_id_ref or "0",
            style_id_ref=style_id_ref or "0",
            char_pr_id_ref=char_pr_id_ref or "0",
            include_run=include_run,
            extra_attrs=extra_attrs,
            run_attributes=run_attributes,
        )
        target_section.root.append(paragraph_xml)
        return ReportParagraph(target_section, paragraph_xml)

    def create_table(
        self,
        rows: int,
        cols: int,
        *,
        section: ReportSection | None = None,
        section_index: int | None = None,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> ReportTable:
        from app.services.report_hwpx.dom import ReportTable

        target_section = section or self.sections[section_index or 0]
        anchor = self.create_paragraph(
            "",
            section=target_section,
            para_pr_id_ref=para_pr_id_ref or "0",
            style_id_ref=style_id_ref or "0",
            char_pr_id_ref=char_pr_id_ref or "0",
            run_attributes=run_attributes,
            **extra_attrs,
        )
        run = anchor.element.find(f"{HP}run")
        if run is None:
            run = append_xml(anchor.element, f"{HP}run", {"charPrIDRef": str(char_pr_id_ref or '0')})
        else:
            for child in list(run):
                run.remove(child)

        table_width = width if width is not None else max(cols, 1) * 10000
        table_height = height if height is not None else max(rows, 1) * 3600
        table_xml = append_xml(
            run,
            f"{HP}tbl",
            {
                "id": anchor.element.get("id", ""),
                "zOrder": "0",
                "numberingType": "TABLE",
                "textWrap": "TOP_AND_BOTTOM",
                "textFlow": "BOTH_SIDES",
                "lock": "0",
                "dropcapstyle": "None",
                "pageBreak": "CELL",
                "repeatHeader": "0",
                "rowCnt": str(rows),
                "colCnt": str(cols),
                "cellSpacing": "0",
                "borderFillIDRef": str(border_fill_id_ref or "1"),
                "noAdjust": "0",
            },
        )
        append_xml(
            table_xml,
            f"{HP}sz",
            {
                "width": str(table_width),
                "widthRelTo": "ABSOLUTE",
                "height": str(table_height),
                "heightRelTo": "ABSOLUTE",
                "protect": "0",
            },
        )
        append_xml(
            table_xml,
            f"{HP}pos",
            {
                "treatAsChar": "1",
                "affectLSpacing": "0",
                "flowWithText": "1",
                "allowOverlap": "0",
                "holdAnchorAndSO": "0",
                "vertRelTo": "PARA",
                "horzRelTo": "COLUMN",
                "vertAlign": "TOP",
                "horzAlign": "LEFT",
                "vertOffset": "0",
                "horzOffset": "0",
            },
        )
        append_xml(table_xml, f"{HP}outMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
        append_xml(table_xml, f"{HP}inMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})

        default_cell_width = table_width // max(cols, 1)
        default_cell_height = table_height // max(rows, 1)
        for row_idx in range(rows):
            row_xml = append_xml(table_xml, f"{HP}tr")
            for col_idx in range(cols):
                cell_xml = append_xml(
                    row_xml,
                    f"{HP}tc",
                    {
                        "name": "",
                        "header": "0",
                        "hasMargin": "0",
                        "protect": "0",
                        "editable": "0",
                        "dirty": "1",
                        "borderFillIDRef": str(border_fill_id_ref or "1"),
                    },
                )
                sub_list = append_xml(
                    cell_xml,
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
                sub_list.append(
                    build_paragraph_xml(
                        text="",
                        para_pr_id_ref=para_pr_id_ref or "0",
                        style_id_ref=style_id_ref or "0",
                        char_pr_id_ref=char_pr_id_ref or "0",
                    )
                )
                append_xml(cell_xml, f"{HP}cellAddr", {"colAddr": str(col_idx), "rowAddr": str(row_idx)})
                append_xml(cell_xml, f"{HP}cellSpan", {"colSpan": "1", "rowSpan": "1"})
                append_xml(cell_xml, f"{HP}cellSz", {"width": str(default_cell_width), "height": str(default_cell_height)})
                append_xml(cell_xml, f"{HP}cellMargin", {"left": "0", "right": "0", "top": "0", "bottom": "0"})
        return ReportTable(target_section, anchor, table_xml)

    def register_binary_asset(self, image_data: bytes, image_format: str, *, asset_id: str | None = None) -> str:
        actual_id = asset_id or f"image{len(self._assets) + 1}"
        self._assets.append(BinaryAsset(asset_id=actual_id, image_format=image_format, data=image_data))
        return actual_id

    def write(self, path: str | Path, *, validate: bool = False) -> str:
        target_path = Path(path)
        write_report_archive(
            target_path=target_path,
            section_xml=self._section_xml,
            header_template_path=self.header_template_path,
            binary_assets=self._assets,
        )
        if validate:
            validate_report_archive(target_path)
        return str(target_path)
