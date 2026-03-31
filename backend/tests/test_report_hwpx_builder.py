from __future__ import annotations

import base64
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.services.markdown_exporter import MarkdownExporter
from app.services.markdown_parser import parse as parse_markdown
from app.services.report_hwpx.archive import validate_report_archive
from app.services.report_hwpx.builder import ReportHwpxBuilder


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO0pQe8AAAAASUVORK5CYII="
)

_LONG_MARKDOWN = """---
title: 장문 검증 보고서
organization: Cryptolab
---

# 장문 검증 보고서

## 보고 개요

스마트물류 플랫폼 구축 사업은 물류센터 입출고, 재고, 배차, 정산 데이터를 하나의 흐름으로 통합하기 위한 사업이다. 현재 센터별로 엑셀과 개별 솔루션을 혼용하고 있어 재고 정확도 저하, 배차 지연, 월 마감 정산 오류가 반복되고 있다.

### 1.1 추진 배경

본 사업은 현장 운영의 불일치와 데이터 표준 부재를 동시에 해소하기 위해 추진한다. `모바일 단말 기준 업무 절차`를 통일하고, 운영본부와 IT실이 같은 기준으로 데이터를 조회할 수 있도록 설계한다.

○ 현장 작업자는 입출고 현황을 같은 화면에서 확인해야 한다.
  - 센터 관리자 승인 절차는 모바일에서도 동일해야 한다.
    · 작업 완료 후 즉시 재고가 반영되어야 한다.
  가. 시범센터는 1개 센터부터 시작한다.
  나. 운영 결과를 기준으로 2단계 반영 범위를 정한다.
※ 기존 시스템 연계 난이도가 높아 사전 인터페이스 정의가 필요하다.

| 구분 | 현행 문제 | 개선 목표 |
| --- | --- | --- |
| 재고 | 센터별 수기 정리 | 실시간 수량 동기화 |
| 배차 | 담당자 경험 의존 | 규칙 기반 우선순위 적용 |
| 정산 | 월말 수작업 집계 | 자동 정산 자료 생성 |

---

# 단계별 구축 계획

## 1단계 구축 범위

1. 입출고 관리 기능을 우선 구축한다.
2. 재고 가시화 기능을 함께 도입한다.

<!-- pagebreak -->

## 2단계 확장 범위

배차 최적화와 협력사 포털을 도입한다. 외부 물류사와 협력 운송사가 같은 기준으로 배차 요청과 실적을 확인할 수 있어야 한다.

### 2.1 운영 기준

- 현장 작업자 모바일 사용성을 최우선으로 한다.
- 운영본부, IT실, 외부 물류사, 협력 운송사 간 권한을 구분한다.

```text
이 코드블록은 문서 본문에 포함되면 안 된다.
테스트에서는 파서가 무시해야 한다.
```

# 예산 및 기대효과

## 예산 계획

총 예산은 **18억 원**이며 분석 2개월, 구축 5개월, 시범운영 1개월 일정으로 추진한다.

## 기대효과

- 재고 정확도 **98%** 달성
- 배차 리드타임 **20%** 단축
- 월 마감 정산시간 **50%** 절감
"""


class ReportHwpxBuilderTest(unittest.TestCase):
    def test_builder_writes_valid_hwpx_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "builder.hwpx"
            header_template_path = Path(__file__).resolve().parents[2] / "template" / "header.xml"
            builder = ReportHwpxBuilder(header_template_path=header_template_path)
            section = builder.sections[0]
            paragraph = builder.create_paragraph(
                "테스트 문단",
                section=section,
                para_pr_id_ref="24",
                style_id_ref="0",
                char_pr_id_ref="83",
            )
            paragraph.append_text(" 추가", char_pr_id_ref="83")
            table = builder.create_table(1, 2, section=section, width=20000, border_fill_id_ref="1")
            table.cell(0, 0).text = "A"
            table.cell(0, 1).text = "B"
            builder.register_binary_asset(_PNG_1X1, "png", asset_id="image1")
            builder.write(output_path, validate=True)

            validate_report_archive(output_path)
            with zipfile.ZipFile(output_path) as archive:
                names = set(archive.namelist())
                self.assertIn("Contents/content.hpf", names)
                self.assertIn("Contents/header.xml", names)
                self.assertIn("Contents/section0.xml", names)
                self.assertIn("BinData/image1.png", names)

    def test_exporter_generates_valid_hwpx_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "exported.hwpx"
            document = parse_markdown(
                _LONG_MARKDOWN,
                title="장문 검증 보고서",
                organization="Cryptolab",
                cover_image=_PNG_1X1,
                cover_image_format="png",
            )
            MarkdownExporter().export_markdown(target_path=output_path, document=document)

            validate_report_archive(output_path)
            with zipfile.ZipFile(output_path) as archive:
                section_xml = archive.read("Contents/section0.xml").decode("utf-8", "ignore")
                header_xml = archive.read("Contents/header.xml").decode("utf-8", "ignore")
                self.assertIn("장문 검증 보고서", section_xml)
                self.assertIn("보고 개요", section_xml)
                self.assertIn("1.1 추진 배경", section_xml)
                self.assertIn("시범센터는 1개 센터부터 시작한다", section_xml)
                self.assertIn("기존 시스템 연계 난이도", section_xml)
                self.assertIn("현행 문제", section_xml)
                self.assertIn("실시간 수량 동기화", section_xml)
                self.assertIn("예산 계획", section_xml)
                self.assertIn("18억 원", section_xml)
                self.assertNotIn("이 코드블록은 문서 본문에 포함되면 안 된다", section_xml)
                self.assertIn("image1", header_xml)


if __name__ == "__main__":
    unittest.main()
