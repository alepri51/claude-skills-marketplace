"""
Yandex Wiki CLI + MCP server.

Режимы работы
─────────────
1) CLI (режим скилла):
     python wiki.py <tool_name> '<json_args>'
   пример:
     python wiki.py page_get '{"slug":"users/foo/bar","fields":"content,breadcrumbs"}'
     python wiki.py page_get_subpages_by_slug '{"slug":"team"}'
     python wiki.py page_create '{"slug":"sandbox/test","title":"Test","content":"hello"}'

2) MCP (legacy): запуск без аргументов — stdio_server для MCP-клиента.

Креденшлы (YANDEX_TOKEN, YANDEX_ORG_ID / YANDEX_CLOUD_ORG_ID) — из корневого .env.
Wiki API v1: https://yandex.ru/support/wiki/ru/api-ref/
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import aiohttp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Config ───────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load .env from project root as fallback for missing env vars.
    Searches: parent of script dir, then CWD, then CWD parents."""
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        # Корень проекта: .claude/skills/ya-wiki/scripts/wiki.py → вверх 4
        Path(__file__).resolve().parent.parent.parent.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    p = Path.cwd()
    for _ in range(5):
        p = p.parent
        candidates.append(p / ".env")

    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and (key not in os.environ or not os.environ[key]):
                    os.environ[key] = val
            return

_load_dotenv()

_VAR_REF_RE = re.compile(r'^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$')

def _resolve_var_ref(value: str) -> str:
    if not isinstance(value, str):
        return value
    m = _VAR_REF_RE.match(value)
    if m and m.group(1) in os.environ:
        return os.environ[m.group(1)]
    return value

WIKI_TOKEN = _resolve_var_ref(os.environ.get("YANDEX_TOKEN", ""))
WIKI_ORG_ID = _resolve_var_ref(os.environ.get("YANDEX_ORG_ID", ""))
WIKI_CLOUD_ORG_ID = _resolve_var_ref(os.environ.get("YANDEX_CLOUD_ORG_ID", ""))
BASE = _resolve_var_ref(os.environ.get("WIKI_BASE_URL", "https://api.wiki.yandex.net"))
DOWNLOAD_DIR = _resolve_var_ref(os.environ.get("WIKI_DOWNLOAD_DIR", os.path.join(os.getcwd(), "downloads")))

sys.stderr.write(f"[ya-wiki] TOKEN={'yes' if WIKI_TOKEN else 'MISSING'} "
                 f"ORG_ID={WIKI_ORG_ID or 'MISSING'} "
                 f"CLOUD_ORG_ID={WIKI_CLOUD_ORG_ID or 'none'} "
                 f"CWD={os.getcwd()}\n")
sys.stderr.flush()

server = Server("ya-wiki")


def _h(content_type: str = "application/json") -> dict[str, str]:
    """Auth + org headers."""
    h = {"Authorization": f"OAuth {WIKI_TOKEN}", "Content-Type": content_type}
    if WIKI_CLOUD_ORG_ID:
        h["X-Cloud-Org-Id"] = WIKI_CLOUD_ORG_ID
    elif WIKI_ORG_ID:
        h["X-Org-Id"] = WIKI_ORG_ID
    return h


def _ok(data: Any) -> list[TextContent]:
    if isinstance(data, str):
        return [TextContent(type="text", text=data)]
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]


