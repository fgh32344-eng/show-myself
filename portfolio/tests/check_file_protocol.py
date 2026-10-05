"""用 file:// 协议（双击的等价方式）检查单文件版的真实可用性。

之前的检查都走 HTTP，但双击打开用的是 file://，
两者的路径解析规则完全不同，必须单独验证。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TARGETS = [
    ("离线单文件版", REPO / "portfolio" / "dist" / "portfolio-standalone.html"),
    ("Pages 产物", REPO / "docs" / "index.html"),
    ("服务端模板（有意不可双击）", REPO / "portfolio" / "frontend" / "pages" / "index.template.html"),
]

failures: list[str] = []

for name, path in TARGETS:
    print(f"=== {name}：{path.relative_to(REPO)} ===")
    if not path.exists():
        print("  [BAD] 文件不存在\n")
        continue

    # 服务端模板是有意不可双击的（文件名即约定），它的绝对引用属于设计本身，
    # 因此对该文件只做“信息展示”，不计入失败。
    is_template = ".template." in path.name

    html = path.read_text(encoding="utf-8")

    # file:// 下所有不以 data:/#/mailto:/http 开头的 href/src 都会按本地路径解析
    refs = re.findall(r'(?:href|src)="([^"]+)"', html)
    risky = [
        r for r in refs
        if not r.startswith(("data:", "#", "mailto:", "http://", "https://", "tel:"))
    ]
    print(f"  file:// 下需要解析的本地引用: {risky or '无'}")

    # 以 / 开头的绝对路径在 file:// 下会指向盘符根目录
    abs_refs = [r for r in risky if r.startswith("/")]
    flag = "提示" if is_template else ("BAD" if abs_refs else "OK")
    print(f"  [{flag}] 根路径绝对引用 {abs_refs or '无'}"
          + ("（模板设计如此，需服务器解析）" if is_template and abs_refs else ""))

    # JS 里是否用绝对路径拼资源（头像）
    js_abs = re.findall(r"__ASSET_BASE__\s*=\s*'([^']*)'", html)
    asset_base = js_abs[0] if js_abs else "(未注入)"
    base_ok = not asset_base.startswith("/")
    flag = "提示" if is_template else ("OK" if base_ok else "BAD")
    print(f"  [{flag}] __ASSET_BASE__ = {asset_base!r}")

    # 头像是否内联
    has_inline_img = "data:image/jpeg;base64," in html or "data:image/png;base64," in html
    ok = has_inline_img or not js_abs
    flag = "提示" if is_template else ("OK" if ok else "BAD")
    print(f"  [{flag}] 头像不依赖外部文件" + ("（已内联）" if has_inline_img else ""))

    # 数据是否内联（否则 file:// 下 fetch 必然失败）
    has_data = "window.__SITE_DATA__" in html
    flag = "提示" if is_template else ("OK" if has_data else "BAD")
    print(f"  [{flag}] 简历数据已内联"
          + ("" if has_data else "（需后端接口，file:// 下无法获取）"))

    # 样式是否内联
    has_style = "<style>" in html and "--cyan:" in html
    flag = "提示" if is_template else ("OK" if has_style else "BAD")
    print(f"  [{flag}] 样式已内联")

    # 记录真正的失败项（模板不计入）
    if not is_template:
        if abs_refs:
            failures.append(f"{name}: 存在根路径绝对引用 {abs_refs}")
        if js_abs and not base_ok:
            failures.append(f"{name}: __ASSET_BASE__ 为绝对路径")
        if not has_data:
            failures.append(f"{name}: 简历数据未内联")
        if not has_style:
            failures.append(f"{name}: 样式未内联")

    print()

print("结果：" + ("通过，产物均可 file:// 双击打开" if not failures else "未通过"))
for item in failures:
    print("  -", item)
sys.exit(0 if not failures else 1)
