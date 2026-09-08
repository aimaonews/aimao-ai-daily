#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI猫 (aimao.today) GitHub 自动化外链同步脚本
- 数据源: WordPress REST API (https://www.aimao.today/wp-json/wp/v2/posts)
- 依赖: 纯 Python 3 标准库 (零额外依赖，无需 pip install)
- 运行环境: /opt/data/yangmaozhang/scripts/
"""

import os
import sys
import json
import html
import re
import urllib.request
import subprocess
from datetime import datetime

# ================= 配置项 =================
# WordPress REST API 地址（支持通过环境变量覆盖）
WP_API_URL = os.environ.get("WP_API_URL", "https://www.aimao.today/wp-json/wp/v2/posts?per_page=10")

# 仓库本地路径（若在 GitHub Actions 中默认当前目录，若在宿主机默认目标路径）
DEFAULT_REPO = "." if os.environ.get("GITHUB_ACTIONS") == "true" else "/opt/data/yangmaozhang/aimao-ai-daily"
REPO_DIR = os.environ.get("REPO_DIR", DEFAULT_REPO)
README_PATH = os.path.join(REPO_DIR, "README.md")

# 摘要最大字数
SUMMARY_MAX_LENGTH = 140

# 占位符标记
START_MARKER = "<!-- POST-LIST:START -->"
END_MARKER = "<!-- POST-LIST:END -->"

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AIMaoBot/1.0; +https://aimao.today)"
}
# ==========================================


def clean_html(raw_html: str) -> str:
    """清理 HTML 标签并解码 HTML 实体"""
    if not raw_html:
        return ""
    # 去除 script/style 等标签
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # 去除所有 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 解码 HTML 实体 (&nbsp;, &#8211;, &quot; 等)
    text = html.unescape(text)
    # 合并多余空白符
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_latest_posts(api_url: str) -> list:
    """从 WordPress REST API 拉取最新文章"""
    print(f"[*] 正在拉取 WordPress 最新文章: {api_url}")
    req = urllib.request.Request(api_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status != 200:
                print(f"[!] API 请求失败，状态码: {resp.status}")
                return []
            content = resp.read().decode("utf-8")
            posts = json.loads(content)
            print(f"[+] 成功获取到 {len(posts)} 篇文章")
            return posts
    except Exception as e:
        print(f"[!] 请求 API 发生异常: {e}")
        return []


def format_markdown(posts: list) -> str:
    """将文章格式化为符合 SEO 规范的精简 Markdown 列表"""
    lines = []
    lines.append(f"<!-- 最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC+8) -->\n")

    for post in posts:
        title = html.unescape(post.get("title", {}).get("rendered", "未命名文章")).strip()
        link = post.get("link", "").strip()
        raw_date = post.get("date", "")
        post_date = raw_date[:10] if raw_date else "最新"

        # 提取并生成 100~150 字纯文本精炼摘要
        content_raw = post.get("content", {}).get("rendered", "")
        cleaned_text = clean_html(content_raw)
        
        # 截断摘要
        if len(cleaned_text) > SUMMARY_MAX_LENGTH:
            summary = cleaned_text[:SUMMARY_MAX_LENGTH].rstrip() + "..."
        else:
            summary = cleaned_text

        # 严格遵守外链与锚文本规范
        lines.append(f"### 📌 {title}")
        lines.append(f"- **发布日期**：`{post_date}`")
        lines.append(f"- **内容摘要**：{summary}")
        lines.append(f"- **官方链接**：👉 阅读完整内容/领取福利：[AI猫]({link})\n")

    return "\n".join(lines).strip()


def update_readme(readme_file: str, new_content: str) -> bool:
    """更新 README.md 中的动态占位区"""
    if not os.path.isfile(readme_file):
        print(f"[!] 未找到目标 README 文件: {readme_file}")
        return False

    with open(readme_file, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        rf"({re.escape(START_MARKER)})([\s\S]*?)({re.escape(END_MARKER)})",
        re.MULTILINE
    )

    if not pattern.search(content):
        print(f"[!] README.md 中缺少定位标记: {START_MARKER} ... {END_MARKER}")
        return False

    replacement = f"{START_MARKER}\n\n{new_content}\n\n{END_MARKER}"
    updated_content = pattern.sub(replacement, content)

    if updated_content == content:
        print("[*] README 内容无变动，无需覆写。")
        return False

    with open(readme_file, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"[+] 成功更新 {readme_file}")
    return True


def git_commit_and_push(repo_dir: str):
    """检测 Git 变动并执行提交与推送"""
    print(f"[*] 检查 Git 仓库变动: {repo_dir}")
    os.chdir(repo_dir)

    # 如果运行在 GitHub Actions 虚拟环境中，自动设置 git 作者信息
    if os.environ.get("GITHUB_ACTIONS") == "true":
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)

    # 检查 README.md 是否有改动 (不管是 modified 还是 untracked)
    status_res = subprocess.run(
        ["git", "status", "--porcelain", "README.md"],
        capture_output=True,
        text=True
    )

    if not status_res.stdout.strip():
        print("[*] Git 检测无文件改动，跳过 Commit/Push。")
        return

    print("[+] 检测到 README.md 变动，准备自动提交...")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 获取当前所在分支（兼容 main / master）
    branch_res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    branch = branch_res.stdout.strip() or "main"

    # 执行提交与推送 (使用 HEAD:branch 兼容 detached HEAD 环境)
    commands = [
        ["git", "add", "README.md"],
        ["git", "commit", "-m", f"chore(sync): auto-sync latest posts ({now_str}) [skip ci]"],
        ["git", "push", "origin", f"HEAD:{branch}"]
    ]

    for cmd in commands:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[!] 执行命令失败: {' '.join(cmd)}\n错误: {res.stderr.strip()}")
            return
        else:
            if res.stdout.strip():
                print(f"    {res.stdout.strip()}")

    print(f"[🎉] 自动化同步并推送到 GitHub ({branch} 分支) 成功！")


def main():
    print("=== AI猫 (aimao.today) GitHub 自动化外链同步开始 ===")
    posts = fetch_latest_posts(WP_API_URL)
    if not posts:
        print("[!] 获取文章列表为空或失败，流程终止。")
        sys.exit(1)

    markdown_list = format_markdown(posts)
    has_changed = update_readme(README_PATH, markdown_list)

    if has_changed:
        git_commit_and_push(REPO_DIR)
    else:
        print("[*] 内容未发生实质变更，同步完成。")

    print("=== 同步任务结束 ===")


if __name__ == "__main__":
    main()