def _err(status: int, text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error {status}: {text}")]


# ── Compact formatters ───────────────────────────────────────────────

def _user(d):
    if not d:
        return None
    if isinstance(d, str):
        return d
    return d.get("username") or d.get("login") or d.get("display") or d.get("id") or (d.get("identity") or {}).get("uid")


def _fmt_page(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    result: dict = {
        "id": d.get("id"),
        "slug": d.get("slug"),
        "title": d.get("title"),
        "page_type": d.get("page_type"),
    }
    if d.get("attributes"):
        attr = d["attributes"]
        result["created_at"] = attr.get("created_at")
        result["modified_at"] = attr.get("modified_at")
        result["author"] = _user(attr.get("author"))
        result["lang"] = attr.get("lang")
        result["is_readonly"] = attr.get("is_readonly")
        result["comments_count"] = attr.get("comments_count")
    if d.get("breadcrumbs"):
        result["breadcrumbs"] = [
            {"id": b.get("id"), "slug": b.get("slug"), "title": b.get("title")}
            for b in d["breadcrumbs"]
        ]
    if d.get("content") is not None:
        result["content"] = d["content"]
    if d.get("redirect"):
        result["redirect"] = d["redirect"]
    return result


def _fmt_attachment(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "name": d.get("name"),
        "size": d.get("size"),
        "mimetype": d.get("mimetype"),
        "created_at": d.get("created_at"),
        "author": _user(d.get("user") or d.get("author")),
        "download_url": d.get("download_url"),
        "check_status": d.get("check_status"),
    }


def _fmt_comment(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "body": d.get("body"),
        "author": _user(d.get("author")),
        "created_at": d.get("created_at"),
        "is_deleted": d.get("is_deleted"),
        "resolved": d.get("resolved"),
        "thread_id": d.get("thread_id"),
        "parent_id": d.get("parent_id"),
    }


def _fmt_session(d: dict) -> dict:
    return {
        "session_id": d.get("session_id"),
        "file_name": d.get("file_name"),
        "file_size": d.get("file_size"),
        "status": d.get("status"),
        "created_at": d.get("created_at"),
        "finished_at": d.get("finished_at"),
        "storage_type": d.get("storage_type"),
    }


# ── Tool definitions ─────────────────────────────────────────────────

TOOLS: list[Tool] = [
    # Pages — read
    Tool(name="page_get",
        description="Get Wiki page by slug. Use 'fields' query (csv) to include extra blocks: attributes, breadcrumbs, content, redirect.",
        inputSchema={"type": "object", "properties": {
            "slug": {"type": "string", "description": "Page slug, e.g. 'users/foo/bar'"},
            "fields": {"type": "string", "description": "CSV list of optional fields to include. Common: 'content,breadcrumbs,attributes'"},
            "raise_on_redirect": {"type": "boolean", "default": False},
            "revision_id": {"type": "integer"},
        }, "required": ["slug"]}),
    Tool(name="page_get_by_id",
        description="Get Wiki page by numeric ID.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "fields": {"type": "string"},
            "raise_on_redirect": {"type": "boolean", "default": False},
            "revision_id": {"type": "integer"},
        }, "required": ["page_id"]}),
    Tool(name="page_get_subpages",
        description="Get descendants (all levels) of a page by ID. Cursor-paginated.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "actuality": {"type": "string", "description": "'actual' or 'obsolete'"},
            "cursor": {"type": "string"},
            "include_self": {"type": "boolean", "default": False},
            "page_size": {"type": "integer", "default": 50},
        }, "required": ["page_id"]}),
    Tool(name="page_get_subpages_by_slug",
        description="Get descendants (all levels) of a page by slug. Cursor-paginated.",
        inputSchema={"type": "object", "properties": {
            "slug": {"type": "string"},
            "actuality": {"type": "string"},
            "cursor": {"type": "string"},
            "include_self": {"type": "boolean", "default": False},
            "page_size": {"type": "integer", "default": 50},
        }, "required": ["slug"]}),
    Tool(name="page_get_url",
        description="Build the web URL for a Wiki page from its slug.",
        inputSchema={"type": "object", "properties": {
            "slug": {"type": "string"},
        }, "required": ["slug"]}),

    # Pages — write
    Tool(name="page_create",
        description="Create a new Wiki page. Required: title, slug, content.",
        inputSchema={"type": "object", "properties": {
            "title": {"type": "string", "description": "1-255 chars"},
            "slug": {"type": "string"},
            "content": {"type": "string"},
            "is_silent": {"type": "boolean", "default": False, "description": "Don't notify subscribers"},
            "fields": {"type": "string", "description": "CSV of extra fields to return"},
        }, "required": ["title", "slug", "content"]}),
    Tool(name="page_update",
        description="Update a Wiki page by ID. Updatable: title, content, redirect.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "redirect": {"type": "object", "description": "{ page: { id|slug } }"},
            "allow_merge": {"type": "boolean"},
            "is_silent": {"type": "boolean"},
        }, "required": ["page_id"]}),
    Tool(name="page_delete",
        description="Delete a Wiki page by ID. Returns recovery_token for restoration.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
        }, "required": ["page_id"]}),
    Tool(name="page_clone",
        description="Clone (copy) a Wiki page to a new slug.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "target": {"type": "string", "description": "Target slug for the new page"},
            "title": {"type": "string"},
            "subscribe_me": {"type": "boolean", "default": False},
        }, "required": ["page_id", "target"]}),
    Tool(name="page_append_content",
        description="Append content to an existing page.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "content": {"type": "string", "description": "Min length 1"},
            "location": {"type": "string", "description": "'top' or 'bottom' (default backend behaviour)"},
            "section_id": {"type": "integer"},
            "anchor_name": {"type": "string"},
        }, "required": ["page_id", "content"]}),

    # Page resources / dynamic tables
    Tool(name="page_get_grids",
        description="Get dynamic tables (grids) attached to a Wiki page by ID.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
        }, "required": ["page_id"]}),

    # Attachments
    Tool(name="page_get_attachments",
        description="List attachments on a Wiki page by ID.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "cursor": {"type": "string"},
            "page_size": {"type": "integer", "default": 50},
        }, "required": ["page_id"]}),
    Tool(name="attachment_download_by_id",
        description="Download an attachment by page ID + file ID.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "file_id": {"type": "integer"},
            "filename": {"type": "string", "description": "Save filename (used for local path)"},
            "save_dir": {"type": "string", "description": "Local directory for saving (default: $WIKI_DOWNLOAD_DIR/<page_id>). Caller-specific layouts (project planning artifacts, per-phase folders) should pass an explicit path here."},
        }, "required": ["page_id", "file_id", "filename"]}),
    Tool(name="attachment_download_by_slug",
        description="Download an attachment by slug + filename. Builds the .files/ URL automatically.",
        inputSchema={"type": "object", "properties": {
            "slug": {"type": "string"},
            "filename": {"type": "string"},
            "save_as": {"type": "string", "description": "Local filename override (default: same as filename)"},
            "save_dir": {"type": "string", "description": "Local directory for saving (default: $WIKI_DOWNLOAD_DIR/<slug>). Caller-specific layouts (project planning artifacts, per-phase folders) should pass an explicit path here."},
        }, "required": ["slug", "filename"]}),
    Tool(name="page_upload_attachment",
        description="Upload a file as an attachment to a Wiki page (full pipeline: create session → upload → finish → attach).",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "file_path": {"type": "string", "description": "Absolute local path"},
            "filename": {"type": "string", "description": "Override filename (default: basename)"},
        }, "required": ["page_id", "file_path"]}),
    Tool(name="attachment_delete",
        description="Delete an attachment by page ID + file ID.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "file_id": {"type": "integer"},
        }, "required": ["page_id", "file_id"]}),

    # Comments
    Tool(name="page_get_comments",
        description="List comments on a Wiki page.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "cursor": {"type": "string"},
            "order_direction": {"type": "string", "description": "'asc' or 'desc' (default 'asc')"},
            "page_size": {"type": "integer", "default": 50},
            "status_filter": {"type": "string", "description": "'resolved' or 'unresolved'"},
        }, "required": ["page_id"]}),
    Tool(name="page_add_comment",
        description="Add a comment to a Wiki page. Body is the comment text.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "body": {"type": "string"},
            "inline_text": {"type": "string"},
            "parent_id": {"type": "integer", "description": "ID of parent comment for replies"},
            "thread_id": {"type": "integer"},
        }, "required": ["page_id", "body"]}),
    Tool(name="comment_delete",
        description="Delete a comment from a Wiki page.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "comment_id": {"type": "integer"},
        }, "required": ["page_id", "comment_id"]}),
    Tool(name="page_get_comment_thread",
        description="Get a comment thread on a Wiki page.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "thread_id": {"type": "integer"},
            "cursor": {"type": "string"},
            "page_size": {"type": "integer", "default": 50},
        }, "required": ["page_id", "thread_id"]}),

    # Users
    Tool(name="users_get_current",
        description="Get info about the current authenticated user (doctor probe).",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_myself",
        description="Alias for users_get_current.",
        inputSchema={"type": "object", "properties": {}}),

    # Upload sessions (low-level — page_upload_attachment uses these internally)
    Tool(name="upload_session_create",
        description="Create an upload session for a file.",
        inputSchema={"type": "object", "properties": {
            "file_name": {"type": "string"},
            "file_size": {"type": "integer"},
        }, "required": ["file_name", "file_size"]}),
    Tool(name="upload_session_get",
        description="Get info about an upload session.",
        inputSchema={"type": "object", "properties": {
            "session_id": {"type": "string"},
        }, "required": ["session_id"]}),
    Tool(name="upload_session_finish",
        description="Finish (complete) an upload session.",
        inputSchema={"type": "object", "properties": {
            "session_id": {"type": "string"},
        }, "required": ["session_id"]}),
    Tool(name="upload_session_abort",
        description="Abort an upload session.",
        inputSchema={"type": "object", "properties": {
            "session_id": {"type": "string"},
        }, "required": ["session_id"]}),

    # Operations
    Tool(name="operation_get",
        description="Get status of an async operation (clone/restore/etc).",
        inputSchema={"type": "object", "properties": {
            "operation_id": {"type": "string"},
        }, "required": ["operation_id"]}),

    # Restoration
    Tool(name="page_restore",
        description="Restore a deleted Wiki page using its recovery_token.",
        inputSchema={"type": "object", "properties": {
            "page_id": {"type": "integer"},
            "recovery_token": {"type": "string"},
        }, "required": ["page_id", "recovery_token"]}),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


