from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownTemplate:
    name: str
    syntax: str
    when_to_use: str


MARKDOWN_TEMPLATES: tuple[MarkdownTemplate, ...] = (
    MarkdownTemplate(
        name="대섹션",
        syntax="# 섹션 제목",
        when_to_use="큰 장/섹션 전환이 필요할 때 사용한다.",
    ),
    MarkdownTemplate(
        name="소제목",
        syntax="## 소제목",
        when_to_use="섹션 안에서 내용을 주제별로 나눌 때 사용한다. □ 기호가 자동 추가된다.",
    ),
    MarkdownTemplate(
        name="번호 소제목",
        syntax="## 1. 소제목",
        when_to_use="번호체계가 필요한 소제목에 사용한다. □ 대신 번호가 표시된다. 예: ## 1. 개요, ## 2. 현황",
    ),
    MarkdownTemplate(
        name="세부 소제목",
        syntax="### 세부 소제목",
        when_to_use="세부 항목을 한 단계 더 나눌 때 사용한다.",
    ),
    MarkdownTemplate(
        name="번호 세부 소제목",
        syntax="### 1.1 세부 소제목",
        when_to_use="번호체계가 필요한 세부 소제목에 사용한다. 예: ### 1.1 개요, ### 2.3 조치사항",
    ),
    MarkdownTemplate(
        name="서술 문단",
        syntax="일반 문단",
        when_to_use="배경, 설명, 맥락, 해석처럼 문장 흐름이 중요한 내용에 사용한다.",
    ),
    MarkdownTemplate(
        name="불릿",
        syntax="- 항목",
        when_to_use="단순 나열, 특징, 체크포인트처럼 병렬 항목을 보여줄 때 사용한다.",
    ),
    MarkdownTemplate(
        name="하위 불릿",
        syntax="    - 하위 항목",
        when_to_use="상위 불릿의 세부사항을 붙일 때 사용한다.",
    ),
    MarkdownTemplate(
        name="순서 불릿",
        syntax="가. 항목",
        when_to_use="순서, 절차, 단계, 조치 순번이 있는 내용을 보여줄 때 사용한다.",
    ),
    MarkdownTemplate(
        name="주석",
        syntax="※ 주석",
        when_to_use="출처, 기준일, 예외사항처럼 본문 흐름과 분리할 정보에 사용한다.",
    ),
    MarkdownTemplate(
        name="표",
        syntax="| 헤더 | 헤더 |\n| --- | --- |\n| 값 | 값 |",
        when_to_use="비교, 현황, 일정, 수치, 속성 대응처럼 열 구조가 분명한 데이터에 사용한다.",
    ),
    MarkdownTemplate(
        name="구분선",
        syntax="---",
        when_to_use="의미 있는 구획 전환이 필요할 때만 제한적으로 사용한다.",
    ),
    MarkdownTemplate(
        name="페이지 나눔",
        syntax="<!-- pagebreak -->",
        when_to_use="출력 문서에서 페이지를 명시적으로 나눠야 할 때 사용한다.",
    ),
)


def render_template_guide() -> str:
    lines = ["사용 가능한 마크다운 템플릿:"]
    for template in MARKDOWN_TEMPLATES:
        lines.append(f"- {template.name}: `{template.syntax}`")
        lines.append(f"  사용 시점: {template.when_to_use}")
    return "\n".join(lines)
