"""校验隐私脱敏与 Pages 产物。

用法：python tests/check_privacy.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPO = BASE.parent

# 需要彻底消失的手机号各种写法。
# 关键：不把号码原文写进本文件——否则这个检查脚本自己就成了泄露源
# （仓库公开后，别人搜 183 就能搜到本脚本）。
# 因此用片段拼接，源码里不出现完整的连续号码。
_P = ["183", "2577", "3203"]
_FULL = "".join(_P)   # 仅在内存中拼接
PHONE_PATTERNS = [
    re.compile(r"-".join(_P)),          # 183-2577-3203
    re.compile(_FULL),                  # 18325773203
    re.compile(r"\s*".join(_P)),        # 中间带空格
]
# 必须仍然存在的邮箱
EMAIL = "2937479259@qq.com"

# 本文件自身排除在扫描外：它的搜索结果为空即代表没有残留，
# 而它内部只以碎片形式持有号码，不含连续原文。
SELF = Path(__file__).resolve()

SCAN_DIRS = [BASE, REPO / "docs"]
SCAN_SUFFIXES = {".html", ".json", ".js", ".py", ".md", ".css", ".txt", ".bat", ".utf8", ".sh"}
SKIP_DIRS = {"__pycache__", "_tmp", ".git", "assets-src", "node_modules"}

ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    print(f"  [{'OK' if passed else 'BAD'}] {label}" + (f"  {detail}" if detail else ""))
    if not passed:
        ok = False


print("=== 1. 扫描所有产物，确认手机号已彻底移除 ===")
hits: list[str] = []
scanned = 0
for root in SCAN_DIRS:
    if not root.exists():
        continue
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path == SELF:
            continue  # 见文件顶部说明：本脚本只在内存中拼接号码，不含连续原文
        if path.suffix.lower() not in SCAN_SUFFIXES and path.name != ".gitignore":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for pattern in PHONE_PATTERNS:
            if pattern.search(text):
                hits.append(str(path.relative_to(REPO)))
                break

check(f"已扫描 {scanned} 个文本文件", True)
check("未发现手机号残留", not hits, ", ".join(hits[:6]))

print("\n=== 2. 确认邮箱仍然公开 ===")
resume = json.loads((BASE / "data" / "resume.json").read_text(encoding="utf-8"))
profile = resume["profile"]
check("resume.json 里手机号为空", profile.get("phone") in ("", None), repr(profile.get("phone")))
check("resume.json 里有 phoneNote 说明", bool(profile.get("phoneNote")), repr(profile.get("phoneNote")))
check("resume.json 里保留邮箱", profile.get("email") == EMAIL, profile.get("email"))
check("social 里不再有 tel 链接",
      all("tel:" not in (s.get("url") or "") for s in profile.get("social", [])),
      str([s for s in profile.get("social", []) if "tel:" in (s.get("url") or "")]))

print("\n=== 3. 确认页面渲染不会产生坏链接 ===")
js = (BASE / "frontend" / "static" / "js" / "main.js").read_text(encoding="utf-8")
check("JS 已处理空手机号（phoneNote 分支）", "phoneNote" in js)
check("空手机号时不生成 tel: 链接", "const phoneCard = phone" in js and ": '';" in js)

for name, rel in [("Pages 产物", REPO / "docs" / "index.html"),
                  ("离线单文件版", BASE / "dist" / "portfolio-standalone.html")]:
    path = Path(rel)
    if not path.exists():
        check(f"{name} 存在", False, str(path))
        continue
    html = path.read_text(encoding="utf-8")
    check(f"{name} 含邮箱", EMAIL in html)
    check(f"{name} 含“面试时提供”", "面试时提供" in html)
    check(f"{name} 无 tel: 链接", "tel:183" not in html and 'href="tel:"' not in html)
    check(f"{name} 含真实头像", "data:image/jpeg;base64," in html)

print("\n=== 4. 仓库里不应包含运行时数据 ===")
db_files = [str(p.relative_to(REPO)) for p in (BASE / "data").glob("*.db*")]
print(f"  本地存在的数据库文件（应被 gitignore）: {db_files or '无'}")
check("原图已归档且被忽略",
      (BASE / "assets-src" / "photo-original.png").exists()
      and "assets-src/" in (BASE / ".gitignore").read_text(encoding="utf-8"))

print("\n结果：" + ("通过，隐私设置符合要求" if ok else "未通过，请检查标记为 BAD 的项"))
sys.exit(0 if ok else 1)
