"""knowledgecomplex.codecs — Built-in codec implementations.

Codecs bridge KC elements and external artifact formats.
Each codec implements the :class:`~knowledgecomplex.schema.Codec` protocol.
"""

from knowledgecomplex.codecs.markdown import MarkdownCodec, verify_documents

__all__ = ["MarkdownCodec", "verify_documents"]
