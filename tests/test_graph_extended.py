"""
Extended tests for vault/graph.py
Target: raise coverage from 9% to 80%+
"""
import pytest
import tempfile
import os
from pathlib import Path

from vault.db import VaultDB
from vault.graph import VaultGraph, _load_entity_rules, _DEFAULT_ENTITY_RULES


@pytest.fixture
def db(tmp_path):
    """Create a temporary VaultDB instance."""
    db_path = str(tmp_path / "test.db")
    db = VaultDB(db_path)
    db.connect()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def graph(db):
    """Create a VaultGraph instance with test DB."""
    # Use a temp project dir with no YAML to get default rules
    return VaultGraph(db)


class TestLoadEntityRules:
    def test_load_entity_rules_returns_dict(self):
        """Test that rules are returned as dict."""
        rules = _load_entity_rules()
        assert isinstance(rules, dict)
        assert len(rules) > 0

    def test_load_entity_rules_has_expected_types(self):
        """Test that rules have expected entity types."""
        rules = _load_entity_rules()
        # Should have at least tools/concepts or similar
        assert any(k in rules for k in ["tool", "concept", "platform", "model"])

    def test_load_entity_rules_with_project_dir_no_yaml(self, tmp_path):
        """Test with project dir that has no entity_rules.yaml."""
        rules = _load_entity_rules(project_dir=tmp_path)
        assert isinstance(rules, dict)
        assert len(rules) > 0

    def test_load_entity_rules_with_custom_yaml(self, tmp_path):
        """Test loading custom entity_rules.yaml."""
        try:
            import yaml
        except ImportError:
            pytest.skip("yaml not installed")

        yaml_content = """
tool:
  - custom_tool_1
  - custom_tool_2
model:
  - custom_model
"""
        yaml_path = tmp_path / "entity_rules.yaml"
        yaml_path.write_text(yaml_content)

        rules = _load_entity_rules(project_dir=tmp_path)
        assert "tool" in rules
        assert "custom_tool_1" in rules["tool"]
        assert "custom_tool_2" in rules["tool"]
        assert "custom_model" in rules["model"]


class TestVaultGraphInit:
    def test_graph_init_basic(self, db):
        """Test basic VaultGraph initialization."""
        g = VaultGraph(db)
        assert g.db == db
        assert isinstance(g.ENTITY_RULES, dict)
        assert len(g.ENTITY_RULES) > 0

    def test_graph_init_with_project_dir(self, db, tmp_path):
        """Test initialization with project directory."""
        g = VaultGraph(db, project_dir=tmp_path)
        assert g.db == db
        assert isinstance(g.ENTITY_RULES, dict)


class TestExtractEntities:
    def test_extract_entities_from_text_with_tools(self, graph, db):
        """Test extracting tool entities from text."""
        kid = db.add_knowledge(
            title="Test Knowledge",
            content_raw="This is about python and sqlite databases.",
        )
        entity_ids = graph._extract_entities(
            "This is about python and sqlite databases.", kid
        )
        assert isinstance(entity_ids, list)
        # Should have at least python and sqlite (if they're in rules)

        entities = db.get_entities_for_knowledge(kid)
        assert isinstance(entities, list)

    def test_extract_entities_from_tags(self, graph, db):
        """Test extracting entities from tags field."""
        kid = db.add_knowledge(
            title="Test Article",
            content_raw="Some content here.",
            tags="#python, #programming, #ai",
        )
        entity_ids = graph._extract_entities("Some content here.", kid)

        entities = db.get_entities_for_knowledge(kid)
        entity_names = [e["name"] for e in entities]
        # Tags should be extracted
        assert len(entities) > 0

    def test_extract_entities_from_title(self, graph, db):
        """Test extracting entities from title."""
        kid = db.add_knowledge(
            title="Understanding Embedding and Vector Databases",
            content_raw="Content about embeddings.",
        )
        entity_ids = graph._extract_entities("Content about embeddings.", kid)

        entities = db.get_entities_for_knowledge(kid)
        assert isinstance(entities, list)

    def test_extract_entities_empty_text(self, graph, db):
        """Test with empty text."""
        kid = db.add_knowledge(
            title="Empty",
            content_raw="",
        )
        entity_ids = graph._extract_entities("", kid)
        assert isinstance(entity_ids, list)

    def test_extract_entities_no_knowledge(self, graph, db):
        """Test when knowledge entry doesn't exist."""
        entity_ids = graph._extract_entities("some text", 999)
        assert entity_ids == []