# ── HTTP helpers ─────────────────────────────────────────────────────

async def _get(session, path, params=None):
    async with session.get(f"{BASE}{path}", headers=_h(), params=params) as r:
        text = await r.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        return r.status, data


async def _post(session, path, body=None, params=None):
    async with session.post(f"{BASE}{path}", headers=_h(), json=body or {}, params=params) as r:
        text = await r.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        return r.status, data


async def _put_octet(session, path, data: bytes, params=None):
    headers = _h(content_type="application/octet-stream")
    async with session.put(f"{BASE}{path}", headers=headers, data=data, params=params) as r:
        text = await r.text()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text
        return r.status, payload


async def _delete(session, path):
    async with session.delete(f"{BASE}{path}", headers=_h()) as r:
        text = await r.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        return r.status, data


async def _download(session, path, dest: Path, params=None):
    """Download a binary file from the Wiki API to local disk."""
    headers = _h()
    del headers["Content-Type"]
    async with session.get(f"{BASE}{path}", headers=headers, params=params, allow_redirects=True) as r:
        if r.status == 200:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                async for chunk in r.content.iter_chunked(8192):
                    f.write(chunk)
            return r.status, None
        text = await r.text()
        return r.status, text


# ── Tool dispatch ────────────────────────────────────────────────────

