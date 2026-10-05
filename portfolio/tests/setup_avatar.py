"""把 photo.png 处理成网站头像：缩放 + 落到 static/assets + 修正 resume.json。

问题背景：
  原先 resume.json 里写的是 'D:\\dshwork\\portfolio\\photo.png'，
  这是 Windows 本地绝对路径，浏览器（尤其部署到 GitHub 后）根本读不到。
  头像必须是能被 HTTP 访问的**站内相对路径**。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "photo.png"
ASSETS = BASE / "frontend" / "static" / "assets"
RESUME = BASE / "data" / "resume.json"

TARGET_SIZE = 512          # 头像展示尺寸约 96px，512 足够 2x 高清屏
AVATAR_NAME = "avatar.jpg"  # 照片用 JPEG 压缩：PNG 存人像体积大 5-6 倍
WEB_PATH = "/static/assets/" + AVATAR_NAME
JPEG_QUALITY = 86


def main() -> int:
    if not SRC.exists():
        print(f"FAIL 找不到源照片：{SRC}")
        return 1

    ASSETS.mkdir(parents=True, exist_ok=True)
    dest = ASSETS / AVATAR_NAME

    image = Image.open(SRC)
    print(f"源图：{image.format} {image.size[0]}x{image.size[1]} {image.mode}")
    print(f"源体积：{SRC.stat().st_size / 1024:.1f} KB")

    # 统一成正方形 RGB（JPEG 不支持透明通道）
    if image.mode != "RGB":
        image = image.convert("RGB")
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    square = image.crop((left, top, left + side, top + side))
    resized = square.resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)

    # 先清掉可能残留的旧版头像文件（png/svg），避免同名资源混淆
    for stale in ASSETS.glob("avatar.*"):
        if stale.name != AVATAR_NAME:
            stale.unlink()
            print(f"清理旧头像：{stale.name}")

    resized.save(dest, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    print(f"已生成：{dest.relative_to(BASE)}  {TARGET_SIZE}x{TARGET_SIZE}  "
          f"{dest.stat().st_size / 1024:.1f} KB")

    # ---- 修正 resume.json ----
    data = json.loads(RESUME.read_text(encoding="utf-8"))
    old = data["profile"].get("avatar")
    data["profile"]["avatar"] = WEB_PATH
    RESUME.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"resume.json 头像：{old!r}  ->  {WEB_PATH!r}")

    # ---- 源图挪出仓库根目录，避免重复占用与误提交 ----
    archived = BASE / "assets-src" / "photo-original.png"
    if SRC.exists():
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(SRC), str(archived))
        print(f"源图已归档到：{archived.relative_to(BASE)}（该目录会被 git 忽略）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
