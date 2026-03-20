# knowledgecomplex — typed simplicial complexes backed by OWL, SHACL, and SPARQL.
# Internal dependencies: rdflib, pyshacl, owlrl
# These are never re-exported. The public API is schema.py and graph.py only.

from knowledgecomplex.schema import SchemaBuilder, vocab, text, TextDescriptor
from knowledgecomplex.graph import KnowledgeComplex
from knowledgecomplex.exceptions import ValidationError, SchemaError, UnknownQueryError

__all__ = [
    "SchemaBuilder",
    "vocab",
    "text",
    "TextDescriptor",
    "KnowledgeComplex",
    "ValidationError",
    "SchemaError",
    "UnknownQueryError",
]
