"""
Yandex Tracker CLI + MCP server.

Режимы работы
─────────────
1) CLI (режим скилла):
     python tracker.py <tool_name> '<json_args>'
   пример:
     python tracker.py issue_get '{"issue_key":"DE-1569"}'
     python tracker.py issues_find '{"query":"Queue: DE AND Status: open","per_page":10}'
     python tracker.py issue_add_comment '{"issue_key":"DE-1569","text":"Текст комментария"}'

2) MCP (legacy): запуск без аргументов — stdio_server для MCP-клиента.

Креденшлы (YANDEX_TOKEN, YANDEX_ORG_ID / YANDEX_CLOUD_ORG_ID) — из корневого .env.
Tracker API v2: https://cloud.yandex.com/en/docs/tracker/concepts/access
"""

import asyncio
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
    Searches: parent of server.py dir, then CWD, then CWD parents."""
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        # Корень проекта: .claude/skills/ya-tracker/scripts/tracker.py → вверх 4
        Path(__file__).resolve().parent.parent.parent.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    # Walk up from CWD
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
            return  # loaded first found .env

_load_dotenv()

_VAR_REF_RE = re.compile(r'^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$')

def _resolve_var_ref(value: str) -> str:
    if not isinstance(value, str):
        return value
    m = _VAR_REF_RE.match(value)
    if m and m.group(1) in os.environ:
        return os.environ[m.group(1)]
    return value

TRACKER_TOKEN = _resolve_var_ref(os.environ.get("YANDEX_TOKEN", ""))
TRACKER_ORG_ID = _resolve_var_ref(os.environ.get("YANDEX_ORG_ID", ""))
TRACKER_CLOUD_ORG_ID = _resolve_var_ref(os.environ.get("YANDEX_CLOUD_ORG_ID", ""))
BASE = _resolve_var_ref(os.environ.get("TRACKER_BASE_URL", "https://api.tracker.yandex.net"))
DOWNLOAD_DIR = _resolve_var_ref(os.environ.get("TRACKER_DOWNLOAD_DIR", os.path.join(os.getcwd(), "downloads")))

# Startup diagnostics (stderr only)
sys.stderr.write(f"[ya-tracker] TOKEN={'yes' if TRACKER_TOKEN else 'MISSING'} "
                 f"ORG_ID={TRACKER_ORG_ID or 'MISSING'} "
                 f"CLOUD_ORG_ID={TRACKER_CLOUD_ORG_ID or 'none'} "
                 f"CWD={os.getcwd()}\n")
sys.stderr.flush()

server = Server("ya-tracker")


def _h(content_type: str = "application/json") -> dict[str, str]:
    """Auth + org headers."""
    h = {"Authorization": f"OAuth {TRACKER_TOKEN}", "Content-Type": content_type}
    if TRACKER_CLOUD_ORG_ID:
        h["X-Cloud-Org-Id"] = TRACKER_CLOUD_ORG_ID
    elif TRACKER_ORG_ID:
        h["X-Org-Id"] = TRACKER_ORG_ID
    return h


def _ok(data: Any) -> list[TextContent]:
    if isinstance(data, str):
        return [TextContent(type="text", text=data)]
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]


def _err(status: int, text: Any) -> list[TextContent]:
    return [TextContent(type="text", text=f"Error {status}: {text}")]


def _require_confirm(args: dict, op: str) -> list[TextContent] | None:
    """Guard for destructive ops. Returns _err response if confirm!=true, else None."""
    if args.get("confirm") is not True:
        return _err(
            400,
            f"Destructive op '{op}' requires confirm:true. "
            f"Operation aborted. Re-run with \"confirm\": true in JSON args.",
        )
    return None


# ── Compact formatters ───────────────────────────────────────────────

def _fmt_issue(d: dict) -> dict:
    result = {
        "key": d.get("key"),
        "summary": d.get("summary"),
        "status": _ref(d.get("status")),
        "type": _ref(d.get("type")),
        "priority": _ref(d.get("priority")),
        "assignee": _user(d.get("assignee")),
        "author": _user(d.get("createdBy")),
        "created": d.get("createdAt"),
        "updated": d.get("updatedAt"),
        "resolved": d.get("resolvedAt"),
        "resolution": _ref(d.get("resolution")),
        "queue": _ref(d.get("queue")),
        "tags": d.get("tags", []),
        "components": [_ref(c) for c in d.get("components", [])],
        "parent": _ref(d.get("parent")),
        "sprint": [_ref(s) for s in d.get("sprint", [])],
        "followers": [_user(f) for f in d.get("followers", [])],
        "epic": _ref(d.get("epic")),
    }
    if d.get("description"):
        result["description"] = d["description"]
    for k, v in d.items():
        if k.startswith("672") or k.startswith("local"):
            result[k] = v
    return result


def _ref(d):
    if not d:
        return None
    return d.get("key") or d.get("display") or d.get("id")


def _user(d):
    if not d:
        return None
    return d.get("id") or d.get("display")


def _fmt_comment(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "text": d.get("text"),
        "author": _user(d.get("createdBy")),
        "created": d.get("createdAt"),
        "updated": d.get("updatedAt"),
        "summonees": [_user(s) for s in d.get("summonees", [])],
    }


def _fmt_link(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "type": d.get("type", {}).get("id"),
        "type_display": d.get("type", {}).get("display"),
        "direction": d.get("direction"),
        "object": _ref(d.get("object")),
        "object_display": (d.get("object") or {}).get("display"),
    }


def _fmt_attachment(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "name": d.get("name"),
        "size": d.get("size"),
        "mimetype": d.get("mimetype"),
        "created": d.get("createdAt"),
        "author": _user(d.get("createdBy")),
        "content_url": d.get("content"),
    }


def _fmt_transition(d: dict) -> dict:
    return {"id": d.get("id"), "display": d.get("display"), "to": _ref(d.get("to"))}


def _fmt_checklist(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "text": d.get("text"),
        "checked": d.get("checked"),
        "assignee": _user(d.get("assignee")),
    }


def _fmt_worklog(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "issue": _ref(d.get("issue")),
        "duration": d.get("duration"),
        "start": d.get("start"),
        "author": _user(d.get("createdBy")),
        "comment": d.get("comment"),
    }


# ── Tool definitions ─────────────────────────────────────────────────

TOOLS: list[Tool] = [
    Tool(name="issue_get",
        description="Get a Yandex Tracker issue by key (e.g. DE-1569). Returns summary, status, type, assignee, description, custom fields.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string", "description": "Issue key, e.g. 'DE-1569'"},
            "include_description": {"type": "boolean", "description": "Include description (can be large). Default: true", "default": True},
        }, "required": ["issue_key"]}),
    Tool(name="issues_find",
        description='Search issues using Tracker query language. Example: "Queue: DE AND Status: open AND Assignee: me()"',
        inputSchema={"type": "object", "properties": {
            "query": {"type": "string", "description": "Tracker query language expression"},
            "include_description": {"type": "boolean", "default": False},
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 50},
        }, "required": ["query"]}),
    Tool(name="issues_count",
        description="Count issues matching a Tracker query.",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    Tool(name="issue_get_comments",
        description="Get comments on a Tracker issue.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),
    Tool(name="issue_get_links",
        description="Get links (relationships) of a Tracker issue to other issues.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),
    Tool(name="issue_get_transitions",
        description="Get available status transitions for an issue. Call this BEFORE issue_execute_transition.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),
    Tool(name="issue_get_attachments",
        description="List attachments on a Tracker issue.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),
    Tool(name="issue_download_attachment",
        description="Download an attachment from a Tracker issue to local disk. "
                    "filename is optional — if omitted, name is auto-resolved from API metadata. "
                    "save_dir is optional — falls back to TRACKER_DOWNLOAD_DIR or ./downloads. "
                    "save_path accepted as alias for save_dir. "
                    "On filename collision: auto-suffix _2, _3, … unless overwrite=true.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
            "attachment_id": {"type": ["string", "integer"]},
            "filename": {"type": "string"},
            "save_dir": {"type": "string"},
            "save_path": {"type": "string"},
            "overwrite": {"type": "boolean"},
        }, "required": ["issue_key", "attachment_id"]}),
    Tool(name="issue_download_all_attachments",
        description="Download ALL attachments of an issue in one call (parallel). "
                    "save_dir is optional — falls back to TRACKER_DOWNLOAD_DIR/<issue_key>/. "
                    "save_path accepted as alias for save_dir. "
                    "On filename collision: auto-suffix _2, _3, … unless overwrite=true.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
            "save_dir": {"type": "string"},
            "save_path": {"type": "string"},
            "overwrite": {"type": "boolean"},
        }, "required": ["issue_key"]}),
    Tool(name="issue_upload_attachment",
        description="Upload a file attachment to a Tracker issue. Provide absolute file path on disk.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
            "file_path": {"type": "string"},
            "filename": {"type": "string"},
        }, "required": ["issue_key", "file_path"]}),
    Tool(name="issue_delete_attachment",
        description="Delete an attachment from a Tracker issue by attachment id.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
            "attachment_id": {"type": ["string", "integer"]},
        }, "required": ["issue_key", "attachment_id"]}),
    Tool(name="issue_get_checklist",
        description="Get checklist items of a Tracker issue.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),
    Tool(name="issue_delete_checklist_item",
        description="Delete a single checklist item from an issue. Returns updated issue.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
            "item_id": {"type": ["string", "integer"]},
        }, "required": ["issue_key", "item_id"]}),
    Tool(name="issue_delete_checklist",
        description="Delete the WHOLE checklist of an issue. Returns updated issue.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
        }, "required": ["issue_key"]}),
    Tool(name="issue_get_worklogs",
        description="Get worklog entries (time tracking) for an issue.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),

    Tool(name="issue_create",
        description="Create a new Tracker issue.",
        inputSchema={"type": "object", "properties": {
            "queue": {"type": "string"}, "summary": {"type": "string"},
            "type": {"type": "integer"}, "description": {"type": "string"},
            "assignee": {"type": "string"}, "priority": {"type": "string"},
            "parent": {"type": "string"},
            "sprint": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
            "fields": {"type": "object"},
        }, "required": ["queue", "summary"]}),
    Tool(name="issue_update",
        description="Update an existing Tracker issue. Only provided fields are changed.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "summary": {"type": "string"},
            "description": {"type": "string"}, "assignee": {"type": "string"},
            "priority": {"type": "string"}, "type": {"type": "integer"},
            "parent": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "sprint": {"type": "array", "items": {"type": "string"}},
            "followers": {"type": "object"},
            "fields": {"type": "object"},
        }, "required": ["issue_key"]}),
    Tool(name="issue_execute_transition",
        description="Execute a status transition on an issue.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "transition_id": {"type": "string"},
            "comment": {"type": "string"}, "fields": {"type": "object"},
        }, "required": ["issue_key", "transition_id"]}),
    Tool(name="issue_add_comment",
        description="Add a comment to a Tracker issue. "
                    "Provide text inline OR text_file (UTF-8 path read and used as text). "
                    "text_file avoids PowerShell cp1251 / JSON-escape boilerplate for multi-line content.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "text": {"type": "string"},
            "text_file": {"type": "string"},
            "summonees": {"type": "array", "items": {"type": "string"}},
        }, "required": ["issue_key"]}),
    Tool(name="issue_update_comment",
        description="Update an existing comment.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "comment_id": {"type": "integer"},
            "text": {"type": "string"},
        }, "required": ["issue_key", "comment_id", "text"]}),
    Tool(name="issue_delete_comment",
        description="Delete a comment.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "comment_id": {"type": "integer"},
        }, "required": ["issue_key", "comment_id"]}),
    Tool(name="issue_close",
        description="Close a Tracker issue with a resolution.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"},
            "resolution_id": {"type": "string", "description": "e.g. 'fixed', 'wontFix'"},
            "comment": {"type": "string"},
        }, "required": ["issue_key", "resolution_id"]}),
    Tool(name="issue_get_url",
        description="Get the web URL for a Tracker issue.",
        inputSchema={"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}),

    Tool(name="issue_add_worklog",
        description="Add a worklog entry (log spent time).",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "duration": {"type": "string", "description": "ISO-8601, e.g. 'PT1H30M'"},
            "comment": {"type": "string"}, "start": {"type": "string"},
        }, "required": ["issue_key", "duration"]}),
    Tool(name="issue_update_worklog",
        description="Update an existing worklog entry.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "worklog_id": {"type": "integer"},
            "duration": {"type": "string"}, "comment": {"type": "string"},
            "start": {"type": "string"},
        }, "required": ["issue_key", "worklog_id"]}),
    Tool(name="issue_delete_worklog",
        description="Delete a worklog entry.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "worklog_id": {"type": "integer"},
        }, "required": ["issue_key", "worklog_id"]}),

    Tool(name="issue_create_link",
        description='Create a link between two issues. Types: relates, depends on, is dependent by, is subtask for, is parent task for, duplicates, is duplicated by, is epic of, has epic.',
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "target_issue": {"type": "string"},
            "relationship": {"type": "string"},
        }, "required": ["issue_key", "target_issue", "relationship"]}),
    Tool(name="issue_delete_link",
        description="Delete a link from a Tracker issue by link ID.",
        inputSchema={"type": "object", "properties": {
            "issue_key": {"type": "string"}, "link_id": {"type": "integer"},
        }, "required": ["issue_key", "link_id"]}),

    Tool(name="queues_get_all",
        description="List all available Tracker queues.",
        inputSchema={"type": "object", "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 50},
        }}),
    Tool(name="queue_get_metadata",
        description="Get metadata for a queue. Use expand=['issueTypesConfig'] for resolutions.",
        inputSchema={"type": "object", "properties": {
            "queue_id": {"type": "string"},
            "expand": {"type": "array", "items": {"type": "string"}},
        }, "required": ["queue_id"]}),
    Tool(name="queue_get_fields",
        description="Get available fields for a queue.",
        inputSchema={"type": "object", "properties": {"queue_id": {"type": "string"}}, "required": ["queue_id"]}),
    Tool(name="queue_get_tags",
        description="Get all tags used in a queue.",
        inputSchema={"type": "object", "properties": {"queue_id": {"type": "string"}}, "required": ["queue_id"]}),
    Tool(name="queue_get_versions",
        description="Get all versions for a queue.",
        inputSchema={"type": "object", "properties": {"queue_id": {"type": "string"}}, "required": ["queue_id"]}),
    Tool(name="queue_delete_macro",
        description="DESTRUCTIVE. Delete a macro from a queue. Requires confirm:true.",
        inputSchema={"type": "object", "properties": {
            "queue_id": {"type": "string"},
            "macro_id": {"type": ["string", "integer"]},
            "confirm": {"type": "boolean", "description": "Must be true to actually delete."},
        }, "required": ["queue_id", "macro_id", "confirm"]}),
    Tool(name="queue_delete",
        description="DESTRUCTIVE. Delete an entire Tracker queue with all its issues. "
                    "Requires confirm:true. Recovery only via API support.",
        inputSchema={"type": "object", "properties": {
            "queue_id": {"type": "string"},
            "confirm": {"type": "boolean"},
        }, "required": ["queue_id", "confirm"]}),

    Tool(name="project_delete",
        description="DESTRUCTIVE. Delete a Tracker project by id. Requires confirm:true.",
        inputSchema={"type": "object", "properties": {
            "project_id": {"type": ["string", "integer"]},
            "confirm": {"type": "boolean"},
        }, "required": ["project_id", "confirm"]}),

    Tool(name="board_delete",
        description="DESTRUCTIVE. Delete an Agile board by id. Requires confirm:true.",
        inputSchema={"type": "object", "properties": {
            "board_id": {"type": ["string", "integer"]},
            "confirm": {"type": "boolean"},
        }, "required": ["board_id", "confirm"]}),
    Tool(name="board_delete_column",
        description="DESTRUCTIVE. Delete a column from a board. Requires confirm:true and "
                    "version (sent as If-Match header for optimistic locking).",
        inputSchema={"type": "object", "properties": {
            "board_id": {"type": ["string", "integer"]},
            "column_id": {"type": ["string", "integer"]},
            "version": {"type": ["string", "integer"], "description": "Board version for If-Match header."},
            "confirm": {"type": "boolean"},
        }, "required": ["board_id", "column_id", "version", "confirm"]}),

    Tool(name="users_get_all",
        description="List user accounts in the organization.",
        inputSchema={"type": "object", "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 50},
        }}),
    Tool(name="users_search",
        description="Search for a user by login, email, or name.",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    Tool(name="user_get",
        description="Get info about a specific user by login or UID.",
        inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}),
    Tool(name="user_get_current",
        description="Get info about the current authenticated user.",
        inputSchema={"type": "object", "properties": {}}),

    Tool(name="get_global_fields",
        description="Get all global fields available in Tracker.",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_issue_types",
        description="Get all issue types (id + name).",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_priorities",
        description="Get all priorities (id + name).",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_resolutions",
        description="Get all resolutions for closing issues.",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_statuses",
        description="Get all statuses available.",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_link_types",
        description="Get all link (relationship) types.",
        inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_myself",
        description="Get the current authenticated user info.",
        inputSchema={"type": "object", "properties": {}}),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


# ── HTTP helpers ─────────────────────────────────────────────────────

async def _get(session, path, params=None):
    async with session.get(f"{BASE}{path}", headers=_h(), params=params) as r:
        text = await r.text()
        return r.status, json.loads(text) if r.status == 200 else text


async def _post(session, path, body=None):
    async with session.post(f"{BASE}{path}", headers=_h(), json=body or {}) as r:
        text = await r.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        return r.status, data


async def _patch(session, path, body):
    async with session.patch(f"{BASE}{path}", headers=_h(), json=body) as r:
        text = await r.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        return r.status, data


async def _delete(session, path, headers_extra: dict[str, str] | None = None):
    headers = _h()
    if headers_extra:
        headers.update(headers_extra)
    async with session.delete(f"{BASE}{path}", headers=headers) as r:
        return r.status, await r.text()


def _claim_dest(dest: Path, overwrite: bool):
    """Open dest for binary write. If exists and not overwrite — try _2, _3, … (atomic via O_EXCL).
    Returns (file_handle, actual_path)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        return open(dest, "wb"), dest
    stem, suffix = dest.stem, dest.suffix
    n = 1
    while True:
        candidate = dest if n == 1 else dest.with_name(f"{stem}_{n}{suffix}")
        try:
            return open(candidate, "xb"), candidate
        except FileExistsError:
            n += 1


