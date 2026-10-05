"""FastAPI 模式专项验证（也兼容零依赖标准库模式）。

检查两种运行模式的能力差异，特别是 FastAPI 才有的交互式接口文档。

用法：先启动服务，再执行
    python tests/check_fastapi.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    print(f"  [{'OK' if passed else 'BAD'}] {label}" + (f"  {detail}" if detail else ""))
    if not passed:
        ok = False


def fetch(path: str):
    """返回 (status, bytes, content_type)，失败返回 (code, b'', '')。"""
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode(), ""


print("=== 运行模式 ===")
status, body, _ = fetch("/api/health")
if status != 200:
    print(f"  服务未运行或异常（status={status}）：{body[:120]!r}")
    sys.exit(1)
health = json.loads(body)
runtime = health.get("runtime", "unknown")
print(f"  runtime = {runtime}")
print(f"  site    = {health.get('site')}")
print(f"  version = {health.get('version')}")

print("\n=== 公共页面与静态资源 ===")
for path, label in [
    ("/", "首页"),
    ("/admin", "后台页"),
    ("/favicon.ico", "favicon"),
    ("/static/css/style.css", "样式"),
    ("/static/js/main.js", "脚本"),
    ("/static/assets/avatar.jpg", "头像"),
]:
    status, body, ctype = fetch(path)
    check(f"{label} {path}", status == 200 and len(body) > 0, f"{status}, {len(body)} 字节")

print("\n=== 简历接口 ===")
for path in ["/api/resume", "/api/profile", "/api/projects", "/api/skills", "/api/stats", "/api/messages"]:
    status, body, _ = fetch(path)
    good = status == 200
    if good:
        try:
            json.loads(body)
        except Exception:  # noqa: BLE001
            good = False
    check(f"GET {path}", good, str(status))

print("\n=== FastAPI 专属能力 ===")
docs_status, docs_body, docs_ctype = fetch("/api/docs")
if runtime == "fastapi":
    check("交互式文档 /api/docs 可访问", docs_status == 200 and b"swagger" in docs_body.lower(),
          f"{docs_status}, {docs_ctype}")
    spec_status, spec_body, _ = fetch("/api/openapi.json")
    paths = {}
    if spec_status == 200:
        try:
            paths = json.loads(spec_body).get("paths", {})
        except Exception:  # noqa: BLE001
            paths = {}
    check("OpenAPI 规范可解析", bool(paths), f"{len(paths)} 个路径")
    expected = {"/api/resume", "/api/profile", "/api/projects", "/api/skills",
                "/api/visit", "/api/stats", "/api/messages",
                "/api/admin/login", "/api/admin/messages", "/api/admin/overview"}
    missing = sorted(p for p in expected if p not in paths)
    check("所有接口都出现在 OpenAPI 里", not missing, f"缺失: {missing}")
else:
    print(f"  当前为 {runtime} 模式，无接口文档（属预期）")
    check("零依赖模式下 /api/docs 返回说明页",
          docs_status == 200 and b"FastAPI" in docs_body, str(docs_status))

print("\n=== 后台鉴权（两种模式都应正常）===")
status, _, _ = fetch("/api/admin/overview")
check("未登录访问后台接口被拒", status == 401, str(status))

req = urllib.request.Request(
    BASE + "/api/admin/login",
    data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read()).get("token", "")
    check("管理员登录成功", bool(token))
    req2 = urllib.request.Request(
        BASE + "/api/admin/overview", headers={"x-admin-token": token}
    )
    with urllib.request.urlopen(req2, timeout=10) as resp:
        overview = json.loads(resp.read())
    check("带令牌可读后台概览", "total_views" in overview, str(list(overview)[:5]))
except Exception as exc:  # noqa: BLE001
    check("管理员登录流程", False, str(exc))

print("\n=== 留言写入（含中文与限流字段）===")
req = urllib.request.Request(
    BASE + "/api/messages",
    data=json.dumps({"name": "FastAPI 验证", "content": "中文与 emoji 🚀 测试"},
                    ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        created = json.loads(resp.read())
    check("提交留言成功", resp.status == 201 and bool(created.get("id")), str(resp.status))
except urllib.error.HTTPError as exc:
    check("提交留言成功", exc.code in (201, 429), f"HTTP {exc.code}")
except Exception as exc:  # noqa: BLE001
    check("提交留言成功", False, str(exc))

print("\n结果：" + ("通过" if ok else "未通过"))
sys.exit(0 if ok else 1)
