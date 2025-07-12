"""
Source analysis tools for the Deep Research Agent.

This module provides tools for analyzing webpage credibility, extracting metadata,
and categorizing sources.
"""

import logging
import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Tuple, TypedDict
from urllib.parse import urlparse

import bs4

from tools.web.get_webpage_raw import _get_webpage_raw
from tools.web.types import GetWebpageResult
from utils.generate_completion import generate_completion

logger = logging.getLogger(__name__)


# Type definitions for strongly typed return values
class CredibilityFactors(TypedDict):
    """Factors used in credibility assessment."""
    domain_credibility: float
    https_enabled: bool
    has_author: bool
    has_publication_date: bool
    content_quality: float
    citation_indicators: float


class CredibilityAssessment(TypedDict):
    """Complete credibility assessment result."""
    url: str
    credibility_score: float
    credibility_level: str
    factors: CredibilityFactors
    domain: str
    recommendations: List[str]


class WebpageMetadata(TypedDict):
    """Comprehensive webpage metadata."""
    url: str
    title: Optional[str]
    author: Optional[str]
    publication_date: Optional[str]
    description: Optional[str]
    keywords: Optional[str]
    language: Optional[str]
    publisher: Optional[str]
    domain: str
    word_count: int
    last_modified: Optional[str]


class SourceCategories(TypedDict):
    """Source categorization classifications."""
    primary_type: str
    secondary_type: Optional[str]
    authority_level: str
    content_type: str
    geographic_focus: Optional[str]
    temporal_relevance: str


class SourceCategorization(TypedDict):
    """Complete source categorization result."""
    url: str
    categories: SourceCategories
    confidence: float
    notes: List[str]


def _safe_get_attribute(element: Any, attr: str, default: str = '') -> str:
    """
    Safely get an attribute value from a BeautifulSoup element.
    
    Args:
        element (Any): The BeautifulSoup element
        attr (str): The attribute name to get
        default (str): Default value if attribute not found
        
    Returns:
        str: The attribute value or default
    """
    if not element or not hasattr(element, 'get'):
        return default
    
    try:
        value = element.get(attr)
        if value is None:
            return default
        
        # Handle AttributeValueList (multiple values)
        if isinstance(value, list):
            return ' '.join(str(v) for v in value).strip()
        
        return str(value).strip()
    except (AttributeError, TypeError):
        return default

# Known credible domains for domain-based credibility assessment
CREDIBLE_DOMAINS: Dict[str, float] = {
    # Academic and research institutions
    'edu': 0.9,
    'ac.uk': 0.9,
    'org': 0.7,
    
    # Government sources
    'gov': 0.95,
    'gov.uk': 0.95,
    'europa.eu': 0.9,
    
    # Established news organizations
    'reuters.com': 0.9,
    'bbc.com': 0.9,
    'bbc.co.uk': 0.9,
    'npr.org': 0.85,
    'apnews.com': 0.9,
    'cnn.com': 0.75,
    'nytimes.com': 0.8,
    'washingtonpost.com': 0.8,
    'theguardian.com': 0.8,
    'wsj.com': 0.85,
    
    # Scientific publishers
    'nature.com': 0.95,
    'science.org': 0.95,
    'cell.com': 0.95,
    'nejm.org': 0.95,
    'bmj.com': 0.9,
    'pubmed.ncbi.nlm.nih.gov': 0.95,
    'arxiv.org': 0.85,
    
    # Technology sources
    'ieee.org': 0.9,
    'acm.org': 0.9,
    
    # International organizations
    'who.int': 0.95,
    'un.org': 0.9,
    'worldbank.org': 0.85,
    'imf.org': 0.85,
}

# Common date patterns for extraction
DATE_PATTERNS: List[str] = [
    # ISO format: 2023-12-31, 2023/12/31
    r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b',
    # US format: 12/31/2023, 12-31-2023
    r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b',
    # European format: 31/12/2023, 31-12-2023
    r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{4})\b',
    # Month name formats: December 31, 2023; Dec 31, 2023
    r'\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b',
    # Format: 31 December 2023
    r'\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b',
]

