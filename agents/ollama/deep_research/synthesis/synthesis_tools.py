"""
Synthesis tools and functionality.

This module provides tools for synthesizing information and generating research reports.
"""

import json
import logging
from typing import Any

from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker
from agents.ollama.deep_research.shared.types import ResearchSource

logger = logging.getLogger(__name__)


class SynthesisTools:
    """
    Synthesis tools with agent-specific source tracking.

    This class provides synthesis capabilities for the Synthesis Agent,
    including multi-source synthesis and knowledge graph building.
    """

    def __init__(self, source_tracker: AgentSourceTracker):
        """
        Initialize synthesis tools with an agent-specific source tracker.

        Args:
            source_tracker (AgentSourceTracker): The agent-specific source tracker to use
        """
        self.source_tracker = source_tracker

    # Knowledge graph building functionality (migrated from legacy Knowledge Graph Builder)
    async def build_knowledge_graph(
        self, research_findings: list[dict[str, Any]], topic: str
    ) -> dict[str, Any]:
        """
        Build a knowledge graph from research findings.

        Args:
            research_findings (List[Dict[str, Any]]): Research findings from all agents
            topic (str): Main research topic

        Returns:
            Dict[str, Any]: Knowledge graph representation
        """
        try:
            # Extract entities and relationships
            entities = await self._extract_entities(research_findings, topic)
            relationships = await self._extract_relationships(
                research_findings, entities
            )

            # Build graph structure
            knowledge_graph = self._build_graph_structure(entities, relationships)

            # Analyze graph properties
            graph_analysis = self._analyze_graph_properties(knowledge_graph)

            # Identify key insights
            key_insights = self._identify_key_insights(knowledge_graph, graph_analysis)

            return {
                "topic": topic,
                "knowledge_graph": knowledge_graph,
                "graph_statistics": graph_analysis,
                "key_insights": key_insights,
                "entity_count": len(entities),
                "relationship_count": len(relationships),
                "graph_visualization": self._generate_graph_visualization_data(
                    knowledge_graph
                ),
            }

        except Exception as e:
            logger.error(f"Error building knowledge graph: {e}")
            return {
                "error": str(e),
                "knowledge_graph": {"nodes": [], "edges": []},
                "graph_statistics": {},
                "key_insights": [],
            }

    async def identify_knowledge_gaps(
        self, knowledge_graph: dict[str, Any], query: str
    ) -> dict[str, Any]:
        """
        Identify knowledge gaps in the research.

        Args:
            knowledge_graph (Dict[str, Any]): Knowledge graph representation
            query (str): Original research query

        Returns:
            Dict[str, Any]: Knowledge gaps analysis
        """
        try:
            nodes = knowledge_graph.get("nodes", [])
            edges = knowledge_graph.get("edges", [])

            # Identify isolated nodes (potential gaps)
            isolated_nodes = self._identify_isolated_nodes(nodes, edges)

            # Identify weak connections
            weak_connections = self._identify_weak_connections(edges)

            # Find missing relationships based on query context
            missing_relationships = self._identify_missing_relationships(
                nodes, edges, query
            )

            # Generate recommendations
            recommendations = self._generate_gap_recommendations(
                isolated_nodes, weak_connections, missing_relationships
            )

            # Calculate overall gap score
            gap_score = self._calculate_gap_score(
                isolated_nodes, weak_connections, missing_relationships
            )

            return {
                "gap_score": gap_score,
                "isolated_nodes": isolated_nodes,
                "weak_connections": weak_connections,
                "missing_relationships": missing_relationships,
                "recommendations": recommendations,
                "query": query,
            }

        except Exception as e:
            logger.error(f"Error identifying knowledge gaps: {e}")
            return {
                "error": str(e),
                "gap_score": 0.0,
                "isolated_nodes": [],
                "weak_connections": [],
                "missing_relationships": [],
                "recommendations": [],
            }

    async def _extract_entities(
        self, research_findings: list[dict[str, Any]], topic: str
    ) -> list[dict[str, Any]]:
        """Extract key entities from research findings."""
        entities = {}

        for finding in research_findings:
            content = finding.get("content", "")
            source_url = finding.get("url", "")

            # Extract potential entities (simplified NLP approach)
            entity_candidates = self._identify_entity_candidates(content, topic)

            for candidate in entity_candidates:
                entity_key = candidate["text"].lower()
                if entity_key not in entities:
                    entities[entity_key] = {
                        "text": candidate["text"],
                        "type": candidate["type"],
                        "mentions": [],
                        "credibility": 0,
                        "frequency": 0,
                    }

                entities[entity_key]["mentions"].append(
                    {
                        "source": source_url,
                        "context": candidate["context"],
                        "credibility": finding.get("credibility_score", 0.5),
                    }
                )
                entities[entity_key]["frequency"] += 1

        # Calculate entity credibility and importance
        for entity in entities.values():
            entity["credibility"] = sum(
                m["credibility"] for m in entity["mentions"]
            ) / len(entity["mentions"])
            entity["importance"] = entity["frequency"] * entity["credibility"]

        # Filter and rank entities
        significant_entities = [
            entity
            for entity in entities.values()
            if entity["frequency"] >= 2 or entity["credibility"] > 0.7
        ]

        return sorted(significant_entities, key=lambda x: x["importance"], reverse=True)

    def _identify_entity_candidates(
        self, content: str, _topic: str
    ) -> list[dict[str, Any]]:
        """Identify potential entities in content."""
        if not content:
            return []

        import re

        candidates = []

        # Simple patterns for entity identification
        # Proper nouns (capitalized words/phrases)
        proper_noun_pattern = r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"
        proper_nouns = re.findall(proper_noun_pattern, content)

        for noun in proper_nouns:
            if len(noun) > 2 and noun.lower() not in ["the", "this", "that", "a", "an"]:
                # Determine entity type (simplified)
                entity_type = self._classify_entity_type(noun)
                context = self._extract_entity_context(content, noun)

                candidates.append(
                    {"text": noun, "type": entity_type, "context": context}
                )

        # Numbers and dates
        number_pattern = r"\b\d{4}\b|\b\d+\.\d+\b|\b\d+%\b"
        numbers = re.findall(number_pattern, content)

        for number in numbers:
            context = self._extract_entity_context(content, number)
            candidates.append({"text": number, "type": "metric", "context": context})

        return candidates

    def _classify_entity_type(self, entity_text: str) -> str:
        """Classify entity type based on text patterns."""
        entity_lower = entity_text.lower()

        # Simple classification rules
        if any(word in entity_lower for word in ["university", "college", "institute"]):
            return "organization"
        if any(word in entity_lower for word in ["dr", "prof", "mr", "ms"]):
            return "person"
        if entity_text.isupper() and len(entity_text) <= 5:
            return "acronym"
        if any(char.isdigit() for char in entity_text):
            return "metric"
        if any(
            word in entity_lower for word in ["company", "corporation", "inc", "ltd"]
        ):
            return "organization"
        return "concept"

    def _extract_entity_context(self, content: str, entity: str) -> str:
        """Extract context around an entity mention."""
        sentences = content.split(". ")
        for sentence in sentences:
            if entity in sentence:
                return sentence[:200]  # Limit context length
        return ""

    async def _extract_relationships(
        self, research_findings: list[dict[str, Any]], entities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Extract relationships between entities."""
        relationships = []

        # Create entity lookup for efficiency
        entity_texts = [entity["text"] for entity in entities]

        for finding in research_findings:
            content = finding.get("content", "")

            # Look for relationships between pairs of entities
            for i, entity1 in enumerate(entity_texts):
                for entity2 in entity_texts[i + 1 :]:
                    relationship = self._analyze_entity_relationship(
                        content, entity1, entity2
                    )
                    if relationship:
                        relationship["source"] = finding.get("url", "")
                        relationship["credibility"] = finding.get(
                            "credibility_score", 0.5
                        )
                        relationships.append(relationship)

        # Consolidate duplicate relationships
        return self._consolidate_relationships(relationships)

    def _analyze_entity_relationship(
        self, content: str, entity1: str, entity2: str
    ) -> dict[str, Any] | None:
        """Analyze the relationship between two entities in content."""
        # Check if both entities appear in the same sentence or nearby sentences
        sentences = content.split(". ")

        for sentence in sentences:
            if entity1 in sentence and entity2 in sentence:
                # Determine relationship type based on context
                relationship_type = "related"
                if any(
                    word in sentence.lower()
                    for word in ["causes", "leads to", "results in"]
                ):
                    relationship_type = "causal"
                elif any(
                    word in sentence.lower()
                    for word in ["part of", "includes", "contains"]
                ):
                    relationship_type = "hierarchical"
                elif any(
                    word in sentence.lower()
                    for word in ["similar", "like", "compared to"]
                ):
                    relationship_type = "similarity"

                return {
                    "source_entity": entity1,
                    "target_entity": entity2,
                    "type": relationship_type,
                    "context": sentence[:200],
                    "strength": 1.0,  # Will be adjusted during consolidation
                }

        return None

    def _consolidate_relationships(
        self, relationships: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Consolidate duplicate relationships."""
        consolidated = {}

        for rel in relationships:
            # Create a key for grouping similar relationships
            key = f"{rel['source_entity']}-{rel['target_entity']}-{rel['type']}"
            reverse_key = f"{rel['target_entity']}-{rel['source_entity']}-{rel['type']}"

            # Use the lexicographically smaller key for consistency
            final_key = min(key, reverse_key)

            if final_key not in consolidated:
                consolidated[final_key] = rel.copy()
                consolidated[final_key]["evidence_count"] = 1
                consolidated[final_key]["sources"] = [rel.get("source", "")]
            else:
                # Increase strength and add source
                consolidated[final_key]["strength"] += rel.get("strength", 1.0)
                consolidated[final_key]["evidence_count"] += 1
                if rel.get("source"):
                    consolidated[final_key]["sources"].append(rel["source"])

        # Normalize strength by evidence count
        for rel in consolidated.values():
            rel["strength"] = rel["strength"] / rel["evidence_count"]

        return list(consolidated.values())

    def _build_graph_structure(
        self, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build graph structure from entities and relationships."""
        # Create nodes
        nodes = []
        for entity in entities:
            nodes.append(
                {
                    "id": entity["text"],
                    "label": entity["text"],
                    "type": entity["type"],
                    "importance": entity["importance"],
                    "credibility": entity["credibility"],
                    "frequency": entity["frequency"],
                }
            )

        # Create edges
        edges = []
        for relationship in relationships:
            edges.append(
                {
                    "source": relationship["source_entity"],
                    "target": relationship["target_entity"],
                    "type": relationship["type"],
                    "strength": relationship["strength"],
                    "evidence_count": relationship["evidence_count"],
                }
            )

        return {"nodes": nodes, "edges": edges}

    def _analyze_graph_properties(
        self, knowledge_graph: dict[str, Any]
    ) -> dict[str, Any]:
        """Analyze properties of the knowledge graph."""
        nodes = knowledge_graph["nodes"]
        edges = knowledge_graph["edges"]

        # Basic metrics
        node_count = len(nodes)
        edge_count = len(edges)

        # Node degree distribution
        node_degrees: dict[str, int] = {}
        for node in nodes:
            node_degrees[node["id"]] = 0

        for edge in edges:
            node_degrees[edge["source"]] = node_degrees.get(edge["source"], 0) + 1
            node_degrees[edge["target"]] = node_degrees.get(edge["target"], 0) + 1

        # Find most connected nodes
        most_connected = sorted(node_degrees.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]

        # Relationship type distribution
        relationship_types: dict[str, int] = {}
        for edge in edges:
            rel_type = edge["type"]
            relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_degree": (
                sum(node_degrees.values()) / len(node_degrees) if node_degrees else 0
            ),
            "max_degree": max(node_degrees.values()) if node_degrees else 0,
            "most_connected_nodes": most_connected,
            "relationship_types": relationship_types,
            "density": (
                (2 * edge_count) / (node_count * (node_count - 1))
                if node_count > 1
                else 0
            ),
        }

    def _identify_key_insights(
        self, knowledge_graph: dict[str, Any], graph_analysis: dict[str, Any]
    ) -> list[str]:
        """Identify key insights from the knowledge graph."""
        insights = []
        nodes = knowledge_graph["nodes"]
        # edges = knowledge_graph["edges"]  # Not currently used

        # Most important entities
        top_entities = sorted(nodes, key=lambda x: x["importance"], reverse=True)[:3]
        if top_entities:
            entity_list = ", ".join([entity["label"] for entity in top_entities])
            insights.append(f"Key entities in this research: {entity_list}")

        # Most connected entities
        most_connected = graph_analysis.get("most_connected_nodes", [])
        if most_connected:
            central_entity = most_connected[0][0]
            degree = most_connected[0][1]
            insights.append(
                f"'{central_entity}' is a central concept with {degree} connections"
            )

        # Relationship patterns
        rel_types = graph_analysis.get("relationship_types", {})
        if rel_types:
            dominant_type = max(rel_types.items(), key=lambda x: x[1])
            insights.append(
                f"Primary relationship type: {dominant_type[0]} ({dominant_type[1]} instances)"
            )

        # Entity type distribution
        entity_types: dict[str, int] = {}
        for node in nodes:
            node_type = node["type"]
            entity_types[node_type] = entity_types.get(node_type, 0) + 1

        if entity_types:
            dominant_entity_type = max(entity_types.items(), key=lambda x: x[1])
            insights.append(
                f"Primary entity type: {dominant_entity_type[0]} ({dominant_entity_type[1]} entities)"
            )

        return insights

    def _generate_graph_visualization_data(
        self, knowledge_graph: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate data for graph visualization."""
        nodes = knowledge_graph.get("nodes", [])
        edges = knowledge_graph.get("edges", [])

        # Prepare visualization data
        viz_nodes = []
        for node in nodes:
            viz_nodes.append(
                {
                    "id": node["id"],
                    "label": node["label"],
                    "size": min(max(node["importance"] * 10, 5), 20),  # Scale node size
                    "color": self._get_node_color(node["type"]),
                    "type": node["type"],
                }
            )

        viz_edges = []
        for edge in edges:
            viz_edges.append(
                {
                    "source": edge["source"],
                    "target": edge["target"],
                    "weight": edge["strength"],
                    "type": edge["type"],
                    "color": self._get_edge_color(edge["type"]),
                }
            )

        return {"nodes": viz_nodes, "edges": viz_edges}

    def _get_node_color(self, node_type: str) -> str:
        """Get color for node type."""
        color_map = {
            "person": "#FF6B6B",
            "organization": "#4ECDC4",
            "concept": "#45B7D1",
            "metric": "#96CEB4",
            "acronym": "#FFEAA7",
        }
        return color_map.get(node_type, "#74B9FF")

    def _get_edge_color(self, edge_type: str) -> str:
        """Get color for edge type."""
        color_map = {
            "causal": "#E17055",
            "hierarchical": "#6C5CE7",
            "similarity": "#A29BFE",
            "related": "#74B9FF",
        }
        return color_map.get(edge_type, "#DDD")

    def _identify_isolated_nodes(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Identify nodes with few or no connections."""
        # Count connections for each node
        node_connections: dict[str, int] = {}
        for node in nodes:
            node_connections[node["id"]] = 0

        for edge in edges:
            node_connections[edge["source"]] = (
                node_connections.get(edge["source"], 0) + 1
            )
            node_connections[edge["target"]] = (
                node_connections.get(edge["target"], 0) + 1
            )

        # Find isolated or weakly connected nodes
        isolated = []
        for node in nodes:
            connections = node_connections.get(node["id"], 0)
            if connections <= 1:  # 0 or 1 connections
                isolated.append(
                    {
                        "node": node,
                        "connections": connections,
                        "importance": node.get("importance", 0),
                    }
                )

        return sorted(isolated, key=lambda x: x["importance"], reverse=True)

    def _identify_weak_connections(
        self, edges: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Identify weak connections that might indicate gaps."""
        weak_connections = []

        for edge in edges:
            strength = edge.get("strength", 0)
            evidence_count = edge.get("evidence_count", 1)

            # Consider connections weak if they have low strength or little evidence
            if strength < 0.3 or evidence_count == 1:
                weak_connections.append(
                    {
                        "edge": edge,
                        "strength": strength,
                        "evidence_count": evidence_count,
                        "weakness_score": (1 - strength) + (1 / evidence_count),
                    }
                )

        return sorted(weak_connections, key=lambda x: x["weakness_score"], reverse=True)

    def _identify_missing_relationships(
        self, nodes: list[dict[str, Any]], _edges: list[dict[str, Any]], query: str
    ) -> list[dict[str, Any]]:
        """Identify potentially missing relationships based on query context."""
        missing = []

        # This is a simplified approach - in practice, this would use more sophisticated NLP
        query_words = query.lower().split()

        # Look for entities that should be connected based on query context
        for i, node1 in enumerate(nodes):
            for node2 in nodes[i + 1 :]:
                # Check if both entities appear in the query
                if (
                    node1["label"].lower() in query_words
                    and node2["label"].lower() in query_words
                ):
                    missing.append(
                        {
                            "source_entity": node1["label"],
                            "target_entity": node2["label"],
                            "reason": "Both entities mentioned in query but not connected",
                            "priority": node1.get("importance", 0)
                            + node2.get("importance", 0),
                        }
                    )

        return sorted(missing, key=lambda x: x["priority"], reverse=True)[:5]

    def _generate_gap_recommendations(
        self,
        isolated_nodes: list[dict[str, Any]],
        weak_connections: list[dict[str, Any]],
        missing_relationships: list[dict[str, Any]],
    ) -> list[str]:
        """Generate recommendations for addressing knowledge gaps."""
        recommendations = []

        # Recommendations for isolated nodes
        if isolated_nodes:
            top_isolated = isolated_nodes[:3]
            entity_names = [node["node"]["label"] for node in top_isolated]
            recommendations.append(
                f"Research more about these isolated entities: {', '.join(entity_names)}"
            )

        # Recommendations for weak connections
        if weak_connections:
            weak_edge = weak_connections[0]["edge"]
            recommendations.append(
                f"Strengthen the connection between '{weak_edge['source']}' and '{weak_edge['target']}' with more evidence"
            )

        # Recommendations for missing relationships
        if missing_relationships:
            missing_rel = missing_relationships[0]
            recommendations.append(
                f"Investigate the relationship between '{missing_rel['source_entity']}' and '{missing_rel['target_entity']}'"
            )

        # General recommendations
        if not recommendations:
            recommendations.append(
                "Knowledge graph appears well-connected. Consider expanding scope of research."
            )

        return recommendations

    def _calculate_gap_score(
        self,
        isolated_nodes: list[dict[str, Any]],
        weak_connections: list[dict[str, Any]],
        missing_relationships: list[dict[str, Any]],
    ) -> float:
        """Calculate overall knowledge gap score (0-1, higher = more gaps)."""
        # Weight different types of gaps
        isolated_score: float = len(isolated_nodes) * 0.3
        weak_score: float = len(weak_connections) * 0.2
        missing_score: float = len(missing_relationships) * 0.5

        # Normalize by expected values (this is domain-specific tuning)
        total_score = isolated_score + weak_score + missing_score

        # Cap at 1.0 and scale
        return min(total_score / 10.0, 1.0)


# Multi-source synthesis functionality
async def synthesize_multi_source_findings(
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Synthesize information from multiple research sources and agents.

    Args:
        findings (List[Dict[str, Any]]): List of research findings from different sources/agents.

    Returns:
        Dict[str, Any]: Synthesized information organized by topic.
    """
    try:
        # Group findings by topic and source type
        grouped_findings = _group_findings_by_topic(findings)

        # Extract key themes across all findings
        key_themes = _extract_key_themes(findings)

        # Identify consensus areas and contradictions
        consensus_analysis = _analyze_consensus_and_contradictions(findings)

        # Create comprehensive synthesis
        return {
            "total_sources": len(findings),
            "grouped_findings": grouped_findings,
            "key_themes": key_themes,
            "consensus_analysis": consensus_analysis,
            "source_types": _categorize_source_types(findings),
            "temporal_coverage": _analyze_temporal_coverage(findings),
            "geographic_coverage": _analyze_geographic_coverage(findings),
            "credibility_assessment": _assess_overall_credibility(findings),
            "synthesis_metadata": {
                "synthesis_date": __import__("datetime").datetime.now().isoformat(),
                "methodology": "multi-agent deep research synthesis",
                "confidence_level": _calculate_synthesis_confidence(findings),
            },
        }

    except Exception as e:
        logger.error(f"Error synthesizing multi-source findings: {e}")
        return {
            "error": str(e),
            "total_sources": len(findings) if findings else 0,
            "grouped_findings": {},
            "key_themes": [],
            "consensus_analysis": {},
        }


def generate_research_report(
    synthesized_info: dict[str, Any], format_type: str = "academic"
) -> str:
    """
    Generate a comprehensive research report.

    Args:
        synthesized_info (Dict[str, Any]): Synthesized information from multiple sources.
        format_type (str): Type of report to generate (academic, summary, detailed).

    Returns:
        str: Formatted research report.
    """
    try:
        if format_type == "academic":
            return _generate_academic_report(synthesized_info)
        if format_type == "summary":
            return _generate_summary_report(synthesized_info)
        if format_type == "detailed":
            return _generate_detailed_report(synthesized_info)
        return _generate_academic_report(synthesized_info)  # Default to academic

    except Exception as e:
        logger.error(f"Error generating research report: {e}")
        return f"Error generating report: {str(e)}"


def create_citation_list(
    sources: list[dict[str, Any]], style: str = "APA"
) -> list[str]:
    """
    Create a formatted citation list from sources.

    Args:
        sources (List[Dict[str, Any]]): List of sources to cite.
        style (str): Citation style (APA, MLA, Chicago).

    Returns:
        List[str]: Formatted citations.
    """
    try:
        citations = []

        for source in sources:
            if style.upper() == "APA":
                citation = _format_apa_citation(source)
            elif style.upper() == "MLA":
                citation = _format_mla_citation(source)
            elif style.upper() == "CHICAGO":
                citation = _format_chicago_citation(source)
            else:
                citation = _format_apa_citation(source)  # Default to APA

            if citation:
                citations.append(citation)

        return sorted(citations)  # Alphabetical order

    except Exception as e:
        logger.error(f"Error creating citation list: {e}")
        return [f"Error creating citations: {str(e)}"]


def generate_bibliography(
    sources: list[dict[str, Any]], style: str = "APA", categorize: bool = True
) -> dict[str, list[str]]:
    """
    Generate a comprehensive bibliography from research sources.

    Args:
        sources (List[Dict[str, Any]]): List of research sources.
        style (str): Citation style (APA, MLA, Chicago).
        categorize (bool): Whether to categorize sources by type.

    Returns:
        Dict[str, List[str]]: Bibliography organized by category if requested.
    """
    try:
        citations = create_citation_list(sources, style)

        if not categorize:
            return {"all_sources": citations}

        # Categorize sources by type
        categorized: dict[str, list[str]] = {
            "academic_sources": [],
            "news_articles": [],
            "social_media": [],
            "government_reports": [],
            "websites": [],
            "other": [],
        }

        for i, source in enumerate(sources):
            if i < len(citations):
                category = _determine_source_category(source)
                categorized[category].append(citations[i])

        # Remove empty categories
        return {k: v for k, v in categorized.items() if v}

    except Exception as e:
        logger.error(f"Error generating bibliography: {e}")
        return {"error": [f"Error generating bibliography: {str(e)}"]}


# Agent tool functions for synthesis capabilities
class SynthesisAgentTools:
    """Agent tools for synthesis capabilities."""

    def __init__(self, source_tracker: AgentSourceTracker):
        """Initialize synthesis agent tools."""
        self.source_tracker = source_tracker
        self.synthesis_tools = SynthesisTools(source_tracker)

    async def synthesize_research_findings(self, research_data: str) -> str:
        """
        Synthesize findings from multiple research sources and agents.

        Args:
            research_data: JSON string containing research findings from all agents

        Returns:
            JSON string with synthesized information
        """
        try:
            # Parse input data
            input_data = (
                json.loads(research_data)
                if isinstance(research_data, str)
                else research_data
            )
            findings = input_data.get("findings", [])

            # Synthesize findings
            synthesis_result = await synthesize_multi_source_findings(findings)

            # Track sources
            for finding in findings:
                if "url" in finding:
                    source = ResearchSource(
                        url=finding["url"],
                        title=finding.get("title", "Unknown"),
                        source_type=finding.get("source_type", "unknown"),
                        description=(
                            finding.get("content", "")[:200]
                            if finding.get("content")
                            else None
                        ),
                        content_summary=(
                            finding.get("content", "")[:500]
                            if finding.get("content")
                            else None
                        ),
                        metadata=finding.get("metadata", {}),
                        first_accessed=__import__("datetime")
                        .datetime.now()
                        .isoformat(),
                        last_accessed=__import__("datetime").datetime.now().isoformat(),
                    )
                    self.source_tracker.register_source(source)

            result = {
                "success": True,
                "synthesis": synthesis_result,
                "sources_processed": len(findings),
                "message": "Successfully synthesized research findings",
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error synthesizing research findings: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "message": "Failed to synthesize research findings",
            }
            return json.dumps(error_result, indent=2)

    async def generate_comprehensive_report(
        self, synthesis_data: str, report_format: str = "academic"
    ) -> str:
        """
        Generate a comprehensive research report from synthesized data.

        Args:
            synthesis_data: JSON string with synthesized research data
            report_format: Format type (academic, summary, detailed)

        Returns:
            Generated research report as a string
        """
        try:
            # Parse input data
            input_data = (
                json.loads(synthesis_data)
                if isinstance(synthesis_data, str)
                else synthesis_data
            )
            synthesized_info = input_data.get("synthesis", {})

            # Generate report
            report = generate_research_report(synthesized_info, report_format)

            logger.info(f"Generated {report_format} research report")
            return report

        except Exception as e:
            logger.error(f"Error generating research report: {e}")
            return f"Error generating research report: {str(e)}"

    async def create_citations_and_bibliography(
        self, sources_data: str, citation_style: str = "APA"
    ) -> str:
        """
        Create citations and bibliography from research sources.

        Args:
            sources_data: JSON string with source data
            citation_style: Citation style (APA, MLA, Chicago)

        Returns:
            JSON string with citations and bibliography
        """
        try:
            # Parse input data
            input_data = (
                json.loads(sources_data)
                if isinstance(sources_data, str)
                else sources_data
            )
            sources = input_data.get("sources", [])

            # Create citations and bibliography
            citations = create_citation_list(sources, citation_style)
            bibliography = generate_bibliography(
                sources, citation_style, categorize=True
            )

            result = {
                "success": True,
                "citation_style": citation_style,
                "citations": citations,
                "bibliography": bibliography,
                "total_sources": len(sources),
                "message": f"Successfully created {citation_style} citations and bibliography",
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error creating citations and bibliography: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "message": "Failed to create citations and bibliography",
            }
            return json.dumps(error_result, indent=2)

    async def build_research_knowledge_graph(
        self, research_data: str, topic: str
    ) -> str:
        """
        Build a knowledge graph from research findings.

        Args:
            research_data: JSON string containing research findings
            topic: Main research topic

        Returns:
            JSON string with knowledge graph representation
        """
        try:
            # Parse input data
            input_data = (
                json.loads(research_data)
                if isinstance(research_data, str)
                else research_data
            )
            findings = input_data.get("findings", [])

            # Build knowledge graph
            knowledge_graph = await self.synthesis_tools.build_knowledge_graph(
                findings, topic
            )

            result = {
                "success": True,
                "knowledge_graph": knowledge_graph,
                "topic": topic,
                "sources_analyzed": len(findings),
                "message": "Successfully built knowledge graph",
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error building knowledge graph: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "message": "Failed to build knowledge graph",
            }
            return json.dumps(error_result, indent=2)

    async def identify_research_gaps(
        self, knowledge_graph_data: str, original_query: str
    ) -> str:
        """
        Identify knowledge gaps and contradictions in research.

        Args:
            knowledge_graph_data: JSON string with knowledge graph data
            original_query: Original research query

        Returns:
            JSON string with knowledge gaps analysis
        """
        try:
            # Parse input data
            input_data = (
                json.loads(knowledge_graph_data)
                if isinstance(knowledge_graph_data, str)
                else knowledge_graph_data
            )
            knowledge_graph = input_data.get("knowledge_graph", {})

            # Identify knowledge gaps
            gaps_analysis = await self.synthesis_tools.identify_knowledge_gaps(
                knowledge_graph, original_query
            )

            result = {
                "success": True,
                "gaps_analysis": gaps_analysis,
                "original_query": original_query,
                "message": "Successfully identified knowledge gaps",
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error identifying knowledge gaps: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "message": "Failed to identify knowledge gaps",
            }
            return json.dumps(error_result, indent=2)

    async def resolve_contradictions(self, synthesis_data: str) -> str:
        """
        Analyze and attempt to resolve contradictions in research findings.

        Args:
            synthesis_data: JSON string with synthesized research data

        Returns:
            JSON string with contradiction analysis and resolution attempts
        """
        try:
            # Parse input data
            input_data = (
                json.loads(synthesis_data)
                if isinstance(synthesis_data, str)
                else synthesis_data
            )
            synthesized_info = input_data.get("synthesis", {})

            # Analyze contradictions (simplified implementation)
            consensus_analysis = synthesized_info.get("consensus_analysis", {})
            contradictions = consensus_analysis.get("contradictions", [])

            # Attempt resolution strategies
            resolution_strategies = []
            for contradiction in contradictions:
                strategy = self._suggest_resolution_strategy(contradiction)
                resolution_strategies.append(strategy)

            result = {
                "success": True,
                "contradictions_found": len(contradictions),
                "resolution_strategies": resolution_strategies,
                "consensus_areas": consensus_analysis.get("consensus_areas", []),
                "message": "Successfully analyzed contradictions",
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error resolving contradictions: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "message": "Failed to resolve contradictions",
            }
            return json.dumps(error_result, indent=2)

    def _suggest_resolution_strategy(
        self, contradiction: dict[str, Any]
    ) -> dict[str, Any]:
        """Suggest a strategy for resolving a contradiction."""
        return {
            "contradiction": contradiction,
            "suggested_strategy": "Compare source credibility and recency",
            "additional_research_needed": True,
            "confidence": "medium",
        }


# Helper functions for synthesis
def _group_findings_by_topic(
    findings: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group findings by topic or theme."""
    grouped: dict[str, list[dict[str, Any]]] = {}

    for finding in findings:
        # Extract topic from content or metadata
        topic = finding.get("topic", "general")
        if topic not in grouped:
            grouped[topic] = []
        grouped[topic].append(finding)

    return grouped


def _extract_key_themes(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract key themes across all findings."""
    themes: dict[str, int] = {}

    for finding in findings:
        content = finding.get("content", "")
        # Simple keyword extraction (in practice, would use more sophisticated NLP)
        words = content.lower().split()
        for word in words:
            if len(word) > 3 and word.isalpha():
                themes[word] = themes.get(word, 0) + 1

    # Return top themes
    top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:10]
    return [{"theme": theme, "frequency": freq} for theme, freq in top_themes]


def _analyze_consensus_and_contradictions(
    findings: list[dict[str, Any]],  # noqa: ARG001
) -> dict[str, Any]:
    """Analyze areas of consensus and contradiction."""
    return {
        "consensus_areas": [],  # Would implement sophisticated analysis
        "contradictions": [],
        "uncertain_areas": [],
        "confidence_levels": {},
    }


def _categorize_source_types(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Categorize sources by type."""
    types: dict[str, int] = {}

    for finding in findings:
        source_type = finding.get("source_type", "unknown")
        types[source_type] = types.get(source_type, 0) + 1

    return types


def _analyze_temporal_coverage(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze temporal coverage of sources."""
    dates = []

    for finding in findings:
        date = finding.get("publication_date") or finding.get("date")
        if date:
            dates.append(date)

    return {
        "total_dated_sources": len(dates),
        "date_range": f"{min(dates)} to {max(dates)}" if dates else "unknown",
        "temporal_distribution": {},  # Would implement proper date analysis
    }


def _analyze_geographic_coverage(
    findings: list[dict[str, Any]],  # noqa: ARG001
) -> dict[str, Any]:
    """Analyze geographic coverage of sources."""
    return {
        "regions_covered": [],
        "geographic_bias": "unknown",
        "global_coverage": False,
    }


def _assess_overall_credibility(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess overall credibility of source collection."""
    credibility_scores = []

    for finding in findings:
        score = finding.get("credibility_score", 0.5)
        credibility_scores.append(score)

    if credibility_scores:
        avg_credibility = sum(credibility_scores) / len(credibility_scores)
    else:
        avg_credibility = 0.5

    return {
        "average_credibility": avg_credibility,
        "high_credibility_sources": len([s for s in credibility_scores if s > 0.8]),
        "low_credibility_sources": len([s for s in credibility_scores if s < 0.3]),
        "overall_assessment": (
            "high"
            if avg_credibility > 0.7
            else "medium" if avg_credibility > 0.4 else "low"
        ),
    }


def _calculate_synthesis_confidence(findings: list[dict[str, Any]]) -> float:
    """Calculate confidence level in synthesis."""
    if not findings:
        return 0.0

    # Simple confidence calculation based on source count and credibility
    source_count_factor: float = min(
        len(findings) / 10, 1.0
    )  # Max benefit at 10 sources
    credibility_assessment = _assess_overall_credibility(findings)
    credibility_factor: float = credibility_assessment["average_credibility"]

    return (source_count_factor + credibility_factor) / 2


# Report generation helper functions
def _generate_academic_report(synthesized_info: dict[str, Any]) -> str:
    """Generate an academic-style research report."""
    report_parts = []

    # Executive Summary
    report_parts.append("# Research Report\n")
    report_parts.append("## Executive Summary\n")
    report_parts.append(
        f"This report synthesizes information from {synthesized_info.get('total_sources', 0)} sources "
    )
    report_parts.append(
        f"with an overall credibility assessment of {synthesized_info.get('credibility_assessment', {}).get('overall_assessment', 'unknown')}.\n\n"
    )

    # Key Themes
    key_themes = synthesized_info.get("key_themes", [])
    if key_themes:
        report_parts.append("## Key Themes\n")
        for theme in key_themes[:5]:  # Top 5 themes
            report_parts.append(
                f"- {theme.get('theme', 'Unknown')} (mentioned {theme.get('frequency', 0)} times)\n"
            )
        report_parts.append("\n")

    # Source Analysis
    source_types = synthesized_info.get("source_types", {})
    if source_types:
        report_parts.append("## Source Analysis\n")
        for source_type, count in source_types.items():
            report_parts.append(f"- {source_type}: {count} sources\n")
        report_parts.append("\n")

    # Credibility Assessment
    credibility = synthesized_info.get("credibility_assessment", {})
    if credibility:
        report_parts.append("## Credibility Assessment\n")
        report_parts.append(
            f"- Average credibility score: {credibility.get('average_credibility', 0):.2f}\n"
        )
        report_parts.append(
            f"- High credibility sources: {credibility.get('high_credibility_sources', 0)}\n"
        )
        report_parts.append(
            f"- Overall assessment: {credibility.get('overall_assessment', 'unknown')}\n\n"
        )

    return "".join(report_parts)


def _generate_summary_report(synthesized_info: dict[str, Any]) -> str:
    """Generate a summary-style report."""
    total_sources = synthesized_info.get("total_sources", 0)
    key_themes = synthesized_info.get("key_themes", [])[:3]  # Top 3 themes
    credibility = synthesized_info.get("credibility_assessment", {}).get(
        "overall_assessment", "unknown"
    )

    summary = f"Research Summary: Analyzed {total_sources} sources with {credibility} overall credibility. "

    if key_themes:
        theme_list = ", ".join([theme.get("theme", "") for theme in key_themes])
        summary += f"Key themes include: {theme_list}."

    return summary


def _generate_detailed_report(synthesized_info: dict[str, Any]) -> str:
    """Generate a detailed research report."""
    # For now, use academic format with additional details
    report = _generate_academic_report(synthesized_info)

    # Add additional sections for detailed report
    report += "\n## Detailed Analysis\n"

    grouped_findings = synthesized_info.get("grouped_findings", {})
    for topic, findings in grouped_findings.items():
        report += f"\n### {topic.title()}\n"
        report += f"Found {len(findings)} sources related to this topic.\n"

    temporal_coverage = synthesized_info.get("temporal_coverage", {})
    if temporal_coverage.get("date_range"):
        report += "\n## Temporal Coverage\n"
        report += f"Sources span from {temporal_coverage['date_range']}\n"

    return report


# Citation formatting helper functions
def _format_apa_citation(source: dict[str, Any]) -> str:
    """Format source in APA style."""
    try:
        url = source.get("url", "")
        title = source.get("title", "Untitled")
        date = source.get("publication_date") or source.get("date", "n.d.")

        if "reddit.com" in url:
            return f"Reddit discussion. ({date}). {title}. Retrieved from {url}"
        if any(domain in url for domain in ["twitter.com", "x.com"]):
            return f"Social media post. ({date}). {title}. Retrieved from {url}"
        return f"Web source. ({date}). {title}. Retrieved from {url}"

    except Exception:
        return f"Source: {source.get('url', 'Unknown source')}"


def _format_mla_citation(source: dict[str, Any]) -> str:
    """Format source in MLA style."""
    try:
        url = source.get("url", "")
        title = source.get("title", "Untitled")
        date = source.get("publication_date") or source.get("date", "")

        citation = f'"{title}." Web'
        if date:
            citation += f". {date}"
        citation += f". <{url}>."

        return citation

    except Exception:
        return f"Source: {source.get('url', 'Unknown source')}"


def _format_chicago_citation(source: dict[str, Any]) -> str:
    """Format source in Chicago style."""
    try:
        url = source.get("url", "")
        title = source.get("title", "Untitled")
        date = source.get("publication_date") or source.get("date", "")

        citation = f'"{title}."'
        if date:
            citation += f" Accessed {date}."
        citation += f" {url}."

        return citation

    except Exception:
        return f"Source: {source.get('url', 'Unknown source')}"


def _determine_source_category(source: dict[str, Any]) -> str:
    """Determine the category of a source."""
    url = source.get("url", "").lower()

    if any(domain in url for domain in ["edu", "org", "gov"]):
        if "gov" in url:
            return "government_reports"
        return "academic_sources"
    if any(
        domain in url
        for domain in ["reddit.com", "twitter.com", "x.com", "facebook.com"]
    ):
        return "social_media"
    if any(domain in url for domain in ["news", "cnn", "bbc", "reuters", "ap", "npr"]):
        return "news_articles"
    return "websites"


async def build_knowledge_graph(
    research_findings: list[dict[str, Any]], topic: str
) -> dict[str, Any]:
    """
    Build a knowledge graph from research findings.

    Args:
        research_findings (List[Dict[str, Any]]): Research findings from all agents
        topic (str): Main research topic

    Returns:
        Dict[str, Any]: Knowledge graph representation
    """
    # Create a temporary tools instance for the module-level function
    from agents.ollama.deep_research.shared.source_tracking import (
        AgentSourceTracker,
        SharedSourceRegistry,
    )

    temp_tracker = AgentSourceTracker("temp", SharedSourceRegistry())
    tools = SynthesisTools(temp_tracker)
    return await tools.build_knowledge_graph(research_findings, topic)


async def identify_knowledge_gaps(
    knowledge_graph: dict[str, Any], query: str
) -> dict[str, Any]:
    """
    Identify knowledge gaps in the research.

    Args:
        knowledge_graph (Dict[str, Any]): Knowledge graph representation
        query (str): Original research query

    Returns:
        Dict[str, Any]: Knowledge gaps analysis
    """
    # Create a temporary tools instance for the module-level function
    from agents.ollama.deep_research.shared.source_tracking import (
        AgentSourceTracker,
        SharedSourceRegistry,
    )

    temp_tracker = AgentSourceTracker("temp", SharedSourceRegistry())
    tools = SynthesisTools(temp_tracker)
    return await tools.identify_knowledge_gaps(knowledge_graph, query)


__all__ = [
    "SynthesisTools",
    "synthesize_multi_source_findings",
    "generate_research_report",
    "create_citation_list",
    "generate_bibliography",
    "identify_knowledge_gaps",
    "build_knowledge_graph",
    "SynthesisAgentTools",
]