async def _dispatch(s, name, a):
    # ── Pages: read ──────────────────────────────────────────
    if name == "page_get":
        params: dict = {"slug": a["slug"]}
        if a.get("fields"):
            params["fields"] = a["fields"]
        if a.get("raise_on_redirect"):
            params["raise_on_redirect"] = "true"
        if a.get("revision_id") is not None:
            params["revision_id"] = a["revision_id"]
        st, data = await _get(s, "/v1/pages", params)
        if st != 200:
            return _err(st, data)
        return _ok(_fmt_page(data))

    if name == "page_get_by_id":
        params: dict = {}
        if a.get("fields"):
            params["fields"] = a["fields"]
        if a.get("raise_on_redirect"):
            params["raise_on_redirect"] = "true"
        if a.get("revision_id") is not None:
            params["revision_id"] = a["revision_id"]
        st, data = await _get(s, f"/v1/pages/{a['page_id']}", params or None)
        if st != 200:
            return _err(st, data)
        return _ok(_fmt_page(data))

    if name == "page_get_subpages":
        params = {k: a[k] for k in ("actuality", "cursor", "include_self", "page_size") if a.get(k) is not None}
        st, data = await _get(s, f"/v1/pages/{a['page_id']}/descendants", params or None)
        if st != 200:
            return _err(st, data)
        if isinstance(data, dict):
            return _ok({
                "results": [_fmt_page(p) for p in data.get("results", [])],
                "next_cursor": data.get("next_cursor"),
                "prev_cursor": data.get("prev_cursor"),
            })
        return _ok(data)

    if name == "page_get_subpages_by_slug":
        params = {"slug": a["slug"]}
        for k in ("actuality", "cursor", "include_self", "page_size"):
            if a.get(k) is not None:
                params[k] = a[k]
        st, data = await _get(s, "/v1/pages/descendants", params)
        if st != 200:
            return _err(st, data)
        if isinstance(data, dict):
            return _ok({
                "results": [_fmt_page(p) for p in data.get("results", [])],
                "next_cursor": data.get("next_cursor"),
                "prev_cursor": data.get("prev_cursor"),
            })
        return _ok(data)

    if name == "page_get_url":
        slug = a["slug"].strip("/")
        return _ok(f"https://wiki.yandex.ru/{slug}")

    # ── Pages: write ─────────────────────────────────────────
    if name == "page_create":
        body = {"title": a["title"], "slug": a["slug"], "content": a["content"]}
        params: dict = {}
        if a.get("is_silent"):
            params["is_silent"] = "true"
        if a.get("fields"):
            params["fields"] = a["fields"]
        st, data = await _post(s, "/v1/pages", body, params=params or None)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_page(data))

    if name == "page_update":
        body: dict = {}
        for k in ("title", "content", "redirect", "allow_merge", "is_silent"):
            if a.get(k) is not None:
                body[k] = a[k]
        if not body:
            return _err(400, "No fields to update")
        st, data = await _post(s, f"/v1/pages/{a['page_id']}", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_page(data) if isinstance(data, dict) else data)

    if name == "page_delete":
        st, data = await _delete(s, f"/v1/pages/{a['page_id']}")
        if st not in (200, 204):
            return _err(st, data)
        token = data.get("recovery_token") if isinstance(data, dict) else None
        return _ok({"deleted": a["page_id"], "recovery_token": token})

    if name == "page_clone":
        body: dict = {"target": a["target"]}
        if a.get("title"):
            body["title"] = a["title"]
        if a.get("subscribe_me") is not None:
            body["subscribe_me"] = a["subscribe_me"]
        st, data = await _post(s, f"/v1/pages/{a['page_id']}/clone", body)
        if st not in (200, 201, 202):
            return _err(st, data)
        return _ok(data)

    if name == "page_append_content":
        body: dict = {"content": a["content"]}
        if a.get("location"):
            body["body"] = {"location": a["location"]}
        if a.get("section_id") is not None:
            body["section"] = {"id": a["section_id"]}
        if a.get("anchor_name"):
            body["anchor"] = {"name": a["anchor_name"]}
        st, data = await _post(s, f"/v1/pages/{a['page_id']}/append-content", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(data)

    # ── Page resources / grids ───────────────────────────────
    if name == "page_get_grids":
        st, data = await _get(s, f"/v1/pages/{a['page_id']}/grids")
        if st != 200:
            return _err(st, data)
        return _ok(data)

    # ── Attachments ──────────────────────────────────────────
    if name == "page_get_attachments":
        params = {k: a[k] for k in ("cursor", "page_size") if a.get(k) is not None}
        st, data = await _get(s, f"/v1/pages/{a['page_id']}/attachments", params or None)
        if st != 200:
            return _err(st, data)
        if isinstance(data, dict):
            return _ok({
                "results": [_fmt_attachment(att) for att in data.get("results", [])],
                "next_cursor": data.get("next_cursor"),
                "prev_cursor": data.get("prev_cursor"),
            })
        return _ok(data)

    if name == "attachment_download_by_id":
        page_id = a["page_id"]; file_id = a["file_id"]; filename = a["filename"]
        save_dir = a.get("save_dir")
        if save_dir:
            dest = Path(save_dir) / filename
        else:
            dest = Path(DOWNLOAD_DIR) / str(page_id) / filename
        st, err = await _download(s, f"/v1/pages/{page_id}/attachments/{file_id}/download", dest)
        if st != 200:
            return _err(st, err or f"Download failed for file {file_id}")
        return _ok({"downloaded": str(dest), "size": dest.stat().st_size, "name": filename})

    if name == "attachment_download_by_slug":
        slug = a["slug"].strip("/"); filename = a["filename"]
        save_as = a.get("save_as", filename)
        url_param = f"{slug}/.files/{filename}"
        params = {"url": url_param, "download": "true"}
        save_dir = a.get("save_dir")
        if save_dir:
            dest = Path(save_dir) / save_as
        else:
            dest = Path(DOWNLOAD_DIR) / slug / save_as
        st, err = await _download(s, "/v1/pages/attachments/download_by_url", dest, params=params)
        if st != 200:
            return _err(st, err or f"Download failed for {url_param}")
        return _ok({"downloaded": str(dest), "size": dest.stat().st_size, "name": save_as})

    if name == "page_upload_attachment":
        return await _upload_pipeline(s, a["page_id"], a["file_path"], a.get("filename"))

    if name == "attachment_delete":
        st, data = await _delete(s, f"/v1/pages/{a['page_id']}/attachments/{a['file_id']}")
        if st not in (200, 204):
            return _err(st, data)
        return _ok({"deleted": a["file_id"], "page_id": a["page_id"]})

    # ── Comments ─────────────────────────────────────────────
    if name == "page_get_comments":
        params = {k: a[k] for k in ("cursor", "order_direction", "page_size", "status_filter") if a.get(k) is not None}
        st, data = await _get(s, f"/v1/pages/{a['page_id']}/comments", params or None)
        if st != 200:
            return _err(st, data)
        if isinstance(data, dict):
            return _ok({
                "results": [_fmt_comment(c) for c in data.get("results", [])],
                "next_cursor": data.get("next_cursor"),
                "prev_cursor": data.get("prev_cursor"),
            })
        return _ok(data)

    if name == "page_add_comment":
        body: dict = {"body": a["body"]}
        for k in ("inline_text", "parent_id", "thread_id"):
            if a.get(k) is not None:
                body[k] = a[k]
        st, data = await _post(s, f"/v1/pages/{a['page_id']}/comments", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_comment(data) if isinstance(data, dict) else data)

    if name == "comment_delete":
        st, data = await _delete(s, f"/v1/pages/{a['page_id']}/comments/{a['comment_id']}")
        if st not in (200, 204):
            return _err(st, data)
        return _ok({"deleted": a["comment_id"], "page_id": a["page_id"], "result": data})

    if name == "page_get_comment_thread":
        params = {k: a[k] for k in ("cursor", "page_size") if a.get(k) is not None}
        st, data = await _get(s, f"/v1/pages/{a['page_id']}/comments/{a['thread_id']}/thread", params or None)
        if st != 200:
            return _err(st, data)
        if isinstance(data, dict):
            return _ok({
                "results": [_fmt_comment(c) for c in data.get("results", [])],
                "next_cursor": data.get("next_cursor"),
                "prev_cursor": data.get("prev_cursor"),
            })
        return _ok(data)

    # ── Users ────────────────────────────────────────────────
    if name in ("users_get_current", "get_myself"):
        st, data = await _get(s, "/v1/users/me")
        if st != 200:
            return _err(st, data)
        ident = data.get("identity") if isinstance(data, dict) else {}
        org = data.get("org") if isinstance(data, dict) else {}
        return _ok({
            "username": data.get("username"),
            "home_cluster": data.get("home_cluster"),
            "uid": (ident or {}).get("uid"),
            "cloud_uid": (ident or {}).get("cloud_uid"),
            "dir_id": (org or {}).get("dir_id"),
            "collab_id": (org or {}).get("collab_id"),
        })

    # ── Upload sessions ──────────────────────────────────────
    if name == "upload_session_create":
        body = {"file_name": a["file_name"], "file_size": a["file_size"]}
        st, data = await _post(s, "/v1/upload_sessions", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_session(data))

    if name == "upload_session_get":
        st, data = await _get(s, f"/v1/upload_sessions/{a['session_id']}")
        if st != 200:
            return _err(st, data)
        return _ok(_fmt_session(data) if isinstance(data, dict) else data)

    if name == "upload_session_finish":
        st, data = await _post(s, f"/v1/upload_sessions/{a['session_id']}/finish")
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_session(data) if isinstance(data, dict) else data)

    if name == "upload_session_abort":
        st, data = await _post(s, f"/v1/upload_sessions/{a['session_id']}/abort")
        if st not in (200, 201, 204):
            return _err(st, data)
        return _ok({"aborted": a["session_id"]})

    # ── Operations ───────────────────────────────────────────
    if name == "operation_get":
        st, data = await _get(s, f"/v1/operations/{a['operation_id']}")
        if st != 200:
            return _err(st, data)
        return _ok(data)

    # ── Restoration ──────────────────────────────────────────
    if name == "page_restore":
        params = {"recovery_token": a["recovery_token"]}
        st, data = await _post(s, f"/v1/pages/{a['page_id']}/restore", None, params=params)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(data)

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Upload pipeline (4 steps wrapped) ────────────────────────────────