async def assess_webpage_credibility(url: str) -> CredibilityAssessment:
    """
    Assess the credibility of a webpage based on various factors.
    
    Args:
        url (str): The URL to assess
        
    Returns:
        Dict[str, Any]: Credibility assessment results
        
    Raises:
        Exception: If webpage cannot be retrieved or analyzed
    """
    try:
        # Get webpage content
        webpage_result = await _get_webpage_raw(url)
        if isinstance(webpage_result, Exception):
            raise webpage_result
            
        # Parse domain
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        
        # Initialize credibility factors
        factors: CredibilityFactors = {
            'domain_credibility': _assess_domain_credibility(domain),
            'https_enabled': url.lower().startswith('https://'),
            'has_author': False,
            'has_publication_date': False,
            'content_quality': 0.5,  # Default middle score
            'citation_indicators': 0.0,
        }
        
        # Parse HTML for analysis
        soup = bs4.BeautifulSoup(webpage_result.html, 'html.parser')
        
        # Check for author information
        author_info = _extract_author_info(soup)
        factors['has_author'] = bool(author_info)
        
        # Check for publication date
        pub_date = _extract_publication_date(soup, webpage_result.html)
        factors['has_publication_date'] = bool(pub_date)
        
        # Assess content quality using LLM
        text_content = _extract_text_content(soup)
        if text_content and len(text_content) > 100:
            factors['content_quality'] = await _assess_content_quality(text_content[:2000])
        
        # Check for citation indicators
        factors['citation_indicators'] = _assess_citation_indicators(soup)
        
        # Calculate overall credibility score
        credibility_score = _calculate_credibility_score(factors)
        
        # Determine credibility level
        if credibility_score >= 0.8:
            credibility_level = "High"
        elif credibility_score >= 0.6:
            credibility_level = "Medium"
        elif credibility_score >= 0.4:
            credibility_level = "Low"
        else:
            credibility_level = "Very Low"
        
        return {
            'url': url,
            'credibility_score': credibility_score,
            'credibility_level': credibility_level,
            'factors': factors,
            'domain': domain,
            'recommendations': _generate_credibility_recommendations(factors, credibility_level)
        }
        
    except Exception as e:
        logger.error(f"Error assessing webpage credibility for {url}: {e}")
        raise


def _assess_domain_credibility(domain: str) -> float:
    """
    Assess credibility based on domain reputation.
    
    Args:
        domain (str): The domain to assess
        
    Returns:
        float: Credibility score between 0.0 and 1.0
    """
    # Direct domain match
    if domain in CREDIBLE_DOMAINS:
        return CREDIBLE_DOMAINS[domain]
    
    # Check for domain endings
    for pattern, score in CREDIBLE_DOMAINS.items():
        if domain.endswith(pattern):
            return score
    
    # Default score for unknown domains
    return 0.5


