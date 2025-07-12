"""
Integration tests for the source analysis module.

These tests make actual HTTP requests to verify the functionality
of webpage analysis tools.

Test Coverage:
- assess_webpage_credibility(): Tests with high-credibility academic sites, 
  government sites, and error handling for invalid URLs
- extract_webpage_metadata(): Tests with news sites, academic sites, 
  and error handling  
- categorize_source(): Tests categorization for academic, government, 
  news media, blog/opinion, and unknown commercial domains

All tests are marked as integration tests and make real HTTP requests
to verify functionality with actual web content.
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from agents.ollama.deep_research.source_analysis import (
    assess_webpage_credibility,
    extract_webpage_metadata,
    categorize_source,
    CredibilityAssessment,
    WebpageMetadata,
    SourceCategorization,
)


class TestWebpageCredibilityAssessment:
    """Integration tests for assess_webpage_credibility function."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_assess_webpage_credibility_high_credibility_site(self):
        """
        Test credibility assessment of a high-credibility academic site.
        
        This test verifies that the function correctly identifies and scores
        a well-known academic/research website with high credibility.
        """
        # Using a well-known academic site
        url = "https://www.nature.com/articles/d41586-023-03023-4"
        
        # Mock the LLM content quality assessment to avoid dependency
        with patch('agents.ollama.deep_research.source_analysis._assess_content_quality') as mock_quality:
            mock_quality.return_value = 0.8
            
            result = await assess_webpage_credibility(url)
        
        # Verify return type and structure
        assert isinstance(result, dict)
        assert 'url' in result
        assert 'credibility_score' in result
        assert 'credibility_level' in result
        assert 'factors' in result
        assert 'domain' in result
        assert 'recommendations' in result
        
        # Verify specific values for nature.com
        assert result['url'] == url
        assert result['domain'] == 'www.nature.com'
        assert result['credibility_score'] >= 0.7  # Should be high for nature.com
        assert result['credibility_level'] in ['High', 'Medium']
        
        # Verify factors structure
        factors = result['factors']
        assert 'domain_credibility' in factors
        assert 'https_enabled' in factors
        assert 'has_author' in factors
        assert 'has_publication_date' in factors
        assert 'content_quality' in factors
        assert 'citation_indicators' in factors
        
        # Nature.com should have high domain credibility and HTTPS
        assert factors['domain_credibility'] >= 0.8
        assert factors['https_enabled'] is True
        
        # Recommendations should be a list
        assert isinstance(result['recommendations'], list)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_assess_webpage_credibility_government_site(self):
        """
        Test credibility assessment of a government website.
        
        This test verifies proper assessment of official government sources
        which should receive high credibility scores.
        """
        # Using a government site
        url = "https://www.cdc.gov/about/index.html"
        
        # Mock the LLM content quality assessment
        with patch('agents.ollama.deep_research.source_analysis._assess_content_quality') as mock_quality:
            mock_quality.return_value = 0.75
            
            result = await assess_webpage_credibility(url)
        
        # Government sites should have very high credibility
        assert result['credibility_score'] >= 0.8
        assert result['credibility_level'] in ['High', 'Medium']
        assert result['factors']['domain_credibility'] >= 0.9  # .gov domains are highly credible
        assert result['factors']['https_enabled'] is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_assess_webpage_credibility_error_handling(self):
        """
        Test error handling for invalid URLs.
        
        This test verifies that the function properly handles and raises
        exceptions for URLs that cannot be retrieved.
        """
        invalid_url = "https://this-domain-does-not-exist-12345.invalid"
        
        with pytest.raises(Exception):
            await assess_webpage_credibility(invalid_url)


