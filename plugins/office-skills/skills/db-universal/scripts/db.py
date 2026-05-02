"""
Universal DB Inspector CLI + MCP — MySQL, PostgreSQL, ClickHouse, Redis, MongoDB.

Режимы работы
─────────────
1) CLI (режим скилла):
     python db.py <tool_name> '<json_args>' [--connection <name>]
   пример:
     python db.py db_tables '{"pattern":"user_%"}' --connection db-parsing-dev
     python db.py db_schema '{"table":"users"}' --connection db-bnmap-prod
     python db.py db_query '{"sql":"SELECT * FROM users"}' --connection db-parsing-dev

2) MCP (legacy): запуск без аргументов — stdio_server для MCP-клиента.

Параметры подключения берутся из:
- --connection <name> → config/connections.json (резолвит ${VAR} из .env)
- аргументы tool'а (host/port/user/password/database/db_type)
- переменные окружения DB_HOST/DB_PORT/…

Инструменты: db_tables, db_schema, db_query, db_keys, db_get
"""

import json
import os
import re
import sys
import asyncio
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Config: .env, connections.json, var refs ──────────────────────────────

_SKILL_ROOT = Path(__file__).resolve().parent.parent   # .../db-universal


def _find_env() -> Path | None:
    """Ищет .env от cwd вверх по дереву (до 8 уровней). Fallback — рядом со скилом."""
    cur = Path.cwd().resolve()
    for _ in range(8):
        cand = cur / ".env"
        if cand.exists():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    cand = _SKILL_ROOT / ".env"
    return cand if cand.exists() else None


_env_path = _find_env()
if _env_path is not None:
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path, override=False)
    except ImportError:
        # Минимальный парсер .env, если python-dotenv не установлен
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k and (k not in os.environ or not os.environ[k]):
                os.environ[k] = v

_VAR_REF_RE = re.compile(r'^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$')

def _resolve_var_ref(value):
    """Резолвит значение вида "${VAR_NAME}" из os.environ."""
    if not isinstance(value, str):
        return value
    m = _VAR_REF_RE.match(value)
    if m and m.group(1) in os.environ:
        return os.environ[m.group(1)]
    return value


def _load_named_connection(name: str) -> dict:
    """Читает config/connections.json и возвращает параметры подключения по имени.

    Значения вида "${VAR_NAME}" резолвятся из .env/окружения.
    Возвращает пустой dict, если имя не найдено или файла нет.
    """
    cfg_path = _SKILL_ROOT / "config" / "connections.json"
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    raw = data.get(name) or {}
    return {k: _resolve_var_ref(v) for k, v in raw.items()}


server = Server("db-universal")

DEFAULTS = {
    "host":     _resolve_var_ref(os.environ.get("DB_HOST", "localhost")),
    "port":     _resolve_var_ref(os.environ.get("DB_PORT", "")),
    "user":     _resolve_var_ref(os.environ.get("DB_USER", "")),
    "password": _resolve_var_ref(os.environ.get("DB_PASSWORD", "")),
    "database": _resolve_var_ref(os.environ.get("DB_NAME", "")),
    "db_type":  _resolve_var_ref(os.environ.get("DB_TYPE", "mysql")),
}

CONN_SCHEMA = {
    "host":     {"type": "string", "description": "DB host"},
    "port":     {"type": "integer", "description": "DB port"},
    "user":     {"type": "string", "description": "DB user"},
    "password": {"type": "string", "description": "DB password"},
    "database": {"type": "string", "description": "Database/schema name"},
    "db_type":  {
        "type": "string",
        "enum": ["mysql", "postgres", "clickhouse", "redis", "mongo"],
        "description": "DB engine: mysql | postgres | clickhouse | redis | mongo"
    },
}


def R(args, key, default=None):
    return args.get(key) or DEFAULTS.get(key) or default


def port_of(args, db_type):
    p = args.get("port") or DEFAULTS.get("port")
    if p: return int(p)
    return {"mysql": 3306, "postgres": 5432, "clickhouse": 9000, "redis": 6379, "mongo": 27017}.get(db_type, 3306)


# ── MySQL ──────────────────────────────────────────────────────────────────

def _mysql(args):
    import mysql.connector
    return mysql.connector.connect(
        host=R(args, "host"), port=port_of(args, "mysql"),
        user=R(args, "user"), password=R(args, "password"), database=R(args, "database"),
    )

async def mysql_tables(args, pattern):
    c = _mysql(args); cur = c.cursor()
    cur.execute("SHOW TABLES LIKE %s", (pattern,))
    r = [x[0] for x in cur.fetchall()]; cur.close(); c.close(); return r

