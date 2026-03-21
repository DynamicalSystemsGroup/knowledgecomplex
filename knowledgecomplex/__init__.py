# knowledgecomplex — typed simplicial complexes backed by OWL, SHACL, and SPARQL.
# Internal dependencies: rdflib, pyshacl, owlrl
# These are never re-exported. The public API is schema.py and graph.py only.

from knowledgecomplex.schema import SchemaBuilder, vocab, text, TextDescriptor, Codec
from knowledgecomplex.graph import KnowledgeComplex, Element
from knowledgecomplex.filtration import Filtration
from knowledgecomplex.exceptions import ValidationError, SchemaError, UnknownQueryError
from knowledgecomplex.io import save_graph, load_graph, dump_graph
from knowledgecomplex.clique import find_cliques, infer_faces, fill_cliques
from knowledgecomplex.viz import (
    to_networkx, verify_networkx, type_color_map,
    plot_hasse, plot_hasse_star, plot_hasse_skeleton,
    plot_geometric, plot_geometric_interactive,
    plot_complex, plot_star, plot_skeleton,  # deprecated aliases
)

try:
    from knowledgecomplex.analysis import (
        boundary_matrices,
        betti_numbers,
        euler_characteristic,
        hodge_laplacian,
        edge_pagerank,
        edge_pagerank_all,
        hodge_decomposition,
        edge_influence,
        hodge_analysis,
        BoundaryMatrices,
        HodgeDecomposition,
        EdgeInfluence,
        HodgeAnalysisResults,
    )
    _HAS_ANALYSIS = True
except ImportError:
    _HAS_ANALYSIS = False

__all__ = [
    "SchemaBuilder",
    "vocab",
    "text",
    "TextDescriptor",
    "Codec",
    "KnowledgeComplex",
    "Element",
    "Filtration",
    "ValidationError",
    "SchemaError",
    "UnknownQueryError",
    "save_graph",
    "load_graph",
    "dump_graph",
    "to_networkx",
    "verify_networkx",
    "type_color_map",
    "plot_hasse",
    "plot_hasse_star",
    "plot_hasse_skeleton",
    "plot_geometric",
    "plot_geometric_interactive",
    "plot_complex",
    "plot_star",
    "plot_skeleton",
    "find_cliques",
    "infer_faces",
    "fill_cliques",
]

if _HAS_ANALYSIS:
    __all__ += [
        "boundary_matrices",
        "betti_numbers",
        "euler_characteristic",
        "hodge_laplacian",
        "edge_pagerank",
        "edge_pagerank_all",
        "hodge_decomposition",
        "edge_influence",
        "hodge_analysis",
        "BoundaryMatrices",
        "HodgeDecomposition",
        "EdgeInfluence",
        "HodgeAnalysisResults",
    ]
