from vault.db import VaultDB


def test_graph_helper_reuses_duplicate_edges_and_filters_direction(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        kid1 = db.add_knowledge(title="First", content_raw="first")
        kid2 = db.add_knowledge(title="Second", content_raw="second")
        edge_id = db.add_edge(kid1, kid2, relation="related", weight=0.7)
        duplicate_id = db.add_edge(kid1, kid2, relation="related", weight=0.9)
        db.add_edge(kid2, kid1, relation="related", weight=0.5)

        assert duplicate_id == edge_id
        outgoing = db.get_edges(node_id=kid1, direction="outgoing")
        incoming = db.get_edges(node_id=kid1, direction="incoming")
        assert [edge["target_id"] for edge in outgoing] == [kid2]
        assert [edge["source_id"] for edge in incoming] == [kid2]
    finally:
        db.close()


def test_graph_helper_neighbors_clamps_filters_and_invalid_inputs(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        kid1 = db.add_knowledge(title="Root", content_raw="root", trust=0.9, layer="L2", category="project")
        kid2 = db.add_knowledge(title="Allowed", content_raw="allowed", trust=0.8, layer="L2", category="project")
        kid3 = db.add_knowledge(title="Filtered", content_raw="filtered", trust=0.2, layer="L3", category="other")
        db.add_edge(kid1, kid2, weight=0.7)
        db.add_edge(kid2, kid3, weight=0.7)

        assert db.get_neighbors(None) == []
        neighbors = db.get_neighbors(kid1, max_depth=99, min_trust=0.5, layer="L2", category="project")
        assert [row["id"] for row in neighbors] == [kid2]
        assert neighbors[0]["distance"] == 1
    finally:
        db.close()


def test_graph_helper_entities_and_knowledge_links_are_idempotent(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        kid = db.add_knowledge(title="Entity doc", content_raw="entity doc")
        entity_id = db.add_entity("Vault", "project")
        assert db.add_entity("Vault", "concept") == entity_id

        db.link_entity_knowledge(entity_id, kid)
        db.link_entity_knowledge(entity_id, kid)

        entities = db.get_entities_for_knowledge(kid)
        knowledge_ids = db.get_knowledge_for_entity("Vault")
        assert len(entities) == 1
        assert entities[0]["name"] == "Vault"
        assert knowledge_ids == [kid]
    finally:
        db.close()
