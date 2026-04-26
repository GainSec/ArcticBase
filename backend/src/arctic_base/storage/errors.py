class StorageError(Exception):
    """Base for storage-layer failures."""


class NotFound(StorageError):
    pass


class AlreadyExists(StorageError):
    pass


class StaleETag(StorageError):
    """Raised when If-Match precondition fails on object content writes."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"stale etag: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


class InvalidTheme(StorageError):
    pass
