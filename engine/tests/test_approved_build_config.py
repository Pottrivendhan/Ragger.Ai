"""
Unit tests for ApprovedBuildConfig snapshot immutability, SHA-256 integrity,
revision lifecycle, and Phase 5 verification contract.
"""

import json
import pytest
from ragger_engine.recommendation.exceptions import ImmutableConfigMutationError
from ragger_engine.recommendation.models import (
    ChunkingConfig,
    ChunkingStrategyType,
    RagArchitectureId,
)
from ragger_engine.recommendation.service import RecommendationService
from ragger_engine.recommendation.validation import (
    compute_canonical_config_hash,
    validate_approved_build_config,
)


def test_approved_build_config_creation_and_hash(tmp_path):
    service = RecommendationService(storage_dir=tmp_path)

    sources = ["src_pdf_1", "src_xlsx_2"]
    approved = service.approve_configuration(
        workspace_id="test_ws",
        approved_architecture_id=RagArchitectureId.HYBRID_RAG,
        source_ids=sources,
    )

    assert approved.config_version == 1
    assert approved.is_frozen is True
    assert approved.approved_architecture == RagArchitectureId.HYBRID_RAG
    assert approved.config_id.startswith("cfg_")
    assert len(approved.config_hash) == 64  # SHA-256 length

    # Verify cryptographic hash recomputation
    expected_hash = compute_canonical_config_hash(
        architecture_id=approved.approved_architecture,
        chunking_config=approved.chunking_config,
        embedding_config=approved.embedding_config,
        vector_db_config=approved.vector_db_config,
        retrieval_config=approved.retrieval_config,
        source_ids=sources,
    )
    assert approved.config_hash == expected_hash


def test_approved_config_cannot_be_silently_mutated(tmp_path):
    service = RecommendationService(storage_dir=tmp_path)
    sources = ["src_1"]

    service.approve_configuration(
        workspace_id="test_ws",
        approved_architecture_id=RagArchitectureId.DOCUMENT_RAG,
        source_ids=sources,
    )

    # Attempting to re-approve without is_revision=True must raise ImmutableConfigMutationError
    with pytest.raises(ImmutableConfigMutationError) as exc:
        service.approve_configuration(
            workspace_id="test_ws",
            approved_architecture_id=RagArchitectureId.DOCUMENT_RAG,
            source_ids=sources,
            is_revision=False,
        )
    assert "already frozen" in str(exc.value)


def test_approved_config_revision_lifecycle(tmp_path):
    service = RecommendationService(storage_dir=tmp_path)
    sources = ["src_1"]

    # Version 1
    v1 = service.approve_configuration(
        workspace_id="test_ws",
        approved_architecture_id=RagArchitectureId.DOCUMENT_RAG,
        source_ids=sources,
    )
    assert v1.config_version == 1

    # Version 2 with customization
    custom_chunking = ChunkingConfig(
        strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
        chunk_size=256,
        chunk_overlap=32,
    )
    v2 = service.approve_configuration(
        workspace_id="test_ws",
        approved_architecture_id=RagArchitectureId.DOCUMENT_RAG,
        source_ids=sources,
        custom_chunking=custom_chunking,
        is_revision=True,
    )
    assert v2.config_version == 2
    assert v2.config_id != v1.config_id
    assert v2.chunking_config.chunk_size == 256
    assert v2.user_customized is True


def test_phase_5_validation_contract_checks(tmp_path):
    service = RecommendationService(storage_dir=tmp_path)
    sources = ["src_1", "src_2"]

    # 1. Check before approval -> must fail
    is_valid, reason = service.validate_build_prerequisites(current_source_ids=sources)
    assert is_valid is False
    assert "BUILD_NOT_APPROVED" in reason

    # 2. Approve
    service.approve_configuration(
        workspace_id="test_ws",
        approved_architecture_id=RagArchitectureId.HYBRID_RAG,
        source_ids=sources,
    )

    # 3. Check with matching sources -> must pass
    is_valid, reason = service.validate_build_prerequisites(current_source_ids=sources)
    assert is_valid is True
    assert reason is None

    # 4. Check with source drift -> must fail
    is_valid, reason = service.validate_build_prerequisites(current_source_ids=["src_1", "src_2", "src_3"])
    assert is_valid is False
    assert "Source drift" in reason

    # 5. Check with tampered hash on disk -> must fail
    config_file = tmp_path / "approved_build_config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["config_hash"] = "0" * 64  # Tamper
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    is_valid, reason = service.validate_build_prerequisites(current_source_ids=sources)
    assert is_valid is False
    assert "Hash mismatch" in reason
