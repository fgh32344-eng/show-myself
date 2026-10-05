"""校验单文件离线版是否真的自包含（不依赖任何外部请求）。

用法：python tests/check_standalone.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FILE = BASE / "dist" / "portfolio-standalone.html"

if not FILE.exists():
    print(f"FAIL 找不到 {FILE}，请先执行 python tests/build_standalone.py")
    sys.exit(1)

html = FILE.read_text(encoding="utf-8")
ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    print(f"  [{'OK' if passed else 'BAD'}] {label}" + (f"  {detail}" if detail else ""))
    if not passed:
        ok = False


print(f"文件：{FILE.name}  {FILE.stat().st_size / 1024:.1f} KB\n")

# 1. 不能有任何需要网络/file:// 才能取到的外链
external = re.findall(r'(?:href|src)="((?:https?:)?//[^"]+)"', html)
check("无 http(s) 外链", not external, str(external[:3]))

abs_paths = re.findall(r'(?:href|src)="(/[^"]*)"', html)
check("无根路径绝对引用（file:// 下会指向盘符根）", not abs_paths, str(abs_paths[:3]))

file_paths = re.findall(r'(?:href|src)="(file://[^"]*)"', html)
check("无 file:// 链接", not file_paths, str(file_paths[:3]))

# 2. 样式与脚本必须内联
check("样式已内联", "<style>" in html and "--cyan:" in html)
check("脚本已内联", "function renderProfile" in html)
check("无 <link rel=stylesheet>", 'rel="stylesheet"' not in html)
check("无 <script src=", "<script src=" not in html)

# 3. 图片资源不能指向外部文件
#    注意：/static/ 会作为 JS 里的**兜底常量**出现（ASSET_BASE 默认值），
#    离线版由 __ASSET_BASE__='' 覆盖，因此只需确认没有静态资源外链。
static_refs = re.findall(r'(?:href|src)="/static/[^"]*"', html)
check("无 /static 静态资源外链", not static_refs, str(static_refs))
data_uris = re.findall(
    r'"data:image/(?:svg\+xml|jpeg|png|webp);base64,[A-Za-z0-9+/=]{20,}"', html
)
check("图标与头像均为内联 data URI", len(data_uris) >= 2, f"发现 {len(data_uris)} 处")
check("头像为真实照片（JPEG 内联）", "data:image/jpeg;base64," in html)

# 3. 数据必须内联且可解析
match = re.search(r"window\.__SITE_DATA__\s*=\s*(\{.*?\});\s*\nwindow\.__STANDALONE__", html, re.S)
check("找到内联数据", match is not None)
if match:
    try:
        data = json.loads(match.group(1))
        resume = data["resume"]
        check("JSON 可解析", True)
        check("含姓名", resume["profile"]["name"] == "王耀威", resume["profile"]["name"])
        check("含 4 个项目", len(resume["projects"]) == 4, str(len(resume["projects"])))
        check("含技能矩阵", len(data["skills"]["skills"]) == 5, str(len(data["skills"]["skills"])))
        check("含自我评价", len(resume["about"]) > 30)
    except Exception as exc:
        check("JSON 可解析", False, str(exc))

check("标记为离线模式", "window.__STANDALONE__ = true" in html)

# 5. 离线时必须短路掉后端调用（有 STANDALONE 守卫）
api_refs = sorted(set(re.findall(r"api\('(/api/[^']+)'", html)))
guard_count = html.count("if (STANDALONE)")
check("后端调用均已加离线守卫", guard_count >= 2,
      f"守卫 {guard_count} 处；代码中仍保留的接口引用: {api_refs}")

print("\n结果：" + ("通过，可双击直接打开" if ok else "未通过，请检查上面标记为 BAD 的项"))
sys.exit(0 if ok else 1)