# Wiki API multipart spec: parts 5–16 MB except last. For one-shot upload of
# small files we send the whole file as part 1 (no minimum part size on the
# last part).
_PART_SIZE = 8 * 1024 * 1024


async def _upload_pipeline(s, page_id: int, file_path: str, filename: str | None):
    path = Path(file_path)
    if not path.exists():
        return _err(404, f"File not found: {file_path}")
    if not path.is_file():
        return _err(400, f"Not a regular file: {file_path}")

    fname = filename or path.name
    fsize = path.stat().st_size

    # 1. Create upload session
    st, sess = await _post(s, "/v1/upload_sessions", {"file_name": fname, "file_size": fsize})
    if st not in (200, 201) or not isinstance(sess, dict):
        return _err(st, sess)
    session_id = sess.get("session_id")
    if not session_id:
        return _err(500, f"upload session created without session_id: {sess}")

    # 2. Upload parts (single part for files ≤ _PART_SIZE)
    try:
        with open(path, "rb") as f:
            part_number = 1
            while True:
                chunk = f.read(_PART_SIZE)
                if not chunk:
                    if part_number == 1:
                        # empty file: still send a single empty part
                        st, payload = await _put_octet(
                            s, f"/v1/upload_sessions/{session_id}/upload_part",
                            b"", params={"part_number": 1},
                        )
                        if st not in (200, 201, 204):
                            return _err(st, payload)
                    break
                st, payload = await _put_octet(
                    s, f"/v1/upload_sessions/{session_id}/upload_part",
                    chunk, params={"part_number": part_number},
                )
                if st not in (200, 201, 204):
                    return _err(st, payload)
                part_number += 1
    except OSError as e:
        return _err(500, f"read error: {e}")

    # 3. Finish session
    st, fin = await _post(s, f"/v1/upload_sessions/{session_id}/finish")
    if st not in (200, 201):
        return _err(st, fin)

    # 4. Attach to page
    st, att = await _post(s, f"/v1/pages/{page_id}/attachments",
                         {"upload_sessions": [session_id]})
    if st not in (200, 201):
        return _err(st, att)
    if isinstance(att, dict) and isinstance(att.get("results"), list):
        return _ok({
            "uploaded": fname,
            "size": fsize,
            "session_id": session_id,
            "attachments": [_fmt_attachment(x) for x in att["results"]],
        })
    return _ok({"uploaded": fname, "size": fsize, "session_id": session_id, "result": att})


