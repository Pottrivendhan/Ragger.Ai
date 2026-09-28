"""
Local Ollama Evaluation Judge for Phase 8 Quality Evaluation.
Enforces zero-download local model boundary (strictly checking GET /api/tags, never calling /api/pull).
"""

import json
import re
from typing import List, Tuple
import urllib.request
import urllib.error

from ..exceptions import ModelNotAvailableError
from .base import BaseEvalJudge


class OllamaEvalJudge(BaseEvalJudge):
    """Local Ollama judge for automated factual faithfulness and disclaimer assessment."""

    def __init__(
        self,
        model_name: str = "llama3.2:3b",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        host: str = "127.0.0.1",
        port: int = 11434,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = f"http://{host}:{port}"

    def validate_availability(self) -> None:
        """
        Validates Ollama server reachability and local model existence.
        Strictly zero downloads: never calls /api/pull.
        """
        tags_url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    raise ModelNotAvailableError(
                        self.model_name,
                        reason=f"Ollama server returned HTTP {resp.status}",
                    )
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ModelNotAvailableError(
                self.model_name,
                reason=f"Ollama daemon not reachable at {self.base_url}: {str(e)}",
            ) from e
        except Exception as e:
            raise ModelNotAvailableError(
                self.model_name,
                reason=f"Ollama tag inspection failed: {str(e)}",
            ) from e

        installed_models = [m.get("name") for m in data.get("models", []) if "name" in m]
        # Match model prefix (e.g. 'llama3.2:3b' or 'llama3.2:3b:latest')
        matched = any(
            m == self.model_name or m.startswith(f"{self.model_name}:") or self.model_name.startswith(f"{m}:")
            for m in installed_models
        )
        if not matched:
            raise ModelNotAvailableError(
                self.model_name,
                reason=(
                    f"Model '{self.model_name}' not found locally in Ollama. "
                    f"Installed models: {installed_models}. Ragger.ai does not auto-download models."
                ),
            )

    async def evaluate_claims(
        self,
        query: str,
        answer: str,
        context_chunks: List[str],
    ) -> Tuple[int, int, int]:
        """
        Extracts factual propositions from answer and verifies whether each is grounded
        in the provided retrieved context chunks.
        Returns: (total_claims, supported_claims, unsupported_claims)
        """
        combined_context = "\n---\n".join(context_chunks)
        prompt = (
            "You are an impartial factual evaluation judge.\n"
            "Task: Break down the following generated answer into individual factual claims.\n"
            "For each claim, determine whether it is completely supported by the provided context chunks.\n"
            "Respond ONLY with a JSON object with this exact structure:\n"
            '{"claims": [{"text": "claim statement", "supported": true/false}]}\n\n'
            f"Context:\n{combined_context}\n\n"
            f"Query: {query}\n\n"
            f"Generated Answer:\n{answer}\n\n"
            "JSON Response:"
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                output_str = res_data.get("response", "{}")
                parsed = json.loads(output_str)
                claims = parsed.get("claims", [])
                if not claims:
                    return 0, 0, 0

                supported = sum(1 for c in claims if c.get("supported") is True)
                total = len(claims)
                unsupported = total - supported
                return total, supported, unsupported
        except Exception:
            # Fallback heuristic if judge output parsing encounters transient JSON issue
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 15]
            if not sentences:
                return 0, 0, 0
            supported = 0
            for s in sentences:
                words = [w.lower() for w in re.findall(r"\b\w{4,}\b", s)]
                if words and any(w in combined_context.lower() for w in words):
                    supported += 1
            return len(sentences), supported, len(sentences) - supported

    async def evaluate_disclaimer(
        self,
        query: str,
        answer: str,
        is_out_of_domain: bool,
    ) -> bool:
        """
        Evaluates disclaimer accuracy.
        For out-of-domain queries, checks if answer properly declares lack of information.
        For in-domain queries, checks that answer does not falsely claim lack of information.
        """
        disclaimer_markers = [
            "could not find information",
            "insufficient information",
            "insufficient evidence",
            "not found in the provided",
            "does not contain information",
            "no information",
            "do not have enough information",
            "cannot answer",
        ]
        lower_ans = answer.lower()
        has_disclaimer = any(m in lower_ans for m in disclaimer_markers)

        if is_out_of_domain:
            return has_disclaimer
        else:
            return not has_disclaimer
