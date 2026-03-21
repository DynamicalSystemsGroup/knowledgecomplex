"""
knowledgecomplex.audit — Verification and audit tooling.

Terminology:
  - **verify**: deterministic, automated checks (SHACL constraints, type
    guards, cardinality). These are pass/fail with no human judgment.
  - **validate**: human review and approval of fitness for purpose.
    Not implemented here — this module is for verification only.

Provides:
  - ``AuditReport`` / ``AuditViolation`` — structured verification results
  - ``audit_file()`` — verify a serialized RDF file against SHACL shapes
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class AuditViolation:
    """A single verification violation from a SHACL report."""
    element_id: str | None
    constraint: str
    message: str

    def __str__(self) -> str:
        eid = self.element_id or "?"
        return f"[{eid}] {self.constraint}: {self.message}"


@dataclass
class AuditReport:
    """Structured result of a SHACL verification pass.

    Attributes
    ----------
    conforms : bool
        True if no violations were found.
    text : str
        Full human-readable SHACL report text.
    violations : list[AuditViolation]
        Parsed individual violations.
    """
    conforms: bool
    text: str
    violations: list[AuditViolation] = field(default_factory=list)

    def __str__(self) -> str:
        if self.conforms:
            return "Verification passed: no violations"
        lines = [f"Verification failed: {len(self.violations)} violation(s)"]
        for v in self.violations:
            lines.append(f"  {v}")
        return "\n".join(lines)

    def __bool__(self) -> bool:
        return self.conforms


def _parse_shacl_report(results_text: str, namespace: str = "") -> list[AuditViolation]:
    """Extract individual violations from a pyshacl results text string."""
    violations = []

    # Split on "Constraint Violation" or "Result" blocks
    # pyshacl output format: blocks separated by blank lines
    blocks = re.split(r"\n\n+", results_text)

    for block in blocks:
        if "Violation" not in block and "Result" not in block:
            continue

        element_id = None
        constraint = ""
        message = ""

        for line in block.strip().split("\n"):
            line = line.strip()
            if line.startswith("Focus Node:"):
                # Extract element ID from IRI
                match = re.search(r"#(\S+)", line)
                if match:
                    element_id = match.group(1)
            elif line.startswith("Source Shape:"):
                match = re.search(r"[#/](\S+?)>?\s*$", line)
                if match:
                    constraint = match.group(1)
            elif line.startswith("Message:"):
                message = line.replace("Message:", "").strip()
            elif line.startswith("Severity:"):
                pass  # could capture severity if needed

        if constraint or message:
            violations.append(AuditViolation(
                element_id=element_id,
                constraint=constraint,
                message=message,
            ))

    return violations


def _build_report(conforms: bool, results_text: str, namespace: str = "") -> AuditReport:
    """Build an AuditReport from pyshacl output."""
    violations = _parse_shacl_report(results_text, namespace) if not conforms else []
    return AuditReport(conforms=conforms, text=results_text, violations=violations)


def audit_file(
    instance_path: str | Path,
    shapes: str | Path,
    ontology: str | Path | None = None,
) -> AuditReport:
    """Verify a serialized RDF file against SHACL shapes.

    Runs pyshacl on static files without instantiating a KnowledgeComplex.
    Useful for CI pipelines and pre-commit hooks.

    Parameters
    ----------
    instance_path : str or Path
        Path to the instance graph (Turtle, JSON-LD, etc.).
    shapes : str or Path
        Path to the SHACL shapes file.
    ontology : str or Path, optional
        Path to the OWL ontology file. If not provided, only SHACL
        shapes are used (no RDFS inference).

    Returns
    -------
    AuditReport
    """
    import pyshacl
    from rdflib import Graph

    instance_path = Path(instance_path)
    shapes = Path(shapes)

    if not instance_path.exists():
        raise FileNotFoundError(f"Instance file not found: {instance_path}")
    if not shapes.exists():
        raise FileNotFoundError(f"Shapes file not found: {shapes}")

    data_graph = Graph()
    data_graph.parse(str(instance_path))

    shacl_graph = Graph()
    shacl_graph.parse(str(shapes))

    ont_graph = None
    if ontology is not None:
        ontology = Path(ontology)
        if not ontology.exists():
            raise FileNotFoundError(f"Ontology file not found: {ontology}")
        ont_graph = Graph()
        ont_graph.parse(str(ontology))
        # Also parse ontology into data graph for type inference
        data_graph.parse(str(ontology))

    conforms, _, results_text = pyshacl.validate(
        data_graph=data_graph,
        shacl_graph=shacl_graph,
        ont_graph=ont_graph,
        inference="rdfs" if ont_graph else None,
        abort_on_first=False,
    )

    return _build_report(conforms, results_text)
