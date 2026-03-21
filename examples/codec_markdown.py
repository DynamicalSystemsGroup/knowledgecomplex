"""
codec_markdown.py — Reusable MarkdownCodec for YAML-frontmatter + markdown files.

Implements the Codec protocol for knowledge complexes where each element
is a markdown file with YAML frontmatter (metadata) and a markdown body
with predefined section headers (content).

This follows the pattern used in production knowledge complexes authored
in Obsidian — each element is a .md file, the YAML header holds structured
attributes, and ## sections hold prose content.

Usage::

    from codec_markdown import MarkdownCodec, verify_documents

    codec = MarkdownCodec(
        frontmatter_attrs=["name", "author", "abstract"],
        section_attrs=["notes", "methodology"],
    )
    kc.register_codec("Paper", codec)

    # Compile: KC element → markdown file
    kc.element("paper-1").compile()

    # Decompile: markdown file → KC element attributes
    kc.element("paper-1").decompile()
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class MarkdownCodec:
    """Codec for YAML-frontmatter + markdown files.

    Attributes are stored in two places in each markdown file:

    - **YAML frontmatter** (between ``---`` delimiters): structured metadata
      fields like ``name``, ``author``, ``description``. These map 1:1 to
      KC element attributes.

    - **Markdown body sections** (``## Header`` blocks): prose content like
      notes or analysis. The section header becomes the attribute name
      (lowercased, spaces replaced with underscores), and the section body
      becomes the attribute value.

    Parameters
    ----------
    frontmatter_attrs : list[str]
        Attribute names stored in the YAML frontmatter.
    section_attrs : list[str]
        Attribute names stored as ``## Section`` blocks in the body.
    """

    def __init__(
        self,
        frontmatter_attrs: list[str],
        section_attrs: list[str],
    ) -> None:
        self.frontmatter_attrs = list(frontmatter_attrs)
        self.section_attrs = list(section_attrs)

    def compile(self, element: dict) -> None:
        """Write an element record to a markdown file at its URI.

        Parameters
        ----------
        element : dict
            Keys: ``id``, ``type``, ``uri``, plus all attribute key-value pairs.
        """
        uri = element["uri"]
        path = Path(uri.replace("file://", ""))
        path.parent.mkdir(parents=True, exist_ok=True)

        # Build YAML frontmatter
        fm: dict[str, Any] = {
            "id": element["id"],
            "type": element["type"],
        }
        for attr in self.frontmatter_attrs:
            if attr in element:
                fm[attr] = element[attr]

        # Build markdown body
        title = element.get("name", element["id"])
        lines = [f"# {title}", ""]
        for attr in self.section_attrs:
            header = attr.replace("_", " ").title()
            content = element.get(attr, "")
            lines.append(f"## {header}")
            lines.append("")
            lines.append(content if content else "(empty)")
            lines.append("")

        # Write file
        fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False).strip()
        body = "\n".join(lines)
        path.write_text(f"---\n{fm_str}\n---\n\n{body}\n")

    def decompile(self, uri: str) -> dict:
        """Read a markdown file and return attribute key-value pairs.

        Parameters
        ----------
        uri : str
            File URI (``file://`` prefix stripped automatically).

        Returns
        -------
        dict
            Attribute key-value pairs (no ``id``, ``type``, or ``uri``).
        """
        path = Path(uri.replace("file://", ""))
        text = path.read_text()

        # Split frontmatter from body
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not fm_match:
            raise ValueError(f"No YAML frontmatter found in {path}")

        fm_raw = fm_match.group(1)
        body = fm_match.group(2)

        # Parse YAML frontmatter
        fm = yaml.safe_load(fm_raw) or {}
        attrs: dict[str, str] = {}
        for attr in self.frontmatter_attrs:
            if attr in fm:
                attrs[attr] = str(fm[attr])

        # Parse ## sections from body
        section_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
        sections = {}
        matches = list(section_pattern.finditer(body))
        for i, m in enumerate(matches):
            header = m.group(1).strip().lower().replace(" ", "_")
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            content = body[start:end].strip()
            if content == "(empty)":
                content = ""
            sections[header] = content

        for attr in self.section_attrs:
            if attr in sections:
                attrs[attr] = sections[attr]

        return attrs


def verify_documents(
    kc: Any,
    directory: str | Path,
) -> list[str]:
    """Check consistency between KC elements and markdown files on disk.

    Verifies:
    - Every element with a URI has a corresponding file
    - Every ``.md`` file in the directory has a corresponding element
    - Attribute values in files match the KC (via decompile)

    Parameters
    ----------
    kc : KnowledgeComplex
    directory : str or Path
        Root directory containing the markdown files.

    Returns
    -------
    list[str]
        Discrepancy messages. Empty list means everything is consistent.
    """
    directory = Path(directory)
    issues: list[str] = []

    # Collect URIs from KC elements
    uri_to_id: dict[str, str] = {}
    for eid in kc.element_ids():
        elem = kc.element(eid)
        if elem.uri:
            uri_to_id[elem.uri] = eid
            fpath = Path(elem.uri.replace("file://", ""))
            if not fpath.exists():
                issues.append(f"MISSING FILE: {eid} -> {fpath}")

    # Check for orphan files (in directory but not in KC)
    for md_file in sorted(directory.rglob("*.md")):
        file_uri = f"file://{md_file}"
        if file_uri not in uri_to_id:
            issues.append(f"ORPHAN FILE: {md_file} (no element in KC)")

    # Check attribute consistency
    for uri, eid in sorted(uri_to_id.items()):
        fpath = Path(uri.replace("file://", ""))
        if not fpath.exists():
            continue
        elem = kc.element(eid)
        try:
            codec = kc._resolve_codec(elem.type)
            file_attrs = codec.decompile(uri)
            kc_attrs = elem.attrs
            for key in file_attrs:
                if key in kc_attrs and file_attrs[key] != kc_attrs[key]:
                    issues.append(
                        f"MISMATCH: {eid}.{key} — "
                        f"KC='{kc_attrs[key][:40]}' vs file='{file_attrs[key][:40]}'"
                    )
        except Exception as e:
            issues.append(f"ERROR reading {eid}: {e}")

    return issues
