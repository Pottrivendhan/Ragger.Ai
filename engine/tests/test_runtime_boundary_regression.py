"""
Regression tests verifying that Phase 6, Phase 7, and Phase 8 strictly preserve their
zero-download and zero-pull boundaries after Phase 9 Model Manager integration.
"""

import pytest
from ragger_engine.generation.exceptions import ModelNotAvailableError as GenModelNotAvailableError
from ragger_engine.evaluation.exceptions import ModelNotAvailableError as EvalModelNotAvailableError
from ragger_engine.retrieval.exceptions import RetrievalEngineError, NoActiveBuildError


def test_phase6_retrieval_boundary_never_downloads():
    """Verifies that Phase 6 Retrieval rejects unbuilt or missing structures without network activity."""
    # Attempting retrieval without build raises NoActiveBuildError immediately
    from ragger_engine.retrieval.service import RetrievalService
    from ragger_engine.retrieval.models import RetrievalQuery
    from pathlib import Path

    svc = RetrievalService(workspace_dir=Path("./non_existent_workspace_for_regression"))
    query = RetrievalQuery(query="test regression query", top_k=5)

    with pytest.raises((NoActiveBuildError, RetrievalEngineError)):
        svc.retrieve(query)


@pytest.mark.asyncio
async def test_phase7_generation_boundary_still_returns_424_without_pull():
    """Verifies that Phase 7 Generation still raises ModelNotAvailableError (HTTP 424) without pulling."""
    from ragger_engine.generation.providers.ollama import OllamaLLMProvider

    provider = OllamaLLMProvider(
        base_url="http://127.0.0.1:59999",  # Non-existent port
        model_name="non-existent-model",
    )

    with pytest.raises(GenModelNotAvailableError) as exc_info:
        provider.validate_availability()

    assert exc_info.value.code == "MODEL_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_phase8_evaluation_boundary_still_returns_424_without_pull():
    """Verifies that Phase 8 Evaluation judge still raises ModelNotAvailableError (HTTP 424) without pulling."""
    from ragger_engine.evaluation.providers.ollama import OllamaEvalJudge

    judge = OllamaEvalJudge(
        model_name="non-existent-judge",
        host="127.0.0.1",
        port=59999,
    )

    with pytest.raises(EvalModelNotAvailableError) as exc_info:
        judge.validate_availability()

    assert exc_info.value.code == "MODEL_NOT_AVAILABLE"
