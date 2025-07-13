"""
Tests for source tracker serialization and persistence functionality.

This module tests the enhanced source tracking capabilities including
serialization, persistence, and workflow integration.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from agents.ollama.deep_research.shared import (
    AgentSourceTracker,
    SharedSourceRegistry,
    WorkflowStorage,
    get_storage,
)
from agents.ollama.deep_research.shared.source_tracker_utils import (
    clear_workflow_sources,
    create_agent_source_tracker,
    export_workflow_sources,
    get_workflow_source_summary,
    import_workflow_sources,
)
from agents.ollama.deep_research.shared.types import (
    ResearchSource,
    ResearchWorkflow,
)


class TestSharedSourceRegistry:
    """Tests for SharedSourceRegistry serialization."""

    def test_to_dict_empty_registry(self):
        """Test serialization of empty registry."""
        registry = SharedSourceRegistry()
        data = registry.to_dict()

        assert data == {
            "sources": {},
            "all_accesses": [],
            "agent_accesses": {},
        }

    def test_to_dict_with_data(self):
        """Test serialization of registry with data."""
        registry = SharedSourceRegistry()

        # Add a source
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        registry.register_source(source)

        # Add an access
        tracker = AgentSourceTracker("test_agent", registry)
        tracker.register_access("https://example.com", "search_google", "test query")

        data = registry.to_dict()

        assert "sources" in data
        assert "all_accesses" in data
        assert "agent_accesses" in data
        assert "https://example.com" in data["sources"]
        assert len(data["all_accesses"]) == 1
        assert "test_agent" in data["agent_accesses"]

    def test_from_dict_restoration(self):
        """Test restoration from serialized data."""
        # Create original registry
        original = SharedSourceRegistry()
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        original.register_source(source)

        tracker = AgentSourceTracker("test_agent", original)
        tracker.register_access("https://example.com", "search_google", "test query")

        # Serialize and restore
        data = original.to_dict()
        restored = SharedSourceRegistry.from_dict(data)

        # Verify restoration
        assert restored.has_source("https://example.com")
        assert len(restored.get_all_sources()) == 1
        assert len(restored.get_all_accesses()) == 1
        assert "test_agent" in restored.get_accessing_agents("https://example.com")

    def test_json_serialization(self):
        """Test JSON serialization round-trip."""
        registry = SharedSourceRegistry()

        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        registry.register_source(source)

        # Serialize to JSON and back
        json_str = registry.to_json()
        restored = SharedSourceRegistry.from_json(json_str)

        assert restored.has_source("https://example.com")
        assert len(restored.get_all_sources()) == 1

    def test_clear_registry(self):
        """Test clearing registry data."""
        registry = SharedSourceRegistry()

        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        registry.register_source(source)

        tracker = AgentSourceTracker("test_agent", registry)
        tracker.register_access("https://example.com", "search_google")

        # Clear and verify
        registry.clear()
        assert len(registry.get_all_sources()) == 0
        assert len(registry.get_all_accesses()) == 0


class TestAgentSourceTracker:
    """Tests for AgentSourceTracker serialization."""

    def test_tracker_serialization(self):
        """Test tracker serialization and restoration."""
        registry = SharedSourceRegistry()
        tracker = AgentSourceTracker("test_agent", registry)

        # Add some data
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        tracker.register_source(source)
        tracker.register_access("https://example.com", "search_google", "test query")

        # Serialize and restore
        data = tracker.to_dict()
        restored = AgentSourceTracker.from_dict(data, registry)

        assert restored.agent_id == "test_agent"
        assert len(restored.get_local_accesses()) == 1
        assert len(restored.get_local_sources()) == 1
        assert restored.has_accessed("https://example.com")


class TestWorkflowStorage:
    """Tests for enhanced WorkflowStorage with source tracking."""

    def test_create_workflow_with_source_registry(self):
        """Test workflow creation includes source registry."""
        storage = WorkflowStorage()

        workflow = ResearchWorkflow(
            workflow_id="test_workflow",
            original_query="test query",
            current_phase="decomposition",
            source_tracking_enabled=True,
            source_registry_id="test_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow)

        assert storage.get_workflow("test_workflow") is not None
        assert storage.get_source_registry("test_workflow") is not None

    def test_workflow_file_persistence(self):
        """Test saving and loading workflows to/from files."""
        storage = WorkflowStorage()

        # Create workflow
        workflow = ResearchWorkflow(
            workflow_id="test_workflow",
            original_query="test query",
            current_phase="decomposition",
            source_tracking_enabled=True,
            source_registry_id="test_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow)

        # Add some source data
        registry = storage.get_source_registry("test_workflow")
        assert registry is not None  # Ensure registry exists
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        registry.register_source(source)

        # Save to file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            storage.save_workflow_to_file("test_workflow", filepath)

            # Clear storage and reload
            new_storage = WorkflowStorage()
            workflow_id = new_storage.load_workflow_from_file(filepath)

            assert workflow_id == "test_workflow"
            assert new_storage.get_workflow("test_workflow") is not None
            registry = new_storage.get_source_registry("test_workflow")
            assert registry is not None
            assert registry.has_source("https://example.com")

        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_workflow_summary(self):
        """Test workflow summary with source tracking stats."""
        storage = WorkflowStorage()

        workflow = ResearchWorkflow(
            workflow_id="test_workflow",
            original_query="test query",
            current_phase="decomposition",
            source_tracking_enabled=True,
            source_registry_id="test_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow)

        # Add source data
        registry = storage.get_source_registry("test_workflow")
        assert registry is not None  # Ensure registry exists
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        registry.register_source(source)

        tracker = AgentSourceTracker("test_agent", registry)
        tracker.register_access("https://example.com", "search_google")

        # Get summary
        summary = storage.get_workflow_summary("test_workflow")

        assert summary is not None
        assert summary["workflow_id"] == "test_workflow"
        assert summary["total_sources"] == 1
        assert summary["total_accesses"] == 1
        assert summary["active_agents"] == 1


class TestSourceTrackerUtils:
    """Tests for source tracker utility functions."""

    def test_create_agent_source_tracker(self):
        """Test creating agent source tracker via utility function."""
        # Set up storage with workflow
        storage = get_storage()
        storage.clear_all()  # Start fresh

        workflow = ResearchWorkflow(
            workflow_id="test_workflow",
            original_query="test query",
            current_phase="decomposition",
            source_tracking_enabled=True,
            source_registry_id="test_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow)

        # Create tracker
        tracker = create_agent_source_tracker("test_agent", "test_workflow")

        assert tracker.agent_id == "test_agent"
        assert tracker.shared_registry is not None

    def test_workflow_source_summary(self):
        """Test getting workflow source summary."""
        storage = get_storage()
        storage.clear_all()

        # Create workflow with source data
        workflow = ResearchWorkflow(
            workflow_id="test_workflow",
            original_query="test query",
            current_phase="research",
            source_tracking_enabled=True,
            source_registry_id="test_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow)

        # Add sources through tracker
        tracker = create_agent_source_tracker("web_agent", "test_workflow")

        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        tracker.register_source(source)
        tracker.register_access("https://example.com", "search_google", "test query")

        # Get summary
        summary = get_workflow_source_summary("test_workflow")

        assert summary["workflow_id"] == "test_workflow"
        assert summary["total_sources"] == 1
        assert summary["total_accesses"] == 1
        assert "web_agent" in summary["active_agents"]
        assert "web_agent" in summary["agent_activity"]

    def test_export_import_workflow_sources(self):
        """Test exporting and importing workflow sources."""
        storage = get_storage()
        storage.clear_all()

        # Create source workflow
        workflow1 = ResearchWorkflow(
            workflow_id="source_workflow",
            original_query="source query",
            current_phase="research",
            source_tracking_enabled=True,
            source_registry_id="source_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow1)

        # Add data
        tracker = create_agent_source_tracker("test_agent", "source_workflow")
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        tracker.register_source(source)
        tracker.register_access("https://example.com", "search_google")

        # Export data
        export_data = export_workflow_sources("source_workflow")

        # Create target workflow
        workflow2 = ResearchWorkflow(
            workflow_id="target_workflow",
            original_query="target query",
            current_phase="research",
            source_tracking_enabled=True,
            source_registry_id="target_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow2)

        # Import data
        import_workflow_sources("target_workflow", export_data)

        # Verify import
        summary = get_workflow_source_summary("target_workflow")
        assert summary["total_sources"] == 1
        assert summary["total_accesses"] == 1

    def test_clear_workflow_sources(self):
        """Test clearing workflow sources."""
        storage = get_storage()
        storage.clear_all()

        workflow = ResearchWorkflow(
            workflow_id="test_workflow",
            original_query="test query",
            current_phase="research",
            source_tracking_enabled=True,
            source_registry_id="test_workflow",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        storage.create_workflow(workflow)

        # Add data
        tracker = create_agent_source_tracker("test_agent", "test_workflow")
        source = ResearchSource(
            url="https://example.com",
            title="Test Source",
            content_summary="Test content summary",
        )
        tracker.register_source(source)
        tracker.register_access("https://example.com", "search_google")

        # Verify data exists
        summary = get_workflow_source_summary("test_workflow")
        assert summary["total_sources"] == 1

        # Clear and verify
        clear_workflow_sources("test_workflow")
        summary = get_workflow_source_summary("test_workflow")
        assert summary["total_sources"] == 0
        assert summary["total_accesses"] == 0


if __name__ == "__main__":
    # Run tests manually
    pytest.main([__file__, "-v"])