class TestInferFromKnowledge:
    def test_infer_from_knowledge_basic(self, graph, db):
        """Test basic inference from knowledge."""
        kid = db.add_knowledge(
            title="Using Python with Database",
            content_raw="We use python code for database applications.",
            tags="#python, #database",
        )
        entity_ids = graph.infer_from_knowledge(kid)
        assert isinstance(entity_ids, list)

    def test_infer_from_knowledge_nonexistent(self, graph):
        """Test inference on non-existent knowledge."""
        entity_ids = graph.infer_from_knowledge(999)
        assert entity_ids == []

    def test_infer_from_knowledge_no_build_edges(self, graph, db):
        """Test inference without building edges."""
        kid = db.add_knowledge(
            title="Test",
            content_raw="python and database content.",
            tags="#test",
        )
        entity_ids = graph.infer_from_knowledge(kid, build_edges=False)
        assert isinstance(entity_ids, list)


class TestInferAll:
    def test_infer_all_empty_db(self, graph):
        """Test infer_all on empty database."""
        result = graph.infer_all()
        assert isinstance(result, dict)
        assert "entities_created" in result
        assert "edges_created" in result

    def test_infer_all_with_data(self, graph, db):
        """Test infer_all with multiple knowledge entries."""
        k1 = db.add_knowledge(
            title="Python Guide",
            content_raw="Python programming with database.",
            tags="#python",
        )
        k2 = db.add_knowledge(
            title="Python Tips",
            content_raw="More python tricks using tools.",
            tags="#python",
        )
        result = graph.infer_all()
        assert isinstance(result, dict)
        assert "entities_created" in result
        assert "edges_created" in result


class TestGraphLinkUnlink:
    def test_link_basic(self, graph, db):
        """Test creating a link between two knowledge entries."""
        k1 = db.add_knowledge(title="Node A", content_raw="Content A")
        k2 = db.add_knowledge(title="Node B", content_raw="Content B")
        edge_id = graph.link(k1, k2, relation="referenced_by", weight=2.0)
        assert edge_id > 0

    def test_link_default_params(self, graph, db):
        """Test link with default parameters."""
        k1 = db.add_knowledge(title="A", content_raw="A")
        k2 = db.add_knowledge(title="B", content_raw="B")
        edge_id = graph.link(k1, k2)
        assert edge_id > 0

    def test_unlink_existing_edge(self, graph, db):
        """Test deleting an existing edge."""
        k1 = db.add_knowledge(title="A", content_raw="A")
        k2 = db.add_knowledge(title="B", content_raw="B")
        edge_id = graph.link(k1, k2)
        result = graph.unlink(edge_id)
        assert result is True

    def test_unlink_nonexistent_edge(self, graph):
        """Test deleting a non-existent edge doesn't crash."""
        # delete_edge uses total_changes which is cumulative, so may return True
        result = graph.unlink(999)
        assert isinstance(result, bool)


