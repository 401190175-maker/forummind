"""Durable, group-scoped knowledge search for real research documents."""

from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import SearchHit, SearchScope
from app.knowledge.search import KnowledgeSearch

__all__ = ["KnowledgeRepository", "KnowledgeSearch", "SearchHit", "SearchScope"]
