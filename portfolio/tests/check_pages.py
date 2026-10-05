"""模拟 GitHub Pages：静态托管 docs/ 目录，校验产物是否可用。

用法：python tests/check_pages.py [端口]
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

PORT = sys.argv[1] if len(sys.argv) > 1 else "8100"
BASE = f"http://127.0.0.1:{PORT}"
REPO = Path(__file__).resolve().parent.parent.parent

html = urllib.request.urlopen(BASE + "/", timeout=8).read().decode("utf-8")

print(f"=== 模拟 GitHub Pages（静态托管 docs/，端口 {PORT}）===")
print(f"  首页状态 200 | 大小 {len(html.encode('utf-8')) / 1024:.1f} KB")

# 静态托管下不应有任何额外的资源请求
refs = re.findall(r'(?:href|src)="([^"]+)"', html)
allowed_prefix = ("#", "data:", "mailto:", "https://github.com", "tel:")
# 只检查 HTML 属性里的真实外链；
# JS 源码内部含有兜底常量 ASSET_BASE='/static/'（离线时被 __ASSET_BASE__='' 覆盖），
# 那是代码文本而非资源引用，不能算外链。
external = [r for r in refs if not r.startswith(allowed_prefix) and not r.startswith("${")]
static_refs = [r for r in refs if r.startswith("/static/")]
print(f"  需额外请求的资源: {external or '无（完全自包含）'}")
print(f"  指向 /static 的属性引用: {static_refs or '无'}")

# 内联数据可解析
match = re.search(
    r"window\.__SITE_DATA__\s*=\s*(\{.*?\});\s*\nwindow\.__STANDALONE__", html, re.S
)
data = json.loads(match.group(1))
profile = data["resume"]["profile"]

print(f"  姓名        : {profile['name']}")
print(f"  手机号字段  : {profile['phone']!r}（应为空）")
print(f"  提示文案    : {profile.get('phoneNote')!r}")
print(f"  邮箱        : {profile['email']}")
print(f"  头像        : 内联 {profile['avatar'][:28]}...")
print(f"  项目数      : {len(data['resume']['projects'])}")
print(f"  技能类别    : {len(data['skills']['skills'])}")
print(f"  离线标记    : {'window.__STANDALONE__ = true' in html}")

checks = {
    "手机号字段为空": profile["phone"] == "",
    "页面不含手机号原文": "2577" not in html and "3203" not in html,
    "邮箱保留": "2937479259@qq.com" in html,
    "头像已内联为图片数据": "data:image/jpeg;base64," in html,
    "样式已内联": "--cyan:" in html,
    "无 /static 属性外链": not static_refs,
    "含“面试时提供”": "面试时提供" in html,
}

print("\n--- 检查项 ---")
ok = True
for label, passed in checks.items():
    print(f"  [{'OK' if passed else 'BAD'}] {label}")
    ok = ok and passed

print("\n--- 仓库文件 ---")
for rel in ["docs/index.html", "docs/.nojekyll"]:
    path = REPO / rel
    exists = path.exists()
    size = f"{path.stat().st_size} B" if exists else "缺失"
    print(f"  [{'OK' if exists else 'BAD'}] {rel}  {size}")
    ok = ok and exists

print("\n结果：" + ("通过，可直接启用 GitHub Pages" if ok else "未通过"))
sys.exit(0 if ok else 1)