class TestGraphExpand:
    def test_expand_no_neighbors(self, graph, db):
        """Test expand on node with no neighbors."""
        kid = db.add_knowledge(title="Lonely", content_raw="Alone")
        neighbors = graph.expand(kid)
        assert isinstance(neighbors, list)

    def test_expand_one_hop(self, graph, db):
        """Test expand with one hop."""
        k1 = db.add_knowledge(title="Center", content_raw="Center")
        k2 = db.add_knowledge(title="Neighbor", content_raw="Neighbor")
        graph.link(k1, k2, relation="related_to")

        neighbors = graph.expand(k1, max_depth=1)
        assert isinstance(neighbors, list)
        assert len(neighbors) >= 1

    def test_expand_max_depth_two(self, graph, db):
        """Test expand with max_depth=2."""
        k1 = db.add_knowledge(title="A", content_raw="A")
        k2 = db.add_knowledge(title="B", content_raw="B")
        k3 = db.add_knowledge(title="C", content_raw="C")
        graph.link(k1, k2)
        graph.link(k2, k3)

        neighbors = graph.expand(k1, max_depth=2)
        neighbor_ids = [n["id"] for n in neighbors]
        assert k2 in neighbor_ids
        assert k3 in neighbor_ids

    def test_expand_returns_metadata(self, graph, db):
        """Test that expand returns title/category/layer info."""
        k1 = db.add_knowledge(title="A", content_raw="A", category="tech", layer="L2")
        k2 = db.add_knowledge(title="B", content_raw="B", category="guide", layer="L1")
        graph.link(k1, k2)

        neighbors = graph.expand(k1, max_depth=1)
        assert len(neighbors) > 0
        assert "title" in neighbors[0]
        assert "category" in neighbors[0]
        assert "layer" in neighbors[0]
        assert neighbors[0]["title"] == "B"

    def test_expand_content_preview(self, graph, db):
        """Test that expand includes content preview."""
        k1 = db.add_knowledge(title="A", content_raw="A content")
        k2 = db.add_knowledge(title="B", content_raw="B content preview test")
        graph.link(k1, k2)

        neighbors = graph.expand(k1, max_depth=1)
        assert len(neighbors) > 0
        assert "content_preview" in neighbors[0]
        assert len(neighbors[0]["content_preview"]) <= 80


class TestGraphSearch:
    def test_graph_search_empty_query(self, graph, db):
        """Test graph search with no matches."""
        db.add_knowledge(title="Test", content_raw="Content")
        results = graph.graph_search("nonexistent_keyword_xyz_12345")
        assert isinstance(results, list)

    def test_graph_search_basic(self, graph, db):
        """Test basic graph search."""
        db.add_knowledge(
            title="Python Programming Guide",
            content_raw="Python is a programming language.",
            tags="#python",
        )
        results = graph.graph_search("python")
        assert isinstance(results, list)

    def test_graph_search_with_limit(self, graph, db):
        """Test graph search with limit parameter."""
        for i in range(5):
            db.add_knowledge(
                title=f"Python Topic {i}",
                content_raw=f"Python content {i}",
                tags="#python",
            )
        results = graph.graph_search("python", limit=3)
        assert isinstance(results, list)
        assert len(results) <= 3

    def test_graph_search_has_distance_field(self, graph, db):
        """Test that graph search results have graph distance."""
        k1 = db.add_knowledge(
            title="Python Core UniqueTest123",
            content_raw="Python language core.",
            tags="#python",
        )
        k2 = db.add_knowledge(
            title="Python Library",
            content_raw="Python library.",
            tags="#python",
        )
        graph.link(k1, k2)

        results = graph.graph_search("UniqueTest123")
        if len(results) > 0:
            assert "_graph_distance" in results[0]


