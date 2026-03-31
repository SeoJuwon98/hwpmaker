import json
import re

import httpx

from app.core.config import Settings


class VllmClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
    ) -> str:
        effective_max_tokens = max_tokens or self.settings.vllm_max_tokens
        effective_enable_thinking = (
            self.settings.vllm_enable_thinking if enable_thinking is None else enable_thinking
        )
        message = await self._request_message(
            messages,
            temperature=temperature,
            max_tokens=effective_max_tokens,
            enable_thinking=effective_enable_thinking,
        )

        content = self._extract_content_text(message.get("content"))
        if content:
            return self._strip_think(content)

        if effective_enable_thinking and (message.get("reasoning") or message.get("reasoning_content")):
            # 재시도: thinking 비활성화 + temperature를 약간 올려 동일 응답 반복 방지
            retry_temp = min(temperature + 0.2, 1.0)
            retry_message = await self._request_message(
                messages,
                temperature=retry_temp,
                max_tokens=effective_max_tokens,
                enable_thinking=False,
            )
            retry_content = self._extract_content_text(retry_message.get("content"))
            if retry_content:
                return self._strip_think(retry_content)

            raise ValueError("vLLM reasoning 응답 재시도 후에도 최종 content가 없습니다.")

        if message.get("reasoning") or message.get("reasoning_content"):
            raise ValueError("vLLM reasoning 응답에 최종 content가 없습니다.")

        raise ValueError("vLLM 응답에서 문서 내용을 찾지 못했습니다.")

    async def _request_message(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        enable_thinking: bool,
    ) -> dict:
        request_payload = {
            "model": self.settings.vllm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        }
        if enable_thinking:
            request_payload["reasoning_effort"] = self.settings.vllm_reasoning_effort
        headers = {
            "Authorization": f"Bearer {self.settings.vllm_api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.settings.vllm_base_url.rstrip('/')}/chat/completions"
        timeout = httpx.Timeout(self.settings.vllm_timeout_seconds, connect=10.0)

        content_parts: list[str] = []
        reasoning_parts: list[str] = []

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=request_payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    if delta.get("content"):
                        content_parts.append(delta["content"])
                    if delta.get("reasoning_content"):
                        reasoning_parts.append(delta["reasoning_content"])
                    if delta.get("reasoning"):
                        reasoning_parts.append(delta["reasoning"])

        message: dict = {}
        if content_parts:
            message["content"] = "".join(content_parts)
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        return message

    @staticmethod
    def _extract_content_text(content: object) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            return "".join(text_parts)

        return ""

    @staticmethod
    def _strip_think(text: str) -> str:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        close_idx = text.find("</think>")
        if close_idx != -1:
            text = text[close_idx + len("</think>"):]
        match = re.search(r"[가-힣]", text)
        if match and match.start() > 200:
            text = text[match.start():]
        return text.strip()
