"""Shared type definitions for the multi-agent research workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CredibilityAssessment(BaseModel):
    """Represents a credibility assessment of a source."""

    url: str
    domain_credibility: float  # 0.0 to 1.0
    content_quality: float  # 0.0 to 1.0
    authoritativeness: float  # 0.0 to 1.0
    bias_indicators: list[str] = []
    credibility_factors: list[str] = []
    overall_score: float  # 0.0 to 1.0
    recommendation: str  # high, medium, low, unreliable
    assessment_details: dict[str, Any] = {}


class SourceCategorization(BaseModel):
    """Represents the categorization of a source."""

    url: str
    primary_category: str  # academic, government, news, commercial, etc.
    secondary_categories: list[str] = []
    confidence: float  # 0.0 to 1.0
    reasoning: str
    indicators: list[str] = []


class WebpageMetadata(BaseModel):
    """Represents extracted metadata from a webpage."""

    url: str
    title: str | None = None
    author: str | None = None
    publication_date: str | None = None
    last_modified: str | None = None
    description: str | None = None
    keywords: list[str] = []
    language: str | None = None
    content_type: str | None = None
    word_count: int | None = None
    extracted_at: str


class ResearchSource(BaseModel):
    """Represents a research source with tracking information."""

    url: str
    source_type: str = "web"  # web, reddit, academic, etc.
    title: str | None = None
    description: str | None = None
    content_summary: str | None = None  # For backward compatibility with tests
    access_count: int = 0
    first_accessed: str | None = None
    last_accessed: str | None = None
    tools_used: list[str] = []
    metadata: dict[str, Any] = {}


class ResearchCitation(BaseModel):
    """Represents a research citation."""

    source: ResearchSource
    citation_text: str
    citation_style: str = "apa"  # apa, mla, chicago
    page_accessed: str | None = None
    relevance_score: float = 0.0
