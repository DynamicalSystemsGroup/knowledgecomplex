"""
Operations ontology — actor / activity / resource workflows.

Models operational processes where actors perform activities that
require and produce resources.

Vertex types:
    actor       — a person, team, or agent (name)
    activity    — a process, task, or workflow (name)
    resource    — a dataset, document, or artifact (name)

Edge types:
    performs    — actor↔activity (role: lead/support)
    requires    — activity↔resource, input dependency (mode: read/write)
    produces    — activity↔resource, output artifact (mode: read/write)
    accesses    — actor↔resource, direct access (mode: read/write)
    responsible — actor↔resource, ownership (level: owner/steward)

Face types:
    operation   — actor + activity + input resource triad
    production  — actor + activity + output resource triad
"""

from knowledgecomplex.schema import SchemaBuilder, vocab, text


def schema(namespace: str = "ops") -> SchemaBuilder:
    """Return a SchemaBuilder configured for the operations ontology."""
    sb = SchemaBuilder(namespace=namespace)

    sb.add_vertex_type("actor",    attributes={"name": text()})
    sb.add_vertex_type("activity", attributes={"name": text()})
    sb.add_vertex_type("resource", attributes={"name": text()})

    sb.add_edge_type("performs",     attributes={"role": vocab("lead", "support")})
    sb.add_edge_type("requires",    attributes={"mode": vocab("read", "write")})
    sb.add_edge_type("produces",    attributes={"mode": vocab("read", "write")})
    sb.add_edge_type("accesses",    attributes={"mode": vocab("read", "write")})
    sb.add_edge_type("responsible", attributes={"level": vocab("owner", "steward")})

    sb.add_face_type("operation")
    sb.add_face_type("production")

    return sb
