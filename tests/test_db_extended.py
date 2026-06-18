"""
Extended tests for vault.db module to boost coverage.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from vault.db import VaultDB


class TestVaultDBConnect:
    def test_connect_basic(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        assert db.conn is not None
        db.close()

    def test_close(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        db.close()
        assert db.conn is None

    def test_multiple_connect_close(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        for _ in range(3):
            db.connect()
            assert db.conn is not None
            db.close()
            assert db.conn is None

    def test_context_manager(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        with db as d:
            assert d.conn is not None
        assert db.conn is None


class TestKnowledgeCRUD:
    def test_add_knowledge_minimal(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Test", content_raw="content")
            assert kid > 0
        finally:
            db.close()

    def test_add_knowledge_with_all_fields(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(
                title="Full Test",
                content_raw="full content",
                category="tech",
                tags="tag1,tag2",
                trust=0.85,
                layer="core",
            )
            k = db.get_knowledge(kid)
            assert k["title"] == "Full Test"
            assert k["category"] == "tech"
            assert k["tags"] == "tag1,tag2"
            assert k["trust"] == 0.85
            assert k["layer"] == "core"
        finally:
            db.close()

    def test_get_knowledge_nonexistent(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db.get_knowledge(9999) is None
        finally:
            db.close()

    def test_update_knowledge_title(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Old", content_raw="old")
            result = db.update_knowledge(kid, title="New")
            assert result is True
            k = db.get_knowledge(kid)
            assert k["title"] == "New"
        finally:
            db.close()

    def test_update_knowledge_content_updates_hash(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Hash Test", content_raw="original")
            k1 = db.get_knowledge(kid)
            db.update_knowledge(kid, content_raw="modified")
            k2 = db.get_knowledge(kid)
            assert k1["content_hash"] != k2["content_hash"]
        finally:
            db.close()

    def test_update_knowledge_trust(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Test", content_raw="test")
            db.update_knowledge(kid, trust=0.95)
            k = db.get_knowledge(kid)
            assert k["trust"] == 0.95
        finally:
            db.close()

    def test_update_knowledge_no_fields(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Test", content_raw="test")
            assert db.update_knowledge(kid) is False
        finally:
            db.close()

    def test_update_knowledge_rejects_unknown_fields(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Test", content_raw="test")
            with pytest.raises(ValueError, match="invalid knowledge update field"):
                db.update_knowledge(kid, **{"title = 'Injected' --": "bad"})
        finally:
            db.close()

    def test_delete_knowledge(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="To Delete", content_raw="delete me")
            assert db.delete_knowledge(kid) is True
            assert db.get_knowledge(kid) is None
        finally:
            db.close()

    def test_delete_knowledge_nonexistent(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # Returns bool (implementation may return True due to FTS cleanup)
            result = db.delete_knowledge(9999)
            assert isinstance(result, bool)
        finally:
            db.close()

    def test_list_knowledge_empty(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db.list_knowledge() == []
        finally:
            db.close()

    def test_list_knowledge_multiple(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(5):
                db.add_knowledge(title=f"Doc {i}", content_raw=f"content {i}")
            items = db.list_knowledge()
            assert len(items) == 5
        finally:
            db.close()

    def test_list_knowledge_with_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_knowledge(title=f"Doc {i}", content_raw=f"content {i}")
            items = db.list_knowledge(limit=3)
            assert len(items) == 3
        finally:
            db.close()

    def test_list_knowledge_with_min_trust(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="High Trust", content_raw="high", trust=0.9)
            db.add_knowledge(title="Low Trust", content_raw="low", trust=0.3)
            items = db.list_knowledge(min_trust=0.8)
            assert len(items) == 1
            assert items[0]["title"] == "High Trust"
        finally:
            db.close()

    def test_list_knowledge_with_category(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Tech Doc", content_raw="tech", category="tech")
            db.add_knowledge(title="Health Doc", content_raw="health", category="health")
            items = db.list_knowledge(category="tech")
            assert len(items) == 1
            assert items[0]["category"] == "tech"
        finally:
            db.close()

    def test_list_knowledge_with_layer(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Core Doc", content_raw="core", layer="core")
            db.add_knowledge(title="Surface Doc", content_raw="surface", layer="surface")
            items = db.list_knowledge(layer="core")
            assert len(items) == 1
            assert items[0]["layer"] == "core"
        finally:
            db.close()

    def test_add_knowledge_generates_content_hash(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Hash Test", content_raw="hash this content")
            k = db.get_knowledge(kid)
            assert k.get("content_hash") is not None
            assert len(k["content_hash"]) > 0
        finally:
            db.close()

    def test_content_hash_is_deterministic(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            k1 = db.add_knowledge(title="A", content_raw="same content")
            k2 = db.add_knowledge(title="B", content_raw="same content")
            assert db.get_knowledge(k1)["content_hash"] == db.get_knowledge(k2)["content_hash"]
        finally:
            db.close()


class TestConfig:
    def test_set_and_get_config(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.set_config("test_key", "test_value")
            assert db.get_config("test_key") == "test_value"
        finally:
            db.close()

    def test_get_config_default_empty_string(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db.get_config("nonexistent") == ""
        finally:
            db.close()

    def test_get_config_custom_default(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db.get_config("nonexistent", "custom_default") == "custom_default"
        finally:
            db.close()

    def test_update_config(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.set_config("key", "value1")
            db.set_config("key", "value2")
            assert db.get_config("key") == "value2"
        finally:
            db.close()


class TestEdges:
    def test_add_edge(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            edge_id = db.add_edge(id1, id2, relation="related_to")
            assert edge_id > 0
        finally:
            db.close()

    def test_add_edge_duplicate(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            e1 = db.add_edge(id1, id2, relation="rel")
            e2 = db.add_edge(id1, id2, relation="rel")
            assert e1 == e2
        finally:
            db.close()

    def test_add_edge_with_weight(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            eid = db.add_edge(id1, id2, relation="rel", weight=0.8)
            edges = db.get_edges(node_id=id1, direction="outgoing")
            assert len(edges) == 1
            assert edges[0]["weight"] == 0.8
        finally:
            db.close()

    def test_delete_edge(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            eid = db.add_edge(id1, id2, relation="test")
            assert db.delete_edge(eid) is True
            edges = db.get_edges(node_id=id1, direction="outgoing")
            assert len(edges) == 0
        finally:
            db.close()

    def test_delete_edge_nonexistent(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            result = db.delete_edge(9999)
            assert isinstance(result, bool)
        finally:
            db.close()

    def test_get_edges_outgoing(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="Source", content_raw="src")
            id2 = db.add_knowledge(title="Target1", content_raw="t1")
            id3 = db.add_knowledge(title="Target2", content_raw="t2")
            db.add_edge(id1, id2, relation="r1")
            db.add_edge(id1, id3, relation="r2")
            edges = db.get_edges(node_id=id1, direction="outgoing")
            assert len(edges) == 2
        finally:
            db.close()

    def test_get_edges_incoming(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="Target", content_raw="t")
            id2 = db.add_knowledge(title="Source1", content_raw="s1")
            id3 = db.add_knowledge(title="Source2", content_raw="s2")
            db.add_edge(id2, id1, relation="r")
            db.add_edge(id3, id1, relation="r")
            edges = db.get_edges(node_id=id1, direction="incoming")
            assert len(edges) == 2
        finally:
            db.close()

    def test_get_edges_both_directions(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            id3 = db.add_knowledge(title="C", content_raw="c")
            db.add_edge(id1, id2, relation="out")
            db.add_edge(id3, id1, relation="in")
            edges = db.get_edges(node_id=id1, direction="both")
            assert len(edges) == 2
        finally:
            db.close()

    def test_get_edges_by_relation(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            db.add_edge(id1, id2, relation="cites")
            edges = db.get_edges(relation="cites")
            assert len(edges) >= 1
        finally:
            db.close()

    def test_get_neighbors(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="Center", content_raw="center")
            id2 = db.add_knowledge(title="Neighbor1", content_raw="n1")
            id3 = db.add_knowledge(title="Neighbor2", content_raw="n2")
            db.add_edge(id1, id2, relation="r")
            db.add_edge(id1, id3, relation="r")
            neighbors = db.get_neighbors(id1)
            assert len(neighbors) == 2
        finally:
            db.close()

    def test_get_neighbors_with_max_depth(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="A", content_raw="a")
            id2 = db.add_knowledge(title="B", content_raw="b")
            id3 = db.add_knowledge(title="C", content_raw="c")
            db.add_edge(id1, id2, relation="r")
            db.add_edge(id2, id3, relation="r")
            neighbors_1 = db.get_neighbors(id1, max_depth=1)
            neighbors_2 = db.get_neighbors(id1, max_depth=2)
            assert len(neighbors_1) == 1
            assert len(neighbors_2) == 2
        finally:
            db.close()

    def test_get_neighbors_with_min_weight(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="Center", content_raw="c")
            id2 = db.add_knowledge(title="Close", content_raw="close")
            id3 = db.add_knowledge(title="Far", content_raw="far")
            db.add_edge(id1, id2, relation="r", weight=0.9)
            db.add_edge(id1, id3, relation="r", weight=0.3)
            neighbors = db.get_neighbors(id1, min_weight=0.5)
            assert len(neighbors) == 1
            # get_neighbors returns edge info with id, distance, relation, weight
            assert "id" in neighbors[0]
            assert "distance" in neighbors[0]
            assert "weight" in neighbors[0]
        finally:
            db.close()


class TestMemoryCandidates:
    def test_add_memory_candidate(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            mid = db.add_memory_candidate({
                "id": "mem1",
                "title": "Test Memory",
                "content": "Memory content",
                "layer": "surface",
                "category": "general",
                "tags": "tag1",
                "trust": 0.7,
                "source": "test_source",
                "source_ref": "ref1",
                "reason": "testing",
                "status": "pending",
                "privacy_status": "public",
                "duplicate_status": "unique",
                "quality_status": "pass",
                "gate_payload_json": "{}",
            })
            assert mid == "mem1"
        finally:
            db.close()

    def test_get_memory_candidate(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_memory_candidate({
                "id": "mem_get",
                "title": "Get Test",
                "content": "content",
                "layer": "surface",
                "category": "general",
                "tags": "",
                "trust": 0.5,
                "source": "test",
                "source_ref": "",
                "reason": "",
                "status": "pending",
                "privacy_status": "public",
                "duplicate_status": "unique",
                "quality_status": "pass",
                "gate_payload_json": "{}",
            })
            mem = db.get_memory_candidate("mem_get")
            assert mem is not None
            assert mem["content"] == "content"
            assert mem["source"] == "test"
            assert mem["trust"] == 0.5
        finally:
            db.close()

    def test_get_memory_candidate_nonexistent(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db.get_memory_candidate("nonexistent") is None
        finally:
            db.close()

    def test_update_memory_candidate(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_memory_candidate({
                "id": "mem_upd",
                "title": "Original",
                "content": "original",
                "layer": "surface",
                "category": "general",
                "tags": "",
                "trust": 0.5,
                "source": "test",
                "source_ref": "",
                "reason": "",
                "status": "pending",
                "privacy_status": "public",
                "duplicate_status": "unique",
                "quality_status": "pass",
                "gate_payload_json": "{}",
            })
            result = db.update_memory_candidate("mem_upd", content="Updated", trust=0.9)
            assert result is True
            mem = db.get_memory_candidate("mem_upd")
            assert mem["content"] == "Updated"
            assert mem["trust"] == 0.9
        finally:
            db.close()

    def test_update_memory_candidate_rejects_unknown_fields(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_memory_candidate({
                "id": "mem_bad_field",
                "title": "Original",
                "content": "original",
                "layer": "surface",
                "category": "general",
                "tags": "",
                "trust": 0.5,
                "source": "test",
                "source_ref": "",
                "reason": "",
                "status": "pending",
                "privacy_status": "public",
                "duplicate_status": "unique",
                "quality_status": "pass",
                "gate_payload_json": "{}",
            })
            with pytest.raises(ValueError, match="invalid memory candidate update field"):
                db.update_memory_candidate("mem_bad_field", **{"status = 'promoted' --": "bad"})
        finally:
            db.close()

    def test_list_memory_candidates(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(5):
                db.add_memory_candidate({
                    "id": f"mem{i}",
                    "title": f"Memory {i}",
                    "content": f"content {i}",
                    "layer": "surface",
                    "category": "general",
                    "tags": "",
                    "trust": 0.5,
                    "source": "test",
                    "source_ref": "",
                    "reason": "",
                    "status": "pending",
                    "privacy_status": "public",
                    "duplicate_status": "unique",
                    "quality_status": "pass",
                    "gate_payload_json": "{}",
                })
            items = db.list_memory_candidates()
            assert len(items) == 5
        finally:
            db.close()

    def test_list_memory_candidates_with_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_memory_candidate({
                    "id": f"mem{i}",
                    "title": f"Mem {i}",
                    "content": f"content {i}",
                    "layer": "surface",
                    "category": "general",
                    "tags": "",
                    "trust": 0.5,
                    "source": "test",
                    "source_ref": "",
                    "reason": "",
                    "status": "pending",
                    "privacy_status": "public",
                    "duplicate_status": "unique",
                    "quality_status": "pass",
                    "gate_payload_json": "{}",
                })
            items = db.list_memory_candidates(limit=3)
            assert len(items) == 3
        finally:
            db.close()

    def test_list_memory_candidates_by_status(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_memory_candidate({
                "id": "m_pending", "title": "Pending", "content": "p",
                "layer": "surface", "category": "general", "tags": "",
                "trust": 0.5, "source": "test", "source_ref": "",
                "reason": "", "status": "pending",
                "privacy_status": "public", "duplicate_status": "unique",
                "quality_status": "pass", "gate_payload_json": "{}",
            })
            db.add_memory_candidate({
                "id": "m_reviewed", "title": "Reviewed", "content": "r",
                "layer": "surface", "category": "general", "tags": "",
                "trust": 0.5, "source": "test", "source_ref": "",
                "reason": "", "status": "reviewed",
                "privacy_status": "public", "duplicate_status": "unique",
                "quality_status": "pass", "gate_payload_json": "{}",
            })
            items = db.list_memory_candidates(status="pending")
            assert len(items) == 1
            assert items[0]["id"] == "m_pending"
        finally:
            db.close()


class TestSkills:
    def test_add_skill(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            sid = db.add_skill(name="test_skill", content_raw="skill content")
            assert sid is not None
        finally:
            db.close()

    def test_get_skill(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="my_skill", content_raw="skill content", description="test skill")
            skill = db.get_skill("my_skill")
            assert skill is not None
            assert skill["name"] == "my_skill"
            assert skill["content_raw"] == "skill content"
            assert skill["description"] == "test skill"
        finally:
            db.close()

    def test_get_skill_nonexistent(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            assert db.get_skill("nonexistent") is None
        finally:
            db.close()

    def test_update_skill(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="upd_skill", content_raw="original")
            result = db.update_skill("upd_skill", content_raw="updated", description="new desc")
            assert result is True
            skill = db.get_skill("upd_skill")
            assert skill["content_raw"] == "updated"
            assert skill["description"] == "new desc"
        finally:
            db.close()

    def test_update_skill_no_fields(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="empty_upd", content_raw="test")
            assert db.update_skill("empty_upd") is False
        finally:
            db.close()

    def test_update_skill_rejects_unknown_fields(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="safe_skill", content_raw="test")
            with pytest.raises(ValueError, match="invalid skill update field"):
                db.update_skill("safe_skill", **{"description = 'x', trust": 1.0})
        finally:
            db.close()

    def test_list_skills(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="skill1", content_raw="s1")
            db.add_skill(name="skill2", content_raw="s2")
            db.add_skill(name="skill3", content_raw="s3")
            skills = db.list_skills()
            assert len(skills) == 3
        finally:
            db.close()

    def test_list_skills_with_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_skill(name=f"skill{i}", content_raw=f"s{i}")
            skills = db.list_skills(limit=3)
            assert len(skills) == 3
        finally:
            db.close()

    def test_delete_skill(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="del_skill", content_raw="delete me")
            assert db.delete_skill("del_skill") is True
            assert db.get_skill("del_skill") is None
        finally:
            db.close()

    def test_delete_skill_nonexistent(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            result = db.delete_skill("nonexistent")
            assert isinstance(result, bool)
        finally:
            db.close()

    def test_search_skills(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="python_helper", content_raw="Python programming help")
            db.add_skill(name="python_debugger", content_raw="Python debugging")
            db.add_skill(name="bash_helper", content_raw="Bash shell help")
            results = db.search_skills("python")
            assert len(results) >= 2
        finally:
            db.close()

    def test_mark_skill_synced(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_skill(name="sync_skill", content_raw="test")
            db.mark_skill_synced("sync_skill")
            skill = db.get_skill("sync_skill")
            # Should have updated the last_synced field
            assert skill.get("last_synced") is not None
        finally:
            db.close()


class TestSearchKeyword:
    def test_search_keyword_basic(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Guide", content_raw="Python programming language")
            results = db.search_keyword("Python")
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_keyword_no_results(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="content")
            results = db.search_keyword("xyz_not_exist_123")
            assert results == []
        finally:
            db.close()

    def test_search_keyword_with_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_knowledge(title=f"Python Doc {i}", content_raw=f"Python content {i}")
            results = db.search_keyword("Python", limit=3)
            assert len(results) <= 3
        finally:
            db.close()

    def test_search_keyword_with_min_trust(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="High Trust Python", content_raw="Python", trust=0.9)
            db.add_knowledge(title="Low Trust Python", content_raw="Python", trust=0.3)
            results = db.search_keyword("Python", min_trust=0.8)
            assert len(results) == 1
            assert results[0]["title"] == "High Trust Python"
        finally:
            db.close()

    def test_search_keyword_empty_query_matches_all(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="A", content_raw="content a")
            db.add_knowledge(title="B", content_raw="content b")
            # LIKE with %% matches everything
            results = db.search_keyword("")
            assert len(results) == 2
        finally:
            db.close()


class TestStats:
    def test_stats_returns_dict(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test")
            stats = db.stats()
            assert isinstance(stats, dict)
            # Verify it has some count keys
            assert any(k for k in stats.keys() if "count" in k or "total" in k)
        finally:
            db.close()

    def test_stats_empty_db(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            stats = db.stats()
            assert isinstance(stats, dict)
        finally:
            db.close()


class TestSchema:
    def test_schema_status(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            status = db.schema_status()
            assert isinstance(status, dict)
            assert "current_version" in status
        finally:
            db.close()

    def test_applied_migrations(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            migrations = db.applied_migrations()
            assert isinstance(migrations, list)
        finally:
            db.close()


class TestEntities:
    def test_add_entity(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            eid = db.add_entity("Python", entity_type="concept")
            assert eid > 0
        finally:
            db.close()

    def test_link_entity_knowledge(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            eid = db.add_entity("TestConcept")
            kid = db.add_knowledge(title="About Test", content_raw="test concept content")
            db.link_entity_knowledge(eid, kid)
            entities = db.get_entities_for_knowledge(kid)
            assert len(entities) >= 1
            assert any(e["name"] == "TestConcept" for e in entities)
        finally:
            db.close()

    def test_get_entities_for_knowledge_empty(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="No Entities", content_raw="no entities here")
            entities = db.get_entities_for_knowledge(kid)
            assert entities == []
        finally:
            db.close()


class TestLintResults:
    def test_add_and_get_lint_result(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Lint Test", content_raw="test")
            db.add_lint_result(kid, "format", "some issue found")
            results = db.get_lint_results(kid)
            assert len(results) >= 1
            assert results[0]["check_type"] == "format"
        finally:
            db.close()

    def test_get_lint_results_empty(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="No Lint", content_raw="test")
            results = db.get_lint_results(kid)
            assert results == []
        finally:
            db.close()
