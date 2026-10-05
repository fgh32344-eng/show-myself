"""生成单文件离线版页面：dist/portfolio-standalone.html

为什么需要它
-----------
frontend/pages/index.template.html 是**服务端模板**，不能直接双击打开：
  1. 它引用 /static/css/style.css 这类绝对路径，file:// 下会被解析成
     D:\\static\\css\\style.css（盘符根目录），必然 404；
  2. 页面数据由后端接口提供，file:// 下 fetch('/api/...') 无法工作；
  3. 模板里的 $site_name 等占位符只有经服务器渲染才会替换；
  4. 样式缺失时头像会退化成一张巨大的占位图，观感极差。

（该文件已特意改名为 *.template.html，避免被误认为可直接打开的入口。）

本脚本把样式、脚本、简历数据、头像全部内联进一个 HTML 文件，
双击即可查看（但留言板与访问统计需要后端，会显示为停用状态）。

用法：python tests/build_standalone.py
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PAGE = BASE / "frontend" / "pages" / "index.template.html"
CSS = BASE / "frontend" / "static" / "css" / "style.css"
JS = BASE / "frontend" / "static" / "js" / "main.js"
FAVICON = BASE / "frontend" / "static" / "favicon.svg"
ASSETS_DIR = BASE / "frontend" / "static" / "assets"
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


def to_data_uri(path: Path) -> str:
    """把图片转成 data URI。SVG 与位图分别用对应的 MIME 类型。"""
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build(out_path: Path = OUT) -> int:
    """生成单文件离线版到 out_path。返回 0 表示成功。"""
    for required in (PAGE, CSS, JS, RESUME, FAVICON):
        if not required.exists():
            print(f"FAIL 缺少文件：{required}")
            return 1

    html = PAGE.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    resume = json.loads(RESUME.read_text(encoding="utf-8"))

    # 头像以 resume.json 为准（用户可能换成 .jpg/.png），避免写死文件名
    avatar_web = resume["profile"].get("avatar", "")
    avatar_file = ASSETS_DIR / Path(avatar_web).name
    if not avatar_file.exists():
        print(f"FAIL resume.json 指向的头像不存在：{avatar_web}  ->  {avatar_file}")
        print("     请先执行 python tests/setup_avatar.py")
        return 1

    # ---- 0. 剥掉模板里的「误双击兜底」脚本 ----
    # 那段脚本只在「未经服务器渲染 + file:// 打开」时提示用户换文件，
    # 单文件版自己就是正确的文件，留着只是死代码，还会把提示文字带进公开产物。
    html, n_guard = re.subn(
        r"\s*<script>\s*/\* 误双击兜底.*?</script>", "", html, flags=re.S
    )

    # ---- 1. 内联样式，替换掉指向 /static 的 link ----
    # 注意：替换内容一律用 lambda 返回，避免 re.subn 把替换串里的 \d、\1 等
    #       当成正则转义解析（JS 代码里 replace(/[^\d+]/g, '') 就会触发这个坑）
    style_tag = "<style>\n" + css + "\n</style>"
    html, n_link = re.subn(
        r'\s*<link rel="stylesheet" href="/static/css/style\.css">',
        lambda m: "\n" + style_tag,
        html,
    )

    # ---- 2. favicon 内联为 data URI（离线时也要有图标）----
    # 注意：link 标签的属性顺序不保证，用 [^>]* 兜住
    favicon_data = to_data_uri(FAVICON)
    favicon_tag = f'<link rel="icon" href="{favicon_data}" type="image/svg+xml">'
    html, n_icon = re.subn(
        r'<link[^>]*rel="icon"[^>]*>', lambda m: favicon_tag, html
    )

    # ---- 3. 头像也内联，避免依赖外部文件 ----
    avatar_data = to_data_uri(avatar_file)
    resume["profile"]["avatar"] = avatar_data
    # 首页里 <img id="avatarImg" src="/static/assets/avatar.*"> 是 JS 加载前的占位
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
        r'\s*<script src="/static/js/main\.js"></script>',
        lambda m: "\n" + script_tag,
        html,
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    # ---- 校验 ----
    print(f"已生成：{out_path}")
    print(f"  体积        : {out_path.stat().st_size / 1024:.1f} KB")
    print(f"  内联样式    : {'成功' if n_link else '失败（未匹配到 link 标签）'}")
    print(f"  剥离兜底脚本: {n_guard} 处")
    print(f"  内联图标    : {'成功' if n_icon else '失败'}")
    print(f"  内联头像    : {'成功' if n_avatar else '失败'}")
    print(f"  内联脚本    : {'成功' if n_script else '失败'}")
    leftover = re.findall(r'(?:href|src)="(/static/[^"]*)"', html)
    print(f"  残留 /static 绝对路径: {leftover if leftover else '无'}")
    print(f"  残留 $ 占位符: {sorted(set(re.findall(r'\$[a-z_]+', html))) or '无'}")
    print(f"  含内联数据  : {'是' if '__SITE_DATA__' in html else '否'}")
    return 0 if (n_link and n_script and not leftover) else 1


def main() -> int:
    return build(OUT)


if __name__ == "__main__":
    raise SystemExit(main())
