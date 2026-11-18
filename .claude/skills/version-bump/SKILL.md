---
name: version-bump
description: 当完成一组功能开发后，同步更新版本号与文档。
---
# 版本更新与文档同步

## 触发条件

用户说 "bump version"、"更新版本"、"同步文档"、"编入 changelog" 或类似表述。

## 流程

### 1. 确定版本号

遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)：

版本格式：主版本号.次版本号.修订号，版本号递增规则如下：

主版本号：当你做了不兼容的 API 修改，

次版本号：当你做了向下兼容的功能性新增，

修订号：当你做了向下兼容的问题修正。

先行版本号及版本编译信息可以加到“主版本号.次版本号.修订号”的后面，作为延伸。

同步版本号到：
- `backend/pyproject.toml` → `version` 字段
- `frontend/package.json` → `version` 字段
- `README.md` → 版本徽章

### 2. 更新 CHANGELOG.md

遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式：

```markdown
## X.Y.Z

### 添加
- 新增功能描述

### 变更
- 修改描述

### 修复
- 修复描述
```

### 3. 更新 README.md

- 版本徽章：`[![Version](https://img.shields.io/badge/版本-X.Y.Z-green)]()`
- 如有新增/删除模块，更新 "项目结构" 章节
- 如有新增技术栈，更新 "技术栈" 章节

### 4. 更新 CLAUDE.md

- "Current state" 版本号
- 新增的 API 端点（如有）
- 新增的模块或设计模式（如有）


### 5. Git 提交

分两次提交：
1. **backend + docs**：`feat: vX.Y.Z — 简短描述`（含 `uv.lock`）
2. **frontend**：`chore: frontend version → X.Y.Z`

**重要**：提交信息中**禁止**添加 `Co-Authored-By:` 行。仅使用标准 Conventional Commits 格式。


## 示例

```
用户: "bump version to 0.3.0"

→ 1. 编辑 backend/pyproject.toml: version = "0.3.0"
→ 2. 编辑 frontend/package.json: "version": "0.3.0"
→ 3. 编辑 README.md: 版本徽章 → 0.3.0
→ 4. 编辑 CHANGELOG.md: 新增 0.3.0 条目
→ 5. 编辑 CLAUDE.md: 更新版本号
<!-- → 6. git add backend/ docs/ + commit (feat)
→ 7. git add frontend/ + commit (chore) -->
```
