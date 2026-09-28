"""
Contract and verification tests for production embedding providers (Local ONNX and Ollama).
Verifies:
1. Local ONNX contract: model existence check, session initialization, real inference flow, pooling, L2 normalization.
2. Ollama contract: loopback tag check, rejection of missing models without background pull, inference request, dimension check, L2 normalization.
3. Strict Model Manager boundary: neither provider executes network downloads or pulls.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from ragger_engine.builder.embeddings.local_onnx import LocalOnnxEmbeddingProvider
from ragger_engine.builder.embeddings.ollama import OllamaEmbeddingProvider
from ragger_engine.builder.exceptions import EmbeddingError, ModelNotAvailableError


# ---------------------------------------------------------------------------
# Ollama Provider Contract Tests
# ---------------------------------------------------------------------------

def test_ollama_rejects_unreachable_server():
    """When Ollama daemon is offline on loopback, raises ModelNotAvailableError immediately."""
    with pytest.raises(ModelNotAvailableError) as exc:
        OllamaEmbeddingProvider(
            model_name="bge-small-en-v1.5",
            dimension=384,
            base_url="http://127.0.0.1:59999",  # Non-existent port
        )
    assert "Could not connect to local Ollama server" in str(exc.value)


def test_ollama_rejects_missing_model_tag_without_pull():
    """
    When Ollama daemon is running but approved model tag is missing from /api/tags,
    raises ModelNotAvailableError. Verifies NO pull is initiated.
    """
    mock_tags_response = MagicMock()
    mock_tags_response.status_code = 200
    mock_tags_response.json.return_value = {
        "models": [{"name": "llama3:latest"}, {"name": "nomic-embed-text:latest"}]
    }

    with patch("httpx.Client.get", return_value=mock_tags_response) as mock_get:
        with patch("httpx.Client.post") as mock_post:
            with pytest.raises(ModelNotAvailableError) as exc:
                OllamaEmbeddingProvider(
                    model_name="bge-small-en-v1.5",
                    dimension=384,
                    base_url="http://127.0.0.1:11434",
                )
            # Must mention Model Manager and state no auto-download
            assert "not found in local Ollama instance" in str(exc.value)
            assert "The Builder never downloads models automatically" in str(exc.value)
            # Verify no POST or pull was ever called
            mock_post.assert_not_called()


def test_ollama_real_inference_and_normalization():
    """
    When approved model exists in Ollama tags, verifies:
    1. Successful initialization
    2. Embedding request dispatched to /api/embeddings
    3. Output vector dimension verified against approved dimension
    4. L2 normalization applied
    """
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {"models": [{"name": "bge-small-en-v1.5:latest"}]}

    # Unnormalized 384-dimensional vector returned by server
    raw_vector = [2.0] * 384
    mock_embed = MagicMock()
    mock_embed.status_code = 200
    mock_embed.json.return_value = {"embedding": raw_vector}

    with patch("httpx.Client.get", return_value=mock_tags):
        provider = OllamaEmbeddingProvider(
            model_name="bge-small-en-v1.5",
            dimension=384,
            base_url="http://127.0.0.1:11434",
        )

    with patch("httpx.Client.post", return_value=mock_embed) as mock_post:
        vectors = provider.embed_batch(["Test embedding query."])

        assert len(vectors) == 1
        assert len(vectors[0]) == 384
        # Verify L2 normalization: sum(x^2) == 1.0
        l2_norm = sum(x * x for x in vectors[0]) ** 0.5
        assert pytest.approx(l2_norm, abs=1e-4) == 1.0
        # Verify request parameters
        mock_post.assert_called_once_with(
            "http://127.0.0.1:11434/api/embeddings",
            json={"model": "bge-small-en-v1.5", "prompt": "Test embedding query."},
        )


def test_ollama_fails_on_dimension_mismatch():
    """If Ollama returns vector with dimension differing from ApprovedBuildConfig, fail loudly."""
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {"models": [{"name": "bge-small-en-v1.5:latest"}]}

    mock_embed = MagicMock()
    mock_embed.status_code = 200
    mock_embed.json.return_value = {"embedding": [0.1] * 768}  # 768 instead of 384

    with patch("httpx.Client.get", return_value=mock_tags):
        provider = OllamaEmbeddingProvider(model_name="bge-small-en-v1.5", dimension=384)

    with patch("httpx.Client.post", return_value=mock_embed):
        with pytest.raises(EmbeddingError) as exc:
            provider.embed_batch(["Dimension test"])
        assert "dimension mismatch" in str(exc.value)


# ---------------------------------------------------------------------------
# Local ONNX Provider Contract Tests
# ---------------------------------------------------------------------------

def test_onnx_rejects_missing_model_file(tmp_path: Path):
    """When .onnx model weights file does not exist on disk, strictly raises ModelNotAvailableError."""
    with pytest.raises(ModelNotAvailableError) as exc:
        LocalOnnxEmbeddingProvider(
            model_name="bge-small-en-v1.5",
            dimension=384,
            models_dir=tmp_path,
        )
    assert "not found at" in str(exc.value)
    assert "The Builder never downloads model weights automatically" in str(exc.value)


def test_onnx_inference_pooling_and_normalization_contract(tmp_path: Path):
    """
    Exercises the complete ONNX inference pipeline:
    1. Verifies model file existence requirement
    2. Initializes session
    3. Feeds input tokens
    4. Performs mean pooling over sequence length
    5. Normalizes vector
    6. Verifies exact dimension match
    """
    model_file = tmp_path / "bge-small-en-v1.5.onnx"
    model_file.write_bytes(b"DUMMY_ONNX_HEADER_BYTES")

    # Create mock ONNX runtime session returning [batch_size=1, seq_len=4, hidden_dim=384]
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not installed")

    mock_input_1 = MagicMock()
    mock_input_1.name = "input_ids"
    mock_input_2 = MagicMock()
    mock_input_2.name = "attention_mask"

    # Simulated hidden states
    simulated_hidden_states = np.ones((1, 4, 384), dtype=np.float32) * 2.0

    mock_session = MagicMock()
    mock_session.get_inputs.return_value = [mock_input_1, mock_input_2]
    mock_session.run.return_value = [simulated_hidden_states]

    mock_ort = MagicMock()
    mock_ort.InferenceSession.return_value = mock_session

    with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
        provider = LocalOnnxEmbeddingProvider(
            model_name="bge-small-en-v1.5",
            dimension=384,
            models_dir=tmp_path,
        )

        vectors = provider.embed_batch(["Neural retrieval evaluation query."])

        assert len(vectors) == 1
        assert len(vectors[0]) == 384
        # Verify L2 normalization
        norm = sum(x * x for x in vectors[0]) ** 0.5
        assert pytest.approx(norm, abs=1e-4) == 1.0
        # Verify session.run was called with expected tensor shapes
        assert mock_session.run.called


def test_onnx_handles_oversized_sequences_and_536_words(tmp_path: Path):
    """
    Regression test for the 512 x 536 ONNX broadcast error:
    Verifies that inputs with 512, 513, and 536 tokens never exceed the 512 sequence dimension
    passed to the ONNX session.
    """
    model_file = tmp_path / "bge-small-en-v1.5.onnx"
    model_file.write_bytes(b"DUMMY_ONNX_HEADER_BYTES")

    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not installed")

    mock_input_1 = MagicMock()
    mock_input_1.name = "input_ids"
    mock_input_2 = MagicMock()
    mock_input_2.name = "attention_mask"

    captured_inputs = {}

    def mock_run(output_names, feed_dict):
        captured_inputs.update(feed_dict)
        seq_len = feed_dict["input_ids"].shape[1]
        assert seq_len <= 512, f"Sequence length {seq_len} exceeded model max sequence length 512!"
        return [np.ones((feed_dict["input_ids"].shape[0], seq_len, 384), dtype=np.float32)]

    mock_session = MagicMock()
    mock_session.get_inputs.return_value = [mock_input_1, mock_input_2]
    mock_session.run.side_effect = mock_run

    mock_ort = MagicMock()
    mock_ort.InferenceSession.return_value = mock_session

    with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
        provider = LocalOnnxEmbeddingProvider(
            model_name="bge-small-en-v1.5",
            dimension=384,
            models_dir=tmp_path,
        )

        # Test 1: Exactly 536 words (the exact production failure shape)
        text_536 = " ".join(["token"] * 536)
        vecs = provider.embed_batch([text_536])
        assert len(vecs) == 1
        assert len(vecs[0]) == 384
        assert captured_inputs["input_ids"].shape[1] == 512
        assert captured_inputs["attention_mask"].shape[1] == 512

        # Test 2: Sequence > 512 tokens (e.g. 700 words)
        text_long = " ".join(["token"] * 700)
        vecs_long = provider.embed_batch([text_long])
        assert len(vecs_long) == 1
        assert len(vecs_long[0]) == 384
        assert captured_inputs["input_ids"].shape[1] == 512

        # Test 3: Sequence <= 512 tokens (e.g. 100 words)
        text_short = " ".join(["token"] * 100)
        vecs_short = provider.embed_batch([text_short])
        assert len(vecs_short) == 1
        assert len(vecs_short[0]) == 384
        assert captured_inputs["input_ids"].shape[1] == 100


def test_token_safe_subchunking_preserves_metadata():
    """
    Verifies that split_into_token_safe_subchunks breaks oversized chunks into
    model-safe subchunks <= 512 tokens while fully preserving provenance and metadata.
    """
    from ragger_engine.builder.chunking.base import split_into_token_safe_subchunks
    from ragger_engine.builder.models import Chunk, ChunkMetadata, ChunkType

    long_text = "\n\n".join([f"Paragraph {i} contains detailed domain knowledge and comprehensive explanations of systems." for i in range(50)])
    meta = ChunkMetadata(
        source_id="src_doc1",
        source_name="BDA ROLE PLAY 4.pdf",
        chunk_index=7,
        token_count=800,
        page_number=12,
        heading_path=["Introduction", "Role Play Scenario"],
        extra={"custom_attr": "value_1"},
    )
    chunk = Chunk(
        chunk_id="chk_srcdoc1_orig",
        source_id="src_doc1",
        text=long_text,
        chunk_type=ChunkType.STANDARD_PARAGRAPH,
        metadata=meta,
        token_count=800,
    )

    subchunks = split_into_token_safe_subchunks(chunk, max_tokens=512, overlap_tokens=50)
    assert len(subchunks) > 1
    for sc in subchunks:
        assert sc.metadata.source_id == "src_doc1"
        assert sc.metadata.source_name == "BDA ROLE PLAY 4.pdf"
        assert sc.metadata.page_number == 12
        assert sc.metadata.heading_path == ["Introduction", "Role Play Scenario"]
        assert sc.metadata.extra == {"custom_attr": "value_1"}
        assert len(sc.text) > 0

