import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import Settings, get_settings
from app.models.report import ReportRequest
from app.services.llm_client import VllmClient
from app.services.markdown_exporter import MarkdownExporter
from app.services.markdown_parser import parse as parse_markdown
from app.services.pipeline_service import PipelineService

router = APIRouter()


def get_pipeline_service(settings: Settings = Depends(get_settings)) -> PipelineService:
    return PipelineService(
        settings=settings,
        llm_client=VllmClient(settings),
        markdown_exporter=MarkdownExporter(),
    )


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/reports/convert")
async def convert_markdown(
    background_tasks: BackgroundTasks,
    markdown: str = Form(...),
) -> FileResponse:
    """마크다운 텍스트를 받아 HWPX 파일로 변환해 반환한다."""
    exporter = MarkdownExporter()
    document = parse_markdown(markdown)

    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as tmp:
        output_path = Path(tmp.name)

    exporter.export_markdown(target_path=output_path, document=document)
    background_tasks.add_task(output_path.unlink, True)
    return FileResponse(
        path=output_path,
        filename="output.hwpx",
        media_type="application/octet-stream",
    )


@router.post("/reports/generate-pipeline")
async def generate_pipeline_report(
    request: Request,
    service: PipelineService = Depends(get_pipeline_service),
    source_text: str = Form(default=""),
    title_hint: str | None = Form(default=None),
    organization: str | None = Form(default=None),
    cover_image: UploadFile | None = File(default=None),
) -> StreamingResponse:
    payload = ReportRequest(
        source_text=source_text or None,
        title_hint=title_hint or None,
        organization=organization or None,
    )
    cover_image_bytes: bytes | None = None
    cover_image_format = "png"
    if cover_image and cover_image.filename:
        cover_image_bytes = await cover_image.read()
        ext = (cover_image.filename.rsplit(".", 1)[-1] or "png").lower()
        cover_image_format = ext

    await service.cleanup_expired_files()
    return StreamingResponse(
        service.stream_pipeline_report(
            payload=payload,
            request=request,
            cover_image=cover_image_bytes,
            cover_image_format=cover_image_format,
        ),
        media_type="application/x-ndjson",
    )


@router.get("/reports/download/{file_id}", name="download_report")
async def download_report(
    file_id: str,
    file_format: str = Query(default="hwpx"),
    service: PipelineService = Depends(get_pipeline_service),
) -> FileResponse:
    try:
        path = service.resolve_download_path(file_id=file_id, file_format=file_format)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = path.name
    return FileResponse(path=path, filename=filename, media_type="application/octet-stream")
