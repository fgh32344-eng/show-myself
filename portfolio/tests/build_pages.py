"""生成 GitHub Pages 产物：docs/index.html（仓库根目录下）

为什么放在 docs/
---------------
GitHub Pages 需要一个仓库内的目录作为发布源，常见选择：
  * 仓库根目录（/）           —— 但本项目仓库根是 D:\\dshwork，里面还有别的目录
  * /docs 目录                —— 干净、不影响源码结构 ✅ 本脚本采用这个
  * gh-pages 分支             —— 需要额外分支管理

Pages 只能托管**静态文件**，因此这里复用单文件离线版：
样式、脚本、简历数据、头像全部内联，不需要后端。
留言板 / 访问统计 / 后台在静态托管下天然不可用，页面会自行提示。

用法：python tests/build_pages.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_standalone import build  # noqa: E402

# 仓库根是 D:\dshwork，项目在 portfolio/ 下，因此 Pages 目录在仓库根的 docs/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = REPO_ROOT / "docs"
INDEX = DOCS / "index.html"
STANDALONE = Path(__file__).resolve().parent.parent / "dist" / "portfolio-standalone.html"


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)

    # 直接生成到 docs/index.html
    code = build(INDEX)
    if code != 0:
        return code

    # 同步一份到 portfolio/dist，保持两个产物一致
    STANDALONE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INDEX, STANDALONE)

    # 关键：禁用 Jekyll。
    # 否则 Pages 构建会走 Jekyll 流程，以下划线开头的文件/目录会被忽略；
    # 本项目虽然暂时没有这类文件，但加上可避免后续踩坑，也能加快部署。
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    print(f"\nPages 产物：{INDEX}")
    print(f"  大小      : {INDEX.stat().st_size / 1024:.1f} KB")
    print(f"  .nojekyll : 已生成（禁用 Jekyll 处理）")
    print(f"  已同步到  : {STANDALONE.relative_to(REPO_ROOT)}")
    print("\n下一步：")
    print("  1. 提交并推送：git add -A && git commit -m \"发布 GitHub Pages\" && git push")
    print("  2. 仓库 Settings → Pages → Source 选 “Deploy from a branch”")
    print("     分支选 main，目录选 /docs，保存后等 1-2 分钟")
    print("  3. 访问 https://<你的用户名>.github.io/<仓库名>/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
