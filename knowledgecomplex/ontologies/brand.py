"""
Brand ontology — audience / theme brand strategy.

Models how audiences relate to themes and how themes relate to each
other, capturing both synergies and tensions.

Vertex types:
    audience — a target audience segment (name, description)
    theme    — a brand theme or topic (name, description)

Edge types:
    resonance — audience↔theme: how this theme lands with this audience
        valence: positive/negative/mixed
        intensity: strong/moderate/weak

    interplay — theme↔theme: relationship between themes
        nature: synergy/tension/paradox
        direction: reinforcing/undermining/independent

    overlap — audience↔audience: shared or contested ground
        alignment: agreement/disagreement/partial
        significance: high/moderate/low

Face types:
    thematic_alignment — theme↔theme↔audience: two interplaying themes
        both resonate with the same audience. Captures whether synergies
        or tensions between themes play out positively or negatively for
        a given audience.

    audience_bridge — audience↔audience↔theme: two overlapping audiences
        both engage with the same theme. Captures whether a theme unites
        or divides audiences.
"""

from knowledgecomplex.schema import SchemaBuilder, vocab, text


def schema(namespace: str = "brand") -> SchemaBuilder:
    """Return a SchemaBuilder configured for the brand ontology."""
    sb = SchemaBuilder(namespace=namespace)

    sb.add_vertex_type("audience", attributes={
        "name": text(),
        "description": text(required=False),
    })
    sb.add_vertex_type("theme", attributes={
        "name": text(),
        "description": text(required=False),
    })

    sb.add_edge_type("resonance", attributes={
        "valence": vocab("positive", "negative", "mixed"),
        "intensity": vocab("strong", "moderate", "weak"),
    })
    sb.add_edge_type("interplay", attributes={
        "nature": vocab("synergy", "tension", "paradox"),
        "direction": vocab("reinforcing", "undermining", "independent"),
    })
    sb.add_edge_type("overlap", attributes={
        "alignment": vocab("agreement", "disagreement", "partial"),
        "significance": vocab("high", "moderate", "low"),
    })

    sb.add_face_type("thematic_alignment")
    sb.add_face_type("audience_bridge")

    return sb
