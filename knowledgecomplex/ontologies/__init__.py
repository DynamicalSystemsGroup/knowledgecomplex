"""
knowledgecomplex.ontologies — Pre-built ontologies for common domains.

Each module exports a ``schema()`` function returning a configured
:class:`~knowledgecomplex.schema.SchemaBuilder`.

Available ontologies:

- **operations** — actor / activity / resource workflows
- **brand** — audience / theme brand strategy
- **research** — paper / concept / note for literature review

Usage::

    from knowledgecomplex.ontologies import brand
    from knowledgecomplex import KnowledgeComplex

    sb = brand.schema()
    kc = KnowledgeComplex(schema=sb)
"""

from knowledgecomplex.ontologies import operations, brand, research

__all__ = ["operations", "brand", "research"]
