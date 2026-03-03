"""LLM 기반 에이전트 추상 클래스 (Claude / Gemini / Groq 지원)"""

import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..utils.logger import get_logger
from config.settings import get_settings

logger = get_logger("agent")

# JSON 추출 실패 시 사용자 메시지 (2-4)
JSON_PARSE_FAILED_MESSAGE = (
    "RFP 분석 결과를 JSON으로 파싱하지 못했습니다. LLM 응답 형식을 확인해 주세요."
)


class BaseAgent(ABC):
    """LLM 기반 에이전트 (Claude / Gemini / Groq 중 .env 설정에 따라 선택)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        settings = get_settings()
        self._provider = settings.llm_provider
        self.prompts_dir = settings.prompts_dir
        self._prompt_cache: Dict[str, str] = {}

        if self._provider == "claude":
            if not settings.anthropic_api_key:
                raise ValueError(
                    "LLM_PROVIDER=claude 인데 ANTHROPIC_API_KEY가 비어 있습니다. "
                    "https://console.anthropic.com 에서 API 키를 발급한 뒤 .env에 ANTHROPIC_API_KEY=... 로 넣어주세요."
                )
            self._use_claude = True
            self._use_groq = False
            from anthropic import Anthropic
            self._anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
            self._anthropic_model = model or settings.anthropic_model
            self.api_key = settings.anthropic_api_key
            self.model = self._anthropic_model
        elif self._provider == "groq":
            if not settings.groq_api_key:
                raise ValueError(
                    "LLM_PROVIDER=groq 인데 GROQ_API_KEY가 비어 있습니다. "
                    "https://console.groq.com 에서 무료 API 키를 발급한 뒤 .env에 GROQ_API_KEY=... 로 넣어주세요."
                )
            self._use_claude = False
            self._use_groq = True
            from groq import Groq
            self._groq_client = Groq(api_key=settings.groq_api_key)
            self._groq_model = model or settings.groq_model
            self.api_key = settings.groq_api_key
            self.model = self._groq_model
        else:
            # gemini (기본)
            self._use_claude = False
            self._use_groq = False
            from google import genai
            from google.genai import types
            self._genai_types = types
            self.api_key = api_key or settings.gemini_api_key
            self.model = model or settings.gemini_model
            self.client = genai.Client(api_key=self.api_key)

    @abstractmethod
    async def execute(
        self,
        input_data: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> Any:
        """에이전트 실행"""
        pass

    def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        LLM API 호출 (Claude / Gemini / Groq)

        Args:
            system_prompt: 시스템 프롬프트
            user_message: 사용자 메시지
            max_tokens: 최대 출력 토큰 수 (None이면 .env LLM_MAX_TOKENS 사용)

        Returns:
            모델 응답 텍스트
        """
        if max_tokens is None:
            max_tokens = get_settings().llm_max_tokens_default
        if self._use_claude:
            return self._call_claude(system_prompt, user_message, max_tokens)
        if self._use_groq:
            return self._call_groq(system_prompt, user_message, max_tokens)
        return self._call_gemini(system_prompt, user_message, max_tokens)

    def _call_claude(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> str:
        """Claude (Anthropic) API 호출 (재시도·로깅 적용)"""
        settings = get_settings()
        max_retries = settings.llm_retry_count
        base_delay = settings.llm_retry_base_delay_seconds
        delay_sec = settings.llm_delay_seconds
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            logger.debug(
                "LLM 호출 model=%s input_len=%d",
                self._anthropic_model,
                len(user_message),
            )
            try:
                message = self._anthropic_client.messages.create(
                    model=self._anthropic_model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                if not message.content or not hasattr(message.content[0], "text"):
                    raise ValueError("Claude 응답이 비어 있습니다.")
                result = message.content[0].text.strip()
                if not result:
                    raise ValueError("Claude 응답 텍스트가 비어 있습니다.")
                elapsed = time.perf_counter() - t0
                logger.debug(
                    "LLM 응답 len=%d elapsed=%.2fs",
                    len(result),
                    elapsed,
                )
                if delay_sec > 0:
                    time.sleep(delay_sec)
                return result
            except Exception as e:
                last_error = e
                err_str = str(e).upper()
                is_retryable = (
                    "429" in err_str
                    or "RATE_LIMIT" in err_str
                    or "OVERLOADED" in err_str
                    or "TIMEOUT" in err_str
                )
                if is_retryable and attempt < max_retries - 1:
                    wait = base_delay * (2**attempt)
                    logger.warning(
                        "Claude 일시 오류, %d초 후 재시도 (%d/%d): %s",
                        int(wait),
                        attempt + 1,
                        max_retries,
                        str(e)[:200],
                    )
                    time.sleep(wait)
                    continue
                logger.error("Claude API 호출 실패: %s: %s", type(e).__name__, (str(e)[:200] or ""))
                raise RuntimeError(f"Claude API 호출 실패: {e}") from e
        raise RuntimeError(f"Claude API 호출 실패: {last_error}") from last_error

    def _call_groq(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> str:
        """Groq API 호출 (413/429 대응: 입력 길이 제한·재시도·로깅)"""
        settings = get_settings()
        max_chars = settings.groq_max_user_message_chars or 0
        if max_chars > 0 and len(user_message) > max_chars:
            user_message = user_message[:max_chars] + "\n\n... (길이 제한으로 일부 생략됨)"
            logger.debug("Groq user_message %d자로 제한 적용", max_chars)
        max_retries = settings.llm_retry_count
        base_delay = settings.llm_retry_base_delay_seconds
        delay_sec = settings.llm_delay_seconds
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            logger.debug(
                "LLM 호출 model=%s input_len=%d",
                self._groq_model,
                len(user_message),
            )
            try:
                response = self._groq_client.chat.completions.create(
                    model=self._groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    max_tokens=max_tokens,
                )
                result = (response.choices[0].message.content or "").strip()
                if not result:
                    raise ValueError("Groq 응답이 비어 있습니다.")
                elapsed = time.perf_counter() - t0
                logger.debug(
                    "LLM 응답 len=%d elapsed=%.2fs",
                    len(result),
                    elapsed,
                )
                if delay_sec > 0:
                    time.sleep(delay_sec)
                return result
            except Exception as e:
                last_error = e
                err_str = str(e).upper()
                is_retryable = (
                    "429" in err_str
                    or "RATE_LIMIT" in err_str
                    or "413" in err_str
                    or "OVERLOADED" in err_str
                )
                if is_retryable and attempt < max_retries - 1:
                    wait = base_delay * (2**attempt)
                    logger.warning(
                        "Groq 일시 오류, %d초 후 재시도 (%d/%d): %s",
                        int(wait),
                        attempt + 1,
                        max_retries,
                        str(e)[:200],
                    )
                    time.sleep(wait)
                    continue
                logger.error("Groq API 호출 실패: %s: %s", type(e).__name__, (str(e)[:200] or ""))
                raise RuntimeError(f"Groq API 호출 실패: {e}") from e
        raise RuntimeError(f"Groq API 호출 실패: {last_error}") from last_error

    def _call_gemini(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
    ) -> str:
        """Gemini API 호출 (설정 기반 재시도·로깅)"""
        settings = get_settings()
        max_retries = settings.llm_retry_count
        base_delay = settings.llm_retry_base_delay_seconds
        types = self._genai_types
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            logger.debug(
                "LLM 호출 model=%s input_len=%d",
                self.model,
                len(user_message),
            )
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=max_tokens,
                    ),
                )
                if response.text is None:
                    raise ValueError("Gemini 응답 텍스트가 비어 있습니다.")
                result = response.text
                elapsed = time.perf_counter() - t0
                logger.debug(
                    "LLM 응답 len=%d elapsed=%.2fs",
                    len(result),
                    elapsed,
                )
                delay_sec = settings.llm_delay_seconds
                if delay_sec > 0:
                    time.sleep(delay_sec)
                return result
            except Exception as e:
                err_str = str(e).upper()
                is_quota_error = (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "QUOTA" in err_str
                    or "RATE_LIMIT" in err_str
                )
                if is_quota_error and attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Gemini 할당량/속도 제한. %d초 후 재시도 (%d/%d)",
                        int(delay),
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(delay)
                    continue
                logger.error("Gemini API 호출 실패: %s: %s", type(e).__name__, (str(e)[:200] or ""))
                if is_quota_error:
                    raise RuntimeError(
                        "Gemini API 할당량 초과(429). .env에서 LLM_PROVIDER=groq 또는 LLM_PROVIDER=claude 로 바꾸고 해당 API 키를 설정하면 다른 모델로 전환할 수 있습니다."
                    ) from e
                raise RuntimeError(
                    "Gemini API 호출 실패. API 키와 네트워크를 확인하세요."
                ) from e

    def _load_prompt(self, prompt_name: str) -> str:
        """
        프롬프트 템플릿 로드 (캐시 사용으로 디스크 I/O 감소)

        Args:
            prompt_name: 프롬프트 파일명 (확장자 제외)

        Returns:
            프롬프트 텍스트
        """
        if prompt_name in self._prompt_cache:
            return self._prompt_cache[prompt_name]
        prompt_path = self.prompts_dir / f"{prompt_name}.txt"
        if not prompt_path.exists():
            logger.warning(f"프롬프트 파일 없음: {prompt_path}")
            return ""
        text = prompt_path.read_text(encoding="utf-8")
        self._prompt_cache[prompt_name] = text
        return text

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        텍스트에서 JSON 추출 (LLM 응답 형식 다양성 대응)

        Args:
            text: JSON을 포함한 텍스트

        Returns:
            파싱된 JSON 딕셔너리
        """
        if not (text or "").strip():
            return {}

        # 후보 문자열 수집 (코드 블록 우선, 그다음 중괄호 블록)
        candidates: List[str] = []
        for pattern in [
            r"```(?:json)?\s*([\s\S]*?)\s*```",
            r"(\{[\s\S]*\})",
        ]:
            for match in re.finditer(pattern, text):
                candidates.append(match.group(1).strip())

        # 중괄호로 시작하는 연속 영역만 있으면 한 번 더 시도 (가장 긴 것)
        if not candidates and "{" in text:
            start = text.index("{")
            depth = 0
            end = start
            for i, c in enumerate(text[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if depth == 0 and end > start:
                candidates.append(text[start : end + 1])

        def _parse(s: str) -> Optional[Dict[str, Any]]:
            s = (s or "").strip()
            if not s:
                return None
            # trailing comma 등 흔한 비표준 수정
            s = re.sub(r",\s*}(?=\s*[\]}]|$)", "}", s)
            s = re.sub(r",\s*](?=\s*[\]}]|$)", "]", s)
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return None

        for raw in candidates:
            if not raw:
                continue
            result = _parse(raw)
            if result is not None and isinstance(result, dict):
                return result

        # 폴백: 마크다운 뒤에 JSON이 올 때. "project_name" 등 키가 보이는 구간에서 { } 블록 찾기
        for anchor in ('"project_name"', '"client_name"', '"project_overview"', '"project_type"'):
            idx = text.find(anchor)
            if idx == -1:
                continue
            # anchor 앞에서 가장 가까운 { 찾기 (같은 줄 또는 최근)
            start = text.rfind("{", 0, idx + 1)
            if start == -1:
                continue
            depth = 0
            end = start
            for i, c in enumerate(text[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if depth == 0 and end > start:
                block = text[start : end + 1]
                result = _parse(block)
                if result is not None and isinstance(result, dict) and len(result) >= 2:
                    logger.debug("JSON 추출: 마크다운 뒤 블록에서 복구")
                    return result

        # 폴백: 마크다운 **key**: "value" 형태만 있을 때 (Groq 등이 JSON 대신 마크다운 반환)
        md_key_value = re.findall(
            r"\*\*([^*]+)\*\*\s*:\s*\"([^\"]*)\"",
            text,
        )
        if md_key_value:
            recovered = {k.strip().replace(" ", "_"): v for k, v in md_key_value}
            if recovered:
                logger.debug("JSON 추출: 마크다운 **key**: \"value\" 형태에서 복구")
                return recovered

        snippet = (text[:300] + "..." if len(text) > 300 else text).replace("\n", " ")
        preview = (snippet[:200] + "..." if len(snippet) > 200 else snippet) if snippet else "(빈 응답)"
        logger.warning(f"JSON 추출 실패 (응답 일부: {preview}). {JSON_PARSE_FAILED_MESSAGE}")
        return {}

    def _normalize_json_keys(
        self, data: Dict[str, Any], alias_map: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        모델별 응답 키 차이 흡수: camelCase 등 별칭을 snake_case로 복사 (기존 키 없을 때만).
        Claude/Gemini/Groq 등 모델별로 키 명명이 달라도 공통 처리 가능.
        """
        if not data or not isinstance(data, dict):
            return data
        for alias_key, canonical_key in alias_map.items():
            if alias_key in data and canonical_key not in data:
                data[canonical_key] = data[alias_key]
        return data

    def _truncate_text(self, text: str, max_chars: int = 30000) -> str:
        """텍스트 길이 제한"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n... (텍스트가 잘렸습니다)"
