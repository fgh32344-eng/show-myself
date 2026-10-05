"""提交 GitHub 前的敏感信息扫描。

用途：确保没有把口令、IP、私有数据、运行时产物带进公开仓库。
用法：python tests/pre_commit_check.py
退出码：0 = 可以提交，1 = 发现问题需先处理。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

# 不该入库的路径/文件名（对应 .gitignore）
IGNORED_PATTERNS = [
    re.compile(r"\.git/"),
    re.compile(r"__pycache__/"),
    re.compile(r"\.pyc$"),
    re.compile(r"\.db(-wal|-shm)?$"),
    re.compile(r"tests/test_report\.json$"),
    re.compile(r"\.vscode/"),
    re.compile(r"_tmp/"),
]

# 需要人工确认的内容
REVIEW_RULES = [
    (re.compile(r"admin123"), "默认后台口令 admin123（若仓库公开，务必改掉或说明仅本地默认）"),
    (re.compile(r"183-?2577-?3203"), "手机号出现在文件中"),
    (re.compile(r"2937479259@qq\.com"), "邮箱出现在文件中"),
    (re.compile(r"127\.0\.0\.1:\d+"), "本地地址（正常，仅供确认）"),
    (re.compile(r"(password|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{8,}['\"]", re.I),
     "疑似硬编码凭证"),
]


def ignored(rel: str) -> bool:
    return any(p.search(rel) for p in IGNORED_PATTERNS)


def main() -> int:
    files = [p for p in BASE.rglob("*") if p.is_file()]
    tracked = []
    skipped = []
    for path in files:
        rel = path.relative_to(BASE).as_posix()
        if path == SELF:
            continue
        if ignored(rel):
            skipped.append(rel)
        else:
            tracked.append((rel, path))

    print(f"项目根目录：{BASE}")
    print(f"将纳入版本控制：{len(tracked)} 个文件")
    print(f"已被 .gitignore 排除：{len(skipped)} 个文件")
    if skipped:
        for rel in sorted(skipped)[:12]:
            print(f"   跳过  {rel}")
        if len(skipped) > 12:
            print(f"   ...另有 {len(skipped) - 12} 个")

    problems: list[str] = []
    notes: list[str] = []

    print("\n--- 内容扫描 ---")
    for rel, path in sorted(tracked):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, message in REVIEW_RULES:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                entry = f"{rel}:{line_no}  {message}  ->  {match.group(0)[:60]}"
                if "仅供确认" in message:
                    notes.append(entry)
                else:
                    problems.append(entry)

    for entry in notes:
        print(f"  [注] {entry}")
    if problems:
        for entry in problems:
            print(f"  [!!] {entry}")
    else:
        print("  未发现硬编码凭证、手机号、邮箱等高危内容")

    # 检查默认口令是否有环境变量兜底
    app = BASE / "backend" / "app.py"
    if app.exists():
        src = app.read_text(encoding="utf-8")
        has_env = 'os.environ.get("PORTFOLIO_ADMIN_PASSWORD"' in src
        print(f"\n后台口令可用环境变量覆盖：{'是' if has_env else '否（建议加上）'}")

    print("\n--- 结论 ---")
    if problems:
        print("发现需要处理的问题，请先修正再提交。")
        return 1
    print("未发现高危内容，可以提交。")
    print("提醒：若仓库设为公开，data/resume.json 里的手机号与邮箱任何人可见——")
    print("      这是你简历上本来就公开的信息，但请自行确认是否接受。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
