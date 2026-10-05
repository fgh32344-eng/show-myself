"""
王耀威 · 个人展示网站 —— 后端（业务与数据层 + FastAPI 应用）

本文件分三部分：
  1. util / db / schema / views —— 纯标准库实现，不依赖任何第三方包
     （backend/server.py 零依赖服务器直接复用这一部分）
  2. FastAPI 应用与路由 —— 仅在安装了 fastapi 时才会构建
  3. main() —— 优先用 uvicorn 启动 FastAPI 应用；未安装则自动回退到标准库服务器

推荐运行方式（二选一）：
  python backend\\app.py        自动选择可用后端
  python backend\\server.py     强制使用零依赖标准库服务器

安装依赖后可用：pip install -r backend\\requirements.txt

注意：本文件**刻意不使用** `from __future__ import annotations`。
原因：该导入会把所有注解变成字符串，而 FastAPI/pydantic 是在**模块命名空间**
中求值这些字符串的。build_app() 内部局部导入的 Request / Query / Header 等名字
在模块级并不存在，导致 pydantic 报
    ForwardRef('Request') is not fully defined
进而把 `request: Request` 误判为请求体字段，OpenAPI 生成失败，
所有相关接口返回 422。Python 3.10+ 本身已支持 `X | None` 写法，无需该导入。
"""
import json
import os
import secrets
import sqlite3
import string
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, AsyncIterator, Optional

