"""把本地仓库推送到 GitHub（用 PAT 完成建仓 + 推送）。

用法：
    set GITHUB_TOKEN=ghp_xxx && python tools/push_github.py
    python tools/push_github.py --token ghp_xxx --repo strelitzia-hid-battery --private

做的事：
    1. GET  /user                    确认 token 身份
    2. POST /user/repos              建仓（已存在则跳过）
    3. git remote set-url origin     临时用 token 鉴权
    4. git push -u origin HEAD       推送当前分支
    5. 推送后把 remote 改回无 token 的地址，避免 token 留在 .git/config
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def api(method: str, path: str, token: str, body: dict | None = None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="ignore")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"message": raw[:300]}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=check, text=True,
                          capture_output=True, encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--owner", default="StrelitziaZYN")
    ap.add_argument("--repo", default="HID-Battery")
    ap.add_argument("--private", default="1")
    args = ap.parse_args()

    token = args.token.strip()
    if not token:
        print("ERROR: 没有 token。用 --token 或环境变量 GITHUB_TOKEN 传入。")
        return 2

    code, me = api("GET", "/user", token)
    if code != 200:
        print(f"ERROR: token 无效（{code}）{me.get('message')}")
        return 3
    owner = args.owner or me["login"]
    print(f"[auth] {me['login']}  (scopes: 见 token 设置页)")

    code, repo = api("GET", f"/repos/{args.owner}/{args.repo}", token)
    if code == 200:
        print(f"[repo] 复用已有仓库 {repo['full_name']}（private={repo['private']}）")
    elif code == 404:
        code, repo = api("POST", "/user/repos", token, {
            "name": args.repo,
            "description": "Windows 2.4G HID 设备电量监测：托盘电量、悬浮面板、"
                           "电量历史与预测、接口协议插件、AI 接入包。",
            "private": args.private not in {"0", "false", "no"},
            "has_issues": True, "has_wiki": False, "auto_init": False,
        })
        if code != 201:
            print(f"ERROR: 建仓失败 {code} {repo.get('message')}")
            return 5
        print(f"[repo] created {repo['full_name']}")
    else:
        print(f"ERROR: 读仓库失败 {code} {repo.get('message')}")
        return 4

    owner = repo["owner"]["login"]
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    auth_url = f"https://x-access-token:{token}@github.com/{owner}/{args.repo}.git"
    plain_url = f"https://github.com/{owner}/{args.repo}.git"

    remotes = git("remote").stdout.split()
    if "origin" in remotes:
        git("remote", "set-url", "origin", auth_url)
    else:
        git("remote", "add", "origin", auth_url)

    # 远端可能已有初始提交（比如建仓时勾了 LICENSE），和本地没有共同祖先。
    # 先 fetch，再用 --allow-unrelated-histories 合并，冲突就在这里停下并报错。
    fetch = git("fetch", "origin", branch, check=False)
    if fetch.returncode == 0:
        has_remote = git("rev-parse", "--verify", f"origin/{branch}", check=False).returncode == 0
        common = git("merge-base", "HEAD", f"origin/{branch}", check=False).returncode == 0
        if has_remote and not common:
            print(f"[merge] 远端已有 {branch} 且与本地无共同祖先，执行无关历史合并")
            mg = git("merge", "--allow-unrelated-histories", "--no-rebase",
                     f"origin/{branch}",
                     "-m", "chore: 合并远端初始提交（LICENSE）", check=False)
            out = (mg.stdout + mg.stderr).strip()
            if mg.returncode != 0:
                print(f"ERROR: 合并冲突，需手工处理：\n{out[-600:]}")
                git("remote", "set-url", "origin", plain_url)
                return 7
            print(f"[merge] ok {out.splitlines()[0] if out else ''}")
        elif has_remote:
            behind = git("rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip()
            if behind and behind != "0":
                print(f"[merge] 远端领先 {behind} 个提交，先快进")
                git("merge", "--ff-only", f"origin/{branch}", check=False)
    else:
        print("[fetch] 远端暂无该分支或为空，直接推")

    print(f"[push] {branch} -> origin")
    res = git("push", "-u", "origin", branch, check=False)
    out = (res.stdout + res.stderr)
    print(re.sub(r"x-access-token:[^@]+@", "x-access-token:***@", out).strip()[-800:])

    git("remote", "set-url", "origin", plain_url)      # 清掉 config 里的 token
    if res.returncode != 0:
        return 6

    head = git("rev-parse", "--short", "HEAD").stdout.strip()
    files = len(git("ls-files").stdout.splitlines())
    print(f"[done] {plain_url}  {branch}@{head}  {files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
