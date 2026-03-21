# Examples

Each example is a self-contained script in its own directory.
Generated outputs (PNGs, temp files) go into an `output/` subdirectory.

| # | Directory | What it demonstrates |
|---|-----------|---------------------|
| 01 | `01_quickstart/` | Load a pre-built complex, discover triangles via clique detection, add faces, see topology change |
| 02 | `02_construction/` | Build a complex from scratch with schema, vertices, edges, faces, Betti numbers, and visualization |
| 03 | `03_topology/` | All 8 topological operators (boundary, coboundary, star, closure, link, etc.) with set algebra |
| 04 | `04_clique_inference/` | Explore-inspect-type workflow: find_cliques, infer_faces, edge_type filtering |
| 05 | `05_constraints/` | Schema-level query registration and topological constraint escalation to SHACL |
| 06 | `06_io_roundtrip/` | Multi-format I/O (Turtle, JSON-LD, N-Triples), additive loading, directory export/load |
| 07 | `07_filtration/` | Proper filtration: startup growing over quarters, birth tracking, Betti number evolution |
| 08 | `08_temporal_sweep/` | Non-filtration time slicing: elements with active_from/active_until, parameterized queries |
| 09 | `09_diff_sequence/` | ComplexDiff and ComplexSequence: sprint-by-sprint evolution with SPARQL UPDATE export/import |
| 10 | `10_markdown_codec/` | MarkdownCodec: round-trip KC elements to YAML+markdown files, verify consistency |
| 11 | `11_local_partition/` | Local partitioning via diffusion: PageRank, heat kernel, Hodge edge partition on a barbell graph |

## Running

From the repository root:

```sh
pip install knowledgecomplex[analysis,viz]
python examples/01_quickstart/quickstart.py
```

Each script prints its results and saves any generated images to its `output/` directory.
