"""
Query analysis and decomposition functionality.

This module provides tools for analyzing and breaking down complex research queries.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class QueryDecomposer:
    """
    Core class for query decomposition and analysis functionality.
    """

    def __init__(self) -> None:
        """Initialize the QueryDecomposer."""
        pass

    def get_tools(self) -> list[dict[str, Any]]:
        """Get all query decomposition tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_query_complexity",
                    "description": "Analyze the complexity and scope of a research query to determine decomposition strategy",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The research query to analyze",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "decompose_research_query",
                    "description": "Break down a complex research query into manageable sub-queries with metadata",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The complex research query to decompose",
                            },
                            "max_sub_queries": {
                                "type": "integer",
                                "description": "Maximum number of sub-queries to generate (default: 7)",
                                "default": 7,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "identify_query_dependencies",
                    "description": "Identify dependencies and relationships between sub-queries",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sub_queries": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "List of sub-queries to analyze for dependencies",
                            }
                        },
                        "required": ["sub_queries"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "prioritize_sub_queries",
                    "description": "Prioritize sub-queries based on importance, dependencies, and research efficiency",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sub_queries": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "List of sub-queries to prioritize",
                            },
                            "dependencies": {
                                "type": "object",
                                "description": "Dictionary mapping query IDs to their dependencies",
                            },
                        },
                        "required": ["sub_queries", "dependencies"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_research_strategy",
                    "description": "Create a comprehensive research strategy with sequenced tasks",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The original research query",
                            },
                            "sub_queries": {
                                "type": "array",
                                "items": {"type": "object"},
                                "description": "List of prioritized sub-queries",
                            },
                            "dependencies": {
                                "type": "object",
                                "description": "Query dependencies mapping",
                            },
                        },
                        "required": ["query", "sub_queries", "dependencies"],
                    },
                },
            },
        ]

    def analyze_query_complexity(self, query: str) -> dict[str, Any]:
        """
        Analyze the complexity and scope of a research query.

        Args:
            query (str): The research query to analyze.

        Returns:
            Dict[str, Any]: Analysis results including complexity metrics and recommendations.
        """
        try:
            # Basic complexity indicators
            word_count = len(query.split())
            sentence_count = len(re.split(r"[.!?]+", query))
            question_count = query.count("?")
            and_or_count = len(
                re.findall(
                    r"\b(?:and|or|but|however|also|additionally)\b", query.lower()
                )
            )

            # Identify complex patterns
            time_references = len(
                re.findall(
                    r"\b(?:history|historical|timeline|evolution|development|recent|current|future|trend)\b",
                    query.lower(),
                )
            )
            comparison_words = len(
                re.findall(
                    r"\b(?:compare|contrast|versus|vs|difference|similar|different)\b",
                    query.lower(),
                )
            )
            analysis_words = len(
                re.findall(
                    r"\b(?:analyze|analysis|evaluate|assessment|impact|effect|cause|reason|why|how)\b",
                    query.lower(),
                )
            )

            # Calculate complexity score (0-10)
            complexity_score = min(
                10,
                (
                    (word_count / 10)
                    + (sentence_count * 1.5)
                    + (and_or_count * 2)
                    + (time_references * 1.5)
                    + (comparison_words * 2)
                    + (analysis_words * 1.5)
                ),
            )

            # Estimate sub-queries needed
            estimated_sub_queries = max(
                2, min(7, int(complexity_score / 1.5 + question_count))
            )

            # Recommend source types
            recommended_sources = ["web"]
            if any(
                word in query.lower()
                for word in [
                    "opinion",
                    "debate",
                    "controversy",
                    "discussion",
                    "people think",
                ]
            ):
                recommended_sources.append("social")
            if any(
                word in query.lower()
                for word in ["academic", "research", "study", "scholarly", "scientific"]
            ):
                recommended_sources.append("academic")
            if any(
                word in query.lower()
                for word in ["news", "recent", "current", "latest", "breaking"]
            ):
                recommended_sources.append("news")

            result = {
                "complexity_score": round(complexity_score, 2),
                "estimated_sub_queries": estimated_sub_queries,
                "recommended_sources": recommended_sources,
                "analysis_complete": True,
                "metrics": {
                    "word_count": word_count,
                    "sentence_count": sentence_count,
                    "question_count": question_count,
                    "connector_words": and_or_count,
                    "time_references": time_references,
                    "comparison_indicators": comparison_words,
                    "analysis_indicators": analysis_words,
                },
                "recommendations": self._generate_decomposition_recommendations(
                    complexity_score, query
                ),
            }

            logger.info(
                f"Query complexity analysis complete. Score: {complexity_score}, Sub-queries: {estimated_sub_queries}"
            )
            return result

        except Exception as e:
            logger.error(f"Error analyzing query complexity: {e}")
            return {
                "complexity_score": 5.0,
                "estimated_sub_queries": 3,
                "recommended_sources": ["web"],
                "analysis_complete": False,
                "error": str(e),
            }

    def _generate_decomposition_recommendations(
        self, complexity_score: float, query: str
    ) -> list[str]:
        """Generate recommendations for query decomposition strategy."""
        recommendations = []

        if complexity_score < 3:
            recommendations.append("Simple query - consider 2-3 focused sub-queries")
        elif complexity_score < 6:
            recommendations.append("Moderate complexity - break into 3-5 sub-queries")
        else:
            recommendations.append("High complexity - decompose into 5-7 sub-queries")

        if "compare" in query.lower() or "versus" in query.lower():
            recommendations.append(
                "Comparison detected - create separate sub-queries for each item being compared"
            )

        if any(
            word in query.lower() for word in ["history", "evolution", "development"]
        ):
            recommendations.append(
                "Temporal analysis needed - consider chronological sub-queries"
            )

        if "why" in query.lower() or "cause" in query.lower():
            recommendations.append(
                "Causal analysis required - separate cause and effect sub-queries"
            )

        return recommendations

    def decompose_research_query(
        self, query: str, max_sub_queries: int = 7
    ) -> list[dict[str, Any]]:
        """
        Break down a complex research query into manageable sub-queries.

        Args:
            query (str): The complex research query to decompose.
            max_sub_queries (int): Maximum number of sub-queries to generate.

        Returns:
            List[Dict[str, Any]]: List of sub-queries with metadata.
        """
        try:
            sub_queries = []

            # Analyze the query first
            analysis = self.analyze_query_complexity(query)
            estimated_count = min(max_sub_queries, analysis["estimated_sub_queries"])

            # Generate sub-queries based on query patterns
            sub_queries.extend(self._extract_direct_questions(query))
            sub_queries.extend(self._identify_comparison_queries(query))
            sub_queries.extend(self._identify_temporal_queries(query))
            sub_queries.extend(self._identify_causal_queries(query))
            sub_queries.extend(self._identify_context_queries(query))

            # Remove duplicates and limit to max count
            unique_queries = self._deduplicate_sub_queries(sub_queries)
            limited_queries = unique_queries[:estimated_count]

            # Add metadata to each sub-query
            for i, sub_query in enumerate(limited_queries):
                sub_query.update(
                    {
                        "query_id": f"sq_{i+1:02d}",
                        "importance": self._calculate_importance(
                            sub_query["query_text"], query
                        ),
                        "estimated_complexity": self._estimate_complexity(
                            sub_query["query_text"]
                        ),
                        "suggested_sources": self._suggest_sources(
                            sub_query["query_text"]
                        ),
                        "context_requirements": self._identify_context_needs(
                            sub_query["query_text"], query
                        ),
                    }
                )

            logger.info(
                f"Generated {len(limited_queries)} sub-queries from: {query[:100]}..."
            )
            return limited_queries

        except Exception as e:
            logger.error(f"Error decomposing research query: {e}")
            return [
                {
                    "query_id": "sq_01",
                    "query_text": query,
                    "description": "Original query (decomposition failed)",
                    "research_type": "factual",
                    "importance": 5,
                    "estimated_complexity": 3,
                    "suggested_sources": ["web"],
                    "context_requirements": [],
                    "error": str(e),
                }
            ]

    def _extract_direct_questions(self, query: str) -> list[dict[str, Any]]:
        """Extract direct questions from the query."""
        questions = []
        sentences = re.split(r"[.!?]+", query)

        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and (
                "?" in sentence
                or any(
                    word in sentence.lower()
                    for word in ["what", "how", "why", "when", "where", "who"]
                )
            ):
                questions.append(
                    {
                        "query_text": sentence.rstrip("?") + "?",
                        "description": "Direct question from original query",
                        "research_type": "factual",
                    }
                )

        return questions

    def _identify_comparison_queries(self, query: str) -> list[dict[str, Any]]:
        """Identify comparison-based sub-queries."""
        queries = []

        # Look for comparison keywords
        comparison_patterns = [
            r"compare\s+([^,]+?)\s+(?:and|vs|versus|with)\s+([^,.]+)",
            r"([^,]+?)\s+(?:vs|versus)\s+([^,.]+)",
            r"difference\s+between\s+([^,]+?)\s+and\s+([^,.]+)",
            r"([^,]+?)\s+and\s+([^,]+?)\s+(?:comparison|different|similar)",
        ]

        for pattern in comparison_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            for match in matches:
                item1, item2 = match.group(1).strip(), match.group(2).strip()
                queries.extend(
                    [
                        {
                            "query_text": f"What are the key characteristics of {item1}?",
                            "description": f"Research {item1} for comparison",
                            "research_type": "comparative",
                        },
                        {
                            "query_text": f"What are the key characteristics of {item2}?",
                            "description": f"Research {item2} for comparison",
                            "research_type": "comparative",
                        },
                        {
                            "query_text": f"How do {item1} and {item2} differ?",
                            "description": f"Direct comparison between {item1} and {item2}",
                            "research_type": "analytical",
                        },
                    ]
                )

        return queries

    def _identify_temporal_queries(self, query: str) -> list[dict[str, Any]]:
        """Identify time-based sub-queries."""
        queries = []

        temporal_keywords = [
            "history",
            "historical",
            "timeline",
            "evolution",
            "development",
            "recent",
            "current",
            "future",
            "trend",
            "change",
            "over time",
        ]

        if any(keyword in query.lower() for keyword in temporal_keywords):
            # Extract main subject
            subject_patterns = [
                r"history\s+of\s+([^,.]+)",
                r"evolution\s+of\s+([^,.]+)",
                r"development\s+of\s+([^,.]+)",
                r"([^,.]+?)\s+(?:history|timeline|evolution|development)",
            ]

            subjects = set()
            for pattern in subject_patterns:
                matches = re.finditer(pattern, query, re.IGNORECASE)
                for match in matches:
                    subjects.add(match.group(1).strip())

            for subject in subjects:
                queries.extend(
                    [
                        {
                            "query_text": f"What is the historical background of {subject}?",
                            "description": f"Historical context for {subject}",
                            "research_type": "factual",
                        },
                        {
                            "query_text": f"What are the recent developments in {subject}?",
                            "description": f"Current state and trends for {subject}",
                            "research_type": "factual",
                        },
                    ]
                )

        return queries

    def _identify_causal_queries(self, query: str) -> list[dict[str, Any]]:
        """Identify cause-and-effect sub-queries."""
        queries = []

        # Look for causal keywords
        if any(
            word in query.lower()
            for word in [
                "why",
                "cause",
                "reason",
                "because",
                "due to",
                "result",
                "effect",
                "impact",
            ]
        ):
            causal_patterns = [
                r"why\s+(?:is|are|do|does|did|has|have)\s+([^?,.]+)",
                r"(?:cause|reason)\s+for\s+([^,.]+)",
                r"(?:impact|effect)\s+of\s+([^,.]+)",
                r"([^,.]+?)\s+(?:causes?|results?\s+in|leads?\s+to)\s+([^,.]+)",
            ]

            for pattern in causal_patterns:
                matches = re.finditer(pattern, query, re.IGNORECASE)
                for match in matches:
                    if len(match.groups()) == 1:
                        phenomenon = match.group(1).strip()
                        queries.append(
                            {
                                "query_text": f"What are the causes of {phenomenon}?",
                                "description": f"Identify causes of {phenomenon}",
                                "research_type": "analytical",
                            }
                        )
                    elif len(match.groups()) == 2:
                        cause, effect = match.group(1).strip(), match.group(2).strip()
                        queries.extend(
                            [
                                {
                                    "query_text": f"How does {cause} influence {effect}?",
                                    "description": f"Causal relationship between {cause} and {effect}",
                                    "research_type": "analytical",
                                }
                            ]
                        )

        return queries

    def _identify_context_queries(self, query: str) -> list[dict[str, Any]]:
        """Identify context-setting sub-queries."""
        queries = []

        # Look for entities that need context
        entities = self._extract_key_entities(query)

        for entity in entities[:3]:  # Limit to avoid too many context queries
            queries.append(
                {
                    "query_text": f"What is {entity} and why is it significant?",
                    "description": f"Provide context and background for {entity}",
                    "research_type": "factual",
                }
            )

        return queries

    def _extract_key_entities(self, query: str) -> list[str]:
        """Extract key entities that might need context."""
        # Simple entity extraction - look for capitalized terms and quoted terms
        entities = []

        # Capitalized words (potential proper nouns)
        capitalized = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", query)
        entities.extend([entity for entity in capitalized if len(entity) > 2])

        # Quoted terms
        quoted = re.findall(r'"([^"]+)"', query)
        entities.extend(quoted)

        # Remove common words
        common_words = {
            "The",
            "This",
            "That",
            "What",
            "How",
            "Why",
            "When",
            "Where",
            "Who",
        }
        entities = [e for e in entities if e not in common_words]

        return list(set(entities))

    def _deduplicate_sub_queries(
        self, sub_queries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate sub-queries based on text similarity."""
        unique_queries = []
        seen_texts = set()

        for query in sub_queries:
            query_text = query["query_text"].lower().strip()

            # Simple deduplication - could be enhanced with semantic similarity
            if query_text not in seen_texts:
                seen_texts.add(query_text)
                unique_queries.append(query)

        return unique_queries

    def _calculate_importance(self, sub_query: str, original_query: str) -> int:
        """Calculate importance score (1-10) for a sub-query."""
        # Simple heuristic based on keyword overlap and question type
        original_lower = original_query.lower()
        sub_lower = sub_query.lower()

        # Count overlapping significant words
        original_words = set(re.findall(r"\b\w{4,}\b", original_lower))
        sub_words = set(re.findall(r"\b\w{4,}\b", sub_lower))
        overlap = len(original_words.intersection(sub_words))

        # Boost for certain types of questions
        importance = min(10, 3 + overlap)

        if any(word in sub_lower for word in ["what", "definition", "background"]):
            importance += 2  # Context is important
        if any(word in sub_lower for word in ["why", "cause", "reason"]):
            importance += 1  # Causal analysis is valuable

        return min(10, importance)

    def _estimate_complexity(self, sub_query: str) -> int:
        """Estimate complexity (1-5) for a sub-query."""
        query_lower = sub_query.lower()
        complexity = 2  # Base complexity

        if any(word in query_lower for word in ["analyze", "compare", "evaluate"]):
            complexity += 2
        if any(word in query_lower for word in ["why", "how", "cause"]):
            complexity += 1
        if len(sub_query.split()) > 10:
            complexity += 1

        return min(5, complexity)

    def _suggest_sources(self, sub_query: str) -> list[str]:
        """Suggest appropriate source types for a sub-query."""
        query_lower = sub_query.lower()
        sources = ["web"]  # Always include web

        if any(
            word in query_lower
            for word in ["opinion", "people think", "popular", "consensus"]
        ):
            sources.append("social")
        if any(
            word in query_lower
            for word in ["study", "research", "academic", "scholarly"]
        ):
            sources.append("academic")
        if any(word in query_lower for word in ["recent", "current", "latest", "news"]):
            sources.append("news")

        return sources

    def _identify_context_needs(
        self, sub_query: str, _original_query: str
    ) -> list[str]:
        """Identify what context this sub-query needs from other queries."""
        requirements = []

        query_lower = sub_query.lower()

        if any(word in query_lower for word in ["compare", "difference", "versus"]):
            requirements.append("definition_context")
        if any(word in query_lower for word in ["impact", "effect", "influence"]):
            requirements.append("causal_context")
        if any(word in query_lower for word in ["recent", "current", "development"]):
            requirements.append("historical_context")

        return requirements

    def identify_query_dependencies(
        self, sub_queries: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        """
        Identify dependencies between sub-queries.

        Args:
            sub_queries (List[Dict[str, Any]]): List of sub-queries to analyze.

        Returns:
            Dict[str, List[str]]: Mapping of query IDs to their dependencies.
        """
        try:
            dependencies: dict[str, list[str]] = {}

            for query in sub_queries:
                query_id = query["query_id"]
                dependencies[query_id] = []

                # Check context requirements
                context_requirements = query.get("context_requirements", [])

                for other_query in sub_queries:
                    if other_query["query_id"] == query_id:
                        continue

                    # Check if this query depends on the other query
                    if self._has_dependency(query, other_query, context_requirements):
                        dependencies[query_id].append(other_query["query_id"])

            logger.info(f"Identified dependencies for {len(sub_queries)} sub-queries")
            return dependencies

        except Exception as e:
            logger.error(f"Error identifying query dependencies: {e}")
            return {
                query.get("query_id", f"sq_{i:02d}"): []
                for i, query in enumerate(sub_queries)
            }

    def _has_dependency(
        self,
        query: dict[str, Any],
        potential_prerequisite: dict[str, Any],
        context_requirements: list[str],
    ) -> bool:
        """Check if query depends on potential_prerequisite."""
        query_text = query["query_text"].lower()
        prereq_text = potential_prerequisite["query_text"].lower()
        prereq_type = potential_prerequisite.get("research_type", "")

        # Context-based dependencies
        if "definition_context" in context_requirements and "what is" in prereq_text:
            return True
        if "historical_context" in context_requirements and any(
            word in prereq_text for word in ["history", "background"]
        ):
            return True
        if "causal_context" in context_requirements and any(
            word in prereq_text for word in ["cause", "reason"]
        ):
            return True

        # Type-based dependencies
        if query.get("research_type") == "comparative" and prereq_type == "factual":
            # Comparative queries need factual information first
            return True
        if query.get("research_type") == "analytical" and prereq_type in [
            "factual",
            "comparative",
        ]:
            # Analytical queries need foundation information
            return True

        # Keyword-based dependencies
        if "compare" in query_text and any(
            word in prereq_text for word in ["what", "definition", "characteristics"]
        ):
            return True
        return "impact" in query_text and "cause" in prereq_text

    def prioritize_sub_queries(
        self, sub_queries: list[dict[str, Any]], dependencies: dict[str, list[str]]
    ) -> list[str]:
        """
        Prioritize sub-queries based on importance and dependencies.

        Args:
            sub_queries (List[Dict[str, Any]]): List of sub-queries.
            dependencies (Dict[str, List[str]]): Query dependencies mapping.

        Returns:
            List[str]: Ordered list of query IDs by priority.
        """
        try:
            # Calculate priority scores
            priority_scores = {}
            for query in sub_queries:
                query_id = query["query_id"]

                # Base score from importance
                importance = query.get("importance", 5)
                complexity = query.get("estimated_complexity", 3)

                # Dependency factor - prerequisites should come first
                dependency_penalty = len(dependencies.get(query_id, [])) * 2

                # Prerequisites get bonus (they're needed by others)
                prerequisite_bonus = (
                    sum(1 for deps in dependencies.values() if query_id in deps) * 3
                )

                # Research type priority (context first, then analysis)
                type_bonus = {
                    "factual": 4,
                    "comparative": 2,
                    "analytical": 1,
                    "opinion": 0,
                }.get(query.get("research_type", "factual"), 2)

                priority_scores[query_id] = (
                    importance
                    + prerequisite_bonus
                    + type_bonus
                    - dependency_penalty
                    - complexity
                )

            # Topological sort considering dependencies
            ordered_queries = self._topological_sort(
                sub_queries, dependencies, priority_scores
            )

            logger.info(f"Prioritized {len(ordered_queries)} sub-queries")
            return ordered_queries

        except Exception as e:
            logger.error(f"Error prioritizing sub-queries: {e}")
            return [q.get("query_id", f"sq_{i:02d}") for i, q in enumerate(sub_queries)]

    def _topological_sort(
        self,
        sub_queries: list[dict[str, Any]],
        dependencies: dict[str, list[str]],
        priority_scores: dict[str, float],
    ) -> list[str]:
        """Perform topological sort with priority consideration."""
        # Build reverse dependency graph
        in_degree = {q["query_id"]: 0 for q in sub_queries}
        graph: dict[str, list[str]] = {q["query_id"]: [] for q in sub_queries}

        for query_id, deps in dependencies.items():
            for dep in deps:
                if dep in graph:
                    graph[dep].append(query_id)
                    in_degree[query_id] += 1

        # Start with queries that have no dependencies
        available = [q_id for q_id, degree in in_degree.items() if degree == 0]
        available.sort(key=lambda x: priority_scores.get(x, 0), reverse=True)

        result = []

        while available:
            # Take highest priority available query
            current = available.pop(0)
            result.append(current)

            # Update in-degrees and add newly available queries
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    # Insert in priority order
                    neighbor_priority = priority_scores.get(neighbor, 0)
                    inserted = False
                    for i, existing in enumerate(available):
                        if priority_scores.get(existing, 0) < neighbor_priority:
                            available.insert(i, neighbor)
                            inserted = True
                            break
                    if not inserted:
                        available.append(neighbor)

        # Handle any circular dependencies (shouldn't happen with good decomposition)
        remaining = [q_id for q_id in in_degree if q_id not in result]
        if remaining:
            remaining.sort(key=lambda x: priority_scores.get(x, 0), reverse=True)
            result.extend(remaining)

        return result

    def create_research_strategy(
        self,
        query: str,
        sub_queries: list[dict[str, Any]],
        dependencies: dict[str, list[str]],
    ) -> dict[str, Any]:
        """
        Create a comprehensive research strategy with sequenced tasks.

        Args:
            query (str): The original research query.
            sub_queries (List[Dict[str, Any]]): List of prioritized sub-queries.
            dependencies (Dict[str, List[str]]): Query dependencies mapping.

        Returns:
            Dict[str, Any]: Comprehensive research strategy.
        """
        try:
            from datetime import datetime

            # Get execution order
            execution_order = self.prioritize_sub_queries(sub_queries, dependencies)

            # Estimate duration
            total_complexity = sum(
                q.get("estimated_complexity", 3) for q in sub_queries
            )
            estimated_duration = max(
                30, total_complexity * 5
            )  # 5 minutes per complexity point

            # Identify potential challenges
            challenges = self._identify_potential_challenges(sub_queries, dependencies)

            # Define success criteria
            success_criteria = [
                "All sub-queries have been researched with credible sources",
                "Dependencies between sub-queries have been satisfied",
                "Sufficient information gathered to address the original query",
                "Sources have been cross-referenced for consistency",
                "Key findings have been synthesized into coherent response",
            ]

            strategy = {
                "strategy_id": f"strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "original_query": query,
                "sub_queries": sub_queries,
                "dependencies": dependencies,
                "execution_order": execution_order,
                "estimated_duration": estimated_duration,
                "success_criteria": success_criteria,
                "potential_challenges": challenges,
                "research_phases": self._create_research_phases(
                    sub_queries, execution_order
                ),
                "created_at": datetime.now().isoformat(),
            }

            logger.info(
                f"Created research strategy with {len(sub_queries)} sub-queries, estimated duration: {estimated_duration} minutes"
            )
            return strategy

        except Exception as e:
            logger.error(f"Error creating research strategy: {e}")
            return {
                "strategy_id": "error_strategy",
                "original_query": query,
                "sub_queries": sub_queries,
                "dependencies": dependencies,
                "execution_order": [
                    q.get("query_id", f"sq_{i:02d}") for i, q in enumerate(sub_queries)
                ],
                "estimated_duration": 60,
                "success_criteria": ["Complete research on original query"],
                "potential_challenges": ["Strategy creation failed"],
                "error": str(e),
            }

    def _identify_potential_challenges(
        self, sub_queries: list[dict[str, Any]], dependencies: dict[str, list[str]]
    ) -> list[str]:
        """Identify potential challenges in the research strategy."""
        challenges = []

        # Check for high complexity queries
        high_complexity = [
            q for q in sub_queries if q.get("estimated_complexity", 3) > 4
        ]
        if high_complexity:
            challenges.append(
                f"High complexity queries detected: {len(high_complexity)} queries may require extended research"
            )

        # Check for long dependency chains
        max_chain_length = (
            max(len(deps) for deps in dependencies.values()) if dependencies else 0
        )
        if max_chain_length > 3:
            challenges.append(
                f"Long dependency chains detected: some queries depend on {max_chain_length} others"
            )

        # Check for queries requiring multiple source types
        multi_source = [
            q for q in sub_queries if len(q.get("suggested_sources", [])) > 2
        ]
        if multi_source:
            challenges.append(
                f"Multi-source research needed: {len(multi_source)} queries require diverse source types"
            )

        # Check for comparative or analytical queries
        complex_types = [
            q
            for q in sub_queries
            if q.get("research_type") in ["comparative", "analytical"]
        ]
        if complex_types:
            challenges.append(
                f"Complex analysis required: {len(complex_types)} queries need comparative or analytical research"
            )

        return challenges

    def _create_research_phases(
        self, sub_queries: list[dict[str, Any]], execution_order: list[str]
    ) -> list[dict[str, Any]]:
        """Create research phases for parallel execution where possible."""
        phases = []
        query_map = {q["query_id"]: q for q in sub_queries}
        processed: set[str] = set()

        phase_num = 1

        while len(processed) < len(sub_queries):
            # Find queries that can be executed in this phase
            phase_queries = []

            for query_id in execution_order:
                if query_id in processed:
                    continue

                # Check if dependencies are satisfied
                # This is a simplified check - in reality would check actual dependencies
                phase_queries.append(query_id)

                if len(phase_queries) >= 3:  # Limit phase size for manageability
                    break

            if phase_queries:
                phases.append(
                    {
                        "phase_number": phase_num,
                        "phase_name": f"Research Phase {phase_num}",
                        "query_ids": phase_queries,
                        "can_parallel": len(phase_queries) > 1,
                        "estimated_duration": sum(
                            query_map[qid].get("estimated_complexity", 3) * 5
                            for qid in phase_queries
                        ),
                    }
                )
                processed.update(phase_queries)
                phase_num += 1
            else:
                # Avoid infinite loop
                break

        return phases


# Module exports
__all__ = [
    "QueryDecomposer",
]
