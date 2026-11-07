#!/usr/bin/env python3
"""同步公开 GitHub 源码快照；不执行上游代码或安装上游依赖。"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

MAX_FILE = 90 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*\Z')


def validate_sources(sources):
    if not isinstance(sources, list):
        raise ValueError('sources.json 必须是数组')
    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('每个收录条目必须是对象')
        repo = source.get('repo', '')
        if not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.lower().endswith('.git'):
            raise ValueError('repo 必须为 owner/repository，不能包含路径或 URL')
        if repo.lower() in seen:
            raise ValueError('重复收录：' + repo)
        seen.add(repo.lower())
        for key in ['branch', 'description']:
            if key in source and not isinstance(source[key], str):
                raise ValueError(key + ' 必须是字符串')
        branch = source.get('branch', '')
        if branch and (branch.startswith('-') or any(c.isspace() for c in branch)):
            raise ValueError('无效的分支名')
    return sources


def git(*args, cwd=None, stdout=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=' + os.devnull, *args],
                            cwd=cwd, env=env, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=300, check=False)
    if result.returncode:
        raise RuntimeError('Git 操作失败：' + result.stderr.decode('utf-8', 'replace').strip())
    return result.stdout.decode('utf-8', 'replace').strip() if stdout is None else ''


def extract_archive(archive, dest):
    members = archive.getmembers()
    links = {m.name.rstrip('/') for m in members if m.issym()}
    total = 0
    for member in members:
        name = member.name.rstrip('/')
        parts = PurePosixPath(name).parts
        if not parts or name.startswith('/') or '\\' in name or any(p in ('.', '..') or p.lower() == '.git' for p in parts):
            raise ValueError('归档包含不安全路径：' + name)
        if any('/'.join(parts[:i]) in links for i in range(1, len(parts))):
            raise ValueError('归档路径穿过符号链接：' + name)
        if not (member.isdir() or member.isfile() or member.issym()):
            raise ValueError('不支持的归档条目：' + name)
        total += member.size
        if member.size > MAX_FILE or total > MAX_TOTAL:
            raise ValueError('源码超过大小限制，需要单独处理：' + name)
        if member.issym():
            target = member.linkname
            normalized = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if not target or target.startswith('/') or '\\' in target or normalized == '..' or normalized.startswith('../'):
                raise ValueError('符号链接指向项目以外：' + name)
    dest.mkdir(parents=True, exist_ok=True)
    for member in members:
        path = dest / member.name
        if member.isdir():
            path.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, path.open('wb') as output:
                head = source.read(200)
                if head.startswith(b'version https://git-lfs.github.com/spec/v1'):
                    raise ValueError('发现 Git LFS 指针，需要单独收录实体文件：' + member.name)
                output.write(head)
                shutil.copyfileobj(source, output)
            path.chmod(0o755 if member.mode & 0o111 else 0o644)
    for member in members:
        if member.issym():
            path = dest / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(member.linkname)
    for member in members:
        if member.issym():
            try:
                (dest / member.name).resolve().relative_to(dest.resolve())
            except (ValueError, RuntimeError) as error:
                raise ValueError('符号链接链越界或循环：' + member.name) from error


def export_snapshot(url, branch, dest):
    with tempfile.TemporaryDirectory(prefix='code-atlas-git-') as temp:
        clone = Path(temp) / 'source'
        args = ['clone', '--depth', '1', '--single-branch', '--no-checkout']
        if branch:
            args.extend(['--branch', branch])
        git(*args, '--', str(url), str(clone))
        sha = git('rev-parse', 'HEAD', cwd=clone)
        if any(line.startswith('160000 ') for line in git('ls-tree', '-r', 'HEAD', cwd=clone).splitlines()):
            raise ValueError('发现 Git 子模块，需逐项目配置后再收录')
        archive_path = Path(temp) / 'source.tar'
        with archive_path.open('wb') as output:
            git('archive', '--format=tar', 'HEAD', cwd=clone, stdout=output)
        with tarfile.open(archive_path) as archive:
            extract_archive(archive, dest)
        return {'commit': sha, 'branch': branch or git('symbolic-ref', '--short', 'HEAD', cwd=clone)}


def github_prepare(source, dest):
    # 读取元数据确认公开属性；不使用个人令牌读取或导出私密仓库。
    url = 'https://api.github.com/repos/' + source['repo']
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'code-atlas'})
    with urllib.request.urlopen(request, timeout=30) as response:
        meta = json.load(response)
    if meta.get('private') is not False:
        raise ValueError('只允许收录公开仓库：' + source['repo'])
    branch = source.get('branch') or meta['default_branch']
    return export_snapshot('https://github.com/' + source['repo'] + '.git', branch, dest)


def ensure_local_path(root, relative):
    path = root
    for part in PurePosixPath(relative).parts:
        if part in ('.', '..') or '/' in part or '\\' in part:
            raise ValueError('无效的本地路径')
        path = path / part
        if path.is_symlink():
            raise ValueError('受管理路径不允许是符号链接：' + relative)
    return path


def catalogue(sources, state):
    def cell(value):
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')
    lines = ['# 源码收藏目录', '', '由同步脚本生成；推荐理由请修改 `sources.json`。', '',
             '| 项目 | 推荐理由 | 同步分支 | 已收录版本 | 最近更新（UTC） |', '| --- | --- | --- | --- | --- |']
    for source in sources:
        repo = source['repo']; info = state.get(repo, {})
        sha = info.get('commit', '')
        version = '[' + sha[:12] + '](https://github.com/' + repo + '/commit/' + sha + ')' if sha else '尚未同步'
        lines.append('| [' + repo + '](repos/' + repo + '/) | ' + cell(source.get('description', '')) + ' | ' + cell(info.get('branch', source.get('branch') or '默认分支')) + ' | ' + version + ' | ' + cell(info.get('updated_at', '—')) + ' |')
    if not sources:
        lines.extend(['', '尚未收录项目。把喜欢的 GitHub 仓库链接发给我即可。'])
    lines.extend(['', '原作者保留著作权，各项目许可证以对应目录的 LICENSE / NOTICE 等文件为准。', ''])
    return '\n'.join(lines)


def install(root, changes, temp):
    """同一文件系统内替换；失败时逆序恢复已替换的目标。"""
    applied = []
    try:
        for index, (relative, staged) in enumerate(changes):
            target = ensure_local_path(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = temp / ('backup-' + str(index))
            existed = target.exists()
            if existed:
                target.rename(backup)
            applied.append((target, backup, existed))
            staged.rename(target)
    except Exception:
        for target, backup, existed in reversed(applied):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            if existed:
                backup.rename(target)
        raise


def synchronize(root, sources, prepare=github_prepare):
    root = Path(root).resolve()
    validate_sources(sources)
    state_path = ensure_local_path(root, 'sync-state.json')
    ensure_local_path(root, 'CATALOG.md')
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not isinstance(state, dict):
        raise ValueError('sync-state.json 必须是对象')
    changes = []
    updated = 0
    with tempfile.TemporaryDirectory(prefix='.sync-', dir=root) as temp_dir:
        temp = Path(temp_dir)
        for index, source in enumerate(sources):
            repo = source['repo']; relative = 'repos/' + repo
            target = ensure_local_path(root, relative)
            if target.exists() and repo not in state:
                raise ValueError('目标目录已存在但不受同步管理，请先核实：' + relative)
            staged = temp / ('snapshot-' + str(index))
            info = prepare(source, staged)
            if not re.fullmatch(r'[0-9a-f]{40,64}', info['commit']):
                raise ValueError('上游返回无效提交号')
            if state.get(repo, {}).get('commit') == info['commit'] and state[repo].get('branch') == info['branch'] and target.is_dir():
                continue
            state[repo] = {**info, 'url': 'https://github.com/' + repo,
                           'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
            changes.append((relative, staged)); updated += 1
        outputs = {'sync-state.json': json.dumps(state, ensure_ascii=False, indent=2) + '\n', 'CATALOG.md': catalogue(sources, state)}
        for name, text in outputs.items():
            target = ensure_local_path(root, name)
            if not target.exists() or target.read_text() != text:
                staged = temp / name; staged.write_text(text, encoding='utf-8')
                changes.append((name, staged))
        install(root, changes, temp)
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sources = json.loads((args.root / 'sources.json').read_text(encoding='utf-8'))
    count = synchronize(args.root, sources)
    print('已检查 %d 个项目，更新 %d 个源码快照。' % (len(sources), count))


if __name__ == '__main__':
    main()
