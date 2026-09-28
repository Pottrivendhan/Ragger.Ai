"""
Factory for instantiating evaluation judges according to evaluation configuration.
"""

from typing import Optional

from ..exceptions import InvalidEvaluationParameterError
from ..models import EvaluationConfig
from .base import BaseEvalJudge
from .ollama import OllamaEvalJudge
from .test_judge import TestDeterministicEvalJudge


def get_eval_judge(
    config: EvaluationConfig,
    judge_override: Optional[BaseEvalJudge] = None,
) -> BaseEvalJudge:
    """Instantiates the appropriate evaluation judge provider."""
    if judge_override is not None:
        return judge_override

    provider = config.judge_provider.lower()
    if provider == "test":
        return TestDeterministicEvalJudge()
    elif provider == "ollama":
        return OllamaEvalJudge(
            model_name=config.judge_model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    else:
        raise InvalidEvaluationParameterError(f"Unsupported judge provider: '{config.judge_provider}'")
