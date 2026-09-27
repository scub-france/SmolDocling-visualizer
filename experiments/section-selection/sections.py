"""Section candidates of a DoclingDocument, as docling-agent's RAG loop sees them.

Mirrors ``DoclingRAGAgent`` at docling-agent 9c754cf (docling_agent/agent/rag.py):

- candidates are the ``TitleItem`` / ``SectionHeaderItem`` refs (``_extract_section_refs``);
- a section's text is its subtree text when the header has children, i.e. in a
  hierarchized document (``collect_subtree_text``), otherwise a forward scan until the
  next header at the same or a shallower depth (``_collect_flat_section_text``).

``own_text`` leaves nested sections out: evidence is attributed to the most specific
section, and its ancestors are recorded separately. tests/test_sections.py checks
parity with docling-agent when it is installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from docling_core.types.doc import (
    DoclingDocument,
    NodeItem,
    RefItem,
    SectionHeaderItem,
    TitleItem,
)

_HEADER_TYPES = (TitleItem, SectionHeaderItem)


@dataclass(frozen=True)
class Section:
    ref: str
    heading: str
    level: int  # 0 for a TitleItem, SectionHeaderItem.level otherwise
    parents: tuple[str, ...]  # enclosing sections, outermost first
    text: str  # what docling-agent hands to the LLM for this section
    own_text: str  # the section without its nested sections


def _resolve(doc: DoclingDocument, ref: str) -> NodeItem | None:
    try:
        return RefItem(cref=ref).resolve(doc)
    except Exception:
        return None


def subtree_text(node: NodeItem, doc: DoclingDocument) -> str:
    """Same output as docling-agent's ``collect_subtree_text``."""
    parts: list[str] = []
    if getattr(node, "text", None):
        parts.append(node.text)
    for child_ref in node.children or []:
        child = _resolve(doc, child_ref.cref)
        if child:
            sub = subtree_text(child, doc)
            if sub:
                parts.append(sub)
    return "\n".join(parts)


def flat_section_text(doc: DoclingDocument, section_ref: str) -> str:
    """Same output as ``DoclingRAGAgent._collect_flat_section_text``."""
    texts: list[str] = []
    in_section = False
    section_depth: int | None = None
    for item, depth in doc.iterate_items():
        if item.self_ref == section_ref:
            in_section = True
            section_depth = depth
            if getattr(item, "text", None):
                texts.append(item.text)
            continue
        if in_section:
            if (
                isinstance(item, _HEADER_TYPES)
                and section_depth is not None
                and depth <= section_depth
            ):
                break
            if getattr(item, "text", None):
                texts.append(item.text)
    return "\n\n".join(texts)


def agent_section_text(doc: DoclingDocument, section_ref: str) -> str:
    """Same output as ``DoclingRAGAgent._get_section_content`` in section mode."""
    node = _resolve(doc, section_ref)
    if node is None:
        return ""
    if len(node.children or []) == 0 and isinstance(node, _HEADER_TYPES):
        return flat_section_text(doc, section_ref)
    return subtree_text(node, doc)


def _own_text(node: NodeItem, doc: DoclingDocument) -> str:
    if len(node.children or []) == 0:
        return flat_section_text(doc, node.self_ref)
    parts = [node.text] if getattr(node, "text", None) else []
    for child_ref in node.children:
        child = _resolve(doc, child_ref.cref)
        if child is None or isinstance(child, _HEADER_TYPES):
            continue
        sub = subtree_text(child, doc)
        if sub:
            parts.append(sub)
    return "\n".join(parts)


def _parents(node: NodeItem, doc: DoclingDocument) -> tuple[str, ...]:
    chain: list[str] = []
    parent_ref = node.parent
    while parent_ref is not None:
        parent = _resolve(doc, parent_ref.cref)
        if parent is None:
            break
        if isinstance(parent, _HEADER_TYPES):
            chain.append(parent.self_ref)
        parent_ref = parent.parent
    return tuple(reversed(chain))


def extract_sections(doc: DoclingDocument) -> list[Section]:
    """All section candidates in reading order."""
    sections: list[Section] = []
    for item, _depth in doc.iterate_items():
        if not isinstance(item, _HEADER_TYPES):
            continue
        sections.append(
            Section(
                ref=item.self_ref,
                heading=item.text,
                level=0 if isinstance(item, TitleItem) else item.level,
                parents=_parents(item, doc),
                text=agent_section_text(doc, item.self_ref),
                own_text=_own_text(item, doc),
            )
        )
    return sections
