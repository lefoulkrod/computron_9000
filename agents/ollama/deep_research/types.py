"""
Type definitions for the Deep Research Agent.
"""

import pydantic
from typing import List, Dict, Optional, Union

class ResearchSource(pydantic.BaseModel):
    """
    Represents a source used in research.

    Attributes:
        url (str): The URL of the source.
        title (str): The title of the source.
        author (Optional[str]): The author of the source, if available.
        publication_date (Optional[str]): The publication date of the source, if available.
        credibility_score (Optional[float]): A score from 0 to 1 representing the estimated credibility.
        content_summary (str): A brief summary of the source content.
    """
    url: str
    title: str
    author: Optional[str] = None
    publication_date: Optional[str] = None
    credibility_score: Optional[float] = None
    content_summary: str

class ResearchCitation(pydantic.BaseModel):
    """
    Represents a formatted citation.

    Attributes:
        source (ResearchSource): The source being cited.
        citation_text (str): The formatted citation text.
        citation_style (str): The style used for the citation (APA, MLA, etc.).
    """
    source: ResearchSource
    citation_text: str
    citation_style: str = "APA"

class ResearchReport(pydantic.BaseModel):
    """
    Represents a comprehensive research report.

    Attributes:
        topic (str): The main research topic.
        summary (str): Executive summary of findings.
        methodology (str): Description of research methodology.
        findings (Dict[str, str]): Key findings organized by subtopic.
        analysis (str): Analysis of the findings.
        limitations (str): Limitations of the research.
        conclusion (str): Conclusion of the research.
        sources (List[ResearchSource]): List of sources used.
        citations (List[ResearchCitation]): List of citations.
    """
    topic: str
    summary: str
    methodology: str
    findings: Dict[str, str]
    analysis: str
    limitations: str
    conclusion: str
    sources: List[ResearchSource]
    citations: List[ResearchCitation]
