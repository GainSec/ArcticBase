"""Parse and serialize the workbench `theme.md` format.

The file is YAML frontmatter (between `---` fences) followed by a Markdown prose body.
"""

from __future__ import annotations

import io

from ruamel.yaml import YAML

from arctic_base.models import (
    REQUIRED_CORE_TOKENS,
    REQUIRED_ROUNDED,
    REQUIRED_SPACING,
    REQUIRED_TYPOGRAPHY,
    Theme,
    ThemeTokens,
)
from arctic_base.storage.errors import InvalidTheme

_yaml = YAML(typ="safe")
_yaml.default_flow_style = False


def parse_theme_md(raw: str) -> Theme:
    frontmatter, prose = _split(raw)
    if not frontmatter:
        raise InvalidTheme("theme.md is missing the YAML frontmatter section")
    try:
        data = _yaml.load(frontmatter) or {}
    except Exception as e:
        raise InvalidTheme(f"theme.md frontmatter is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise InvalidTheme("theme.md frontmatter must be a YAML mapping")
    tokens = ThemeTokens.model_validate(data)
    _validate_required(tokens)
    return Theme(tokens=tokens, prose=prose)


def serialize_theme(theme: Theme) -> str:
    """Round-trip a Theme back to `theme.md` format."""

    buf = io.StringIO()
    dump = YAML()
    dump.default_flow_style = False
    dump.dump(theme.tokens.model_dump(exclude_none=True, exclude_defaults=False), buf)
    fm = buf.getvalue().rstrip("\n")
    return f"---\n{fm}\n---\n\n{theme.prose}"


def _split(raw: str) -> tuple[str, str]:
    text = raw.lstrip("﻿")
    if not text.startswith("---"):
        return "", text
    rest = text[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end == -1:
        return "", text
    frontmatter = rest[:end]
    after = rest[end + 4 :]
    if after.startswith("\n"):
        after = after[1:]
    return frontmatter, after


def _validate_required(tokens: ThemeTokens) -> None:
    missing_core = [k for k in REQUIRED_CORE_TOKENS if k not in tokens.core]
    if missing_core:
        raise InvalidTheme(f"theme is missing required core tokens: {missing_core}")
    missing_typo = [k for k in REQUIRED_TYPOGRAPHY if k not in tokens.typography]
    if missing_typo:
        raise InvalidTheme(f"theme is missing required typography styles: {missing_typo}")
    missing_rounded = [k for k in REQUIRED_ROUNDED if k not in tokens.rounded]
    if missing_rounded:
        raise InvalidTheme(f"theme is missing required rounded scale: {missing_rounded}")
    missing_spacing = [k for k in REQUIRED_SPACING if k not in tokens.spacing]
    if missing_spacing:
        raise InvalidTheme(f"theme is missing required spacing scale: {missing_spacing}")