class TestWebpageMetadataExtraction:
    """Integration tests for extract_webpage_metadata function."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extract_webpage_metadata_news_site(self):
        """
        Test metadata extraction from a news website.
        
        This test verifies comprehensive metadata extraction including
        title, author, publication date, and other relevant fields.
        """
        # Using BBC News as it typically has good metadata
        url = "https://www.bbc.com/news"
        
        result = await extract_webpage_metadata(url)
        
        # Verify return type and required fields
        assert isinstance(result, dict)
        assert 'url' in result
        assert 'title' in result
        assert 'author' in result
        assert 'publication_date' in result
        assert 'description' in result
        assert 'keywords' in result
        assert 'language' in result
        assert 'publisher' in result
        assert 'domain' in result
        assert 'word_count' in result
        assert 'last_modified' in result
        
        # Verify specific values
        assert result['url'] == url
        assert result['domain'] == 'www.bbc.com'
        assert isinstance(result['word_count'], int)
        assert result['word_count'] > 0
        
        # BBC should have a title
        assert result['title'] is not None
        assert len(result['title']) > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extract_webpage_metadata_academic_site(self):
        """
        Test metadata extraction from an academic website.
        
        This test verifies extraction of academic-specific metadata
        such as author information and publication details.
        """
        # Using a university page
        url = "https://www.mit.edu/about/"
        
        result = await extract_webpage_metadata(url)
        
        # Verify basic structure
        assert result['url'] == url
        assert result['domain'] == 'www.mit.edu'
        assert isinstance(result['word_count'], int)
        
        # MIT should have a title and description
        assert result['title'] is not None
        assert len(result['title']) > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extract_webpage_metadata_error_handling(self):
        """
        Test error handling for metadata extraction with invalid URLs.
        
        This test ensures proper exception handling when webpage
        content cannot be retrieved or parsed.
        """
        invalid_url = "https://invalid-domain-12345.nonexistent"
        
        with pytest.raises(Exception):
            await extract_webpage_metadata(invalid_url)


class TestSourceCategorization:
    """Integration tests for categorize_source function."""

    @pytest.mark.integration
    def test_categorize_source_academic_site(self):
        """
        Test source categorization for academic websites.
        
        This test verifies proper categorization of educational institutions
        and academic sources with appropriate authority levels.
        """
        url = "https://www.stanford.edu/research/publications"
        metadata: WebpageMetadata = {
            'url': url,
            'title': 'Research Publications - Stanford University',
            'author': None,
            'publication_date': '2024-01-15',
            'description': 'Latest research publications from Stanford',
            'keywords': 'research, publications, academia',
            'language': 'en',
            'publisher': 'Stanford University',
            'domain': 'www.stanford.edu',
            'word_count': 1500,
            'last_modified': '2024-01-20',
        }
        
        result = categorize_source(url, metadata)
        
        # Verify return type and structure
        assert isinstance(result, dict)
        assert 'url' in result
        assert 'categories' in result
        assert 'confidence' in result
        assert 'notes' in result
        
        # Verify specific categorization for academic site
        assert result['url'] == url
        categories = result['categories']
        assert categories['primary_type'] == 'Academic'
        assert categories['authority_level'] == 'High'
        assert categories['temporal_relevance'] == 'Current'  # 2024 date is current
        
        # Confidence should be reasonable
        assert isinstance(result['confidence'], float)
        assert 0.0 <= result['confidence'] <= 1.0
        assert result['confidence'] >= 0.6  # Should be confident about .edu domains
        
        # Notes should include academic source information
        assert isinstance(result['notes'], list)
        assert any('academic' in note.lower() for note in result['notes'])

    @pytest.mark.integration
    def test_categorize_source_government_site(self):
        """
        Test source categorization for government websites.
        
        This test verifies proper identification and categorization
        of official government sources.
        """
        url = "https://www.fda.gov/food/food-safety-modernization-act-fsma"
        metadata: WebpageMetadata = {
            'url': url,
            'title': 'Food Safety Modernization Act (FSMA) | FDA',
            'author': None,
            'publication_date': '2023-06-15',
            'description': 'Information about food safety regulations',
            'keywords': 'food safety, regulation, FDA',
            'language': 'en',
            'publisher': 'U.S. Food and Drug Administration',
            'domain': 'www.fda.gov',
            'word_count': 2500,
            'last_modified': '2023-07-01',
        }
        
        result = categorize_source(url, metadata)
        
        # Verify government categorization
        categories = result['categories']
        assert categories['primary_type'] == 'Government'
        assert categories['authority_level'] == 'High'
        assert categories['geographic_focus'] == 'US'
        
        # Government sources should have high confidence
        assert result['confidence'] >= 0.7
        
        # Notes should mention government source
        assert any('government' in note.lower() for note in result['notes'])

    @pytest.mark.integration
    def test_categorize_source_news_media(self):
        """
        Test source categorization for news media websites.
        
        This test verifies proper categorization of established
        news organizations and media outlets.
        """
        url = "https://www.reuters.com/business/technology/ai-regulation-2024"
        metadata: WebpageMetadata = {
            'url': url,
            'title': 'AI Regulation Trends in 2024 - Reuters',
            'author': 'Jane Smith',
            'publication_date': '2024-03-10',
            'description': 'Analysis of AI regulation developments',
            'keywords': 'AI, regulation, technology, policy',
            'language': 'en',
            'publisher': 'Reuters',
            'domain': 'www.reuters.com',
            'word_count': 1200,
            'last_modified': '2024-03-11',
        }
        
        result = categorize_source(url, metadata)
        
        # Verify news media categorization
        categories = result['categories']
        assert categories['primary_type'] == 'News Media'
        assert categories['authority_level'] == 'Medium-High'
        # Content type may be Unknown if URL doesn't contain specific keywords
        assert categories['content_type'] in ['News Article', 'Unknown']
        assert categories['temporal_relevance'] == 'Current'  # 2024 date
        
        # Should have good confidence for established news source
        assert result['confidence'] >= 0.6

    @pytest.mark.integration
    def test_categorize_source_blog_opinion(self):
        """
        Test source categorization for blog and opinion content.
        
        This test verifies proper identification of lower-authority
        sources like personal blogs and opinion pieces.
        """
        url = "https://medium.com/@user/my-thoughts-on-tech-trends"
        metadata: WebpageMetadata = {
            'url': url,
            'title': 'My Thoughts on Tech Trends',
            'author': 'John Blogger',
            'publication_date': '2024-02-20',
            'description': 'Personal opinions on technology trends',
            'keywords': 'technology, opinion, trends',
            'language': 'en',
            'publisher': 'Medium',
            'domain': 'medium.com',
            'word_count': 800,
            'last_modified': None,
        }
        
        result = categorize_source(url, metadata)
        
        # Verify blog categorization
        categories = result['categories']
        assert categories['primary_type'] == 'Blog/Opinion'
        assert categories['authority_level'] == 'Low-Medium'
        # Content type may be Unknown if URL doesn't contain specific keywords
        assert categories['content_type'] in ['Opinion/Blog', 'Unknown']
        
        # Should recommend verification for opinion pieces
        assert any('opinion' in note.lower() or 'verify' in note.lower() 
                  for note in result['notes'])

    @pytest.mark.integration
    def test_categorize_source_unknown_domain(self):
        """
        Test source categorization for unknown or commercial domains.
        
        This test verifies handling of domains that don't match
        common patterns and require more careful assessment.
        """
        url = "https://www.example-company.com/article/technology-review"
        metadata: WebpageMetadata = {
            'url': url,
            'title': 'Technology Review Article',
            'author': 'Company Writer',
            'publication_date': '2020-05-15',
            'description': 'Company perspective on technology',
            'keywords': 'technology, business, review',
            'language': 'en',
            'publisher': 'Example Company',
            'domain': 'www.example-company.com',
            'word_count': 1000,
            'last_modified': '2020-06-01',
        }
        
        result = categorize_source(url, metadata)
        
        # Should categorize as commercial with medium authority
        categories = result['categories']
        assert categories['primary_type'] == 'Commercial'
        assert categories['authority_level'] == 'Medium'
        assert categories['temporal_relevance'] == 'Recent'  # 2020 date is within 5 years
        
        # Confidence might be lower for unknown domains
        assert 0.0 <= result['confidence'] <= 1.0
