"""生成单文件离线版页面：dist/portfolio-standalone.html

为什么需要它
-----------
frontend/pages/index.html 是**服务端模板**，不能直接双击打开：
  1. 它引用 /static/css/style.css 这类绝对路径，file:// 下会被解析成
     D:\\static\\css\\style.css（盘符根目录），必然 404；
  2. 页面数据由后端接口提供，file:// 下 fetch('/api/...') 无法工作；
  3. 模板里的 $site_name 等占位符只有经服务器渲染才会替换。

本脚本把样式、脚本、简历数据全部内联进一个 HTML 文件，
双击即可查看（但留言板与访问统计需要后端，会显示为停用状态）。

用法：python tests/build_standalone.py
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PAGE = BASE / "frontend" / "pages" / "index.html"
CSS = BASE / "frontend" / "static" / "css" / "style.css"
JS = BASE / "frontend" / "static" / "js" / "main.js"
AVATAR = BASE / "frontend" / "static" / "assets" / "avatar.svg"
RESUME = BASE / "data" / "resume.json"
OUT_DIR = BASE / "dist"
OUT = OUT_DIR / "portfolio-standalone.html"

OFFLINE_NOTE = """<!--
  ============================================================
  离线单文件版（由 tests/build_standalone.py 生成，请勿手工修改）

  本文件把样式、脚本、简历数据全部内联，双击即可查看。
  以下功能需要后端支持，在离线模式下会显示为停用：
    * 留言板（写入 SQLite）
    * 访问量统计
  需要完整体验请回到项目根目录双击 start.bat，
  然后访问 http://127.0.0.1:8000/
  ============================================================
-->"""


def svg_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


def main() -> int:
    for required in (PAGE, CSS, JS, RESUME):
        if not required.exists():
            print(f"FAIL 缺少文件：{required}")
            return 1

    html = PAGE.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    resume = json.loads(RESUME.read_text(encoding="utf-8"))

    # ---- 1. 内联样式，替换掉指向 /static 的 link ----
    style_tag = "<style>\n" + css + "\n</style>"
    html, n_link = re.subn(
        r'\s*<link rel="stylesheet" href="/static/css/style\.css">', "\n" + style_tag, html
    )

    # ---- 2. favicon 内联为 data URI（离线时也要有图标）----
    # 注意：link 标签的属性顺序不保证，用 [^>]* 兜住
    favicon_data = svg_to_data_uri(BASE / "frontend" / "static" / "favicon.svg")
    favicon_tag = f'<link rel="icon" href="{favicon_data}" type="image/svg+xml">'
    html, n_icon = re.subn(
        r'<link[^>]*rel="icon"[^>]*>', favicon_tag, html
    )

    # ---- 3. 头像也内联，避免依赖外部文件 ----
    avatar_data = svg_to_data_uri(AVATAR)
    resume["profile"]["avatar"] = avatar_data
    # 首页里 <img id="avatarImg" src="/static/assets/avatar.svg"> 是 JS 加载前的占位
    html, n_avatar = re.subn(
        r'(<img id="avatarImg"[^>]*?)src="[^"]*"',
        lambda m: m.group(1) + f'src="{avatar_data}"',
        html,
    )

    # ---- 4. 替换模板占位符（服务器才会做的事，这里自己代劳）----
    replacements = {
        "$site_name": "王耀威 · 个人主页",
        "$version": "1.0.0-standalone",
        "$client_ip": "离线",
        "$year": "2025",
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    # ---- 5. 注入数据与运行模式标记，并内联脚本 ----
    bootstrap = json.dumps(
        {"resume": resume, "skills": {"skills": resume["skills"], "learning": resume["learning"]}},
        ensure_ascii=False,
    )
    script_tag = (
        "<script>\n"
        f"window.__SITE_DATA__ = {bootstrap};\n"
        "window.__STANDALONE__ = true;\n"
        "window.__ASSET_BASE__ = '';\n"  # 资源已内联，无需前缀
        "</script>\n<script>\n" + js + "\n</script>"
    )
    html, n_script = re.subn(
        r'\s*<script src="/static/js/main\.js"></script>', "\n" + script_tag, html
    )

    # ---- 6. 注入说明注释 ----
    html = html.replace("<!DOCTYPE html>", "<!DOCTYPE html>\n" + OFFLINE_NOTE, 1)

    # ---- 7. 收尾：把导航里无法工作的入口改成提示 ----
    html = html.replace('href="/admin"', 'href="#" data-offline="1" title="离线版无后台"')
    html = html.replace(
        '<a class="btn btn--ghost" href="/api/resume" target="_blank" rel="noopener">简历 JSON 接口</a>',
        '<a class="btn btn--ghost" href="#" data-offline="1" title="离线版无接口，见 data/resume.json">简历 JSON 接口</a>',
    )
    html = html.replace(
        '<a class="btn btn--ghost" href="/api/docs" target="_blank" rel="noopener">API 文档</a>',
        '<a class="btn btn--ghost" href="#" data-offline="1" title="离线版无接口文档">API 文档</a>',
    )
    # 点击这些占位链接时给出友好提示，而不是跳到 file:///#
    html = html.replace(
        "</body>",
        """<script>
document.addEventListener('click', function (event) {
  var el = event.target.closest('[data-offline]');
  if (!el) return;
  event.preventDefault();
  var toast = document.getElementById('toast');
  if (toast) {
    toast.textContent = '该功能需要后端服务，请双击 start.bat 启动后访问 http://127.0.0.1:8000/';
    toast.classList.add('is-on');
    setTimeout(function () { toast.classList.remove('is-on'); }, 3600);
  }
});
</script>
</body>""",
        1,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    # ---- 校验 ----
    print(f"已生成：{OUT}")
    print(f"  体积        : {OUT.stat().st_size / 1024:.1f} KB")
    print(f"  内联样式    : {'成功' if n_link else '失败（未匹配到 link 标签）'}")
    print(f"  内联图标    : {'成功' if n_icon else '失败'}")
    print(f"  内联头像    : {'成功' if n_avatar else '失败'}")
    print(f"  内联脚本    : {'成功' if n_script else '失败'}")
    leftover = re.findall(r'(?:href|src)="(/static/[^"]*)"', html)
    print(f"  残留 /static 绝对路径: {leftover if leftover else '无'}")
    print(f"  残留 $ 占位符: {sorted(set(re.findall(r'\$[a-z_]+', html))) or '无'}")
    print(f"  含内联数据  : {'是' if '__SITE_DATA__' in html else '否'}")
    return 0 if (n_link and n_script and not leftover) else 1


if __name__ == "__main__":
    raise SystemExit(main())
