"""
Exceptions for Phase 12 RAG Artifact Lifecycle & Storage Contract.
"""


class RAGLifecycleError(Exception):
    """Base exception for RAG lifecycle operations."""
    pass


class RAGNotFoundError(RAGLifecycleError):
    def __init__(self, rag_id: str):
        self.rag_id = rag_id
        super().__init__(f"RAG Knowledge Artifact '{rag_id}' not found.")


class RAGAlreadyExistsError(RAGLifecycleError):
    def __init__(self, rag_id: str):
        self.rag_id = rag_id
        super().__init__(f"RAG Knowledge Artifact '{rag_id}' already exists.")


class RAGInUseError(RAGLifecycleError):
    """Raised when attempting to delete a RAG artifact attached to active agents."""
    def __init__(self, rag_id: str, referencing_agents: list):
        self.rag_id = rag_id
        self.referencing_agents = referencing_agents
        super().__init__(
            f"Cannot delete RAG '{rag_id}' because it is in use by {len(referencing_agents)} agent(s): "
            f"{', '.join(referencing_agents)}. Detach the RAG from these agents first, or request administrative force unlinking."
        )


class RAGVersionNotFoundError(RAGLifecycleError):
    def __init__(self, rag_id: str, version_id: str):
        self.rag_id = rag_id
        self.version_id = version_id
        super().__init__(f"Version '{version_id}' not found in RAG Artifact '{rag_id}'.")


class InvalidRAGPackError(RAGLifecycleError):
    """Raised when a .ragpack bundle fails archive, manifest, hash, or schema validation."""
    pass


class ForbiddenModelWeightError(InvalidRAGPackError):
    """Raised when an imported .ragpack contains prohibited model weight artifacts."""
    def __init__(self, file_path: str):
        self.file_path = file_path
        super().__init__(
            f"Security Violation: Forbidden model weight asset '{file_path}' detected inside .ragpack bundle. "
            f"RAG Knowledge Artifacts must contain only knowledge representations, never model weights."
        )
