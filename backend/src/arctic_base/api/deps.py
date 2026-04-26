from functools import lru_cache

from arctic_base.config import get_settings
from arctic_base.storage.filesystem import FilesystemStorage


@lru_cache(maxsize=1)
def get_storage() -> FilesystemStorage:
    settings = get_settings()
    return FilesystemStorage(settings.data)