# --------------------------------------------------------------------------
# util
# --------------------------------------------------------------------------
class util:
    """环境、路径与通用工具。"""

    BASE_DIR = Path(__file__).resolve().parent.parent
    STATIC_DIR = BASE_DIR / "frontend" / "static"
    PAGE_DIR = BASE_DIR / "frontend" / "pages"
    DATA_DIR = BASE_DIR / "data"
    DB_PATH = DATA_DIR / "portfolio.db"
    RESUME_PATH = DATA_DIR / "resume.json"

    SITE_NAME = "王耀威 · 个人主页"
    HOST = os.environ.get("PORTFOLIO_HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORTFOLIO_PORT", "8000"))
    VERSION = "1.0.0"

    ADMIN_USER = os.environ.get("PORTFOLIO_ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("PORTFOLIO_ADMIN_PASSWORD", "admin123")
    TOKEN_TTL = 6 * 3600  # 后台登录有效期（秒）

    MAX_MESSAGES_PER_HOUR = 6  # 同一 IP 每小时留言上限
    MESSAGE_MAX_LEN = 500
    NAME_MAX_LEN = 20

    @staticmethod
    def ensure_dirs() -> None:
        for path in (util.DATA_DIR, util.STATIC_DIR, util.PAGE_DIR):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def read_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def render(page: str, request: Any, **kwargs: Any) -> str:
        """极简模板渲染：frontend/pages/*.html 里用 $var 占位。"""
        template_path = util.PAGE_DIR / page
        if not template_path.exists():
            raise FileNotFoundError(f"页面不存在: {page}")
        tpl = Template(template_path.read_text(encoding="utf-8"))
        ctx = {
            "site_name": util.SITE_NAME,
            "version": util.VERSION,
            "year": datetime.now().year,
            "client_ip": util.client_ip(request),
        }
        ctx.update(kwargs)
        return tpl.safe_substitute(**ctx)

    @staticmethod
    def client_ip(request: Any) -> str:
        """同时兼容 FastAPI Request 与 http.server 的 handler。"""
        headers = getattr(request, "headers", None)
        if headers is not None:
            forwarded = headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        client = getattr(request, "client", None)
        if client is not None:
            host = getattr(client, "host", None)
            if host:
                return host
            if isinstance(client, tuple):
                return client[0]
        address = getattr(request, "client_address", None)
        if isinstance(address, tuple) and address:
            return address[0]
        return "unknown"

    @staticmethod
    def now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def mask_ip(ip: str) -> str:
        """对外展示时对 IP 脱敏。"""
        if not ip:
            return "未知"
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
        return ip[:6] + "***"

    @staticmethod
    def humanize_ua(ua: str) -> str:
        """把 User-Agent 粗略归类成可读的设备信息。"""
        if not ua:
            return "未知设备"
        text = ua.lower()
        if "micromessenger" in text:
            browser = "微信内置浏览器"
        elif "edg/" in text:
            browser = "Edge"
        elif "chrome/" in text and "safari/" in text:
            browser = "Chrome"
        elif "firefox/" in text:
            browser = "Firefox"
        elif "safari/" in text:
            browser = "Safari"
        elif "curl" in text:
            browser = "命令行工具"
        else:
            browser = "其他浏览器"

        if "windows" in text:
            platform = "Windows"
        elif "android" in text:
            platform = "Android"
        elif "iphone" in text or "ipad" in text:
            platform = "iOS"
        elif "mac os" in text:
            platform = "macOS"
        elif "linux" in text:
            platform = "Linux"
        else:
            platform = "未知系统"
        return f"{platform} · {browser}"


# --------------------------------------------------------------------------
# db
# --------------------------------------------------------------------------
class db:
    """SQLite 访问层。每次操作一个短连接，天然线程安全。"""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS visits (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        path       TEXT    NOT NULL,
        ip         TEXT    NOT NULL DEFAULT '',
        user_agent TEXT    NOT NULL DEFAULT '',
        referer    TEXT    NOT NULL DEFAULT '',
        day        TEXT    NOT NULL,
        created_at TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_visits_day ON visits(day);
    CREATE INDEX IF NOT EXISTS idx_visits_path ON visits(path);

    CREATE TABLE IF NOT EXISTS messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        contact    TEXT    NOT NULL DEFAULT '',
        content    TEXT    NOT NULL,
        ip         TEXT    NOT NULL DEFAULT '',
        user_agent TEXT    NOT NULL DEFAULT '',
        approved   INTEGER NOT NULL DEFAULT 1,
        created_at TEXT    NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);

    CREATE TABLE IF NOT EXISTS counters (
        key   TEXT PRIMARY KEY,
        value INTEGER NOT NULL DEFAULT 0
    );
    """

    @staticmethod
    def connect() -> sqlite3.Connection:
        util.ensure_dirs()
        conn = sqlite3.connect(util.DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def init() -> None:
        with db.connect() as conn:
            conn.executescript(db.SCHEMA)
            conn.execute("INSERT OR IGNORE INTO counters(key, value) VALUES ('page_views', 0)")
            conn.commit()

    # ---------------- 访问统计 ----------------
    @staticmethod
    def record_visit(path: str, ip: str, user_agent: str, referer: str) -> None:
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO visits(path, ip, user_agent, referer, day, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (path, ip, user_agent, referer, util.today(), util.now()),
            )
            conn.execute("UPDATE counters SET value = value + 1 WHERE key = 'page_views'")
            conn.commit()

    @staticmethod
    def visit_stats() -> dict[str, Any]:
        with db.connect() as conn:
            total = conn.execute("SELECT value FROM counters WHERE key = 'page_views'").fetchone()
            today = conn.execute("SELECT COUNT(*) AS c FROM visits WHERE day = ?", (util.today(),)).fetchone()
            unique_today = conn.execute(
                "SELECT COUNT(DISTINCT ip) AS c FROM visits WHERE day = ?", (util.today(),)
            ).fetchone()
            unique_all = conn.execute("SELECT COUNT(DISTINCT ip) AS c FROM visits").fetchone()
            first = conn.execute("SELECT created_at FROM visits ORDER BY id ASC LIMIT 1").fetchone()
            daily = conn.execute(
                """SELECT day, COUNT(*) AS views, COUNT(DISTINCT ip) AS visitors
                   FROM visits
                   WHERE day >= date('now', 'localtime', '-13 days')
                   GROUP BY day ORDER BY day ASC"""
            ).fetchall()
            top_pages = conn.execute(
                """SELECT path, COUNT(*) AS views FROM visits
                   GROUP BY path ORDER BY views DESC LIMIT 6"""
            ).fetchall()
            recent = conn.execute(
                "SELECT path, ip, user_agent, created_at FROM visits ORDER BY id DESC LIMIT 12"
            ).fetchall()

        by_day = {row["day"]: row for row in daily}
        series: list[dict[str, Any]] = []
        now_ts = datetime.now().timestamp()
        for offset in range(13, -1, -1):  # 补齐空缺日期，避免图表断裂
            day = datetime.fromtimestamp(now_ts - offset * 86400)
            key = day.strftime("%Y-%m-%d")
            row = by_day.get(key)
            series.append(
                {
                    "day": key,
                    "label": day.strftime("%m-%d"),
                    "views": row["views"] if row else 0,
                    "visitors": row["visitors"] if row else 0,
                }
            )

        return {
            "total_views": total["value"] if total else 0,
            "today_views": today["c"] if today else 0,
            "today_visitors": unique_today["c"] if unique_today else 0,
            "total_visitors": unique_all["c"] if unique_all else 0,
            "since": first["created_at"] if first else util.now(),
            "daily": series,
            "top_pages": [dict(row) for row in top_pages],
            "recent": [
                {
                    "path": row["path"],
                    "ip": util.mask_ip(row["ip"]),
                    "device": util.humanize_ua(row["user_agent"]),
                    "created_at": row["created_at"],
                }
                for row in recent
            ],
        }

    # ---------------- 留言板 ----------------
    @staticmethod
    def add_message(name: str, contact: str, content: str, ip: str, user_agent: str) -> dict[str, Any]:
        with db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO messages(name, contact, content, ip, user_agent, approved, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (name, contact, content, ip, user_agent, util.now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return db.public_message(row)

    @staticmethod
    def public_message(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "content": row["content"],
            "created_at": row["created_at"],
            "device": util.humanize_ua(row["user_agent"]),
        }

    @staticmethod
    def recent_messages_by_ip(ip: str, hours: int = 1) -> int:
        with db.connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS c FROM messages
                   WHERE ip = ? AND created_at >= datetime('now', 'localtime', ?)""",
                (ip, f"-{hours} hours"),
            ).fetchone()
        return row["c"] if row else 0

    @staticmethod
    def list_messages(
        page: int,
        page_size: int,
        keyword: str = "",
        approved: Optional[int] = None,
        include_private: bool = True,
    ) -> dict[str, Any]:
        """分页查询留言。

        include_private=False 时只返回公开字段（id/name/content/created_at/device），
        联系方式与 IP 仅在后台接口可见。
        """
        where: list[str] = []
        params: list[Any] = []
        if keyword:
            where.append("(name LIKE ? OR content LIKE ? OR contact LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like, like])
        if approved is not None:
            where.append("approved = ?")
            params.append(approved)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        with db.connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS c FROM messages {clause}", params).fetchone()["c"]
            rows = conn.execute(
                f"SELECT * FROM messages {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()

        if include_private:
            items = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "contact": row["contact"],
                    "content": row["content"],
                    "ip": row["ip"],
                    "device": util.humanize_ua(row["user_agent"]),
                    "approved": bool(row["approved"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        else:
            items = [db.public_message(row) for row in rows]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "items": items,
        }

    @staticmethod
    def message_count(approved: Optional[int] = None) -> int:
        clause = "" if approved is None else "WHERE approved = ?"
        params: list[Any] = [] if approved is None else [approved]
        with db.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) AS c FROM messages {clause}", params).fetchone()["c"]

    @staticmethod
    def set_approved(message_id: int, approved: bool) -> bool:
        with db.connect() as conn:
            cursor = conn.execute(
                "UPDATE messages SET approved = ? WHERE id = ?", (1 if approved else 0, message_id)
            )
            conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def delete_message(message_id: int) -> bool:
        with db.connect() as conn:
            cursor = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            conn.commit()
        return cursor.rowcount > 0


# --------------------------------------------------------------------------
# schema
#
# 这里刻意**不继承 pydantic**BaseModel：早先的版本在模型上覆盖了 __init__
# 来同时兼容两种运行模式，结果破坏了 pydantic 的内部状态，FastAPI 模式下
# 会抛 `AttributeError: object has no attribute '__pydantic_fields_set__'`，
# 登录与留言接口直接 500。
#
# 现在的做法是把「校验」和「模型」分开：
#   * 校验规则集中在 _normalize_* 纯函数里，两种模式共用，行为完全一致
#   * MessageIn / LoginIn 只是普通容器；FastAPI 路由用 Body(...) 接收 dict，
#     再交给同一个 from_payload() 校验
# 这样既不与 pydantic 的内部机制冲突，OpenAPI 也能正常生成。
# --------------------------------------------------------------------------
HAS_PYDANTIC = False


def _normalize_message(payload: dict[str, Any]) -> tuple[str, str, str]:
    """校验并规范化留言入参，返回 (name, contact, content)。失败抛 ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")

    name = str(payload.get("name") or "").strip()[: util.NAME_MAX_LEN]
    contact = str(payload.get("contact") or "").strip()[:80]
    content = str(payload.get("content") or "").strip()

    if not content:
        raise ValueError("留言内容不能为空")
    if len(content) > util.MESSAGE_MAX_LEN:
        raise ValueError(f"留言内容不能超过 {util.MESSAGE_MAX_LEN} 字")

    return name or "匿名访客", contact, content


def _normalize_login(payload: dict[str, Any]) -> tuple[str, str]:
    """校验并规范化登录入参，返回 (username, password)。"""
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    username = str(payload.get("username") or "").strip()[:40]
    password = str(payload.get("password") or "")[:80]
    return username, password


class MessageIn:
    """留言提交模型（普通容器 + 共享校验）。"""

    __slots__ = ("name", "contact", "content")

    def __init__(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> None:
        merged = dict(payload or {})
        merged.update(kwargs)
        self.name, self.contact, self.content = _normalize_message(merged)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MessageIn":
        return cls(payload)


class LoginIn:
    """后台登录模型（普通容器 + 共享校验）。"""

    __slots__ = ("username", "password")

    def __init__(self, payload: dict[str, Any] | None = None, **kwargs: Any) -> None:
        merged = dict(payload or {})
        merged.update(kwargs)
        self.username, self.password = _normalize_login(merged)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LoginIn":
        return cls(payload)


# --------------------------------------------------------------------------
# views / 鉴权
# --------------------------------------------------------------------------
class views:
    """后台登录令牌管理（内存态，重启即失效）。"""

    _tokens: dict[str, dict[str, Any]] = {}

    @staticmethod
    def login(username: str, password: str) -> Optional[str]:
        ok_user = secrets.compare_digest(username or "", util.ADMIN_USER)
        ok_pass = secrets.compare_digest(password or "", util.ADMIN_PASSWORD)
        if not (ok_user and ok_pass):
            return None
        token = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        views._tokens[token] = {"created": time.time(), "user": username}
        return token

    @staticmethod
    def verify(token: Optional[str]) -> bool:
        if not token:
            return False
        record = views._tokens.get(token)
        if not record:
            return False
        if time.time() - record["created"] > util.TOKEN_TTL:
            views._tokens.pop(token, None)
            return False
        return True

    @staticmethod
    def revoke(token: Optional[str]) -> None:
        if token:
            views._tokens.pop(token, None)


# --------------------------------------------------------------------------
# FastAPI 应用（可选）
# --------------------------------------------------------------------------
def build_app() -> Any:
    """构建 FastAPI 应用；未安装 fastapi 时返回 None。"""
    try:
        from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
        from fastapi.responses import FileResponse, HTMLResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError:
        return None

    # 注意：注解在 `from __future__ import annotations` 下是字符串，
    # 由 pydantic 在**模块全局命名空间**中求值。因此这里必须使用模块级
    # 导入的 Optional，不能在函数内起 `Optional` 之类的别名——
    # 那样 pydantic 找不到名字，OpenAPI 生成失败，所有相关接口返回 422。

    @asynccontextmanager
    async def lifespan(_: Any) -> AsyncIterator[None]:
        """应用启动/关闭钩子。

        使用 lifespan 而非已弃用的 @app.on_event("startup")，
        避免 FastAPI 输出 DeprecationWarning。
        """
        util.ensure_dirs()
        db.init()
        yield

    application = FastAPI(
        title="王耀威 · 个人主页 API",
        description="个人展示网站后端：简历数据接口、留言板、访问统计与后台管理。",
        version=util.VERSION,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> str:
        if not views.verify(x_admin_token):
            raise HTTPException(status_code=401, detail="未登录或登录已过期，请重新登录")
        return x_admin_token or ""

    # ------------- 简历 -------------
    @application.get("/api/resume", tags=["简历"], summary="获取简历结构化数据")
    def get_resume() -> Any:
        if not util.RESUME_PATH.exists():
            raise HTTPException(status_code=500, detail="resume.json 缺失")
        return util.read_json(util.RESUME_PATH)

    @application.get("/api/profile", tags=["简历"], summary="获取个人信息卡片")
    def get_profile() -> Any:
        return util.read_json(util.RESUME_PATH)["profile"]

    @application.get("/api/projects", tags=["简历"], summary="获取项目列表")
    def get_projects(tag: Optional[str] = Query(default=None, description="按技术栈过滤")) -> Any:
        projects = util.read_json(util.RESUME_PATH)["projects"]
        if tag:
            projects = [p for p in projects if any(tag.lower() in t.lower() for t in p.get("tags", []))]
        return {"total": len(projects), "items": projects}

    @application.get("/api/skills", tags=["简历"], summary="获取技能与在学清单")
    def get_skills() -> Any:
        data = util.read_json(util.RESUME_PATH)
        return {"skills": data["skills"], "learning": data["learning"]}

    # ------------- 统计 -------------
    @application.post("/api/visit", tags=["统计"], summary="上报一次页面访问")
    async def post_visit(
        request: Request,
        payload: Optional[dict] = Body(default=None, description="可选，形如 {\"path\": \"/\"}"),
    ) -> Any:
        path = "/"
        if isinstance(payload, dict):
            path = str(payload.get("path") or "/")[:200]
        db.record_visit(
            path,
            util.client_ip(request),
            request.headers.get("user-agent", ""),
            request.headers.get("referer", ""),
        )
        stats = db.visit_stats()
        return {
            "ok": True,
            "total_views": stats["total_views"],
            "today_views": stats["today_views"],
            "today_visitors": stats["today_visitors"],
        }

    @application.get("/api/stats", tags=["统计"], summary="获取站点访问统计")
    def get_stats() -> Any:
        stats = db.visit_stats()
        stats["total_messages"] = db.message_count(approved=1)
        return stats

    # ------------- 留言 -------------
    @application.get("/api/messages", tags=["留言"], summary="留言列表（公开）")
    def get_messages(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=50),
    ) -> Any:
        data = db.list_messages(page=page, page_size=page_size, approved=1, include_private=False)
        data["total_all"] = db.message_count()
        return data

    @application.post("/api/messages", status_code=201, tags=["留言"], summary="提交留言")
    def create_message(
        request: Request,
        payload: dict = Body(
            ...,
            description="留言内容",
            openapi_examples={
                "默认": {
                    "value": {"name": "访客", "contact": "you@example.com", "content": "你好！"},
                }
            },
        ),
    ) -> Any:
        try:
            message = MessageIn.from_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        ip = util.client_ip(request)
        if db.recent_messages_by_ip(ip) >= util.MAX_MESSAGES_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail=f"留言过于频繁，同一访客每小时最多 {util.MAX_MESSAGES_PER_HOUR} 条，请稍后再试。",
            )
        return db.add_message(
            message.name, message.contact, message.content, ip, request.headers.get("user-agent", "")
        )

    # ------------- 后台 -------------
    @application.post("/api/admin/login", tags=["后台"], summary="管理员登录")
    def admin_login(
        payload: dict = Body(
            ...,
            description="后台账号密码",
            openapi_examples={
                "默认": {"value": {"username": util.ADMIN_USER, "password": util.ADMIN_PASSWORD}},
            },
        ),
    ) -> Any:
        try:
            login = LoginIn.from_payload(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        token = views.login(login.username, login.password)
        if not token:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {"token": token, "expires_in": util.TOKEN_TTL, "user": login.username}

    @application.post("/api/admin/logout", tags=["后台"], summary="管理员登出")
    def admin_logout(token: str = Depends(require_admin)) -> Any:
        views.revoke(token)
        return {"ok": True}

    @application.get("/api/admin/messages", tags=["后台"], summary="留言管理列表")
    def admin_messages(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
        keyword: str = Query(default=""),
        approved: Optional[int] = Query(default=None, ge=0, le=1),
        _: str = Depends(require_admin),
    ) -> Any:
        return db.list_messages(page=page, page_size=page_size, keyword=keyword.strip(), approved=approved)

    @application.get("/api/admin/overview", tags=["后台"], summary="后台概览数据")
    def admin_overview(_: str = Depends(require_admin)) -> Any:
        stats = db.visit_stats()
        return {
            "total_views": stats["total_views"],
            "today_views": stats["today_views"],
            "today_visitors": stats["today_visitors"],
            "total_messages": db.message_count(),
            "total_visitors": stats["total_visitors"],
            "daily": stats["daily"],
            "top_pages": stats["top_pages"],
            "recent_visits": stats["recent"],
        }

    @application.patch("/api/admin/messages/{message_id}", tags=["后台"], summary="审核留言")
    def admin_review(
        message_id: int, approved: bool = Query(...), _: str = Depends(require_admin)
    ) -> Any:
        if not db.set_approved(message_id, approved):
            raise HTTPException(status_code=404, detail="留言不存在")
        return {"ok": True, "id": message_id, "approved": approved}

    @application.delete("/api/admin/messages/{message_id}", tags=["后台"], summary="删除留言")
    def admin_delete(message_id: int, _: str = Depends(require_admin)) -> Any:
        if not db.delete_message(message_id):
            raise HTTPException(status_code=404, detail="留言不存在")
        return {"ok": True, "id": message_id}

    @application.get("/api/health", tags=["系统"], summary="健康检查")
    def health() -> Any:
        return {
            "status": "ok",
            "site": util.SITE_NAME,
            "version": util.VERSION,
            "server_time": util.now(),
            "database": str(util.DB_PATH),
            "admin_user": util.ADMIN_USER,
            "runtime": "fastapi",
        }

    # ------------- 页面 -------------
    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def page_index(request: Request) -> Any:
        return HTMLResponse(util.render("index.template.html", request))

    @application.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    def page_admin(request: Request) -> Any:
        return HTMLResponse(util.render("admin.html", request))

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Any:
        icon = util.STATIC_DIR / "favicon.svg"
        if not icon.exists():
            raise HTTPException(status_code=404, detail="favicon 不存在")
        return FileResponse(icon, media_type="image/svg+xml")

    application.mount("/static", StaticFiles(directory=str(util.STATIC_DIR)), name="static")
    return application


app = build_app()


# --------------------------------------------------------------------------
# 控制台输出
# 中文横幅统一交给 Python 打印，而不是写在 .bat 里：
# .bat 由 cmd.exe 按 ANSI 代码页逐字节解析，中文字节极易变成乱码，
# 而 Python 会按当前控制台编码自行处理，稳定得多。
# --------------------------------------------------------------------------
def say(message: str = "") -> None:
    """打印一行控制台信息，遇到当前编码无法表示的字符时降级为 ? 而不是崩溃。"""
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(message.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def banner(mode: str, docs: bool = False) -> None:
    base = f"http://{util.HOST}:{util.PORT}"
    say()
    say(f"  {util.SITE_NAME}")
    say(f"  运行模式：{mode}")
    say("  " + "-" * 52)
    say(f"  首页     {base}/")
    say(f"  后台     {base}/admin   （{util.ADMIN_USER} / {util.ADMIN_PASSWORD}）")
    if docs:
        say(f"  接口文档 {base}/api/docs")
    say("  " + "-" * 52)
    say("  浏览器打开上面的首页地址即可，按 Ctrl+C 停止服务")
    say()


def main() -> None:
    util.ensure_dirs()
    db.init()

    if app is not None:
        import uvicorn

        banner("FastAPI + uvicorn")
        uvicorn.run(app, host=util.HOST, port=util.PORT, log_level="info")
        return

    say("  未检测到 fastapi，自动回退到零依赖标准库模式（页面与接口完全一致）")
    say("  需要交互式接口文档可执行：pip install -r backend\\requirements.txt")
    import server

    server.main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\n已停止")
        sys.exit(0)
