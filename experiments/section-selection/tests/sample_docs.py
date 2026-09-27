"""Small DoclingDocuments shaped like a Docling PDF conversion: a flat body in reading order."""

from docling_core.types.doc import DocItemLabel, DoclingDocument

INTRO = (
    "Converting PDF documents back into a machine-processable format has been a major "
    "challenge for decades because of their huge variability in formats."
)
MOTIVATION = (
    "Layout analysis and table structure recognition are the two models that matter most "
    "for faithful conversion of scientific papers into structured documents."
)
METHOD = (
    "We fine-tune a small decision model on section labels derived from the evidence "
    "annotations and compare it with a reranker and with the zero-shot model."
)


def paper() -> DoclingDocument:
    """Abstract, 1 Introduction > 1.1 Motivation, 2 Method; levels already inferred."""
    doc = DoclingDocument(name="paper")
    doc.add_title(text="A Small Model for Section Selection")
    doc.add_heading(text="Abstract", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text="We study section selection for retrieval.")
    doc.add_heading(text="1 Introduction", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text=INTRO)
    doc.add_heading(text="1.1 Motivation", level=2)
    doc.add_text(label=DocItemLabel.TEXT, text=MOTIVATION)
    doc.add_heading(text="2 Method", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text=METHOD)
    return doc


def hierarchized_paper() -> DoclingDocument:
    doc = paper()
    doc._hierarchize()
    return doc


def ref_of(doc: DoclingDocument, heading: str) -> str:
    for item, _ in doc.iterate_items():
        if getattr(item, "text", None) == heading:
            return item.self_ref
    raise KeyError(heading)
