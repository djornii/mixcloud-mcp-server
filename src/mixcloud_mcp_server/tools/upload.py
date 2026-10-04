"""Upload and edit tools.

Two things here are load-bearing:

* :func:`safe_file` is the boundary that keeps a prompt-injected path from
  reading arbitrary files off the machine. Do not relax it.
* :func:`meta_fields` validates before the network call, so the model gets a
  precise message instead of an opaque Mixcloud 400.
"""

import mimetypes
import re
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Literal

from .. import client, config
from ..errors import as_tool_error

PICTURE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
AUDIO_EXTS = {".mp3"}
MAX_AUDIO_BYTES = 4 * 1024**3
MAX_PICTURE_BYTES = 10 * 1024**2
MAX_DESCRIPTION_CHARS = 1000
MAX_TAGS = 5
MAX_HOSTS = 2


def safe_file(path: str, exts: set[str], max_bytes: int, what: str) -> Path:
    """Resolve *path* inside the upload directory, or refuse.

    Relative paths resolve against ``MIXCLOUD_UPLOAD_DIR``. Anything that ends up
    outside it raises, which is what stops a path coming from a model's output
    from reading e.g. ``~/.ssh/id_rsa``.
    """
    root = config.ensure_upload_dir()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"{what} must be inside {root}")
    if candidate.suffix.lower() not in exts or not candidate.is_file():
        raise ValueError(f"{what}: expected an existing file with extension {sorted(exts)}")
    if candidate.stat().st_size > max_bytes:
        raise ValueError(f"{what} is too large (max {max_bytes // 1024 // 1024} MB)")
    return candidate


def section_fields(sections: list[dict[str, Any]]) -> dict[str, str]:
    """Flatten sections into the API's indexed ``sections-N-*`` form."""
    out: dict[str, str] = {}
    for i, section in enumerate(sections):
        if section.get("chapter"):
            out[f"sections-{i}-chapter"] = str(section["chapter"])
        elif section.get("artist") and section.get("song"):
            out[f"sections-{i}-artist"] = str(section["artist"])
            out[f"sections-{i}-song"] = str(section["song"])
        else:
            raise ValueError(f"sections[{i}]: need 'chapter', or both 'artist' and 'song'")
        if section.get("start_time") is not None:
            out[f"sections-{i}-start_time"] = str(int(section["start_time"]))
    return out


def meta_fields(
    name: str | None,
    description: str | None,
    tags: list[str] | None,
    sections: list[dict[str, Any]] | None,
    hosts: list[str] | None,
    publish_date: str | None,
    disable_comments: bool | None,
    hide_stats: bool | None,
) -> dict[str, str]:
    """Validate and flatten the metadata shared by upload and edit.

    ``None`` means "leave alone" (edit) or "not supplied" (upload); an empty
    string or empty list is meaningful, so the checks are on ``is None``.
    """
    fields: dict[str, str] = {}
    if name is not None:
        if not name.strip():
            raise ValueError("name is empty")
        fields["name"] = name
    if description is not None:
        if len(description) > MAX_DESCRIPTION_CHARS:
            raise ValueError(f"description: max {MAX_DESCRIPTION_CHARS} characters")
        fields["description"] = description
    if tags:
        if len(tags) > MAX_TAGS:
            raise ValueError(f"max {MAX_TAGS} tags")
        fields.update({f"tags-{i}-tag": tag for i, tag in enumerate(tags)})
    if sections:
        fields.update(section_fields(sections))
    if hosts is not None:
        if len(hosts) > MAX_HOSTS:
            raise ValueError(f"max {MAX_HOSTS} hosts")
        if hosts:
            fields.update({f"hosts-{i}-username": host for i, host in enumerate(hosts)})
        else:
            fields["hosts-0-username"] = ""  # the API removes every host this way
    if publish_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", publish_date):
            raise ValueError("publish_date must look like 2030-11-21T14:05:00Z (UTC)")
        fields["publish_date"] = publish_date
    if disable_comments is not None:
        fields["disable_comments"] = "true" if disable_comments else "false"
    if hide_stats is not None:
        fields["hide_stats"] = "true" if hide_stats else "false"
    return fields


