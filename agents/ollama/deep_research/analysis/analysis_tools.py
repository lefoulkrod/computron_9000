"""
Analysis tools and functionality.

This module provides tools for source analysis, credibility assessment, and cross-reference verification.
Migrated from source_analysis.py as part of Phase 3.2 tool migration refactors.
"""

import logging
from typing import Any

from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker
from agents.ollama.deep_research.source_analysis import (
    CredibilityAssessment,
    SourceCategorization,
    WebpageMetadata,
    assess_webpage_credibility,
    categorize_source,
    extract_webpage_metadata,
)

logger = logging.getLogger(__name__)


class AnalysisTools:
    """
    Analysis tools with agent-specific source tracking.

    This class provides source analysis capabilities for the Analysis Agent,
    including credibility assessment, metadata extraction, and source categorization.
    """

    def __init__(self, source_tracker: AgentSourceTracker):
        """
        Initialize analysis tools with an agent-specific source tracker.

        Args:
            source_tracker (AgentSourceTracker): The agent-specific source tracker to use
        """
        self.source_tracker = source_tracker

    async def assess_webpage_credibility(self, url: str) -> CredibilityAssessment:
        """
        Assess webpage credibility with automatic source tracking.

        Args:
            url (str): The URL to assess

        Returns:
            CredibilityAssessment: Credibility assessment results
        """
        self.source_tracker.register_access(
            url=url, tool_name="assess_webpage_credibility"
        )
        return await assess_webpage_credibility(url=url)

    async def extract_webpage_metadata(self, url: str) -> WebpageMetadata:
        """
        Extract webpage metadata with automatic source tracking.

        Args:
            url (str): The URL to analyze

        Returns:
            WebpageMetadata: Extracted metadata
        """
        self.source_tracker.register_access(
            url=url, tool_name="extract_webpage_metadata"
        )
        return await extract_webpage_metadata(url=url)

    def categorize_source(
        self, url: str, metadata: WebpageMetadata | None = None
    ) -> SourceCategorization:
        """
        Categorize a source with automatic source tracking.

        Args:
            url (str): The URL of the source
            metadata (WebpageMetadata | None): Extracted metadata. If None, will extract metadata first.

        Returns:
            SourceCategorization: Source categorization results
        """
        self.source_tracker.register_access(url=url, tool_name="categorize_source")

        # If metadata is not provided, we would need to extract it first
        # For now, require metadata to be provided
        if metadata is None:
            raise ValueError(
                "Metadata must be provided for source categorization. Use extract_webpage_metadata first."
            )

        return categorize_source(url=url, metadata=metadata)

    # Cross-reference verification functionality (migrated from legacy Cross-Reference Verifier)
    async def verify_cross_references(
        self, sources: list[dict[str, Any]], claims: list[str]
    ) -> dict[str, Any]:
        """
        Verify claims across multiple sources and identify cross-references.

        Args:
            sources (List[Dict[str, Any]]): List of sources to cross-reference
            claims (List[str]): List of claims to verify

        Returns:
            Dict[str, Any]: Cross-reference verification results
        """
        try:
            verification_results = []

            for claim in claims:
                claim_verification = await self._verify_single_claim(claim, sources)
                verification_results.append(claim_verification)

            # Analyze overall verification strength
            verification_summary = self._analyze_verification_strength(
                verification_results
            )

            # Identify citation chains and networks
            citation_networks = self._identify_citation_networks(sources)

            return {
                "claims_verified": len(claims),
                "sources_analyzed": len(sources),
                "verification_results": verification_results,
                "verification_summary": verification_summary,
                "citation_networks": citation_networks,
                "cross_reference_score": self._calculate_cross_reference_score(
                    verification_results
                ),
                "recommendations": self._generate_verification_recommendations(
                    verification_results
                ),
            }
        except Exception as e:
            logger.error(f"Error in cross-reference verification: {e}")
            return {
                "error": str(e),
                "claims_verified": 0,
                "sources_analyzed": 0,
                "cross_reference_score": 0,
                "recommendations": ["Error during verification"],
            }

    async def _verify_single_claim(
        self, claim: str, sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Verify a single claim across sources."""
        supporting_sources = []
        contradicting_sources = []
        neutral_sources = []

        for source in sources:
            content = source.get("content", "")
            url = source.get("url", "")
            credibility = source.get("credibility_score", 0.5)

            # Analyze claim support in this source
            support_level = await self._analyze_claim_support(claim, content)

            source_analysis = {
                "url": url,
                "credibility": credibility,
                "support_level": support_level["level"],
                "confidence": support_level["confidence"],
                "evidence_text": support_level["evidence_text"],
                "context": support_level["context"],
            }

            if support_level["level"] == "supporting":
                supporting_sources.append(source_analysis)
            elif support_level["level"] == "contradicting":
                contradicting_sources.append(source_analysis)
            else:
                neutral_sources.append(source_analysis)

        # Calculate verification strength
        verification_strength = self._calculate_verification_strength(
            supporting_sources, contradicting_sources, neutral_sources
        )

        return {
            "claim": claim,
            "verification_strength": verification_strength,
            "supporting_sources": supporting_sources,
            "contradicting_sources": contradicting_sources,
            "neutral_sources": neutral_sources,
            "total_sources": len(sources),
            "consensus_level": self._determine_consensus_level(
                supporting_sources, contradicting_sources
            ),
        }

    async def _analyze_claim_support(self, claim: str, content: str) -> dict[str, Any]:
        """Analyze how well content supports a claim."""
        if not content or not claim:
            return {
                "level": "neutral",
                "confidence": 0.1,
                "evidence_text": "",
                "context": "Insufficient content",
            }

        # Simple keyword-based analysis (in practice would use more sophisticated NLP)
        claim_words = set(claim.lower().split())

        # Find relevant sentences
        sentences = content.split(". ")
        relevant_sentences = []

        for sentence in sentences:
            sentence_words = set(sentence.lower().split())
            overlap = len(claim_words & sentence_words)
            if overlap >= 2:  # At least 2 words overlap
                relevant_sentences.append(
                    {
                        "text": sentence,
                        "overlap": overlap,
                        "relevance": overlap / len(claim_words),
                    }
                )

        if not relevant_sentences:
            return {
                "level": "neutral",
                "confidence": 0.2,
                "evidence_text": "",
                "context": "No relevant content found",
            }

        # Analyze sentiment and support
        best_sentence = max(relevant_sentences, key=lambda x: x["relevance"])  # type: ignore
        evidence_text = str(best_sentence["text"])

        # Simple support detection
        positive_indicators = [
            "confirm",
            "shows",
            "proves",
            "demonstrates",
            "evidence",
            "supports",
        ]
        negative_indicators = [
            "disproves",
            "contradicts",
            "denies",
            "refutes",
            "opposes",
        ]

        evidence_lower = evidence_text.lower()
        positive_count = sum(
            1 for indicator in positive_indicators if indicator in evidence_lower
        )
        negative_count = sum(
            1 for indicator in negative_indicators if indicator in evidence_lower
        )

        if positive_count > negative_count:
            level = "supporting"
            confidence = min(0.9, 0.5 + (best_sentence["relevance"] * 0.4))  # type: ignore
        elif negative_count > positive_count:
            level = "contradicting"
            confidence = min(0.9, 0.5 + (best_sentence["relevance"] * 0.4))  # type: ignore
        else:
            level = "neutral"
            confidence = best_sentence["relevance"]  # type: ignore

        return {
            "level": level,
            "confidence": confidence,
            "evidence_text": evidence_text,
            "context": f"Found {len(relevant_sentences)} relevant sentences",
        }

    def _calculate_verification_strength(
        self,
        supporting: list[dict[str, Any]],
        contradicting: list[dict[str, Any]],
        _neutral: list[dict[str, Any]],
    ) -> float:
        """Calculate overall verification strength for a claim."""
        if not supporting and not contradicting:
            return 0.1  # No evidence

        # Weight by credibility
        support_score = sum(
            float(s["credibility"]) * float(s["confidence"]) for s in supporting
        )
        contradict_score = sum(
            float(c["credibility"]) * float(c["confidence"]) for c in contradicting
        )

        total_score = support_score + contradict_score
        if total_score == 0:
            return 0.1

        # Strength is based on support ratio and total evidence
        support_ratio = support_score / total_score
        evidence_factor = min(1.0, (len(supporting) + len(contradicting)) / 3)

        return support_ratio * evidence_factor

    def _determine_consensus_level(
        self, supporting: list[dict[str, Any]], contradicting: list[dict[str, Any]]
    ) -> str:
        """Determine consensus level for a claim."""
        total_sources = len(supporting) + len(contradicting)

        if total_sources == 0:
            return "no_evidence"

        support_ratio = len(supporting) / total_sources

        if support_ratio >= 0.8:
            return "strong_consensus"
        if support_ratio >= 0.6:
            return "moderate_consensus"
        if support_ratio >= 0.4:
            return "mixed_evidence"
        if support_ratio >= 0.2:
            return "weak_opposition"
        return "strong_opposition"

    def _analyze_verification_strength(
        self, verification_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze overall verification strength across all claims."""
        if not verification_results:
            return {
                "average_strength": 0,
                "strong_claims": 0,
                "weak_claims": 0,
                "disputed_claims": 0,
            }

        strengths = [result["verification_strength"] for result in verification_results]
        avg_strength = sum(strengths) / len(strengths)

        strong_claims = sum(1 for s in strengths if s > 0.7)
        weak_claims = sum(1 for s in strengths if s < 0.3)
        disputed_claims = sum(
            1
            for result in verification_results
            if len(result["supporting_sources"]) > 0
            and len(result["contradicting_sources"]) > 0
        )

        return {
            "average_strength": avg_strength,
            "strong_claims": strong_claims,
            "weak_claims": weak_claims,
            "disputed_claims": disputed_claims,
            "total_claims": len(verification_results),
            "verification_quality": self._assess_verification_quality(
                avg_strength, strong_claims, weak_claims
            ),
        }

    def _assess_verification_quality(
        self, avg_strength: float, strong_claims: int, weak_claims: int
    ) -> str:
        """Assess overall verification quality."""
        if avg_strength > 0.7 and weak_claims == 0:
            return "excellent"
        if avg_strength > 0.6 and strong_claims > weak_claims:
            return "good"
        if avg_strength > 0.4:
            return "moderate"
        return "poor"

    def _identify_citation_networks(
        self, sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Identify citation networks and source relationships."""
        # Extract domain information
        domains: dict[str, list[dict[str, Any]]] = {}
        for source in sources:
            url = source.get("url", "")
            if url:
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
                if domain not in domains:
                    domains[domain] = []
                domains[domain].append(source)

        # Identify potential citation chains (simplified analysis)
        citation_chains = []
        for domain, domain_sources in domains.items():
            if len(domain_sources) > 1:
                citation_chains.append(
                    {
                        "domain": domain,
                        "source_count": len(domain_sources),
                        "credibility_range": [
                            min(
                                s.get("credibility_score", 0.5) for s in domain_sources
                            ),
                            max(
                                s.get("credibility_score", 0.5) for s in domain_sources
                            ),
                        ],
                    }
                )

        # Check for source diversity
        unique_domains = len(domains)
        total_sources = len(sources)
        diversity_score = unique_domains / total_sources if total_sources > 0 else 0

        return {
            "unique_domains": unique_domains,
            "total_sources": total_sources,
            "diversity_score": diversity_score,
            "citation_chains": citation_chains,
            "domain_distribution": {
                domain: len(sources) for domain, sources in domains.items()
            },
        }

    def _calculate_cross_reference_score(
        self, verification_results: list[dict[str, Any]]
    ) -> float:
        """Calculate overall cross-reference verification score."""
        if not verification_results:
            return 0.0

        # Factors in cross-reference score
        avg_verification = sum(
            float(r["verification_strength"]) for r in verification_results
        ) / len(verification_results)

        # Consensus factor
        consensus_scores = {
            "strong_consensus": 1.0,
            "moderate_consensus": 0.8,
            "mixed_evidence": 0.4,
            "weak_opposition": 0.2,
            "strong_opposition": 0.1,
            "no_evidence": 0.0,
        }

        avg_consensus = sum(
            consensus_scores.get(r["consensus_level"], 0.0)
            for r in verification_results
        ) / len(verification_results)

        # Evidence coverage factor
        claims_with_evidence = sum(
            1
            for r in verification_results
            if len(r["supporting_sources"]) + len(r["contradicting_sources"]) > 0
        )
        coverage_factor = claims_with_evidence / len(verification_results)

        return avg_verification * 0.4 + avg_consensus * 0.4 + coverage_factor * 0.2

    def _generate_verification_recommendations(
        self, verification_results: list[dict[str, Any]]
    ) -> list[str]:
        """Generate recommendations based on verification results."""
        recommendations = []

        weak_claims = [
            r for r in verification_results if r["verification_strength"] < 0.3
        ]
        disputed_claims = [
            r
            for r in verification_results
            if len(r["supporting_sources"]) > 0 and len(r["contradicting_sources"]) > 0
        ]

        if weak_claims:
            recommendations.append(
                f"{len(weak_claims)} claims have weak verification - seek additional sources"
            )

        if disputed_claims:
            recommendations.append(
                f"{len(disputed_claims)} claims show conflicting evidence - present multiple perspectives"
            )

        # Check for source coverage
        unverified_claims = [
            r
            for r in verification_results
            if len(r["supporting_sources"]) + len(r["contradicting_sources"]) == 0
        ]

        if unverified_claims:
            recommendations.append(
                f"{len(unverified_claims)} claims lack source verification - find supporting evidence"
            )

        # Quality recommendations
        strong_claims = [
            r for r in verification_results if r["verification_strength"] > 0.7
        ]
        if len(strong_claims) == len(verification_results):
            recommendations.append(
                "Excellent verification quality - all claims well-supported"
            )
        elif len(strong_claims) > len(verification_results) / 2:
            recommendations.append(
                "Good verification quality - most claims well-supported"
            )
        else:
            recommendations.append(
                "Mixed verification quality - strengthen evidence base"
            )

        recommendations.append("Always cite sources when presenting verified claims")
        recommendations.append("Acknowledge uncertainty for weakly verified claims")

        return recommendations

    # Advanced credibility evaluation functionality (migrated from legacy Credibility Evaluator)
    async def perform_comprehensive_credibility_assessment(
        self, sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Perform comprehensive credibility assessment across multiple sources.

        Args:
            sources (List[Dict[str, Any]]): List of source information

        Returns:
            Dict[str, Any]: Comprehensive credibility analysis
        """
        try:
            credibility_results = []
            overall_scores = []

            for source in sources:
                url = source.get("url", "")
                source_type = source.get("type", "web")

                if source_type == "web":
                    result = await self.assess_webpage_credibility(url)
                    credibility_results.append(
                        {
                            "url": url,
                            "type": "web",
                            "assessment": result,
                            "score": result["credibility_score"],
                        }
                    )
                    overall_scores.append(result["credibility_score"])
                elif source_type == "reddit":
                    reddit_result = await self.analyze_reddit_credibility(
                        source.get("submission", {}), source.get("comments", [])
                    )
                    credibility_results.append(
                        {
                            "url": url,
                            "type": "reddit",
                            "assessment": reddit_result,
                            "score": reddit_result.get("credibility_score", 0.5),
                        }
                    )
                    overall_scores.append(reddit_result.get("credibility_score", 0.5))

            # Calculate overall credibility metrics
            avg_score = (
                sum(overall_scores) / len(overall_scores) if overall_scores else 0
            )
            high_credibility_count = sum(1 for score in overall_scores if score > 0.7)
            low_credibility_count = sum(1 for score in overall_scores if score < 0.4)

            return {
                "sources_analyzed": len(sources),
                "average_credibility_score": avg_score,
                "high_credibility_sources": high_credibility_count,
                "low_credibility_sources": low_credibility_count,
                "credibility_distribution": {
                    "high": high_credibility_count,
                    "medium": len(overall_scores)
                    - high_credibility_count
                    - low_credibility_count,
                    "low": low_credibility_count,
                },
                "detailed_results": credibility_results,
                "recommendations": self._generate_credibility_recommendations(
                    avg_score, high_credibility_count, low_credibility_count
                ),
            }
        except Exception as e:
            logger.error(f"Error in comprehensive credibility assessment: {e}")
            return {
                "error": str(e),
                "sources_analyzed": 0,
                "average_credibility_score": 0,
                "recommendations": ["Error occurred during analysis"],
            }

    def _generate_credibility_recommendations(
        self, avg_score: float, high_count: int, low_count: int
    ) -> list[str]:
        """Generate recommendations based on credibility analysis."""
        recommendations = []

        if avg_score < 0.5:
            recommendations.append(
                "Overall source credibility is low. Consider finding more authoritative sources."
            )
        elif avg_score > 0.8:
            recommendations.append(
                "Excellent source credibility. This research has a strong foundation."
            )
        else:
            recommendations.append(
                "Mixed source credibility. Consider prioritizing higher-quality sources."
            )

        if low_count > high_count:
            recommendations.append(
                "Too many low-credibility sources. Seek academic or expert sources."
            )

        if high_count == 0:
            recommendations.append(
                "No high-credibility sources found. Add authoritative references."
            )

        recommendations.append(
            "Always cross-reference information across multiple independent sources."
        )

        return recommendations

    async def evaluate_source_consistency(
        self, sources: list[dict[str, Any]], topic: str
    ) -> dict[str, Any]:
        """
        Evaluate consistency of information across sources.

        Args:
            sources (List[Dict[str, Any]]): Sources to analyze for consistency
            topic (str): The research topic for context

        Returns:
            Dict[str, Any]: Consistency analysis results
        """
        try:
            # Extract key claims from each source
            source_claims = []
            for source in sources:
                content = source.get("content", "")
                claims = await self._extract_key_claims(content, topic)
                source_claims.append(
                    {
                        "url": source.get("url", ""),
                        "claims": claims,
                        "credibility": source.get("credibility_score", 0.5),
                    }
                )

            # Analyze consistency between sources
            consistency_score = self._calculate_consistency_score(source_claims)
            contradictions = self._identify_contradictions(source_claims)
            consensus_points = self._identify_consensus(source_claims)

            return {
                "topic": topic,
                "sources_analyzed": len(sources),
                "consistency_score": consistency_score,
                "consensus_points": consensus_points,
                "contradictions": contradictions,
                "reliability_assessment": self._assess_overall_reliability(
                    consistency_score, source_claims
                ),
            }
        except Exception as e:
            logger.error(f"Error evaluating source consistency: {e}")
            return {
                "error": str(e),
                "consistency_score": 0,
                "consensus_points": [],
                "contradictions": [],
            }

    async def _extract_key_claims(self, content: str, topic: str) -> list[str]:
        """Extract key claims from source content."""
        # This would use NLP/LLM to extract key factual claims
        # For now, return a simple analysis
        if not content or len(content) < 50:
            return []

        # Simple extraction - in practice this would use more sophisticated NLP
        sentences = content.split(". ")
        relevant_sentences = [
            s
            for s in sentences
            if any(word.lower() in s.lower() for word in topic.split())
            and len(s.strip()) > 20
        ]

        return relevant_sentences[:5]  # Return top 5 relevant claims

    def _calculate_consistency_score(
        self, source_claims: list[dict[str, Any]]
    ) -> float:
        """Calculate consistency score across sources."""
        if len(source_claims) < 2:
            return 1.0

        # Simple consistency calculation based on claim overlap
        all_claims = []
        for source in source_claims:
            all_claims.extend(source["claims"])

        if not all_claims:
            return 0.5

        # Calculate overlap (simplified approach)
        unique_claims = len({claim.lower() for claim in all_claims})
        total_claims = len(all_claims)

        # Higher overlap indicates higher consistency
        overlap_ratio = 1 - (unique_claims / total_claims) if total_claims > 0 else 0
        return max(0.2, min(1.0, overlap_ratio + 0.3))

    def _identify_contradictions(
        self, source_claims: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Identify potential contradictions between sources."""
        # Simplified contradiction detection
        contradictions = []

        for i, source1 in enumerate(source_claims):
            for _j, source2 in enumerate(source_claims[i + 1 :], i + 1):
                # Look for contradictory patterns
                for claim1 in source1["claims"]:
                    for claim2 in source2["claims"]:
                        if self._are_contradictory(claim1, claim2):
                            contradictions.append(
                                {
                                    "source1": source1["url"],
                                    "source2": source2["url"],
                                    "claim1": claim1,
                                    "claim2": claim2,
                                    "confidence": 0.7,  # Simplified confidence
                                }
                            )

        return contradictions

    def _are_contradictory(self, claim1: str, claim2: str) -> bool:
        """Simple contradiction detection."""
        # Look for obvious contradictions (simplified)
        negative_words = ["not", "no", "never", "false", "incorrect", "wrong"]

        claim1_lower = claim1.lower()
        claim2_lower = claim2.lower()

        # Check for opposite sentiment
        claim1_negative = any(word in claim1_lower for word in negative_words)
        claim2_negative = any(word in claim2_lower for word in negative_words)

        return (
            claim1_negative != claim2_negative
            and len(set(claim1.split()) & set(claim2.split())) > 2
        )

    def _identify_consensus(
        self, source_claims: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Identify consensus points across sources."""
        consensus_points = []

        # Find claims that appear in multiple sources
        claim_counts: dict[str, list[str]] = {}
        for source in source_claims:
            for claim in source["claims"]:
                claim_key = claim.lower().strip()
                if claim_key not in claim_counts:
                    claim_counts[claim_key] = []
                claim_counts[claim_key].append(source["url"])

        # Identify consensus (claims appearing in multiple sources)
        for claim, sources in claim_counts.items():
            if len(sources) > 1:
                consensus_points.append(
                    {
                        "claim": claim,
                        "supporting_sources": sources,
                        "confidence": min(1.0, len(sources) / len(source_claims)),
                    }
                )

        return consensus_points

    def _assess_overall_reliability(
        self, consistency_score: float, source_claims: list[dict[str, Any]]
    ) -> str:
        """Assess overall reliability of the source set."""
        avg_credibility = sum(s["credibility"] for s in source_claims) / len(
            source_claims
        )

        if consistency_score > 0.8 and avg_credibility > 0.7:
            return "High reliability - consistent high-quality sources"
        if consistency_score > 0.6 and avg_credibility > 0.5:
            return "Medium reliability - generally consistent sources"
        if consistency_score < 0.4:
            return "Low reliability - significant inconsistencies detected"
        return "Mixed reliability - requires careful verification"

    async def analyze_reddit_credibility(
        self, submission: dict[str, Any], comments: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """
        Analyze Reddit submission credibility with enhanced metrics.

        Args:
            submission (Dict[str, Any]): Reddit submission data
            comments (List[Dict[str, Any]]): Optional comments data

        Returns:
            Dict[str, Any]: Enhanced credibility analysis
        """
        try:
            if comments is None:
                comments = []

            # Basic metrics
            score = submission.get("score", 0)
            num_comments = submission.get("num_comments", 0)
            created_utc = submission.get("created_utc", 0)
            upvote_ratio = submission.get("upvote_ratio", 0.5)

            # Calculate age in hours
            from datetime import datetime

            current_time = datetime.now().timestamp()
            age_hours = (current_time - created_utc) / 3600 if created_utc else 24

            # Scoring factors
            score_factor = min(1.0, max(0.1, (score + 1) / 100))
            comment_factor = min(0.3, num_comments / 100)
            recency_factor = max(0.1, min(0.3, 72 / max(age_hours, 1)))
            ratio_factor = max(0.1, upvote_ratio)

            # Enhanced factors
            author = submission.get("author", "")
            subreddit = submission.get("subreddit", "")
            title = submission.get("title", "")

            # Author credibility (simplified)
            author_factor = 0.2 if author and author != "[deleted]" else 0.1

            # Subreddit credibility (basic heuristics)
            subreddit_factor = self._assess_subreddit_credibility(subreddit)

            # Title quality (check for clickbait patterns)
            title_factor = self._assess_title_quality(title)

            # Calculate overall credibility score
            credibility_score = (
                score_factor * 0.3
                + comment_factor * 0.15
                + recency_factor * 0.1
                + ratio_factor * 0.15
                + author_factor * 0.1
                + subreddit_factor * 0.15
                + title_factor * 0.05
            )

            # Determine credibility level
            if credibility_score > 0.8:
                credibility_level = "High"
            elif credibility_score > 0.5:
                credibility_level = "Medium"
            else:
                credibility_level = "Low"

            return {
                "credibility_score": credibility_score,
                "credibility_level": credibility_level,
                "factors": {
                    "score": score,
                    "num_comments": num_comments,
                    "upvote_ratio": upvote_ratio,
                    "age_hours": age_hours,
                    "author": author,
                    "subreddit": subreddit,
                },
                "analysis": {
                    "score_factor": score_factor,
                    "engagement_factor": comment_factor,
                    "recency_factor": recency_factor,
                    "ratio_factor": ratio_factor,
                    "author_factor": author_factor,
                    "subreddit_factor": subreddit_factor,
                    "title_factor": title_factor,
                },
                "recommendations": self._generate_reddit_recommendations(
                    credibility_score, submission
                ),
            }
        except Exception as e:
            logger.error(f"Error analyzing Reddit credibility: {e}")
            return {
                "credibility_score": 0.3,
                "credibility_level": "Low",
                "error": str(e),
                "recommendations": ["Error during analysis - use with caution"],
            }

    def _assess_subreddit_credibility(self, subreddit: str) -> float:
        """Assess credibility based on subreddit characteristics."""
        if not subreddit:
            return 0.2

        # High-credibility subreddits
        high_credibility = {
            "science",
            "askscience",
            "askhistorians",
            "academia",
            "scholar",
            "truereddit",
            "neutralpolitics",
            "neutralnews",
            "explainlikeimfive",
            "dataisbeautiful",
            "medicine",
            "economics",
        }

        # Medium-credibility subreddits
        medium_credibility = {
            "news",
            "worldnews",
            "politics",
            "technology",
            "history",
            "todayilearned",
            "askreddit",
            "iama",
        }

        # Low-credibility patterns
        low_credibility_patterns = [
            "meme",
            "funny",
            "joke",
            "circle",
            "jerk",
            "conspiracy",
            "unpopular",
            "shower",
            "thoughts",
        ]

        subreddit_lower = subreddit.lower()

        if subreddit_lower in high_credibility:
            return 0.8
        if subreddit_lower in medium_credibility:
            return 0.5
        if any(pattern in subreddit_lower for pattern in low_credibility_patterns):
            return 0.2
        return 0.4  # Default for unknown subreddits

    def _assess_title_quality(self, title: str) -> float:
        """Assess title quality and detect clickbait patterns."""
        if not title:
            return 0.3

        # Clickbait indicators (negative)
        clickbait_patterns = [
            "you won't believe",
            "shocking",
            "this will",
            "amazing",
            "incredible",
            "unbelievable",
            "mind-blowing",
            "must see",
            "gone wrong",
            "gone right",
            "doctors hate",
            "this trick",
        ]

        # Quality indicators (positive)
        quality_patterns = [
            "study shows",
            "research finds",
            "according to",
            "analysis",
            "report",
            "evidence suggests",
            "data indicates",
        ]

        title_lower = title.lower()

        clickbait_count = sum(
            1 for pattern in clickbait_patterns if pattern in title_lower
        )
        quality_count = sum(1 for pattern in quality_patterns if pattern in title_lower)

        # Excessive caps or punctuation
        caps_ratio = sum(1 for c in title if c.isupper()) / len(title) if title else 0
        exclamation_count = title.count("!")

        score = 0.5  # Base score

        # Adjust based on patterns
        score -= clickbait_count * 0.2
        score += quality_count * 0.2
        score -= min(0.3, caps_ratio * 0.5)  # Penalize excessive caps
        score -= min(0.2, exclamation_count * 0.1)  # Penalize excessive exclamations

        return max(0.1, min(1.0, score))

    def _generate_reddit_recommendations(
        self, credibility_score: float, submission: dict[str, Any]
    ) -> list[str]:
        """Generate recommendations for Reddit source usage."""
        recommendations = []

        if credibility_score < 0.4:
            recommendations.append(
                "Low credibility - use only as supplementary evidence"
            )
            recommendations.append("Verify information through authoritative sources")
        elif credibility_score < 0.7:
            recommendations.append(
                "Medium credibility - cross-reference with other sources"
            )
        else:
            recommendations.append("High credibility for social media content")

        # Specific recommendations based on metrics
        score = submission.get("score", 0)
        num_comments = submission.get("num_comments", 0)

        if score < 10:
            recommendations.append(
                "Low engagement - may not represent community consensus"
            )

        if num_comments < 5:
            recommendations.append(
                "Limited discussion - consider finding more debated topics"
            )

        upvote_ratio = submission.get("upvote_ratio", 0.5)
        if upvote_ratio < 0.6:
            recommendations.append("Controversial topic - expect diverse opinions")

        recommendations.append("Always consider Reddit as opinion/discussion, not fact")

        return recommendations


# Module exports
__all__ = [
    "AnalysisTools",
]
