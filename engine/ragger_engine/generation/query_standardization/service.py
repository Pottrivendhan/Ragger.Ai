"""
QueryStandardizationService: Dedicated component for normalizing user questions
into clean retrieval queries before executing dense and lexical vector retrieval.

Pipeline:
Raw User Query -> Spelling/Grammar/Entity Normalization (Local LLM / Fallback) -> Normalized Query
"""

import asyncio
import re
from typing import List, Optional, Tuple

from ragger_engine.generation.providers.base import BaseLLMProvider
from .models import StandardizedQuery


class QueryStandardizationService:
    """
    Supervises query standardization and entity preservation.
    Rewrites noisy, misspelled, or informal user input into high-quality search queries.
    Strictly NEVER answers the question.
    """

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider

    def set_provider(self, provider: BaseLLMProvider) -> None:
        """Dynamically updates the active LLM provider for query standardization."""
        self.provider = provider

    async def standardize(
        self,
        query: str,
        workspace_id: str = "default",
    ) -> StandardizedQuery:
        """
        Converts the user's natural-language question into a clean retrieval query.
        Uses LLM with strict instruction, falling back to deterministic normalization.
        """
        raw_query = query.strip()
        if not raw_query:
            return StandardizedQuery(
                original_query=query,
                normalized_query=query,
                detected_intent="empty",
                changes_made=[],
                provider="noop",
                model="none",
                success=True,
            )

        # 1. Detect Intent
        detected_intent = self._detect_intent(raw_query)

        # 2. Deterministic Standardization Layer (Regex, Typo Rectification, Entity Preservation)
        # Using fast deterministic standardization guarantees intent preservation and avoids meta-prompt artifacts
        norm_query, changes = self._deterministic_standardize(raw_query, detected_intent)
        return StandardizedQuery(
            original_query=raw_query,
            normalized_query=norm_query,
            detected_intent=detected_intent,
            changes_made=changes,
            provider="rule_normalizer",
            model="deterministic_v1",
            success=True,
        )

    def _detect_intent(self, query: str) -> str:
        q_lower = query.lower()
        if any(w in q_lower for w in ("summary", "summarize", "overview", "main topics", "what is this document about", "table of contents")):
            return "summary"
        if any(w in q_lower for w in ("author", "auther", "authur", "who wrote", "poet", "poetess", "writer", "writter")):
            return "author_lookup"
        if any(w in q_lower for w in ("who is", "who was", "character", "protagonist")):
            return "character_lookup"
        return "fact_lookup"

    async def _standardize_with_llm(self, query: str) -> Tuple[str, List[str]]:
        """
        Executes query standardization prompt against configured local LLM.
        Strictly preserves intent and never converts noun phrases or topics into 'Who is...' questions.
        """
        prompt = (
            "You are the query normalization component of Ragger.ai.\n\n"
            "Your task is ONLY to rewrite noisy or misspelled user queries into clean retrieval queries.\n\n"
            "CRITICAL RULES:\n"
            "1. PRESERVE THE USER'S EXACT INTENT AND INFORMATION NEED.\n"
            "2. If a query is a short topic, entity, or noun phrase (e.g. 'young seagull', 'role play', 'design', 'machine learning'), "
            "PRESERVE IT as a topic retrieval query (e.g. 'young seagull' or 'Tell me about the young seagull.'). "
            "NEVER prepend 'Who is', 'What is', 'Where is', or 'Why is' unless the user's original query already established that intent.\n"
            "3. NEVER assume an entity or noun phrase is a person. NEVER convert concepts, topics, chapters, or unknown phrases into 'Who is...'.\n"
            "4. Correct spelling errors (e.g. 'auther' -> 'author', 'sumary' -> 'summary').\n"
            "5. Correct obvious grammatical errors while preserving all named entities and titles.\n"
            "6. DO NOT answer the question. DO NOT add facts or speculate.\n"
            "7. WHEN UNCERTAIN, PRESERVE THE ORIGINAL QUERY UNCHANGED.\n"
            "8. Return ONLY the normalized query on a single line. No quotes, no explanations.\n\n"
            f"User Query: {query}\n"
            "Normalized Retrieval Query:"
        )

        output = await self.provider.generate(prompt=prompt, max_tokens=128, temperature=0.0)
        cleaned = output.strip().split("\n")[0].strip('"\';: ')

        changes = []
        if cleaned.lower() != query.lower():
            changes.append(f"LLM normalized: '{query}' -> '{cleaned}'")

        return cleaned, changes

    def _validate_normalized_query(self, raw_query: str, normalized: str) -> bool:
        """
        Validates that the model produced a retrieval query, NOT an answer or invented entity.
        """
        if not normalized or len(normalized) < 2:
            return False
        # If model answered instead of rewriting
        norm_lower = normalized.lower()
        if any(phrase in norm_lower for phrase in ("the answer is", "according to", "in this story", "is a renowned", "was born in")):
            return False

        # Guard against semantic distortion: Do not allow converting queries into "who is..." unless original had "who" or clear person title
        raw_lower = raw_query.lower()
        if norm_lower.startswith("who is ") or norm_lower.startswith("who was "):
            has_who_intent = "who" in raw_lower
            has_person_title = bool(re.search(r"\b(dr\.?|doctor|mr\.?|mrs\.?|ms\.?|prof\.?|professor)\b", raw_lower))
            if not has_who_intent and not has_person_title:
                return False

        # Must retain substantial key entities from the original query
        raw_words = [w for w in re.findall(r"[a-zA-Z0-9]+", raw_lower) if len(w) > 3]
        if raw_words:
            matched = sum(1 for w in raw_words if w in norm_lower or w[:4] in norm_lower)
            if matched == 0:
                return False
        return True

    def _deterministic_standardize(self, query: str, intent: str) -> Tuple[str, List[str]]:
        """
        Robust deterministic normalization layer guaranteeing correct retrieval queries
        regardless of model availability.
        Enforces:
        - When uncertain, preserve the original query.
        - Short topic queries (e.g. 'young seagull', 'role play', 'design') remain clean retrieval queries.
        - Never convert unknown entities into 'Who is...'.
        """
        changes: List[str] = []
        q = query.strip()

        # 1. Spelling corrections
        spelling_map = [
            (r"\bauther\b", "author", "auther -> author"),
            (r"\bauthur\b", "author", "authur -> author"),
            (r"\bawthor\b", "author", "awthor -> author"),
            (r"\bwritter\b", "writer", "writter -> writer"),
            (r"\bpoetess\b", "poet", "poetess -> poet"),
            (r"\bsumery\b", "summary", "sumery -> summary"),
            (r"\bsumary\b", "summary", "sumary -> summary"),
            (r"\bprocces\b", "process", "procces -> process"),
            (r"\binstalation\b", "installation", "instalation -> installation"),
            (r"\bcharecter\b", "character", "charecter -> character"),
            (r"\bcharactor\b", "character", "charactor -> character"),
            (r"\bwat is\b", "what is", "wat is -> what is"),
            (r"\bwhr is\b", "where is", "whr is -> where is"),
        ]

        for pattern, repl, desc in spelling_map:
            new_q, count = re.subn(pattern, repl, q, flags=re.IGNORECASE)
            if count > 0:
                changes.append(desc)
                q = new_q

        # 2. Normalize title / entity cases and malformed possessives
        # Only rewrite to "Who is..." if there is an explicit person honorific (e.g. Dr., Mr., Mrs., Prof.)
        possessive_match = re.search(r"([A-Z][a-zA-Z\.\s]+)(?:’s|'s)\s*[\?]?$", q)
        if possessive_match:
            entity = possessive_match.group(1).strip()
            if not q.lower().startswith("who is") and not q.lower().startswith("what is"):
                has_person_title = bool(re.search(r"\b(dr\.?|doctor|mr\.?|mrs\.?|ms\.?|prof\.?|professor)\b", entity, re.IGNORECASE))
                if has_person_title:
                    q = f"Who is {entity}?"
                else:
                    q = entity
            else:
                q = re.sub(r"(?:’s|'s)\s*[\?]?$", "?", q)
            changes.append("resolved malformed possessive entity")

        # 3. Handle informal phrase queries e.g. "The Grumble Family author name?" -> "What is the author of The Grumble Family?"
        if intent == "author_lookup":
            # Match pattern: "<Title/Work> author name?" or "<Title> author?"
            m = re.search(r"^(.*?)\s+(?:author|writer|poet)\s*(?:name)?\s*[\?]?$", q, re.IGNORECASE)
            if m and len(m.group(1).split()) > 0:
                subject = m.group(1).strip()
                if not re.match(r"^(who|what)\s+", subject, re.IGNORECASE):
                    # Clean subject formatting
                    if re.match(r"^unit\s+\d+\s+poem", subject, re.IGNORECASE):
                        q = f"What is the author of the poem in {subject.title().replace('Poem', '').strip()}?"
                    else:
                        q = f"What is the author of {subject}?"
                    changes.append("formulated natural author question")
            elif q.lower().strip() in ("author of book", "author of book?", "author of the book", "author of the book?"):
                q = "What is the author of the book?"
                changes.append("normalized informal author query")

        # 4. Handle natural casing for conversational question openers
        if re.match(r"^(who|what|why|how|where|when|tell me|explain)\s+", q, re.IGNORECASE):
            q = q[0].upper() + q[1:]

        # 5. Clean trailing irregular punctuation
        q = re.sub(r"[\?\.!\s]+$", "", q).strip()

        # Only append '?' if the query is structurally a question (starts with question word or auxiliary verb)
        is_question = bool(re.match(r"^(who|what|why|how|where|when|is|are|was|were|do|does|did|can|could|would|should)\s+", q, re.IGNORECASE))
        if is_question:
            q += "?"

        return q, changes
