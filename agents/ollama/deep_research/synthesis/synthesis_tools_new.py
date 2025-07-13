"""
Synthesis tools and functionality.

This module provides tools for synthesizing information and generating research reports.
"""

import logging
from typing import Any

from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker

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
            relationships = await self._extract_relationships(research_findings, entities)

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
            weak_connections = self._identify_weak_connections(nodes, edges)

            # Find missing relationships based on query context
            missing_relationships = self._identify_missing_relationships(nodes, edges, query)

            # Generate recommendations
            recommendations = self._generate_gap_recommendations(
                isolated_nodes, weak_connections, missing_relationships
            )

            # Calculate overall gap score
            gap_score = self._calculate_gap_score(isolated_nodes, weak_connections, missing_relationships)

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
            entity["credibility"] = sum(m["credibility"] for m in entity["mentions"]) / len(
                entity["mentions"]
            )
            entity["importance"] = entity["frequency"] * entity["credibility"]

        # Filter and rank entities
        significant_entities = [
            entity
            for entity in entities.values()
            if entity["frequency"] >= 2 or entity["credibility"] > 0.7
        ]

        return sorted(significant_entities, key=lambda x: x["importance"], reverse=True)

    def _identify_entity_candidates(self, content: str, _topic: str) -> list[dict[str, Any]]:
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

                candidates.append({"text": noun, "type": entity_type, "context": context})

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
        elif any(word in entity_lower for word in ["dr", "prof", "mr", "ms"]):
            return "person"
        elif entity_text.isupper() and len(entity_text) <= 5:
            return "acronym"
        elif any(char.isdigit() for char in entity_text):
            return "metric"
        elif any(word in entity_lower for word in ["company", "corporation", "inc", "ltd"]):
            return "organization"
        else:
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
                    relationship = self._analyze_entity_relationship(content, entity1, entity2)
                    if relationship:
                        relationship["source"] = finding.get("url", "")
                        relationship["credibility"] = finding.get("credibility_score", 0.5)
                        relationships.append(relationship)

        # Consolidate duplicate relationships
        consolidated_relationships = self._consolidate_relationships(relationships)

        return consolidated_relationships

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
                if any(word in sentence.lower() for word in ["causes", "leads to", "results in"]):
                    relationship_type = "causal"
                elif any(word in sentence.lower() for word in ["part of", "includes", "contains"]):
                    relationship_type = "hierarchical"
                elif any(word in sentence.lower() for word in ["similar", "like", "compared to"]):
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

    def _analyze_graph_properties(self, knowledge_graph: dict[str, Any]) -> dict[str, Any]:
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
        most_connected = sorted(node_degrees.items(), key=lambda x: x[1], reverse=True)[:5]

        # Relationship type distribution
        relationship_types: dict[str, int] = {}
        for edge in edges:
            rel_type = edge["type"]
            relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_degree": sum(node_degrees.values()) / len(node_degrees) if node_degrees else 0,
            "max_degree": max(node_degrees.values()) if node_degrees else 0,
            "most_connected_nodes": most_connected,
            "relationship_types": relationship_types,
            "density": (2 * edge_count) / (node_count * (node_count - 1)) if node_count > 1 else 0,
        }

    def _identify_key_insights(
        self, knowledge_graph: dict[str, Any], graph_analysis: dict[str, Any]
    ) -> list[str]:
        """Identify key insights from the knowledge graph."""
        insights = []
        nodes = knowledge_graph["nodes"]
        edges = knowledge_graph["edges"]

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
            insights.append(f"'{central_entity}' is a central concept with {degree} connections")

        # Relationship patterns
        rel_types = graph_analysis.get("relationship_types", {})
        if rel_types:
            dominant_type = max(rel_types.items(), key=lambda x: x[1])
            insights.append(f"Primary relationship type: {dominant_type[0]} ({dominant_type[1]} instances)")

        # Entity type distribution
        entity_types: dict[str, int] = {}
        for node in nodes:
            node_type = node["type"]
            entity_types[node_type] = entity_types.get(node_type, 0) + 1

        if entity_types:
            dominant_entity_type = max(entity_types.items(), key=lambda x: x[1])
            insights.append(f"Primary entity type: {dominant_entity_type[0]} ({dominant_entity_type[1]} entities)")

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
            node_connections[edge["source"]] = node_connections.get(edge["source"], 0) + 1
            node_connections[edge["target"]] = node_connections.get(edge["target"], 0) + 1

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
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
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
                            "priority": node1.get("importance", 0) + node2.get("importance", 0),
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
            recommendations.append("Knowledge graph appears well-connected. Consider expanding scope of research.")

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


# Module-level convenience functions for backward compatibility
def synthesize_multi_source_findings(_findings: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Synthesize information from multiple research sources and agents.

    Args:
        findings (List[Dict[str, Any]]): List of research findings from different sources/agents.

    Returns:
        Dict[str, Any]: Synthesized information organized by topic.
    """
    # This will be implemented in Phase 3.1.8
    return {}


def generate_research_report(
    _synthesized_info: dict[str, Any], _format_type: str = "academic"
) -> str:
    """
    Generate a comprehensive research report.

    Args:
        synthesized_info (Dict[str, Any]): Synthesized information from multiple sources.
        format_type (str): Type of report to generate (academic, summary, detailed).

    Returns:
        str: Formatted research report.
    """
    # This will be implemented in Phase 3.1.8
    return ""


def create_citation_list(
    _sources: list[dict[str, Any]], _style: str = "APA"
) -> list[str]:
    """
    Create a formatted citation list from sources.

    Args:
        sources (List[Dict[str, Any]]): List of sources to cite.
        style (str): Citation style (APA, MLA, Chicago).

    Returns:
        List[str]: Formatted citations.
    """
    # This will be implemented in Phase 3.1.8
    return []


def generate_bibliography(
    _sources: list[dict[str, Any]], _style: str = "APA", _categorize: bool = True
) -> dict[str, list[str]]:
    """
    Generate a comprehensive bibliography from research sources.

    Args:
        sources (List[Dict[str, Any]]): List of research sources.
        categorize (bool): Whether to categorize sources by type.

    Returns:
        Dict[str, List[str]]: Bibliography organized by category if requested.
    """
    # This will be implemented in Phase 3.1.8
    return {}


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
    from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker, SharedSourceRegistry
    
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
    from agents.ollama.deep_research.shared.source_tracking import AgentSourceTracker, SharedSourceRegistry
    
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
]