def form_fields(fields: dict[str, str]) -> list[tuple[str, tuple]]:
    """Plain fields as multipart parts. The API only accepts multipart/form-data."""
    return [(k, (None, v)) for k, v in fields.items()]


def upload_show(
    audio_path: str,
    name: str,
    description: str | None = None,
    tags: list[str] | None = None,
    sections: list[dict[str, Any]] | None = None,
    picture_path: str | None = None,
    unlisted: bool = True,
    publish_date: str | None = None,
    disable_comments: bool | None = None,
    hide_stats: bool | None = None,
    hosts: list[str] | None = None,
) -> Any:
    """Upload a show. Files must be inside the upload directory (relative paths
    resolve there). mp3 up to 4 GB, picture up to 10 MB, description up to 1000
    chars, up to 5 tags. sections: [{'chapter': 'Intro', 'start_time': 0},
    {'artist': 'A', 'song': 'S', 'start_time': 10}]. unlisted defaults to True
    (private link only) for safety; set unlisted=False to publish publicly.
    publish_date (UTC, 2030-11-21T14:05:00Z), disable_comments, hide_stats and
    hosts (max 2 usernames) are Pro-only."""
    if unlisted and publish_date:
        raise ValueError("unlisted ignores publish_date: pass unlisted=False to schedule")
    audio = safe_file(audio_path, AUDIO_EXTS, MAX_AUDIO_BYTES, "audio")
    picture = (
        safe_file(picture_path, PICTURE_EXTS, MAX_PICTURE_BYTES, "picture")
        if picture_path
        else None
    )
    if not name:
        raise ValueError("name is required")
    fields = meta_fields(
        name, description, tags, sections, hosts, publish_date, disable_comments, hide_stats
    )
    if unlisted:
        fields["unlisted"] = "true"
    with ExitStack() as stack:
        parts = form_fields(fields)
        parts.append(("mp3", (audio.name, stack.enter_context(audio.open("rb")), "audio/mpeg")))
        if picture:
            parts.append(
                (
                    "picture",
                    (
                        picture.name,
                        stack.enter_context(picture.open("rb")),
                        mimetypes.guess_type(picture.name)[0] or "image/jpeg",
                    ),
                )
            )
        response = client.request(
            "POST", "upload", auth=True, files=parts, timeout=client.UPLOAD_TIMEOUT
        )
    return client.as_json(response)


def edit_show(
    key: str,
    name: str | None = None,
    description: str | None = None,
    picture_path: str | None = None,
    tags: list[str] | None = None,
    sections: list[dict[str, Any]] | None = None,
    hosts: list[str] | None = None,
    publish_date: str | None = None,
    disable_comments: bool | None = None,
    hide_stats: bool | None = None,
    visibility: Literal["unlisted", "publish", "unpublish"] | None = None,
) -> Any:
    """Edit one of your shows (key '/me-user/my-upload/'). Omitted fields stay
    unchanged, EXCEPT tags, sections and hosts, which are replaced wholesale:
    re-send the existing ones when adding. hosts=[] removes all hosts.
    visibility: 'unlisted' (private link), 'publish' (make public, also for
    drafts) or 'unpublish' (move to drafts); only one per request."""
    picture = (
        safe_file(picture_path, PICTURE_EXTS, MAX_PICTURE_BYTES, "picture")
        if picture_path
        else None
    )
    fields = meta_fields(
        name, description, tags, sections, hosts, publish_date, disable_comments, hide_stats
    )
    if visibility:
        fields[visibility] = "true"
    if not fields and not picture:
        raise ValueError("Nothing to change")
    path = f"upload/{client.normalize_key(key).strip('/')}/edit"
    with ExitStack() as stack:
        parts = form_fields(fields)
        if picture:
            parts.append(
                (
                    "picture",
                    (
                        picture.name,
                        stack.enter_context(picture.open("rb")),
                        mimetypes.guess_type(picture.name)[0] or "image/jpeg",
                    ),
                )
            )
        response = client.request(
            "POST", path, auth=True, files=parts, timeout=client.UPLOAD_TIMEOUT
        )
    return client.as_json(response)


def register(mcp) -> None:
    mcp.tool()(as_tool_error(upload_show))
    mcp.tool()(as_tool_error(edit_show))
