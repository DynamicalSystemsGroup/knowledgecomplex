"""
knowledgecomplex.exceptions — Public exception types.

These are the only knowledgecomplex types that cross the API boundary on failure.
"""


class ValidationError(Exception):
    """
    Raised when a SHACL validation check fails on write.

    Attributes
    ----------
    report : str
        Human-readable SHACL validation report text.
    """

    def __init__(self, message: str, report: str) -> None:
        super().__init__(message)
        self.report = report

    def __str__(self) -> str:
        return f"{super().__str__()}\n\nSHACL Report:\n{self.report}"


class UnknownQueryError(Exception):
    """
    Raised when KnowledgeComplex.query() is called with an unregistered template name.
    """
    pass


class SchemaError(Exception):
    """
    Raised when a SchemaBuilder method is called with invalid arguments,
    e.g. referencing an undefined type.
    """
    pass