def _extract_author_info(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract author information from webpage.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The author name if found, None otherwise
    """
    # Common author selectors
    author_selectors = [
        'meta[name="author"]',
        'meta[property="article:author"]',
        '.author',
        '.byline',
        '.post-author',
        '.article-author',
        '[rel="author"]',
    ]
    
    for selector in author_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                content = _safe_get_attribute(element, 'content')
                if content:
                    return content
            else:
                text = element.get_text(strip=True)
                if text and len(text) < 100:  # Reasonable author name length
                    return text
    
    return None


def _extract_publication_date(soup: bs4.BeautifulSoup, html_content: str) -> Optional[str]:
    """
    Extract publication date from webpage.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        html_content (str): The raw HTML content for pattern matching
        
    Returns:
        Optional[str]: The publication date if found, None otherwise
    """
    # Meta tag selectors for dates
    date_selectors = [
        'meta[property="article:published_time"]',
        'meta[property="article:modified_time"]',
        'meta[name="publish-date"]',
        'meta[name="publication-date"]',
        'meta[name="date"]',
        'time[datetime]',
        '.publish-date',
        '.publication-date',
        '.post-date',
        '.article-date',
    ]
    
    # Check meta tags and structured elements first
    for selector in date_selectors:
        element = soup.select_one(selector)
        if element:
            if element.name == 'meta':
                content = _safe_get_attribute(element, 'content')
                if content:
                    return content
            elif element.name == 'time':
                datetime_attr = _safe_get_attribute(element, 'datetime')
                if datetime_attr:
                    return datetime_attr
                text_content = element.get_text(strip=True)
                if text_content:
                    return text_content
            else:
                text_content = element.get_text(strip=True)
                if text_content:
                    return text_content
    
    # If no structured date found, search for date patterns in text
    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, html_content)
        if matches:
            return matches[0]
    
    return None


def _extract_text_content(soup: bs4.BeautifulSoup) -> str:
    """
    Extract clean text content from webpage.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        str: Clean text content with whitespace normalized
    """
    # Remove script and style elements
    for script in soup(["script", "style", "nav", "header", "footer"]):
        script.decompose()
    
    # Get text content
    text = soup.get_text()
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = ' '.join(chunk for chunk in chunks if chunk)
    
    return text


async def _assess_content_quality(text_content: str) -> float:
    """
    Use LLM to assess content quality indicators.
    
    Args:
        text_content (str): The text content to analyze
        
    Returns:
        float: Quality score between 0.0 and 1.0
    """
    prompt = f"""
Analyze the following text excerpt and assess its quality for research purposes. Consider:
1. Writing quality and clarity
2. Use of evidence and citations
3. Objectivity vs bias
4. Depth of information
5. Professional tone

Text excerpt:
{text_content}

Respond with a JSON object containing:
- quality_score: float between 0.0 and 1.0
- reasoning: brief explanation

Example response:
{{"quality_score": 0.75, "reasoning": "Well-written with citations, but shows some bias"}}
"""
    
    try:
        response = await generate_completion(
            prompt=prompt,
            model_name="sentiment_analysis"  # Using optimized model for analysis
        )
        
        # Try to parse JSON response
        result = json.loads(response.strip())
        return float(result.get('quality_score', 0.5))
        
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to parse content quality assessment: {e}")
        return 0.5  # Default to middle score


def _assess_citation_indicators(soup: bs4.BeautifulSoup) -> float:
    """
    Assess presence of citations and references.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        float: Citation indicator score between 0.0 and 1.0
    """
    citation_score = 0.0
    
    # Look for reference sections
    ref_sections = soup.find_all(['section', 'div'], class_=re.compile(r'reference|citation|bibliograph', re.I))
    if ref_sections:
        citation_score += 0.3
    
    # Look for academic citation formats
    text = soup.get_text()
    
    # Check for numbered citations [1], [2], etc.
    numbered_citations = len(re.findall(r'\[\d+\]', text))
    if numbered_citations > 0:
        citation_score += min(0.3, numbered_citations * 0.05)
    
    # Check for parenthetical citations (Author, Year)
    parenthetical_citations = len(re.findall(r'\([A-Za-z][^,)]*,\s*\d{4}\)', text))
    if parenthetical_citations > 0:
        citation_score += min(0.2, parenthetical_citations * 0.03)
    
    # Check for DOI links
    doi_links = soup.find_all('a', href=re.compile(r'doi\.org', re.I))
    if doi_links:
        citation_score += 0.2
    
    return min(1.0, citation_score)


def _calculate_credibility_score(factors: CredibilityFactors) -> float:
    """
    Calculate overall credibility score from factors.
    
    Args:
        factors (Dict[str, Any]): Dictionary of credibility factors
        
    Returns:
        float: Overall credibility score between 0.0 and 1.0
    """
    weights = {
        'domain_credibility': 0.3,
        'https_enabled': 0.1,
        'has_author': 0.15,
        'has_publication_date': 0.15,
        'content_quality': 0.2,
        'citation_indicators': 0.1,
    }
    
    score = 0.0
    for factor, weight in weights.items():
        if factor in factors:
            value = factors[factor]
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            score += value * weight
    
    return min(1.0, max(0.0, score))


def _generate_credibility_recommendations(factors: CredibilityFactors, level: str) -> List[str]:
    """
    Generate recommendations for using the source.
    
    Args:
        factors (Dict[str, Any]): Dictionary of credibility factors
        level (str): The credibility level (High, Medium, Low, Very Low)
        
    Returns:
        List[str]: List of recommendation strings
    """
    recommendations = []
    
    if level == "Very Low":
        recommendations.append("Use with extreme caution - verify all claims with other sources")
    elif level == "Low":
        recommendations.append("Cross-reference information with more credible sources")
    
    if not factors.get('has_author'):
        recommendations.append("No author information found - check for organizational authorship")
    
    if not factors.get('has_publication_date'):
        recommendations.append("No publication date found - information currency cannot be verified")
    
    if not factors.get('https_enabled'):
        recommendations.append("Site does not use HTTPS - be cautious with sensitive information")
    
    if factors.get('citation_indicators', 0) < 0.2:
        recommendations.append("Limited citations found - verify claims independently")
    
    if factors.get('content_quality', 0.5) < 0.4:
        recommendations.append("Content quality concerns - use as supplementary source only")
    
    if not recommendations:
        recommendations.append("Source appears credible - suitable for research use")
    
    return recommendations


async def extract_webpage_metadata(url: str) -> WebpageMetadata:
    """
    Extract comprehensive metadata from a webpage.
    
    Args:
        url (str): The URL to analyze
        
    Returns:
        Dict[str, Any]: Extracted metadata
    """
    try:
        # Get webpage content
        webpage_result = await _get_webpage_raw(url)
        if isinstance(webpage_result, Exception):
            raise webpage_result
        
        # Parse HTML
        soup = bs4.BeautifulSoup(webpage_result.html, 'html.parser')
        
        # Extract basic metadata
        metadata: WebpageMetadata = {
            'url': url,
            'title': _extract_title(soup),
            'author': _extract_author_info(soup),
            'publication_date': _extract_publication_date(soup, webpage_result.html),
            'description': _extract_description(soup),
            'keywords': _extract_keywords(soup),
            'language': _extract_language(soup),
            'publisher': _extract_publisher(soup),
            'domain': urlparse(url).netloc,
            'word_count': _estimate_word_count(soup),
            'last_modified': _extract_last_modified(soup),
        }
        
        return metadata
        
    except Exception as e:
        logger.error(f"Error extracting metadata for {url}: {e}")
        raise


def _extract_title(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract page title.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The page title if found, None otherwise
    """
    # Try Open Graph title first
    og_title = soup.find('meta', property='og:title')
    if og_title:
        content = _safe_get_attribute(og_title, 'content')
        if content:
            return content
    
    # Try standard title tag
    title_tag = soup.find('title')
    if title_tag:
        return title_tag.get_text(strip=True)
    
    # Try h1 as fallback
    h1 = soup.find('h1')
    if h1:
        return h1.get_text(strip=True)
    
    return None


def _extract_description(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract page description.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The page description if found, None otherwise
    """
    # Try meta description
    desc_meta = soup.find('meta', attrs={'name': 'description'})
    if desc_meta:
        content = _safe_get_attribute(desc_meta, 'content')
        if content:
            return content
    
    # Try Open Graph description
    og_desc = soup.find('meta', property='og:description')
    if og_desc:
        content = _safe_get_attribute(og_desc, 'content')
        if content:
            return content
    
    return None


def _extract_keywords(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract keywords from meta tags.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The keywords if found, None otherwise
    """
    keywords_meta = soup.find('meta', attrs={'name': 'keywords'})
    if keywords_meta:
        content = _safe_get_attribute(keywords_meta, 'content')
        if content:
            return content
    
    return None


def _extract_language(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract language information.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The language code if found, None otherwise
    """
    html_tag = soup.find('html')
    if html_tag:
        lang = _safe_get_attribute(html_tag, 'lang')
        if lang:
            return lang
    
    return None


def _extract_publisher(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract publisher information.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The publisher name if found, None otherwise
    """
    # Try Open Graph site name
    og_site = soup.find('meta', property='og:site_name')
    if og_site:
        content = _safe_get_attribute(og_site, 'content')
        if content:
            return content
    
    # Try publisher meta tag
    publisher_meta = soup.find('meta', attrs={'name': 'publisher'})
    if publisher_meta:
        content = _safe_get_attribute(publisher_meta, 'content')
        if content:
            return content
    
    return None


def _extract_last_modified(soup: bs4.BeautifulSoup) -> Optional[str]:
    """
    Extract last modified date.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        Optional[str]: The last modified date if found, None otherwise
    """
    last_mod_meta = soup.find('meta', attrs={'name': 'last-modified'})
    if last_mod_meta:
        content = _safe_get_attribute(last_mod_meta, 'content')
        if content:
            return content
    
    # Try article:modified_time
    mod_time = soup.find('meta', property='article:modified_time')
    if mod_time:
        content = _safe_get_attribute(mod_time, 'content')
        if content:
            return content
    
    return None


def _estimate_word_count(soup: bs4.BeautifulSoup) -> int:
    """
    Estimate word count of main content.
    
    Args:
        soup (bs4.BeautifulSoup): The parsed HTML document
        
    Returns:
        int: Estimated word count
    """
    text = _extract_text_content(soup)
    if text:
        words = text.split()
        return len(words)
    return 0


def categorize_source(url: str, metadata: WebpageMetadata) -> SourceCategorization:
    """
    Categorize a source based on URL and metadata.
    
    Args:
        url (str): The URL of the source
        metadata (WebpageMetadata): Extracted metadata
        
    Returns:
        SourceCategorization: Source categorization results
    """
    domain = urlparse(url).netloc.lower()
    
    # Initialize categories
    categories: SourceCategories = {
        'primary_type': 'Unknown',
        'secondary_type': None,
        'authority_level': 'Unknown',
        'content_type': 'Unknown',
        'geographic_focus': None,
        'temporal_relevance': 'Unknown',
    }
    
    # Determine primary type based on domain patterns
    if any(pattern in domain for pattern in ['.edu', '.ac.', 'university', 'college']):
        categories['primary_type'] = 'Academic'
        categories['authority_level'] = 'High'
    elif any(pattern in domain for pattern in ['.gov', '.mil']):
        categories['primary_type'] = 'Government'
        categories['authority_level'] = 'High'
    elif any(pattern in domain for pattern in ['news', 'times', 'post', 'herald', 'guardian', 'bbc', 'cnn', 'reuters', 'ap']):
        categories['primary_type'] = 'News Media'
        categories['authority_level'] = 'Medium-High'
    elif any(pattern in domain for pattern in ['blog', 'medium.com', 'substack']):
        categories['primary_type'] = 'Blog/Opinion'
        categories['authority_level'] = 'Low-Medium'
    elif 'wikipedia' in domain:
        categories['primary_type'] = 'Encyclopedia'
        categories['authority_level'] = 'Medium'
    elif any(pattern in domain for pattern in ['reddit', 'twitter', 'facebook', 'social']):
        categories['primary_type'] = 'Social Media'
        categories['authority_level'] = 'Low'
    elif '.org' in domain:
        categories['primary_type'] = 'Organization'
        categories['authority_level'] = 'Medium'
    elif '.com' in domain:
        categories['primary_type'] = 'Commercial'
        categories['authority_level'] = 'Medium'
    
    # Determine content type from URL patterns and metadata
    if any(pattern in url.lower() for pattern in ['research', 'study', 'paper', 'journal']):
        categories['content_type'] = 'Research'
    elif any(pattern in url.lower() for pattern in ['news', 'article', 'story']):
        categories['content_type'] = 'News Article'
    elif any(pattern in url.lower() for pattern in ['blog', 'post', 'opinion']):
        categories['content_type'] = 'Opinion/Blog'
    elif any(pattern in url.lower() for pattern in ['wiki', 'encyclopedia']):
        categories['content_type'] = 'Reference'
    elif any(pattern in url.lower() for pattern in ['report', 'white-paper', 'publication']):
        categories['content_type'] = 'Report'
    
    # Assess temporal relevance
    pub_date = metadata.get('publication_date')
    if pub_date:
        try:
            # Simple date parsing to assess recency
            current_year = datetime.now().year
            if str(current_year) in pub_date or str(current_year - 1) in pub_date:
                categories['temporal_relevance'] = 'Current'
            elif any(str(year) in pub_date for year in range(current_year - 5, current_year)):
                categories['temporal_relevance'] = 'Recent'
            else:
                categories['temporal_relevance'] = 'Historical'
        except:
            categories['temporal_relevance'] = 'Unknown'
    
    # Geographic focus detection (basic)
    if any(pattern in domain for pattern in ['.uk', 'bbc', 'guardian']):
        categories['geographic_focus'] = 'UK'
    elif any(pattern in domain for pattern in ['.gov', '.edu', 'cnn', 'nytimes']):
        categories['geographic_focus'] = 'US'
    elif '.eu' in domain:
        categories['geographic_focus'] = 'Europe'
    
    result: SourceCategorization = {
        'url': url,
        'categories': categories,
        'confidence': _calculate_categorization_confidence(categories, domain, metadata),
        'notes': _generate_categorization_notes(categories, domain)
    }
    
    return result


def _calculate_categorization_confidence(categories: SourceCategories, domain: str, metadata: WebpageMetadata) -> float:
    """
    Calculate confidence in categorization.
    
    Args:
        categories (Dict[str, str]): The categorization results
        domain (str): The domain name
        metadata (Dict[str, Any]): The extracted metadata
        
    Returns:
        float: Confidence score between 0.0 and 1.0
    """
    confidence = 0.5  # Base confidence
    
    # Higher confidence for well-known domains
    if any(pattern in domain for pattern in CREDIBLE_DOMAINS.keys()):
        confidence += 0.3
    
    # Higher confidence if we have good metadata
    if metadata.get('author'):
        confidence += 0.1
    if metadata.get('publication_date'):
        confidence += 0.1
    
    # Lower confidence for uncertain classifications
    if categories['primary_type'] == 'Unknown':
        confidence -= 0.3
    if categories['authority_level'] == 'Unknown':
        confidence -= 0.2
    
    return min(1.0, max(0.0, confidence))


def _generate_categorization_notes(categories: SourceCategories, domain: str) -> List[str]:
    """
    Generate notes about the categorization.
    
    Args:
        categories (Dict[str, str]): The categorization results
        domain (str): The domain name
        
    Returns:
        List[str]: List of categorization notes
    """
    notes = []
    
    if categories['primary_type'] == 'Academic':
        notes.append("Academic source - likely peer-reviewed or scholarly")
    elif categories['primary_type'] == 'Government':
        notes.append("Government source - official information")
    elif categories['primary_type'] == 'News Media':
        notes.append("News media - check for editorial standards")
    elif categories['primary_type'] == 'Blog/Opinion':
        notes.append("Blog/opinion piece - verify claims independently")
    elif categories['primary_type'] == 'Social Media':
        notes.append("Social media content - use for public opinion, verify facts")
    
    if categories['authority_level'] == 'High':
        notes.append("High authority source")
    elif categories['authority_level'] == 'Low':
        notes.append("Lower authority - use as supplementary source")
    
    if categories['temporal_relevance'] == 'Historical':
        notes.append("Historical source - check for updated information")
    elif categories['temporal_relevance'] == 'Current':
        notes.append("Current source - information is recent")
    
    return notes
