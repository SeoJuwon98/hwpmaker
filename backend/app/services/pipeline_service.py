import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import Request

from app.core.config import Settings
from app.models.report import PipelineResult, ReportRequest
from app.services.llm_client import VllmClient
from app.services.markdown_exporter import MarkdownExporter
from app.services.markdown_parser import parse as parse_markdown
from app.services.pipeline.processor import PipelineComplete, PipelineProgress, ProcessedSection, run_pipeline
from app.services.pipeline.synthesizer import build_synthesize_messages
from app.services.pipeline.writer import normalize_report_markdown


class PipelineService:
    def __init__(
        self,
        settings: Settings,
        llm_client: VllmClient,
        markdown_exporter: MarkdownExporter,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.markdown_exporter = markdown_exporter
        self.settings.storage_path.mkdir(parents=True, exist_ok=True)

    async def stream_pipeline_report(self, *, payload: ReportRequest, request: Request, cover_image: bytes | None = None, cover_image_format: str = "png") -> AsyncIterator[str]:
        try:
            doc_title = ""
            sections: list[ProcessedSection] = []

            async for event in run_pipeline(
                llm=self.llm_client,
                text=payload.normalized_source_text,
                title_hint=payload.normalized_title_hint,
                enable_thinking=self.settings.vllm_enable_thinking,
            ):
                if isinstance(event, PipelineProgress):
                    yield self._event("status", {"phase": event.phase, "message": event.message})
                elif isinstance(event, PipelineComplete):
                    doc_title = event.title
                    sections = event.sections

            if not sections:
                raise RuntimeError("파이프라인이 섹션을 생성하지 못했습니다.")

            # synthesis
            flat_sections = self._flatten_sections(sections)
            fallback_md = "\n\n".join(section["content"] for section in flat_sections).strip()
            if len(flat_sections) > 1:
                yield self._event("status", {"phase": "synthesis", "message": "섹션을 통합하고 있습니다."})
                synth_raw = await self.llm_client.generate(
                    build_synthesize_messages(flat_sections, doc_title=doc_title),
                    temperature=0.2,
                    enable_thinking=self.settings.vllm_enable_thinking,
                )
                md_text = normalize_report_markdown(
                    synth_raw.strip(),
                    fallback=fallback_md,
                    default_title=doc_title or "보고서",
                )
                if self._is_synthesis_incomplete(md_text, flat_sections):
                    md_text = fallback_md
            else:
                md_text = normalize_report_markdown(
                    flat_sections[0]["content"] if flat_sections else "",
                    fallback=fallback_md,
                    default_title=doc_title or "보고서",
                )

            yield self._event("status", {"phase": "rendering", "message": "HWPX를 생성하고 있습니다."})

            # preview 스트림
            chunk_size = 180
            for i in range(0, len(md_text), chunk_size):
                yield self._event("token", {"value": md_text[i:i + chunk_size]})

            # 마크다운 → HwpDocument → HWPX
            hwp_doc = parse_markdown(
                md_text,
                title=doc_title,
                organization=payload.normalized_organization,
                cover_image=cover_image,
                cover_image_format=cover_image_format,
            )

            file_id = uuid.uuid4().hex
            hwpx_path = self.settings.storage_path / f"{file_id}.hwpx"
            await asyncio.to_thread(
                self.markdown_exporter.export_markdown,
                target_path=hwpx_path,
                document=hwp_doc,
            )

            result = PipelineResult(
                title=doc_title,
                body=md_text,
                hwpx_download_url=str(request.url_for("download_report", file_id=file_id)) + "?format=hwpx",
            )
            yield self._event("result", result.model_dump())

        except Exception as exc:
            yield self._event("error", {"message": "파이프라인 처리 중 오류가 발생했습니다.", "detail": str(exc)})

    def resolve_download_path(self, file_id: str, file_format: str) -> Path:
        if file_format not in {"hwpx"}:
            raise FileNotFoundError("unsupported format")

        safe_file_id = re.sub(r"[^a-f0-9]", "", file_id)
        candidate = self.settings.storage_path / f"{safe_file_id}.{file_format}"
        if not candidate.exists():
            raise FileNotFoundError("file not found")
        return candidate

    async def cleanup_expired_files(self) -> None:
        await asyncio.to_thread(self._cleanup_expired_files_sync)

    def _cleanup_expired_files_sync(self) -> None:
        ttl = self.settings.file_ttl_seconds
        now = time.time()

        for path in self.settings.storage_path.glob("*"):
            if not path.is_file():
                continue

            age_seconds = now - path.stat().st_mtime
            if age_seconds > ttl:
                path.unlink(missing_ok=True)

    def _flatten_sections(self, sections: list[ProcessedSection]) -> list[dict]:
        result = []
        for sec in sections:
            if sec.subsections:
                result.extend(self._flatten_sections(sec.subsections))
            elif sec.content:
                result.append({"title": sec.title, "content": sec.content})
        return result

    def _is_synthesis_incomplete(self, md_text: str, sections: list[dict]) -> bool:
        if not md_text.strip():
            return True
        lines = md_text.splitlines()
        # H1(# ) + H2(## ) 모두 포함하여 구조 헤딩 수를 센다
        # "## "은 "# "으로도 시작하므로 정확히 구분
        h1_count = sum(1 for line in lines if re.match(r"^# [^#]", line.strip()))
        h2_count = sum(1 for line in lines if re.match(r"^## [^#]", line.strip()))
        heading_count = h1_count + h2_count
        if heading_count < len(sections):
            return True
        return any(section["title"] and section["title"] not in md_text for section in sections)

    def _event(self, event_type: str, data: dict[str, Any]) -> str:
        return json.dumps({"event": event_type, "data": data}, ensure_ascii=False) + "\n"
