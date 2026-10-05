"""确认「误双击兜底脚本」只存在于模板，不污染真正的产物。

用法：python tests/check_template.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPO = BASE.parent

TEMPLATE = BASE / "frontend" / "pages" / "index.template.html"
ARTIFACTS = [
    ("单文件离线版", BASE / "dist" / "portfolio-standalone.html"),
    ("Pages 产物", REPO / "docs" / "index.html"),
]

MARKER = "请打开正确的文件"   # 兜底提示框里的标题

ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    print(f"  [{'OK' if passed else 'BAD'}] {label}" + (f"  {detail}" if detail else ""))
    if not passed:
        ok = False


print("=== 模板 ===")
check("模板存在", TEMPLATE.exists(), str(TEMPLATE.relative_to(REPO)))
if TEMPLATE.exists():
    text = TEMPLATE.read_text(encoding="utf-8")
    check("模板含误双击兜底脚本", MARKER in text)
    check("兜底脚本带 file:// 协议判断", "location.protocol !== 'file:'" in text)
    check("兜底脚本带数据注入判断（避免误伤离线版）", "window.__SITE_DATA__" in text)
    check("模板顶部有免责注释", "服务端模板" in text)

print("\n=== 产物（必须干净，不能被兜底脚本污染）===")
for name, path in ARTIFACTS:
    if not path.exists():
        check(f"{name} 存在", False, str(path))
        continue
    html = path.read_text(encoding="utf-8")
    check(f"{name} 不含兜底脚本", MARKER not in html)
    check(f"{name} 样式已内联", "--cyan:" in html)
    check(f"{name} 数据已内联", "window.__SITE_DATA__" in html)
    check(f"{name} 头像已内联", "data:image/jpeg;base64," in html)
    # 离线版必须自己声明 STANDALONE，才能让兜底逻辑放行
    check(f"{name} 声明了 STANDALONE", "window.__STANDALONE__ = true" in html)

print("\n=== 旧的 index.html 不应再存在于 pages/ ===")
old = BASE / "frontend" / "pages" / "index.html"
check("pages/index.html 已移除（避免误双击）", not old.exists(),
      "仍存在，用户可能再次打开错误文件" if old.exists() else "")

print("\n结果：" + ("通过" if ok else "未通过"))
sys.exit(0 if ok else 1)