async def _download(session, url, dest: Path, overwrite: bool = False):
    headers = _h()
    del headers["Content-Type"]
    async with session.get(url, headers=headers) as r:
        if r.status != 200:
            return r.status, f"HTTP {r.status} from {url}", None
        try:
            fh, actual = _claim_dest(dest, overwrite)
            try:
                async for chunk in r.content.iter_chunked(8192):
                    fh.write(chunk)
            finally:
                fh.close()
        except OSError as e:
            return 0, f"Filesystem error writing {dest}: {e}", None
        return 200, None, actual


async def _upload_attachment(session, issue_key, file_path, filename=None):
    path = Path(file_path)
    if not path.exists():
        return 404, f"File not found: {file_path}"
    fname = filename or path.name
    headers = _h()
    del headers["Content-Type"]
    with open(path, "rb") as fh:
        data = aiohttp.FormData()
        data.add_field("file", fh, filename=fname)
        async with session.post(f"{BASE}/v2/issues/{issue_key}/attachments",
                                headers=headers, data=data) as r:
            text = await r.text()
            try:
                return r.status, json.loads(text)
            except json.JSONDecodeError:
                return r.status, text


# ── Tool dispatch ────────────────────────────────────────────────────

async def _dispatch(s, name, a):
    # ── Issues: read ─────────────────────────────────────────
    if name == "issue_get":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}")
        if st != 200:
            return _err(st, data)
        issue = _fmt_issue(data)
        if not a.get("include_description", True):
            issue.pop("description", None)
        return _ok(issue)

    if name == "issues_find":
        body = {"query": a["query"]}
        page = a.get("page", 1); per_page = a.get("per_page", 50)
        st, data = await _post(s, f"/v2/issues/_search?page={page}&perPage={per_page}", body)
        if st != 200:
            return _err(st, data)
        issues = [_fmt_issue(i) for i in data]
        if not a.get("include_description", False):
            for i in issues:
                i.pop("description", None)
        return _ok({"count": len(issues), "page": page, "issues": issues})

    if name == "issues_count":
        st, data = await _post(s, "/v2/issues/_count", {"query": a["query"]})
        if st != 200:
            return _err(st, data)
        return _ok({"count": data})

    if name == "issue_get_comments":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}/comments")
        if st != 200:
            return _err(st, data)
        return _ok([_fmt_comment(c) for c in data])

    if name == "issue_get_links":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}/links")
        if st != 200:
            return _err(st, data)
        return _ok([_fmt_link(lnk) for lnk in data])

    if name == "issue_get_transitions":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}/transitions")
        if st != 200:
            return _err(st, data)
        return _ok([_fmt_transition(t) for t in data])

    if name == "issue_get_attachments":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}/attachments")
        if st != 200:
            return _err(st, data)
        return _ok([_fmt_attachment(att) for att in data])

    if name == "issue_download_attachment":
        issue_key = a["issue_key"]; att_id = a["attachment_id"]
        st, data = await _get(s, f"/v2/issues/{issue_key}/attachments")
        if st != 200:
            return _err(st, data)
        att = next((x for x in data if str(x.get("id")) == str(att_id)), None)
        if not att:
            return _err(404, f"Attachment {att_id} not found on {issue_key}")
        content_url = att.get("content")
        if not content_url:
            return _err(404, "No content URL in attachment metadata")
        filename = a.get("filename") or att.get("name")
        if not filename:
            return _err(400, f"Attachment {att_id} has no name in metadata; pass explicit filename")
        save_dir = a.get("save_dir") or a.get("save_path") or str(Path(DOWNLOAD_DIR) / issue_key)
        overwrite = bool(a.get("overwrite", False))
        dest = Path(save_dir) / filename
        dl_status, dl_err, actual = await _download(s, content_url, dest, overwrite=overwrite)
        if dl_status != 200 or actual is None:
            return _err(dl_status, dl_err or f"Failed to download from {content_url}")
        if not actual.exists():
            return _err(500, f"Download reported success but file missing: {actual}")
        return _ok({"downloaded": str(actual), "size": actual.stat().st_size, "name": actual.name,
                    "renamed": actual.name != filename})

    if name == "issue_download_all_attachments":
        issue_key = a["issue_key"]
        save_dir = a.get("save_dir") or a.get("save_path") or str(Path(DOWNLOAD_DIR) / issue_key)
        overwrite = bool(a.get("overwrite", False))
        st, data = await _get(s, f"/v2/issues/{issue_key}/attachments")
        if st != 200:
            return _err(st, data)
        if not data:
            return _ok({"downloaded": [], "count": 0, "save_dir": save_dir})
        async def _dl_one(att):
            name_ = att.get("name")
            url = att.get("content")
            if not name_ or not url:
                return {"id": att.get("id"), "error": "missing name or content url"}
            dest = Path(save_dir) / name_
            status, err, actual = await _download(s, url, dest, overwrite=overwrite)
            if status != 200 or actual is None or not actual.exists():
                return {"id": att.get("id"), "name": name_, "error": err or f"status {status}"}
            return {"id": att.get("id"), "name": name_, "path": str(actual),
                    "size": actual.stat().st_size, "renamed": actual.name != name_}
        results = await asyncio.gather(*[_dl_one(att) for att in data])
        successful = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]
        return _ok({"downloaded": successful, "failed": failed,
                    "count": len(successful), "total": len(data), "save_dir": save_dir})

    if name == "issue_upload_attachment":
        st, data = await _upload_attachment(s, a["issue_key"], a["file_path"], a.get("filename"))
        if st not in (200, 201):
            return _err(st, data)
        if isinstance(data, list):
            return _ok([_fmt_attachment(att) for att in data])
        return _ok(_fmt_attachment(data) if isinstance(data, dict) else data)

    if name == "issue_delete_attachment":
        st, text = await _delete(s, f"/v2/issues/{a['issue_key']}/attachments/{a['attachment_id']}")
        if st in (200, 204):
            return _ok(f"Attachment {a['attachment_id']} deleted from {a['issue_key']}")
        return _err(st, text)

    if name == "issue_get_checklist":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}/checklist")
        if st != 200:
            return _err(st, data)
        items = data if isinstance(data, list) else data.get("items", data.get("checklistItems", []))
        return _ok([_fmt_checklist(c) for c in items])

    if name == "issue_delete_checklist_item":
        st, text = await _delete(
            s, f"/v2/issues/{a['issue_key']}/checklistItems/{a['item_id']}"
        )
        if st in (200, 204):
            try:
                issue = json.loads(text)
                if isinstance(issue, dict) and issue.get("key"):
                    return _ok({"deleted_item": a["item_id"], "issue": _fmt_issue(issue)})
            except (json.JSONDecodeError, TypeError):
                pass
            return _ok(f"Checklist item {a['item_id']} deleted from {a['issue_key']}")
        return _err(st, text)

    if name == "issue_delete_checklist":
        st, text = await _delete(s, f"/v2/issues/{a['issue_key']}/checklistItems")
        if st in (200, 204):
            try:
                issue = json.loads(text)
                if isinstance(issue, dict) and issue.get("key"):
                    return _ok({"checklist_cleared": a["issue_key"], "issue": _fmt_issue(issue)})
            except (json.JSONDecodeError, TypeError):
                pass
            return _ok(f"Whole checklist deleted from {a['issue_key']}")
        return _err(st, text)

    if name == "issue_get_worklogs":
        st, data = await _get(s, f"/v2/issues/{a['issue_key']}/worklogs")
        if st != 200:
            return _err(st, data)
        return _ok([_fmt_worklog(w) for w in data])

    # ── Issues: write ────────────────────────────────────────
    if name == "issue_create":
        body: dict = {"queue": a["queue"], "summary": a["summary"]}
        for k in ("type", "description", "assignee", "priority", "parent", "tags"):
            if a.get(k) is not None:
                body[k] = a[k]
        if a.get("sprint"):
            body["sprint"] = [{"id": sid} for sid in a["sprint"]]
        if a.get("fields"):
            body.update(a["fields"])
        st, data = await _post(s, "/v2/issues", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_issue(data))

    if name == "issue_update":
        iid = a.pop("issue_key")
        body = {}
        for k in ("summary", "description", "assignee", "priority", "type", "parent", "tags", "followers"):
            if a.get(k) is not None:
                body[k] = a[k]
        if a.get("sprint"):
            body["sprint"] = [{"id": sid} for sid in a["sprint"]]
        if a.get("fields"):
            body.update(a["fields"])
        if not body:
            return _err(400, "No fields to update")
        st, data = await _patch(s, f"/v2/issues/{iid}", body)
        if st != 200:
            return _err(st, data)
        return _ok(_fmt_issue(data))

    if name == "issue_execute_transition":
        iid = a["issue_key"]; tid = a["transition_id"]
        body: dict = {}
        if a.get("comment"):
            body["comment"] = a["comment"]
        if a.get("fields"):
            body.update(a["fields"])
        st, data = await _post(s, f"/v2/issues/{iid}/transitions/{tid}/_execute", body or None)
        if st not in (200, 201):
            return _err(st, data)
        st2, data2 = await _get(s, f"/v2/issues/{iid}/transitions")
        if st2 == 200:
            return _ok({"executed": tid, "new_transitions": [_fmt_transition(t) for t in data2]})
        return _ok({"executed": tid, "result": data})

    if name == "issue_add_comment":
        text = a.get("text")
        if not text and a.get("text_file"):
            try:
                text = Path(a["text_file"]).read_text(encoding="utf-8")
            except OSError as e:
                return _err(400, f"text_file read error: {e}")
        if not text:
            return _err(400, "either text or text_file is required")
        body: dict = {"text": text}
        if a.get("summonees"):
            body["summonees"] = a["summonees"]
        st, data = await _post(s, f"/v2/issues/{a['issue_key']}/comments", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_comment(data))

    if name == "issue_update_comment":
        st, data = await _patch(s, f"/v2/issues/{a['issue_key']}/comments/{a['comment_id']}", {"text": a["text"]})
        if st != 200:
            return _err(st, data)
        return _ok(_fmt_comment(data))

    if name == "issue_delete_comment":
        st, text = await _delete(s, f"/v2/issues/{a['issue_key']}/comments/{a['comment_id']}")
        if st == 204:
            return _ok(f"Comment {a['comment_id']} deleted from {a['issue_key']}")
        return _err(st, text)

    if name == "issue_close":
        iid = a["issue_key"]; resolution_id = a["resolution_id"]
        st, transitions = await _get(s, f"/v2/issues/{iid}/transitions")
        if st != 200:
            return _err(st, transitions)
        close_t = None
        for t in transitions:
            to_key = (t.get("to") or {}).get("key", "").lower()
            if to_key in ("closed", "done", "resolved", "complete"):
                close_t = t; break
        if not close_t:
            for t in transitions:
                display = (t.get("display") or "").lower()
                if "close" in display or "done" in display or "resolve" in display:
                    close_t = t; break
        if not close_t:
            return _err(400, f"No close/done transition found. Available: {[_fmt_transition(t) for t in transitions]}")
        body: dict = {"resolution": resolution_id}
        if a.get("comment"):
            body["comment"] = a["comment"]
        st2, data2 = await _post(s, f"/v2/issues/{iid}/transitions/{close_t['id']}/_execute", body)
        if st2 not in (200, 201):
            return _err(st2, data2)
        st3, data3 = await _get(s, f"/v2/issues/{iid}/transitions")
        if st3 == 200:
            return _ok({"closed": iid, "resolution": resolution_id, "new_transitions": [_fmt_transition(t) for t in data3]})
        return _ok({"closed": iid, "resolution": resolution_id})

    if name == "issue_get_url":
        return _ok(f"https://tracker.yandex.ru/{a['issue_key']}")

    # ── Worklogs ─────────────────────────────────────────────
    if name == "issue_add_worklog":
        body: dict = {"duration": a["duration"]}
        if a.get("comment"): body["comment"] = a["comment"]
        if a.get("start"): body["start"] = a["start"]
        st, data = await _post(s, f"/v2/issues/{a['issue_key']}/worklogs", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_worklog(data))

    if name == "issue_update_worklog":
        body: dict = {}
        if a.get("duration"): body["duration"] = a["duration"]
        if a.get("comment"): body["comment"] = a["comment"]
        if a.get("start"): body["start"] = a["start"]
        if not body:
            return _err(400, "No fields to update")
        st, data = await _patch(s, f"/v2/issues/{a['issue_key']}/worklogs/{a['worklog_id']}", body)
        if st != 200:
            return _err(st, data)
        return _ok(_fmt_worklog(data))

    if name == "issue_delete_worklog":
        st, text = await _delete(s, f"/v2/issues/{a['issue_key']}/worklogs/{a['worklog_id']}")
        if st == 204:
            return _ok(f"Worklog {a['worklog_id']} deleted from {a['issue_key']}")
        return _err(st, text)

    # ── Links ────────────────────────────────────────────────
    if name == "issue_create_link":
        valid = ["relates", "is dependent by", "depends on", "is subtask for",
                 "is parent task for", "duplicates", "is duplicated by", "is epic of", "has epic"]
        rel = a["relationship"]
        if rel not in valid:
            return _err(400, f"Invalid relationship: {rel}. Valid: {valid}")
        body = {"relationship": rel, "issue": a["target_issue"]}
        st, data = await _post(s, f"/v2/issues/{a['issue_key']}/links", body)
        if st not in (200, 201):
            return _err(st, data)
        return _ok(_fmt_link(data))

    if name == "issue_delete_link":
        st, text = await _delete(s, f"/v2/issues/{a['issue_key']}/links/{a['link_id']}")
        if st == 204:
            return _ok(f"Link {a['link_id']} deleted from {a['issue_key']}")
        return _err(st, text)

    # ── Queues ───────────────────────────────────────────────
    if name == "queues_get_all":
        page = a.get("page", 1); per_page = a.get("per_page", 50)
        st, data = await _get(s, "/v2/queues", {"page": page, "perPage": per_page})
        if st != 200:
            return _err(st, data)
        return _ok([{"key": q.get("key"), "name": q.get("name"), "lead": _user(q.get("lead"))} for q in data])

    if name == "queue_get_metadata":
        params = {}
        if a.get("expand"):
            params["expand"] = ",".join(a["expand"])
        st, data = await _get(s, f"/v2/queues/{a['queue_id']}", params)
        if st != 200:
            return _err(st, data)
        return _ok(data)

    if name == "queue_get_fields":
        st, data = await _get(s, f"/v2/queues/{a['queue_id']}/fields")
        if st != 200:
            return _err(st, data)
        fields = []
        for f in data:
            field = {
                "id": f.get("field", {}).get("id") or f.get("id"),
                "name": f.get("field", {}).get("name") or f.get("name"),
                "type": f.get("field", {}).get("schema", {}).get("type") or f.get("type"),
                "required": f.get("required", False),
            }
            fields.append(field)
        return _ok(fields)

    if name == "queue_get_tags":
        st, data = await _get(s, f"/v2/queues/{a['queue_id']}/tags")
        if st != 200:
            return _err(st, data)
        return _ok(data)

    if name == "queue_get_versions":
        st, data = await _get(s, f"/v2/queues/{a['queue_id']}/versions")
        if st != 200:
            return _err(st, data)
        return _ok(data)

    if name == "queue_delete_macro":
        guard = _require_confirm(a, "queue_delete_macro")
        if guard is not None:
            return guard
        st, text = await _delete(s, f"/v2/queues/{a['queue_id']}/macros/{a['macro_id']}")
        if st in (200, 204):
            return _ok(f"Macro {a['macro_id']} deleted from queue {a['queue_id']}")
        return _err(st, text)

    if name == "queue_delete":
        guard = _require_confirm(a, "queue_delete")
        if guard is not None:
            return guard
        st, text = await _delete(s, f"/v2/queues/{a['queue_id']}")
        if st in (200, 204):
            return _ok(f"Queue {a['queue_id']} deleted")
        return _err(st, text)

    # ── Projects ─────────────────────────────────────────────
    if name == "project_delete":
        guard = _require_confirm(a, "project_delete")
        if guard is not None:
            return guard
        st, text = await _delete(s, f"/v2/projects/{a['project_id']}")
        if st in (200, 204):
            return _ok(f"Project {a['project_id']} deleted")
        return _err(st, text)

    # ── Boards ───────────────────────────────────────────────
    if name == "board_delete":
        guard = _require_confirm(a, "board_delete")
        if guard is not None:
            return guard
        st, text = await _delete(s, f"/v2/boards/{a['board_id']}")
        if st in (200, 204):
            return _ok(f"Board {a['board_id']} deleted")
        return _err(st, text)

    if name == "board_delete_column":
        guard = _require_confirm(a, "board_delete_column")
        if guard is not None:
            return guard
        st, text = await _delete(
            s,
            f"/v2/boards/{a['board_id']}/columns/{a['column_id']}",
            headers_extra={"If-Match": str(a["version"])},
        )
        if st in (200, 204):
            return _ok(f"Column {a['column_id']} deleted from board {a['board_id']}")
        return _err(st, text)

    # ── Users ────────────────────────────────────────────────
    if name == "users_get_all":
        page = a.get("page", 1); per_page = a.get("per_page", 50)
        st, data = await _get(s, "/v2/users", {"page": page, "perPage": per_page})
        if st != 200:
            return _err(st, data)
        return _ok([{"uid": u.get("uid"), "login": u.get("login"),
                     "display": u.get("display"), "email": u.get("email")} for u in data])

    if name == "users_search":
        query = a["query"].strip().lower()
        page = 1; all_users = []
        while True:
            st, data = await _get(s, "/v2/users", {"page": page, "perPage": 100})
            if st != 200:
                return _err(st, data)
            if not data:
                break
            for u in data:
                login = (u.get("login") or "").lower()
                email = (u.get("email") or "").lower()
                display = (u.get("display") or "").lower()
                first = (u.get("firstName") or "").lower()
                last = (u.get("lastName") or "").lower()
                if query in login or query in email or query in display or query in first or query in last:
                    all_users.append({
                        "uid": u.get("uid"), "login": u.get("login"),
                        "display": u.get("display"), "email": u.get("email"),
                    })
            page += 1
            if len(data) < 100:
                break
        return _ok(all_users)

    if name == "user_get":
        st, data = await _get(s, f"/v2/users/{a['user_id']}")
        if st != 200:
            return _err(st, data)
        return _ok({"uid": data.get("uid"), "login": data.get("login"),
                    "display": data.get("display"), "email": data.get("email"),
                    "firstName": data.get("firstName"), "lastName": data.get("lastName")})

    if name == "user_get_current":
        st, data = await _get(s, "/v2/myself")
        if st != 200:
            return _err(st, data)
        return _ok({"uid": data.get("uid"), "login": data.get("login"),
                    "display": data.get("display"), "email": data.get("email")})

    # ── Metadata ─────────────────────────────────────────────
    if name == "get_global_fields":
        st, data = await _get(s, "/v2/fields")
        if st != 200:
            return _err(st, data)
        return _ok([{
            "id": f.get("id"), "name": f.get("name"),
            "type": f.get("schema", {}).get("type") if isinstance(f.get("schema"), dict) else None,
            "required": f.get("schema", {}).get("required", False) if isinstance(f.get("schema"), dict) else False,
        } for f in data])

    if name == "get_issue_types":
        st, data = await _get(s, "/v2/issuetypes")
        if st != 200:
            return _err(st, data)
        return _ok([{"id": t.get("id"), "key": t.get("key"), "name": t.get("name")} for t in data])

    if name == "get_priorities":
        st, data = await _get(s, "/v2/priorities")
        if st != 200:
            return _err(st, data)
        return _ok([{"id": p.get("id"), "key": p.get("key"), "name": p.get("name")} for p in data])

    if name == "get_resolutions":
        st, data = await _get(s, "/v2/resolutions")
        if st != 200:
            return _err(st, data)
        return _ok([{"id": r.get("id"), "key": r.get("key"), "name": r.get("name")} for r in data])

    if name == "get_statuses":
        st, data = await _get(s, "/v2/statuses")
        if st != 200:
            return _err(st, data)
        return _ok([{"id": st_.get("id"), "key": st_.get("key"), "name": st_.get("name")} for st_ in data])

    if name == "get_link_types":
        st, data = await _get(s, "/v2/linktypes")
        if st != 200:
            return _err(st, data)
        return _ok([{"id": t.get("id"), "inward": t.get("inward"), "outward": t.get("outward")} for t in data])

    if name == "get_myself":
        st, data = await _get(s, "/v2/myself")
        if st != 200:
            return _err(st, data)
        return _ok({"uid": data.get("uid"), "login": data.get("login"),
                    "display": data.get("display"), "email": data.get("email")})

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


