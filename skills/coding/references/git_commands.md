# GitHub Git 操作参考

本文档包含 GitHub 工作流的 git 操作规范，基础 git 命令请直接使用。

## 推送与创建 Pull Request

GitHub 使用标准 git push + Pull Request 工作流：

> **注意**：`<branch-name>` 是功能分支（即 `local_branch`），不是 PR 的目标分支（`remote_branch`）。推送到功能分支后，通过 `gh pr create --base <目标分支>` 创建 PR。

```bash
# 推送分支到远程（推送到功能分支，非目标分支）
git push origin HEAD:<branch-name>

# 示例：推送当前分支
git push origin HEAD:feature/add-cluster-api

# 首次推送并设置上游追踪
git push -u origin <branch-name>
```

推送后使用 `gh` CLI 创建 Pull Request：

```bash
gh pr create --base <目标分支> --title "#<Issue编号> Short English description." --body "## Summary
- Change 1
- Change 2

Closes #<Issue编号>"
```

## 多提交 PR 工作流

GitHub 惯例使用多提交 PR 工作流，每个有意义的改动是一个独立 commit。

**重要：每个 git 命令必须作为独立的 Bash 调用执行，不要用 `&&` 链接。** 链接后的命令无法匹配权限白名单，会导致执行暂停。

**禁止提交 devpipe 状态文件**：`.devpipe/` 目录已加入 `.gitignore`，`git add` 时只添加源代码和测试文件，**不要使用 `git add .`、`git add -A` 或 `git reset`**。

**Commit message 格式要求**：必须是**单行纯文本**，格式为 `#<Issue编号> Short English description.`。禁止使用 HEREDOC、多行消息、Co-Authored-By、日期、作者等额外信息。

```bash
# 首次提交（每行独立执行）
git add <源代码和测试文件列表>
git commit -m "#<Issue编号> Short English description."
git push origin HEAD:<branch-name>

# 后续修改（每行独立执行）
git add <源代码和测试文件列表>
git commit -m "#<Issue编号> Short English description."
git push origin HEAD:<branch-name>
```

## 常见问题

**Q: 推送被拒绝？**
如果远程分支有新的提交，先执行 `git pull --rebase origin <branch>` 再推送。

**Q: 如何更新已有 PR？**
直接推送到同一分支即可，PR 会自动更新：`git push origin HEAD:<branch-name>`。

**Q: 如何关联 Issue？**
在 PR 描述或 commit message 中使用 `Closes #<编号>` 或 `Fixes #<编号>`，合入后自动关闭 Issue。
