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

for name, path in TARGETS:
    print(f"=== {name}：{path.relative_to(REPO)} ===")
    if not path.exists():
        print("  [BAD] 文件不存在\n")
        continue

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
    print(f"  [{'BAD' if abs_refs else 'OK'}] 无根路径绝对引用 {abs_refs or ''}")

    # JS 里是否用绝对路径拼资源（头像）
    js_abs = re.findall(r"__ASSET_BASE__\s*=\s*'([^']*)'", html)
    asset_base = js_abs[0] if js_abs else "(未注入)"
    print(f"  __ASSET_BASE__ = {asset_base!r}"
          + ("  [OK] 相对/空，file:// 下可用" if not asset_base.startswith("/") else "  [BAD] 绝对，file:// 下会 404"))

    # 头像是否内联
    has_inline_img = "data:image/jpeg;base64," in html or "data:image/png;base64," in html
    print(f"  [{'OK' if has_inline_img or not js_abs else 'BAD'}] 头像不依赖外部文件"
          + (f"（已内联）" if has_inline_img else ""))

    # 数据是否内联（否则 file:// 下 fetch 必然失败）
    has_data = "window.__SITE_DATA__" in html
    print(f"  [{'OK' if has_data else 'BAD'}] 简历数据已内联"
          + ("" if has_data else "（file:// 下无法 fetch 接口，页面将空白）"))

    # 样式是否内联
    has_style = "<style>" in html and "--cyan:" in html
    print(f"  [{'OK' if has_style else 'BAD'}] 样式已内联")

    print()
