"""
Generate the pre-built pipeline data for the quickstart example.

Run once:  python examples/_setup_data.py

Creates examples/data/pipeline/ with ontology.ttl, shapes.ttl, instance.ttl
(a data pipeline with actors, activities, resources, and edges — but no faces).
"""

from knowledgecomplex import SchemaBuilder, KnowledgeComplex, vocab, text

# Schema: vertex and edge types only (no faces — those are discovered later)
sb = SchemaBuilder(namespace="ex")
sb.add_vertex_type("actor",    attributes={"name": text()})
sb.add_vertex_type("activity", attributes={"name": text()})
sb.add_vertex_type("resource", attributes={"name": text()})
sb.add_edge_type("performs",     attributes={"role": vocab("lead", "support")})
sb.add_edge_type("requires",    attributes={"mode": vocab("read", "write")})
sb.add_edge_type("produces",    attributes={"mode": vocab("read", "write")})
sb.add_edge_type("accesses",    attributes={"mode": vocab("read", "write")})
sb.add_edge_type("responsible", attributes={"level": vocab("owner", "steward")})

# Instance: 4 vertices, 5 edges forming 2 triangles (but no faces declared)
kc = KnowledgeComplex(schema=sb)
kc.add_vertex("alice",    type="actor",    name="Alice")
kc.add_vertex("etl-run",  type="activity", name="Daily ETL")
kc.add_vertex("dataset1", type="resource", name="JSON Records")
kc.add_vertex("dataset2", type="resource", name="Sales DB")

kc.add_edge("e1", type="performs",    vertices={"alice", "etl-run"},    role="lead")
kc.add_edge("e2", type="requires",   vertices={"etl-run", "dataset1"}, mode="read")
kc.add_edge("e3", type="produces",   vertices={"etl-run", "dataset2"}, mode="write")
kc.add_edge("e4", type="accesses",   vertices={"alice", "dataset1"},   mode="read")
kc.add_edge("e5", type="responsible", vertices={"alice", "dataset2"},  level="owner")

# Export
kc.export("examples/data/pipeline")
print("Exported to examples/data/pipeline/")
print(f"  {len(kc.element_ids())} elements (4 vertices + 5 edges, no faces)")
