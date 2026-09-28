"""Local Ollama Analyzer Provider for Phase 3.

Connects to local Ollama on loopback (http://127.0.0.1:11434) with zero network egress.
Supports strict JSON output formatting, schema repair retry loops (<= 2 retries),
and transparent telemetry tracking when falling back to heuristic offline analysis.
"""

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


class OllamaAnalyzerProvider(BaseAnalyzerProvider):
    """Local LLM Analyzer Provider connecting to Ollama daemon on loopback."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model_name: str = "llama3.2:3b",
        timeout_seconds: float = 15.0,
        enable_fallback: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.enable_fallback = enable_fallback
        self.heuristic_fallback = DeterministicHeuristicAnalyzer()

    @property
    def provider_id(self) -> str:
        return "ollama"

    async def is_available(self) -> bool:
        """Checks if local Ollama daemon is active and responsive on loopback."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

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

        user_prompt = build_analysis_user_prompt(
            filename=source.original_filename,
            structural_facts_json=facts.model_dump_json(indent=2),
            sample_content=sample_text[:6000],  # stay safely within budget
        )

        attempts = 0
        max_attempts = 3  # 1 initial + 2 retries
        last_error = None
        raw_response_text = ""

        while attempts < max_attempts:
            attempts += 1
            try:
                raw_response_text, p_tokens, c_tokens = await self._call_ollama(user_prompt)
                parsed_json = self._extract_json(raw_response_text)
                
                # Strict Pydantic validation (rejects unknown/recommendation fields via extra='forbid')
                observations = SemanticObservations.model_validate(parsed_json)
                
                duration = (time.perf_counter() - start_time) * 1000.0
                telemetry = ProviderTelemetry(
                    requested_provider="ollama",
                    actual_provider="ollama",
                    fallback_used=False,
                    fallback_reason=None,
                    model_name=self.model_name,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    duration_ms=round(duration, 2),
                )
                return observations, telemetry

            except (httpx.ConnectError, httpx.TimeoutException, ProviderUnavailableError) as conn_err:
                last_error = f"Ollama connection error: {conn_err}"
                break  # Do not retry on connection refusal, drop directly to fallback

            except (json.JSONDecodeError, ValidationError) as val_err:
                last_error = f"Schema validation error (attempt {attempts}): {val_err}"
                # Append error feedback to prompt for next retry
                user_prompt += f"\n\nERROR IN PREVIOUS ATTEMPT: {val_err}\nEnsure strictly valid JSON conforming exactly to the required schema."

        # If Ollama failed or was unreachable, handle fallback
        if self.enable_fallback:
            fallback_obs, _ = await self.heuristic_fallback.analyze(source, facts, sample)
            duration = (time.perf_counter() - start_time) * 1000.0
            
            telemetry = ProviderTelemetry(
                requested_provider="ollama",
                actual_provider="heuristic_offline",
                fallback_used=True,
                fallback_reason=last_error or "Unknown failure in Ollama provider",
                model_name=self.model_name,
                duration_ms=round(duration, 2),
            )
            return fallback_obs, telemetry

        raise SchemaValidationError(
            f"Failed to obtain valid observational schema from Ollama: {last_error}",
            raw_output=raw_response_text,
            attempts=attempts,
        )

    async def _call_ollama(self, prompt: str) -> Tuple[str, Optional[int], Optional[int]]:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": ANALYZER_SYSTEM_PROMPT,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,  # Low temperature for deterministic observation
                "top_p": 0.9,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise ProviderUnavailableError(
                        f"Ollama returned HTTP {resp.status_code}: {resp.text}",
                        provider="ollama",
                    )
                data = resp.json()
                response_text = data.get("response", "")
                p_tokens = data.get("prompt_eval_count")
                c_tokens = data.get("eval_count")
                return response_text, p_tokens, c_tokens
        except httpx.ConnectError as e:
            raise ProviderUnavailableError(f"Cannot connect to Ollama at {self.base_url}: {e}", provider="ollama")

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]
        return json.loads(text)
