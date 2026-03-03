"""LLM 기반 에이전트 추상 클래스 (Claude / Gemini / Groq 지원)"""

import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..utils.logger import get_logger
from config.settings import get_settings

logger = get_logger("agent")


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
        max_tokens: int = 4096,
    ) -> str:
        """
        LLM API 호출 (Claude / Gemini / Groq)

        Args:
            system_prompt: 시스템 프롬프트
            user_message: 사용자 메시지
            max_tokens: 최대 출력 토큰 수

        Returns:
            모델 응답 텍스트
        """
        if self._use_claude:
            return self._call_claude(system_prompt, user_message, max_tokens)
        if self._use_groq:
            return self._call_groq(system_prompt, user_message, max_tokens)
        return self._call_gemini(system_prompt, user_message, max_tokens)

    def _is_rate_limit_error(self, e: Exception) -> bool:
        """429/할당량/속도 제한 오류 여부 (재시도 대상)"""
        err_str = str(e).upper()
        return (
            "429" in err_str
            or "RESOURCE_EXHAUSTED" in err_str
            or "QUOTA" in err_str
            or "RATE_LIMIT" in err_str
            or "RATE LIMIT" in err_str
            or "OVERLOADED" in err_str
        )

    def _call_claude(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """Claude (Anthropic) API 호출 (429 시 재시도 + 딜레이)"""
        logger.debug("Claude API 호출 (model: %s)", self._anthropic_model)
        max_retries = 3
        base_delay = max(5, int(get_settings().gemini_delay_seconds))  # 429 시 재시도: base_delay, 2배, 4배

        for attempt in range(max_retries):
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
                delay_sec = get_settings().gemini_delay_seconds
                if delay_sec > 0:
                    time.sleep(delay_sec)
                return result
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Claude 할당량/속도 제한. %d초 후 재시도 (%d/%d)",
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(delay)
                    continue
                logger.error("Claude API 호출 실패: %s", str(e)[:500])
                raise RuntimeError(f"Claude API 호출 실패: {e}") from e

    def _call_groq(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """Groq API 호출 (429 시 재시도 + 딜레이)"""
        logger.debug("Groq API 호출 (model: %s)", self._groq_model)
        max_retries = 3
        base_delay = max(5, int(get_settings().gemini_delay_seconds))  # 429 시 재시도: base_delay, 2배, 4배

        for attempt in range(max_retries):
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
                delay_sec = get_settings().gemini_delay_seconds
                if delay_sec > 0:
                    time.sleep(delay_sec)
                return result
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Groq 할당량/속도 제한. %d초 후 재시도 (%d/%d)",
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(delay)
                    continue
                logger.error("Groq API 호출 실패: %s", str(e)[:500])
                raise RuntimeError(f"Groq API 호출 실패: {e}") from e

    def _call_gemini(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """Gemini API 호출 (429 시 재시도 + 딜레이)"""
        logger.debug("Gemini API 호출 (model: %s)", self.model)
        types = self._genai_types
        max_retries = 3
        base_delay = max(5, int(get_settings().gemini_delay_seconds))  # 429 시 재시도: base_delay, 2배, 4배

        for attempt in range(max_retries):
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
                delay_sec = get_settings().gemini_delay_seconds
                if delay_sec > 0:
                    logger.debug("API 호출 간 대기 %.1f초", delay_sec)
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
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(delay)
                    continue
                logger.error("Gemini API 호출 실패: %s", str(e)[:500])
                if is_quota_error:
                    raise RuntimeError(
                        "Gemini API 할당량 초과(429). .env에서 LLM_PROVIDER=groq 또는 LLM_PROVIDER=claude 로 바꾸고 해당 API 키를 설정하면 다른 모델로 전환할 수 있습니다."
                    ) from e
                raise RuntimeError(
                    "Gemini API 호출 실패. API 키와 네트워크를 확인하세요."
                ) from e

    def _load_prompt(self, prompt_name: str) -> str:
        """
        프롬프트 템플릿 로드

        Args:
            prompt_name: 프롬프트 파일명 (확장자 제외)

        Returns:
            프롬프트 텍스트
        """
        prompt_path = self.prompts_dir / f"{prompt_name}.txt"

        if not prompt_path.exists():
            logger.warning(f"프롬프트 파일 없음: {prompt_path}")
            return ""

        return prompt_path.read_text(encoding="utf-8")

    def _clean_json_string(self, s: str) -> str:
        """JSON 문자열에서 흔한 LLM 오류 정리 (끝 쉼표 등)"""
        s = s.strip()
        # trailing comma 제거: , } -> } , , ] -> ]
        s = re.sub(r",\s*}", "}", s)
        s = re.sub(r",\s*]", "]", s)
        return s

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        텍스트에서 JSON 추출 (다양한 LLM 응답 형식 대응)

        Args:
            text: JSON을 포함한 텍스트

        Returns:
            파싱된 JSON 딕셔너리
        """
        if not (text or text.strip()):
            logger.error("JSON 추출 실패: 응답 비어 있음")
            return {}

        text = text.strip()

        def try_parse(raw: str) -> Optional[Dict[str, Any]]:
            raw = self._clean_json_string(raw)
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None

        # 1) 전체가 JSON인 경우
        result = try_parse(text)
        if result is not None:
            return result

        # 2) ```json ... ``` 블록 (마지막 블록 우선 - 최종 답이 끝에 있는 경우 많음)
        for block_pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
            matches = list(re.finditer(block_pattern, text))
            for m in reversed(matches):
                result = try_parse(m.group(1))
                if result is not None:
                    return result

        # 3) 첫 번째 { 부터 괄호 균형 맞춰서 추출
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        result = try_parse(text[start : i + 1])
                        if result is not None:
                            return result
                        break

        logger.warning(
            "JSON 추출 실패 (응답 일부): %s",
            text[:300].replace("\n", " ") if len(text) > 300 else text.replace("\n", " "),
        )
        return {}

    def _truncate_text(self, text: str, max_chars: int = 30000) -> str:
        """텍스트 길이 제한"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n... (텍스트가 잘렸습니다)"
