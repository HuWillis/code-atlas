# Code Atlas · 代码地图

[![同步收藏的源码](https://github.com/HuWillis/code-atlas/actions/workflows/sync.yml/badge.svg)](https://github.com/HuWillis/code-atlas/actions/workflows/sync.yml)

HuWillis 的 GitHub 源码收藏仓库：把值得学习、使用和研究的项目集中存放，保留实际源码副本，持续跟进上游更新。不需要为每个项目创建 Fork。

**[浏览收藏目录 →](CATALOG.md)** · **[查看同步结果 →](https://github.com/HuWillis/code-atlas/actions/workflows/sync.yml)**

已收录项目见上方收藏目录。以后把 GitHub 仓库链接发给管理这个仓库的助手，并说明推荐理由，即可继续收录。

## 如何收录

1. 提供公开 GitHub 仓库链接，例如 `https://github.com/作者/仓库名`，可附上“这个项目做什么、为什么值得收藏”。
2. 确认上游许可证允许此种保存和分发，保留 LICENSE、NOTICE 等许可证及版权文件。没有明确许可证的项目先核实，不默认视为允许公开复制。
3. 在 `sources.json` 添加条目，提交后自动触发同步；也可本地运行脚本，检查实际变更后提交。
4. 实际代码保存在 `repos/原作者/仓库名/`；收藏目录列出说明、原提交链接、同步分支及更新时间。

配置示意（请替换为要收藏的真实项目，不要原样添加）：

```json
[
  {
    "repo": "OWNER/REPOSITORY",
    "description": "项目用途，以及值得收藏的理由",
    "branch": ""
  }
]
```

`branch` 留空时每次读取上游默认分支；也可以指定分支。这里只支持公开仓库，不使用个人访问令牌拉取私密项目。

## 自动更新

- GitHub Actions 计划在**北京时间每天 09:23**检查所有收录项目。
- 更改清单、脚本、测试或同步工作流时也会触发；可在 **Actions → 同步收藏的源码 → Run workflow** 手动运行。
- 上游提交变化时更新源码副本，包含修改、新增和删除；原版本仍可以从本收藏仓库的 Git 历史找回。
- 同一版本重复检查不会刷新时间或制造空提交。`sync-state.json` 记录上次成功收录的提交、分支和 UTC 更新时间。
- 同步先准备所有新快照，再替换目录；上游不可访问、校验失败等准备错误会让工作流失败，已有副本保持不变。可在 Actions 查看原因，处理后重新运行。
- 推送遇到并发提交时会报错，不强制覆盖远端；重新运行即可重新读取最新清单。
- 定时任务不是实时订阅，可能延迟。GitHub 对公开仓库可能在连续 60 天没有仓库活动时停用定时任务；到 Actions 页面重新启用即可。请留意顶部状态徽章和 Actions 失败通知。

[GitHub 官方定时任务说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 存放什么、不存放什么

```text
code-atlas/
├── README.md                 # 使用说明
├── CATALOG.md                # 自动生成的收藏目录
├── sources.json              # 收录清单与推荐理由
├── sync-state.json           # 已同步的上游版本
├── repos/原作者/仓库名/       # 实际源码文件
├── notes/                    # 自己的学习笔记，自动同步不覆盖
├── scripts/sync.py           # 同步脚本
├── tests/                    # 临时 Git 仓库回归测试
└── .github/workflows/        # 自动同步任务
```

这不是完整 Git 镜像：保存的是指定分支当前提交的源码快照，不保存上游 `.git`、完整提交历史、其他分支或 Release 下载附件。采用 `git archive`，遵循上游的 `export-ignore` 设置；导出的文件强制纳入收藏仓库，避免 `.gitignore` 漏掉上游已经跟踪的文件。

遇到 Git 子模块或 Git LFS 指针时，脚本会明确报错，不用缺失的代码或指针文件冒充完整源码；这类项目需要单独确定收录范围。单文件超过 90 MiB 或解包总量超过 1 GiB 的项目也需要单独处理。

同步只复制文件，不安装依赖、不运行上游脚本，也不会执行被收藏项目的 GitHub Actions。上游工作流位于 `repos/.../.github/`，并非本仓库根目录的工作流。

**请不要直接在 `repos/` 里开发**：下一次上游更新会替换对应目录。自己的笔记放在 `notes/`；需要修改代码时，在独立开发目录或仓库中进行。

从 `sources.json` 删除条目只停止跟踪，不自动删除已有副本。删除代码副本应另行明确操作。

## 本地使用

需要 Python 3.9+、Git 和能访问 GitHub 的网络，无额外 Python 依赖。

```bash
git clone https://github.com/HuWillis/code-atlas.git
cd code-atlas
python3 -m unittest discover -s tests -v
python3 scripts/sync.py
git diff --stat
```

网络请求不携带个人凭证；公开 API 存在访问频率限制，项目较多时应调整同步方案。原仓库删除、转为私密或网络失败时，已收录代码仍保留在这里，但无法继续取得新版本。

## 版权与许可

各收藏项目的版权和许可证归原作者所有，以项目目录中的 LICENSE / NOTICE 等文件为准。本仓库没有给所有收藏项目统一重新授权。收录不代表项目经过安全审计或适合直接用于生产。
