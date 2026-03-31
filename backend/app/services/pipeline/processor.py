from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.services.pipeline.outline import build_outline_messages, build_outline_repair_messages, parse_outline
from app.services.pipeline.splitter import build_split_messages
from app.services.pipeline.writer import build_write_messages, parse_written_content

if TYPE_CHECKING:
    from app.services.llm_client import VllmClient

# 과도한 재귀 분해를 줄여 H1 섹션 수를 보수적으로 유지한다.
MAX_DEPTH = 1
SPLIT_THRESHOLD = 3200  # chars (rough token proxy)


@dataclass
class ProcessedSection:
    title: str
    content: str
    subsections: list[ProcessedSection] = field(default_factory=list)


@dataclass
class PipelineProgress:
    phase: str
    message: str


@dataclass
class PipelineComplete:
    title: str
    sections: list[ProcessedSection]


PipelineEvent = PipelineProgress | PipelineComplete


def _infer_fallback_title(text: str, title_hint: str | None = None) -> str:
    if title_hint and title_hint.strip():
        return title_hint.strip()

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        if len(line) > 40:
            return f"{line[:37].rstrip()}..."
        return line

    return "보고서"


async def _generate_outline(
    *,
    llm: VllmClient,
    text: str,
    title_hint: str | None = None,
    enable_thinking: bool = True,
) -> dict | None:
    outline_raw = await llm.generate(
        build_outline_messages(text, title_hint),
        temperature=0.2,
        enable_thinking=enable_thinking,
    )
    outline = parse_outline(outline_raw)
    if outline and outline.get("sections"):
        return outline

    repair_raw = await llm.generate(
        build_outline_repair_messages(outline_raw, title_hint),
        temperature=0.0,
        enable_thinking=enable_thinking,
    )
    repaired = parse_outline(repair_raw)
    if repaired and repaired.get("sections"):
        return repaired

    return None


async def process_section(
    *,
    llm: VllmClient,
    title: str,
    text: str,
    depth: int = 0,
    enable_thinking: bool = True,
) -> ProcessedSection:
    if not text.strip():
        return ProcessedSection(title=title, content="")

    # 짧거나 max depth 도달 → 바로 작성
    if len(text) <= SPLIT_THRESHOLD or depth >= MAX_DEPTH:
        messages = build_write_messages(title, text)
        raw = await llm.generate(messages, temperature=0.3, enable_thinking=enable_thinking)
        return ProcessedSection(title=title, content=parse_written_content(title, raw))

    # 길면 outline 생성 후 재귀 분해
    outline = await _generate_outline(llm=llm, text=text, title_hint=title, enable_thinking=enable_thinking)

    if not outline or not outline.get("sections"):
        # outline 실패 → 바로 작성
        messages = build_write_messages(title, text)
        raw = await llm.generate(messages, temperature=0.3, enable_thinking=enable_thinking)
        return ProcessedSection(title=title, content=parse_written_content(title, raw))

    subsections: list[ProcessedSection] = []
    for sec in outline["sections"]:
        sec_title = sec.get("title", "")
        sec_desc = sec.get("description")

        # 섹션별 텍스트 추출
        split_raw = await llm.generate(
            build_split_messages(text, sec_title, sec_desc),
            temperature=0.1,
            enable_thinking=enable_thinking,
        )
        sub_text = split_raw.strip()
        if not sub_text or "[EMPTY]" in sub_text[:20]:
            continue

        sub = await process_section(
            llm=llm,
            title=sec_title,
            text=sub_text,
            depth=depth + 1,
            enable_thinking=enable_thinking,
        )
        subsections.append(sub)

    return ProcessedSection(title=title, content="", subsections=subsections)


async def run_pipeline(
    *,
    llm: VllmClient,
    text: str,
    title_hint: str | None = None,
    enable_thinking: bool = True,
) -> AsyncIterator[PipelineEvent]:
    """전체 파이프라인 실행. PipelineProgress를 yield하고 마지막에 PipelineComplete를 yield."""

    yield PipelineProgress(phase="outline", message="문서 구조(outline)를 생성하고 있습니다.")

    # 1단계: 전체 outline
    outline = await _generate_outline(
        llm=llm,
        text=text,
        title_hint=title_hint,
        enable_thinking=enable_thinking,
    )

    if not outline or not outline.get("sections"):
        # outline 실패 → 단일 섹션으로 처리
        fallback_title = _infer_fallback_title(text, title_hint)
        yield PipelineProgress(phase="writing", message=f"섹션 작성 중 (1/1): {fallback_title}")
        raw = await llm.generate(
            build_write_messages(fallback_title, text),
            temperature=0.3,
            enable_thinking=enable_thinking,
        )
        yield PipelineComplete(
            title=_infer_fallback_title(text, title_hint),
            sections=[ProcessedSection(title=fallback_title, content=parse_written_content(fallback_title, raw))],
        )
        return

    doc_title = outline.get("title") or _infer_fallback_title(text, title_hint)
    outline_sections = outline["sections"]
    total = len(outline_sections)
    sections: list[ProcessedSection] = []

    for idx, sec in enumerate(outline_sections, 1):
        sec_title = sec.get("title", "")
        sec_desc = sec.get("description")

        yield PipelineProgress(phase="writing", message=f"섹션 작성 중 ({idx}/{total}): {sec_title}")

        # 섹션별 텍스트 추출
        split_raw = await llm.generate(
            build_split_messages(text, sec_title, sec_desc),
            temperature=0.1,
            enable_thinking=enable_thinking,
        )
        sub_text = split_raw.strip()
        if not sub_text or "[EMPTY]" in sub_text[:20]:
            continue

        processed = await process_section(
            llm=llm,
            title=sec_title,
            text=sub_text,
            depth=0,
            enable_thinking=enable_thinking,
        )
        sections.append(processed)

    yield PipelineComplete(title=doc_title, sections=sections)
