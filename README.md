# hwpmaker

마크다운 또는 자유 원문을 HWPX 보고서로 변환하는 FastAPI 백엔드다.

현재 범위:

- 마크다운 문자열을 바로 HWPX로 변환
- 자유 원문을 LLM 파이프라인으로 보고서형 마크다운으로 정리한 뒤 HWPX로 변환
- 생성된 HWPX 다운로드
- 외부 `python-hwpx` 없이 내부 HWPX writer로 문서 패키지 생성

## 구조

```text
backend/
  app/
    api/                  FastAPI 라우트
    core/                 설정, 로깅, 예외 처리
    models/               문서/요청 모델
    services/
      markdown_parser.py
      markdown_exporter.py
      pipeline_service.py
      report_hwpx/        내부 HWPX writer 및 아카이브 검증
template/
  header.xml              HWPX 스타일 참조 템플릿
```

## 요구 사항

- Python 3.12
- `backend/.env`
- OpenAI 호환 Chat Completions API 엔드포인트

## 설치

```bash
cd backend
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
```

## 환경 변수

`backend/.env` 기준으로 로드된다.

주요 설정값:

- `HOST`
- `PORT`
- `FRONTEND_ORIGIN`
- `VLLM_BASE_URL`
- `VLLM_MODEL`
- `VLLM_API_KEY`
- `VLLM_MAX_TOKENS`
- `VLLM_TIMEOUT_SECONDS`
- `VLLM_ENABLE_THINKING`
- `VLLM_REASONING_EFFORT`
- `FILE_TTL_SECONDS`

기본값은 `backend/app/core/config.py` 에 있다.

## 실행

```bash
cd backend
.venv312/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100
```

헬스체크:

```bash
curl http://127.0.0.1:8100/api/health
```

## API

### 1. 마크다운 변환

`POST /api/reports/convert`

폼 필드:

- `markdown`: 변환할 마크다운 문자열

예시:

```bash
curl -X POST http://127.0.0.1:8100/api/reports/convert \
  -F 'markdown=# 제목

## 섹션

본문입니다.'
  -o output.hwpx
```

응답:

- `application/octet-stream`
- 첨부 파일명 `output.hwpx`

### 2. 원문 기반 보고서 생성

`POST /api/reports/generate-pipeline`

폼 필드:

- `source_text`: 원문 텍스트, 필수
- `title_hint`: 제목 힌트, 선택
- `organization`: 기관명, 선택
- `cover_image`: 표지 이미지 파일, 선택

응답은 `application/x-ndjson` 스트림이다.

이벤트 타입:

- `status`
- `token`
- `result`
- `error`

예시:

```bash
curl -N -X POST http://127.0.0.1:8100/api/reports/generate-pipeline \
  -F 'source_text=스마트물류 플랫폼 구축 사업 추진 계획을 정리한다...' \
  -F 'title_hint=스마트물류 플랫폼 구축 사업 추진 계획' \
  -F 'organization=Cryptolab'
```

### 3. 생성 파일 다운로드

`GET /api/reports/download/{file_id}?format=hwpx`

예시:

```bash
curl -O 'http://127.0.0.1:8100/api/reports/download/<file_id>?format=hwpx'
```

## 지원하는 마크다운 문법

- `# 제목` -> H1 섹션
- `## 제목` -> H2
- `### 제목` -> H3
- `- 항목`, `○ 항목` -> 불릿
- `가. 항목`, `나. 항목` -> 순서형 항목
- `| 헤더 | 값 |` -> 표
- `※ 주석` -> 노트
- `---` -> 구분선
- `<!-- pagebreak -->` -> 페이지 나눔
- 코드블록은 본문에서 제외

## 검증

장문 마크다운 기준 테스트:

```bash
PYTHONPATH=backend backend/.venv312/bin/python -m unittest \
  backend.tests.test_report_hwpx_builder \
  backend.tests.test_convert_api
```

실제 API 호출 예시:

```bash
cd backend
.venv312/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100
```

다른 터미널에서:

```bash
backend/.venv312/bin/python - <<'PY'
from pathlib import Path
import httpx

markdown = """# 실제 API 검증

## 개요

장문 마크다운을 실제 convert 엔드포인트로 전송한다.

- API 응답 확인
- HWPX 생성 확인
"""

resp = httpx.post(
    "http://127.0.0.1:8100/api/reports/convert",
    files={"markdown": (None, markdown)},
    timeout=60.0,
)
Path("output.hwpx").write_bytes(resp.content)
print(resp.status_code, len(resp.content))
PY
```

## 참고

- 생성 파일은 기본적으로 `backend/storage/generated` 아래에 저장된다.
- `/api/reports/convert` 는 임시 파일을 응답 후 삭제한다.
- `/api/reports/generate-pipeline` 결과 파일은 TTL 기준으로 정리된다.
- 현재 파이프라인 결과에는 모델 응답 품질 이슈가 남을 수 있으므로, 운영 전 결과 샘플 확인이 필요하다.