async def mysql_schema(args, table):
    """Columns + indexes + size stats in one call."""
    c = _mysql(args); cur = c.cursor()
    cur.execute(f"DESCRIBE `{table}`")
    columns = [{"field": x[0], "type": x[1], "null": x[2], "key": x[3], "default": x[4]} for x in cur.fetchall()]
    cur.execute(f"SHOW INDEX FROM `{table}`")
    idx_rows = cur.fetchall()
    idx_map: dict = {}
    for r in idx_rows:
        name = r[2]
        idx_map.setdefault(name, {
            "name": name, "unique": (r[1] == 0), "type": r[10],
            "columns": [], "cardinality": 0,
        })
        idx_map[name]["columns"].append((r[3], r[4]))
        if r[6] is not None:
            idx_map[name]["cardinality"] = max(idx_map[name]["cardinality"], int(r[6]))
    indexes = [
        {"name": v["name"], "unique": v["unique"], "type": v["type"],
         "columns": [c for _, c in sorted(v["columns"])],
         "cardinality": v["cardinality"]}
        for v in idx_map.values()
    ]
    cur.execute(
        "SELECT table_rows, data_length, index_length "
        "FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table,)
    )
    row = cur.fetchone()
    stats = (
        {"rows_estimate": int(row[0] or 0),
         "data_mb": round((row[1] or 0) / 1024 / 1024, 2),
         "index_mb": round((row[2] or 0) / 1024 / 1024, 2)}
        if row else {}
    )
    cur.close(); c.close()
    return {"columns": columns, "indexes": indexes, "stats": stats}

async def mysql_query(args, sql):
    c = _mysql(args); cur = c.cursor(dictionary=True)
    cur.execute(sql); r = [_s(x) for x in cur.fetchall()]; cur.close(); c.close(); return r


# ── PostgreSQL ─────────────────────────────────────────────────────────────

def _pg(args):
    import psycopg2, psycopg2.extras
    return psycopg2.connect(
        host=R(args, "host"), port=port_of(args, "postgres"),
        user=R(args, "user"), password=R(args, "password"), dbname=R(args, "database"),
    )

async def pg_tables(args, pattern):
    c = _pg(args); cur = c.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE %s ORDER BY tablename", (pattern,))
    r = [x[0] for x in cur.fetchall()]; cur.close(); c.close(); return r

async def pg_schema(args, table):
    c = _pg(args); cur = c.cursor()
    cur.execute("SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_name=%s AND table_schema='public' ORDER BY ordinal_position", (table,))
    r = [{"field": x[0], "type": x[1], "null": x[2], "default": str(x[3]) if x[3] else None} for x in cur.fetchall()]
    cur.close(); c.close(); return r

async def pg_query(args, sql):
    import psycopg2.extras
    c = _pg(args); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql); r = [_s(dict(x)) for x in cur.fetchall()]; cur.close(); c.close(); return r


# ── ClickHouse ─────────────────────────────────────────────────────────────

async def ch_tables(args, pattern):
    import clickhouse_driver
    cl = clickhouse_driver.Client(host=R(args,"host"), port=port_of(args,"clickhouse"), user=R(args,"user"), password=R(args,"password"), database=R(args,"database"))
    return [x[0] for x in cl.execute("SHOW TABLES LIKE %(p)s", {"p": pattern})]

async def ch_schema(args, table):
    import clickhouse_driver
    cl = clickhouse_driver.Client(host=R(args,"host"), port=port_of(args,"clickhouse"), user=R(args,"user"), password=R(args,"password"), database=R(args,"database"))
    return [{"field": x[0], "type": x[1]} for x in cl.execute(f"DESCRIBE TABLE `{table}`")]

async def ch_query(args, sql):
    import clickhouse_driver
    cl = clickhouse_driver.Client(host=R(args,"host"), port=port_of(args,"clickhouse"), user=R(args,"user"), password=R(args,"password"), database=R(args,"database"))
    rows, cols = cl.execute(sql, with_column_types=True)
    names = [c[0] for c in cols]
    return [dict(zip(names, r)) for r in rows]


# ── Redis ──────────────────────────────────────────────────────────────────

def _redis(args):
    import redis
    return redis.Redis(host=R(args,"host"), port=port_of(args,"redis"), password=R(args,"password") or None, db=int(R(args,"database") or 0), decode_responses=True)

async def redis_keys(args, pattern):
    return _redis(args).keys(pattern or "*")[:200]

