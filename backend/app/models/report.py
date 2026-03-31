from pydantic import BaseModel, Field, model_validator


class ReportRequest(BaseModel):
    source_text: str | None = Field(default=None, min_length=20, max_length=12000)
    title_hint: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_input(self) -> "ReportRequest":
        if not (self.source_text and self.source_text.strip()):
            raise ValueError("source_text는 필요합니다.")
        return self

    @property
    def normalized_source_text(self) -> str:
        return (self.source_text or "").strip()

    @property
    def normalized_title_hint(self) -> str | None:
        if self.title_hint and self.title_hint.strip():
            return self.title_hint.strip()
        return None

    @property
    def normalized_organization(self) -> str:
        if self.organization and self.organization.strip():
            return self.organization.strip()
        return ""


class PipelineResult(BaseModel):
    title: str
    body: str
    hwpx_download_url: str
