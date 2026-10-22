"""Read a multipart upload with a hard size cap, while it streams in.

Collaborators: routes.py (POST /admin/media/images), routes_dev.py (the fake store's direct
upload). Uses Starlette's own multipart parser (python-multipart underneath).

How it works:
  1. A Content-Length above the cap is refused at once (413), before reading anything.
  2. The body is read chunk by chunk and counted anyway (Content-Length may be missing or
     wrong); the moment the count passes the cap, reading stops with 413.
  3. Starlette's parser turns the counted stream into fields and one file, spooled to a
     temporary file after 1 MB, so a 100 MB video never sits in memory.

SECURITY: FastAPI's own `File()`/`Form()` parameters would read the whole body before our code
runs, so these routes read it themselves (SECURITY.md §6).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Final

from python_multipart.multipart import parse_options_header
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from empire_api.errors import ApiProblem

# Room for the boundaries, part headers and the small text fields around the file.
FORM_OVERHEAD_BYTES: Final = 64 * 1024
MAX_FIELDS: Final = 20
MAX_FIELD_BYTES: Final = 4 * 1024
INCOMPLETE: Final = "The upload arrived incomplete. Check the connection and try again."
TAIL_BYTES: Final = 256


@dataclass
class CappedForm:
    fields: dict[str, str]
    file: UploadFile | None

    async def close(self) -> None:
        if self.file is not None:
            await self.file.close()


def _too_large(message: str) -> ApiProblem:
    return ApiProblem(413, message)


async def _close_all(items: list[tuple[str, str | UploadFile]]) -> None:
    for _, value in items:
        if isinstance(value, UploadFile):
            await value.close()


def _closing_boundary(request: Request) -> bytes:
    _, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary", b"")
    return b"--" + (boundary.encode("latin-1") if isinstance(boundary, str) else boundary) + b"--"


async def read_capped_form(request: Request, max_file_bytes: int, too_large: str) -> CappedForm:
    """Fields and the `file` part of a multipart body, never reading past the cap.

    Raises:
        ApiProblem: 413 over the cap (`too_large` is the message), 400 when the body isn't
            multipart/form-data or is malformed.
    """
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise ApiProblem(400, "Send the file as multipart/form-data.")
    cap = max_file_bytes + FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdecimal() and int(declared) > cap:  # 1
        raise _too_large(too_large)

    received = {"bytes": 0}
    tail = bytearray()

    async def counted() -> AsyncGenerator[bytes]:  # 2
        async for chunk in request.stream():
            received["bytes"] += len(chunk)
            if received["bytes"] > cap:
                raise _too_large(too_large)
            tail.extend(chunk)
            del tail[:-TAIL_BYTES]
            yield chunk

    parser = MultiPartParser(
        request.headers,
        counted(),
        max_files=1,
        max_fields=MAX_FIELDS,
        max_part_size=MAX_FIELD_BYTES,
    )
    try:
        form = await parser.parse()  # 3
    except MultiPartException as exc:
        raise ApiProblem(400, f"The upload couldn't be read: {exc.message}") from exc
    cut_short = declared is not None and declared.isdecimal() and received["bytes"] != int(declared)
    if cut_short or _closing_boundary(request) not in tail:
        # WHY: a proxy that cuts a body short (Next.js buffers only 10 MB through proxy.ts)
        # must not turn into "no file was sent"; a complete body ends with the closing boundary.
        await _close_all(form.multi_items())
        raise ApiProblem(400, INCOMPLETE)
    fields: dict[str, str] = {}
    upload: UploadFile | None = None
    for name, value in form.multi_items():
        if isinstance(value, UploadFile):
            if name == "file":
                upload = value
            else:
                await value.close()
        else:
            fields[name] = value
    if upload is not None and (upload.size or 0) > max_file_bytes:
        await upload.close()
        raise _too_large(too_large)
    return CappedForm(fields=fields, file=upload)
