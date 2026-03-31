from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.report_hwpx.archive import validate_report_archive

_LONG_MARKDOWN = """---
title: API 장문 검증
organization: Cryptolab
---

# API 장문 검증

## 개요

본 문서는 convert 엔드포인트가 실제 보고서 수준의 장문 마크다운을 받아 안정적으로 HWPX를 생성하는지 확인하기 위한 것이다. 입력에는 제목, 소제목, 세부 번호 제목, 다양한 불릿, 순서형 항목, 주석, 표, 구분선, 페이지 나눔, 코드블록 무시 규칙이 모두 포함된다.

### 1.1 입력 구성

○ 최상위 불릿은 기본 항목으로 파싱되어야 한다.
  - 하위 불릿은 들여쓰기 기준으로 depth 1로 들어가야 한다.
    · 세부 불릿은 depth 2로 들어가야 한다.
  가. 순서형 항목도 유지되어야 한다.
  나. 후속 조치도 유지되어야 한다.
※ 코드블록과 메타데이터는 본문과 구분되어야 한다.

| 항목 | 요구사항 | 기대 결과 |
| --- | --- | --- |
| 제목 | H1/H2/H3 처리 | 섹션 구조 유지 |
| 표 | 셀 값 보존 | 렌더링 가능 |
| 불릿 | 깊이 보존 | 문단 구조 유지 |

---

# 운영 계획

## 단계별 추진

1. 분석 2개월
2. 구축 5개월
3. 시범운영 1개월

<!-- pagebreak -->

## 기대효과

- 재고 정확도 98% 달성
- 배차 리드타임 20% 단축
- 정산시간 50% 절감

```text
이 블록은 파서가 무시해야 한다.
```
"""


class ConvertApiTest(unittest.TestCase):
    def test_convert_endpoint_returns_valid_hwpx(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/reports/convert",
            files={
                "markdown": (None, _LONG_MARKDOWN),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/octet-stream")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "api.hwpx"
            output_path.write_bytes(response.content)
            validate_report_archive(output_path)
            with zipfile.ZipFile(output_path) as archive:
                section_xml = archive.read("Contents/section0.xml").decode("utf-8", "ignore")
                self.assertIn("API 장문 검증", section_xml)
                self.assertIn("1.1 입력 구성", section_xml)
                self.assertIn("순서형 항목도 유지되어야 한다", section_xml)
                self.assertIn("요구사항", section_xml)
                self.assertIn("재고 정확도 98% 달성", section_xml)
                self.assertNotIn("이 블록은 파서가 무시해야 한다", section_xml)


if __name__ == "__main__":
    unittest.main()