async def redis_get_val(args, key):
    r = _redis(args); t = r.type(key)
    if t == "string":  return {"type": t, "value": r.get(key)}
    if t == "hash":    return {"type": t, "value": r.hgetall(key)}
    if t == "list":    return {"type": t, "value": r.lrange(key, 0, 99)}
    if t == "set":     return {"type": t, "value": list(r.smembers(key))[:100]}
    if t == "zset":    return {"type": t, "value": r.zrange(key, 0, 99, withscores=True)}
    return {"type": t, "value": None}


# ── MongoDB ────────────────────────────────────────────────────────────────

def _mongo(args):
    from pymongo import MongoClient
    u, p = R(args,"user"), R(args,"password")
    h, port, db = R(args,"host"), port_of(args,"mongo"), R(args,"database")
    uri = f"mongodb://{u}:{p}@{h}:{port}/{db}" if u else f"mongodb://{h}:{port}/{db}"
    return MongoClient(uri)[db]

async def mongo_tables(args, pattern):
    import re
    cols = _mongo(args).list_collection_names()
    if pattern and pattern != "%":
        pat = pattern.replace("%", ".*")
        cols = [c for c in cols if re.match(pat, c)]
    return sorted(cols)

async def mongo_schema(args, table):
    sample = list(_mongo(args)[table].aggregate([{"$sample": {"size": 10}}]))
    fields = {}
    for doc in sample:
        for k, v in doc.items(): fields[k] = type(v).__name__
    return [{"field": k, "type": v} for k, v in fields.items()]

async def mongo_query(args, sql):
    try:
        q = json.loads(sql)
        rows = list(_mongo(args)[q["collection"]].aggregate(q.get("pipeline", [])))[:200]
        return [_s(r) for r in rows]
    except Exception as e:
        return [{"error": str(e), "hint": 'JSON: {"collection":"name","pipeline":[...]}'}]


# ── Helpers ────────────────────────────────────────────────────────────────

def _s(obj):
    if isinstance(obj, dict):  return {k: _s(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_s(i) for i in obj]
    if isinstance(obj, (int, float, bool, type(None))): return obj
    return str(obj)


BACKENDS = {
    "mysql":      {"tables": mysql_tables, "schema": mysql_schema, "query": mysql_query},
    "postgres":   {"tables": pg_tables,    "schema": pg_schema,    "query": pg_query},
    "clickhouse": {"tables": ch_tables,    "schema": ch_schema,    "query": ch_query},
    "redis":      {"tables": redis_keys,   "schema": None,         "query": None},
    "mongo":      {"tables": mongo_tables, "schema": mongo_schema, "query": mongo_query},
}

def ok(d): return [TextContent(type="text", text=json.dumps(d, ensure_ascii=False, indent=2))]
def err(e): return [TextContent(type="text", text=f"Error: {e}")]


# ── Tool Definitions ───────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="db_tables",
            description="List tables/collections. db_type: mysql|postgres|clickhouse|redis|mongo.",
            inputSchema={"type": "object", "properties": {"pattern": {"type": "string", "description": "LIKE pattern, default '%'"}, **CONN_SCHEMA}},
        ),
        Tool(
            name="db_schema",
            description="Describe table/collection columns.",
            inputSchema={"type": "object", "properties": {"table": {"type": "string"}, **CONN_SCHEMA}, "required": ["table"]},
        ),
        Tool(
            name="db_query",
            description="Read-only query. MySQL/PG/ClickHouse: SQL SELECT. MongoDB: JSON {collection, pipeline}. LIMIT auto-added.",
            inputSchema={"type": "object", "properties": {"sql": {"type": "string"}, **CONN_SCHEMA}, "required": ["sql"]},
        ),
        Tool(
            name="db_keys",
            description="Redis: list keys by pattern.",
            inputSchema={"type": "object", "properties": {"pattern": {"type": "string", "description": "Key pattern e.g. 'user:*'"}, **CONN_SCHEMA}},
        ),
        Tool(
            name="db_get",
            description="Redis: get value of key (string/hash/list/set/zset).",
            inputSchema={"type": "object", "properties": {"key": {"type": "string"}, **CONN_SCHEMA}, "required": ["key"]},
        ),
    ]


