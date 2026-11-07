# Source Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建公开源码收藏仓库，配置可验证的定期同步。
**Architecture:** Python 标准库 + Git 获取上游提交快照，安全提取并替换受管理目录，Actions 检查和提交。
**Tech Stack:** Python 3.9+，Git，GitHub Actions。
**Spec:** docs/superpowers/specs/2026-11-07-source-collection.md

## Global Constraints
- 不导入用户未指定的项目，不执行上游代码，不触碰其他仓库。
- 保留 LICENSE；未知许可证由收录时人工核实，不自动宣称开源许可。
- 出错保留旧快照，未变更不提交，notes/ 不覆盖。

## Review Focus
- 配置路径逃逸、大小写重复与不合法 GitHub 地址。
- 归档路径/符号链接逃逸，原仓库含子模块或 LFS。
- 一次同步多个项目时部分失败不导致半次更新。
- 更新删除文件不误删笔记；无变化不会反复提交。
- 工作流最小权限、公共上游限制、推送失败可见。

### Task 1: 同步机制与仓库交付
**Files:** scripts/sync.py、tests/test_sync.py、sources.json、sync-state.json、CATALOG.md、README.md、.github/workflows/sync.yml
- [x] 用临时真实 Git 仓库验证首次导入、更新/删除、幂等、失败保留、路径/符号链接、LFS/子模块拒绝；观察失败。
- [x] 实现配置验证、安全归档、版本索引和同步流程；运行全部测试。
- [x] 增加中文文档和每天/手动 Actions，独立审查并处理重要问题。
- [x] 创建公开 GitHub 仓库，推送并手动运行首次工作流，确认 success 和公开状态。