@server.call_tool()
async def call_tool(name: str, args: dict[str, Any]) -> list[TextContent]:
    async with aiohttp.ClientSession() as s:
        try:
            return await _dispatch(s, name, args)
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
    async with aiohttp.ClientSession() as s:
        try:
            return await _dispatch(s, name, args)
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]


def _cli_main():
    import asyncio
    # Windows cp1251 ломает русский текст в stdout — форсим UTF-8
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("\nДоступные инструменты (вызов: python tracker.py <tool> '<json_args>'):")
        for t in TOOLS:
            print(f"  {t.name}")
        sys.exit(0)

    if argv[0] == "list-tools":
        for t in TOOLS:
            print(f"{t.name:<35} {t.description}")
        sys.exit(0)

    tool = argv[0]
    args_json = argv[1] if len(argv) > 1 else "{}"

    # Detect argparse-style misuse (--key value)
    if args_json.startswith("--") or any(a.startswith("--") for a in argv[1:]):
        print(
            f"Error: argparse-style flags не поддерживаются. Параметры передаются JSON-строкой.\n"
            f"\n"
            f"❌ НЕ ТАК:\n"
            f"  python tracker.py {tool} --issue_key DE-88\n"
            f"  python tracker.py {tool} --queue DE --summary 'X'\n"
            f"\n"
            f"✓ ПРАВИЛЬНО (JSON позиционным аргументом):\n"
            f"  python tracker.py {tool} '{{\"issue_key\":\"DE-88\"}}'\n"
            f"  python tracker.py issue_create '{{\"queue\":\"DE\",\"summary\":\"X\"}}'",
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
            f"  python tracker.py {tool} '{{\"issue_key\":\"DE-88\"}}'",
            file=sys.stderr,
        )
        sys.exit(1)

    if not TRACKER_TOKEN:
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
