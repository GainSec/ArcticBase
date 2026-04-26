from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

ManifestVersion = 1


class BannerKind(StrEnum):
    upload = "upload"
    url = "url"


class Banner(BaseModel):
    kind: BannerKind
    ref: str  # path under workbench dir (for upload) or full URL


class WorkbenchMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_computed_inputs(cls, data: object) -> object:
        """Tolerate manifests that have `view_url` baked in (early-bug recovery).

        `view_url` is a computed_field — never stored — but a transient version of
        this code wrote it to disk. Strip it on load so old manifests still parse.
        """
        if isinstance(data, dict):
            data.pop("view_url", None)
        return data

    version: int = ManifestVersion
    slug: str
    title: str
    description: str = ""
    url: str | None = None
    ip: str | None = None  # e.g. "192.168.13.37" — informational, agent-readable
    local_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    banner: Banner | None = None
    custom_fields: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def view_url(self) -> str:
        """Relative URL the SPA serves for this workbench. Hand to a human / put in chat."""
        return f"/wb/{self.slug}"


class ObjectKind(StrEnum):
    md = "md"
    html = "html"
    approval_html = "approval-html"
    image = "image"
    qa_form = "qa-form"
    file = "file"
    runbook = "runbook"  # JSON-content object: structured task list with checkbox state


class ObjectMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = ManifestVersion
    id: str
    kind: ObjectKind
    title: str
    description: str = ""
    drawer: str = ""
    filename: str = ""
    mime: str = "application/octet-stream"
    size_bytes: int = 0
    etag: str = ""
    created_at: datetime
    updated_at: datetime
    state_version: int = 0
    order: int = 0
    last_accessed_at: datetime | None = None
    pinned: bool = False
    archived: bool = False


class ResponseKind(StrEnum):
    submit = "submit"
    autosave = "autosave"
    agent_edit = "agent-edit"


class Submitter(StrEnum):
    user = "user"
    agent = "agent"
    system = "system"


class ResponseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    object_id: str
    submitted_at: datetime
    submitted_by: Submitter = Submitter.user
    kind: ResponseKind = ResponseKind.submit
    payload: dict[str, Any] = Field(default_factory=dict)


class TypographyStyle(BaseModel):
    model_config = ConfigDict(extra="allow")
    fontFamily: str | None = None
    fontSize: str | None = None
    fontWeight: str | None = None
    lineHeight: str | None = None
    letterSpacing: str | None = None


class LayoutTokens(BaseModel):
    """Structural layout choices for a workbench. All fields optional with sensible defaults.

    Drives composition of the per-workbench dashboard and themed surfaces, beyond just colors.
    """

    model_config = ConfigDict(extra="allow")

    # Padding / gap scale for cards, sections, drawers.
    density: str | None = None  # "compact" | "comfortable" (default) | "spacious"

    # Corner radius bias on cards. Falls back to --wb-rounded-md if unset.
    corners: str | None = None  # "sharp" | "soft" | "rounded" | "full"

    # Card shadow style.
    shadow: str | None = None  # "hard-offset" | "soft" | "glow" | "none"

    # Card visual treatment. The dashboard reads this as a data attribute and applies a
    # matching CSS class set: bolted (4-corner bolts), flat (default, no decoration),
    # floating (soft shadow + hover lift), inset (recessed content).
    card_style: str | None = Field(default=None, alias="card-style")

    # Decorative motif on cards (corner accents).
    motif: str | None = None  # "bolts" | "hex" | "tape" | "none"

    # Banner / hero treatment.
    banner_shape: str | None = Field(default=None, alias="banner-shape")  # "rect" | "t-shape" | "circle" | "none"
    hero_style: str | None = Field(default=None, alias="hero-style")  # "cover" | "flat" | "crt-monitor" | "none"


class ThemeTokens(BaseModel):
    """Structured theme tokens. `core` keys are required and validated by the storage layer."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    core: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, TypographyStyle] = Field(default_factory=dict)
    rounded: dict[str, str] = Field(default_factory=dict)
    spacing: dict[str, str] = Field(default_factory=dict)
    custom: dict[str, str] = Field(default_factory=dict)
    layout: LayoutTokens = Field(default_factory=LayoutTokens)


class Theme(BaseModel):
    tokens: ThemeTokens
    prose: str = ""
    assets: list[str] = Field(default_factory=list)


REQUIRED_CORE_TOKENS = (
    "bg",
    "surface",
    "ink",
    "muted",
    "rule",
    "accent",
    "accent-2",
    "success",
    "error",
)
REQUIRED_TYPOGRAPHY = ("body", "mono")
REQUIRED_ROUNDED = ("sm", "md", "lg")
REQUIRED_SPACING = ("unit", "gutter", "margin")
