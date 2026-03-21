"""
Research ontology — paper / concept / note for literature review.

Models research literature and personal annotations. Papers discuss
concepts, cite each other, and notes connect ideas across papers.
Suitable for Obsidian-style knowledge management.

Vertex types:
    paper   — a research paper or article (title, year)
    concept — an idea, method, or theory (name)
    note    — a personal note or annotation (title)

Edge types:
    discusses — paper↔concept: paper engages with this concept
        depth: primary/secondary

    cites — paper↔paper: citation relationship. Since KC edges are
        unoriented, direction is encoded as an attribute.
        role: cites/cited_by
        context: supports/extends/critiques

    connects — note↔concept: note links to a concept
        relation: defines/questions/applies

    references — note↔paper: note references this paper
        purpose: summarizes/responds_to/builds_on

Face types:
    synthesis — paper↔paper↔concept: two papers in a citation
        relationship that both discuss the same concept. Captures
        intellectual lineage through shared conceptual ground.

    annotation — note↔paper↔concept: a note references a paper
        and connects to a concept the paper discusses. Captures
        the reader's engagement with a specific idea in a specific work.
"""

from knowledgecomplex.schema import SchemaBuilder, vocab, text


def schema(namespace: str = "res") -> SchemaBuilder:
    """Return a SchemaBuilder configured for the research ontology."""
    sb = SchemaBuilder(namespace=namespace)

    sb.add_vertex_type("paper", attributes={
        "title": text(),
        "year": text(required=False),
    })
    sb.add_vertex_type("concept", attributes={
        "name": text(),
    })
    sb.add_vertex_type("note", attributes={
        "title": text(),
    })

    sb.add_edge_type("discusses", attributes={
        "depth": vocab("primary", "secondary"),
    })
    sb.add_edge_type("cites", attributes={
        "role": vocab("cites", "cited_by"),
        "context": vocab("supports", "extends", "critiques"),
    })
    sb.add_edge_type("connects", attributes={
        "relation": vocab("defines", "questions", "applies"),
    })
    sb.add_edge_type("references", attributes={
        "purpose": vocab("summarizes", "responds_to", "builds_on"),
    })

    sb.add_face_type("synthesis")
    sb.add_face_type("annotation")

    return sb