async def _call_tool_impl(name: str, arguments: dict) -> list[TextContent]:
    """Общая реализация вызова инструмента. Используется и MCP, и CLI."""
    db_type = R(arguments, "db_type") or "mysql"
    try:
        if name == "db_tables":
            return ok(await BACKENDS[db_type]["tables"](arguments, arguments.get("pattern", "%")))
        elif name == "db_schema":
            return ok(await BACKENDS[db_type]["schema"](arguments, arguments["table"]))
        elif name == "db_query":
            sql = arguments["sql"].strip()
            if db_type in ("mysql", "postgres", "clickhouse"):
                upper = sql.upper()
                first = upper.split(None, 1)[0] if upper else ""
                if first == "SELECT":
                    if "LIMIT" not in upper:
                        sql += " LIMIT 200"
                elif first in ("EXPLAIN", "SHOW", "DESCRIBE", "DESC"):
                    pass
                else:
                    return err("Only read-only queries allowed: SELECT, EXPLAIN, SHOW, DESCRIBE")
            return ok(await BACKENDS[db_type]["query"](arguments, sql))
        elif name == "db_keys":
            return ok(await redis_keys(arguments, arguments.get("pattern", "*")))
        elif name == "db_get":
            return ok(await redis_get_val(arguments, arguments["key"]))
        else:
            return err(f"Unknown tool: {name}")
    except Exception as e:
        return err(str(e))


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    return await _call_tool_impl(name, arguments)


# ── Entry point ────────────────────────────────────────────────────────────

async def _mcp_main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _cli_main():
    """CLI-диспетчер: python db.py <tool_name> [<json_args>] [--connection <name>]"""
    # Windows cp1251 ломает русский текст в stdout — форсим UTF-8
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("\nДоступные tool'ы: db_tables, db_schema, db_query, db_keys, db_get")
        print("Примеры:")
        print("  python db.py db_tables '{\"pattern\":\"user_%\"}' --connection db-parsing-dev")
        print("  python db.py db_schema '{\"table\":\"users\"}' --connection db-bnmap-prod")
        print("  python db.py db_query '{\"sql\":\"SELECT COUNT(*) FROM users\"}' --connection db-parsing-dev")
        print("  python db.py list-connections  # список именованных подключений")
        sys.exit(0)

    tool = argv[0]

    # Список подключений из config/connections.json
    if tool == "list-connections":
        cfg_path = _SKILL_ROOT / "config" / "connections.json"
        if not cfg_path.exists():
            print("config/connections.json не найден")
            sys.exit(1)
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        names = [k for k in data.keys() if not k.startswith("_")]
        print(json.dumps(names, indent=2))
        sys.exit(0)

    # Разбор JSON-аргументов и --connection
    args_json = "{}"
    connection = None
    unknown_flags = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            unknown_flags.append(a)
            i += 1
            continue
        args_json = a
        i += 1

    tool = argv[0] if argv else ""

    # Detect argparse-style misuse — common orchestrator mistake
    if unknown_flags or args_json.startswith("--"):
        print(
            f"Error: argparse-style flags не поддерживаются (кроме --connection). Параметры передаются JSON-строкой.\n"
            f"\n"
            f"❌ НЕ ТАК:\n"
            f"  python db.py {tool} --pattern '%' --connection db-parsing-dev\n"
            f"  python db.py {tool} --table users\n"
            f"\n"
            f"✓ ПРАВИЛЬНО (JSON позиционным аргументом + --connection):\n"
            f"  python db.py {tool} '{{\"pattern\":\"%\"}}' --connection db-parsing-dev\n"
            f"  python db.py db_table_schema '{{\"table\":\"users\"}}' --connection db-bnmap-prod\n"
            f"\n"
            f"Найдены непонятные флаги: {' '.join(unknown_flags) if unknown_flags else args_json}\n"
            f"См. .claude/docs/orchestrator/skills-rules.md §«Нотация вызовов».",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        arguments = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        print(
            f"Error: invalid JSON in args — {e}\n"
            f"\n"
            f"Параметры скрипту передаются ОДНОЙ JSON-строкой + --connection <name>:\n"
            f"  python db.py {tool} '{{\"pattern\":\"%\"}}' --connection db-parsing-dev",
            file=sys.stderr,
        )
        sys.exit(1)

    # Подмешиваем параметры именованного подключения (ручные аргументы имеют приоритет)
    if connection:
        conn = _load_named_connection(connection)
        if not conn:
            print(f"Error: connection '{connection}' не найдено в config/connections.json", file=sys.stderr)
            sys.exit(1)
        for k, v in conn.items():
            arguments.setdefault(k, v)

    result = asyncio.run(_call_tool_impl(tool, arguments))
    # result — list[TextContent]; выводим только текст
    for tc in result:
        print(tc.text)


if __name__ == "__main__":
    # Если есть аргументы CLI — CLI-режим, иначе MCP-режим (stdio)
    if len(sys.argv) > 1:
        _cli_main()
    else:
        asyncio.run(_mcp_main())