@server.call_tool()
async def call_tool(name: str, args: dict[str, Any]) -> list[TextContent]:
    async with aiohttp.ClientSession() as sess:
        try:
            return await _dispatch(sess, name, args)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


# ── Entry points ─────────────────────────────────────────────────────

async def _mcp_main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _mcp_run():
    import asyncio
    asyncio.run(_mcp_main())


async def _cli_call(name, args):
    async with aiohttp.ClientSession() as sess:
        try:
            return await _dispatch(sess, name, args)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


def _cli_main():
    import asyncio
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("\nДоступные инструменты (вызов: python wiki.py <tool> '<json_args>'):")
        for t in TOOLS:
            print(f"  {t.name}")
        sys.exit(0)

    if argv[0] == "list-tools":
        for t in TOOLS:
            print(f"{t.name:<35} {t.description}")
        sys.exit(0)

    tool = argv[0]
    args_json = argv[1] if len(argv) > 1 else "{}"

    # Detect argparse-style misuse
    if args_json.startswith("--") or any(a.startswith("--") for a in argv[1:]):
        print(
            f"Error: argparse-style flags не поддерживаются. Параметры передаются JSON-строкой.\n"
            f"\n"
            f"❌ НЕ ТАК:\n"
            f"  python wiki.py {tool} --slug team/handbook\n"
            f"  python wiki.py {tool} --page_id 123 --content 'X'\n"
            f"\n"
            f"✓ ПРАВИЛЬНО (JSON позиционным аргументом):\n"
            f"  python wiki.py {tool} '{{\"slug\":\"team/handbook\",\"fields\":\"content\"}}'\n"
            f"  python wiki.py page_update '{{\"page_id\":123,\"content\":\"X\"}}'",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        arguments = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        print(
            f"Error: invalid JSON in args — {e}\n"
            f"\n"
            f"Параметры скрипту передаются ОДНОЙ JSON-строкой вторым аргументом:\n"
            f"  python wiki.py {tool} '{{\"slug\":\"team/handbook\"}}'",
            file=sys.stderr,
        )
        sys.exit(1)

    if not WIKI_TOKEN:
        print("Error: YANDEX_TOKEN not set. Fill it in .env (see config/README.md)", file=sys.stderr)
        sys.exit(2)

    result = asyncio.run(_cli_call(tool, arguments))
    for tc in result:
        print(tc.text)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli_main()
    else:
        _mcp_run()
