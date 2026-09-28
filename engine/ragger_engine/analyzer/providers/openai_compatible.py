"""OpenAI-Compatible Analyzer Provider for vLLM, LM Studio, or external endpoints."""

import json
import time
from typing import Optional, Tuple
import httpx
from pydantic import ValidationError

from ragger_engine.analyzer.exceptions import ProviderUnavailableError, SchemaValidationError
from ragger_engine.analyzer.models import (
    ProviderTelemetry,
    SemanticObservations,
    StructuralFacts,
)
from ragger_engine.analyzer.prompts import ANALYZER_SYSTEM_PROMPT, build_analysis_user_prompt
from ragger_engine.analyzer.providers.base import BaseAnalyzerProvider
from ragger_engine.analyzer.providers.heuristic import DeterministicHeuristicAnalyzer
from ragger_engine.ingestion.models import AnalysisSample, SourceRecord


class OpenAICompatibleProvider(BaseAnalyzerProvider):
    """Analyzer Provider for any OpenAI-compatible API (e.g. vLLM, LM Studio, LocalAI)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/v1",
        api_key: str = "EMPTY",
        model_name: str = "default",
        timeout_seconds: float = 20.0,
        enable_fallback: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.enable_fallback = enable_fallback
        self.heuristic_fallback = DeterministicHeuristicAnalyzer()

    @property
    def provider_id(self) -> str:
        return "openai_compatible"

    async def analyze(
        self,
        source: SourceRecord,
        facts: StructuralFacts,
        sample: AnalysisSample,
    ) -> Tuple[SemanticObservations, ProviderTelemetry]:
        start_time = time.perf_counter()
        sample_text = (
            sample.sample_text
            or json.dumps(sample.tabular_sample or {}, indent=2)
        )

        user_content = build_analysis_user_prompt(
            filename=source.original_filename,
            structural_facts_json=facts.model_dump_json(indent=2),
            sample_content=sample_text[:6000],
        )

        messages = [
            {"role": "system", "content": ANALYZER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        attempts = 0
        max_attempts = 3
        last_error = None
        raw_response_text = ""

        while attempts < max_attempts:
            attempts += 1
            try:
                raw_response_text, p_tokens, c_tokens = await self._call_api(messages)
                parsed_json = self._extract_json(raw_response_text)
                observations = SemanticObservations.model_validate(parsed_json)

                duration = (time.perf_counter() - start_time) * 1000.0
                telemetry = ProviderTelemetry(
                    requested_provider="openai_compatible",
                    actual_provider="openai_compatible",
                    fallback_used=False,
                    fallback_reason=None,
                    model_name=self.model_name,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    duration_ms=round(duration, 2),
                )
                return observations, telemetry

            except (httpx.ConnectError, httpx.TimeoutException, ProviderUnavailableError) as conn_err:
                last_error = f"API connection error: {conn_err}"
                break

            except (json.JSONDecodeError, ValidationError) as val_err:
                last_error = f"Schema validation error (attempt {attempts}): {val_err}"
                messages.append({"role": "assistant", "content": raw_response_text})
                messages.append(
                    {
                        "role": "user",
                        "content": f"ERROR: Output did not adhere to required JSON schema: {val_err}. Return valid JSON only.",
                    }
                )

        if self.enable_fallback:
            fallback_obs, _ = await self.heuristic_fallback.analyze(source, facts, sample)
            duration = (time.perf_counter() - start_time) * 1000.0
            telemetry = ProviderTelemetry(
                requested_provider="openai_compatible",
                actual_provider="heuristic_offline",
                fallback_used=True,
                fallback_reason=last_error or "Unknown failure in OpenAI provider",
                model_name=self.model_name,
                duration_ms=round(duration, 2),
            )
            return fallback_obs, telemetry

        raise SchemaValidationError(
            f"Failed to obtain valid observational schema from OpenAI provider: {last_error}",
            raw_output=raw_response_text,
            attempts=attempts,
        )

    async def _call_api(self, messages: list) -> Tuple[str, Optional[int], Optional[int]]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise ProviderUnavailableError(
                        f"Provider returned HTTP {resp.status_code}: {resp.text}",
                        provider="openai_compatible",
                    )
                data = resp.json()
                choice = data.get("choices", [{}])[0]
                text = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})
                return text, usage.get("prompt_tokens"), usage.get("completion_tokens")
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(f"Cannot connect to API at {self.base_url}: {e}", provider="openai_compatible")

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]
        return json.loads(text)