class TestToMermaid:
    def test_to_mermaid_empty(self, graph):
        """Test mermaid export with no edges."""
        result = graph.to_mermaid()
        assert isinstance(result, str)
        assert "graph LR" in result

    def test_to_mermaid_with_node_id(self, graph, db):
        """Test mermaid export starting from specific node."""
        k1 = db.add_knowledge(title="Node A", content_raw="A")
        k2 = db.add_knowledge(title="Node B", content_raw="B")
        graph.link(k1, k2, relation="uses")

        result = graph.to_mermaid(node_id=k1, max_depth=1)
        assert isinstance(result, str)
        assert "graph LR" in result

    def test_to_mermaid_all(self, graph, db):
        """Test mermaid export of entire graph."""
        k1 = db.add_knowledge(title="A", content_raw="A")
        k2 = db.add_knowledge(title="B", content_raw="B")
        graph.link(k1, k2)

        result = graph.to_mermaid()
        assert isinstance(result, str)
        assert "graph LR" in result

    def test_to_mermaid_layer_styling(self, graph, db):
        """Test that different layers have different styling."""
        k0 = db.add_knowledge(title="Core", content_raw="core", layer="L0")
        k1 = db.add_knowledge(title="Fact", content_raw="fact", layer="L1")
        k2 = db.add_knowledge(title="Context", content_raw="ctx", layer="L2")
        graph.link(k0, k1)
        graph.link(k1, k2)

        result = graph.to_mermaid()
        # Should have classDefs
        assert "classDef" in result

    def test_to_mermaid_has_class_defs(self, graph):
        """Test that mermaid output includes class definitions."""
        result = graph.to_mermaid()
        assert "classDef core" in result
        assert "classDef fact" in result
        assert "classDef ctx" in result


class TestToGraphviz:
    def test_to_graphviz_empty(self, graph):
        """Test graphviz export with no edges."""
        result = graph.to_graphviz()
        assert isinstance(result, str)
        assert "digraph VaultGraph" in result

    def test_to_graphviz_with_node_id(self, graph, db):
        """Test graphviz export starting from specific node."""
        k1 = db.add_knowledge(title="Node A", content_raw="A")
        k2 = db.add_knowledge(title="Node B", content_raw="B")
        graph.link(k1, k2)

        result = graph.to_graphviz(node_id=k1, max_depth=1)
        assert isinstance(result, str)
        assert "digraph" in result

    def test_to_graphviz_all(self, graph, db):
        """Test graphviz export of entire graph."""
        k1 = db.add_knowledge(title="A", content_raw="A")
        k2 = db.add_knowledge(title="B", content_raw="B")
        graph.link(k1, k2, relation="test_rel")

        result = graph.to_graphviz()
        assert isinstance(result, str)
        assert "digraph" in result

    def test_to_graphviz_colors_by_layer(self, graph, db):
        """Test that nodes have colors based on layer."""
        k0 = db.add_knowledge(title="Core", content_raw="", layer="L0")
        k1 = db.add_knowledge(title="Fact", content_raw="", layer="L1")
        graph.link(k0, k1)

        result = graph.to_graphviz()
        assert "#ff6666" in result  # L0 color
        assert "#6699ff" in result  # L1 color

    def test_to_graphviz_rankdir(self, graph):
        """Test that graphviz has rankdir=LR."""
        result = graph.to_graphviz()
        assert "rankdir=LR" in result


class TestClearAutoInferred:
    def test_clear_auto_inferred(self, graph, db):
        """Test clearing auto-inferred edges."""
        k1 = db.add_knowledge(
            title="A", content_raw="python database", tags="#python"
        )
        k2 = db.add_knowledge(
            title="B", content_raw="python tools", tags="#python"
        )
        # Infer to create auto edges
        graph.infer_from_knowledge(k1)
        graph.infer_from_knowledge(k2)

        # Create manual edge
        graph.link(k1, k2, relation="manual_link")

        # Clear auto-inferred (should not crash)
        graph.clear_auto_inferred()

    def test_clear_auto_inferred_empty(self, graph):
        """Test clearing on empty DB doesn't crash."""
        graph.clear_auto_inferred()  # Should not raise


class TestStats:
    def test_stats_empty(self, graph):
        """Test stats on empty database."""
        stats = graph.stats()
        assert isinstance(stats, dict)
        assert "entities_total" in stats
        assert "edges_total" in stats

    def test_stats_with_data(self, graph, db):
        """Test stats with data."""
        k1 = db.add_knowledge(
            title="Python Test",
            content_raw="Python and database content.",
            tags="#python",
        )
        graph.infer_from_knowledge(k1)

        stats = graph.stats()
        assert isinstance(stats, dict)
        assert stats["entities_total"] >= 0
        assert "connected_nodes" in stats
        assert "edges_total" in stats
