# 代码规范化检查

对项目进行全面代码质量审查与优化，遵循"无需前向兼容、可维护性与最小可行逻辑"原则。

## 触发条件

用户说 "全面检查优化"、"规范化"、"清理代码"、"standardize" 或类似表述。

## 检查维度

### 1. 版本依赖值 — 以项目配置文件为单一来源

- **禁止**在常量文件中硬编码版本号（如 `IRISFLOW_USER_AGENT = "IrisFlow/0.24.0"`）
- 版本号应从 `pyproject.toml`（后端）或 `package.json`（前端）动态读取
- 每次版本更新后，检查 `README.md` 中的 curl 示例、徽章等是否同步更新

### 2. 硬编码字符串 → 常量

| 类别 | 后端常量文件 | 前端常量文件 |
|------|-------------|-------------|
| 会话状态 | `constants.py` | `constants.ts` |
| 消息角色 | `ROLE_USER/ASSISTANT/SYSTEM/TOOL` | 同名 |
| SSE 事件类型 | `SSE_*` | 同名 |
| HTTP 状态码 | — | `HTTP_BAD_GATEWAY` 等 |
| UI 文案 | — | `UI_*` 前缀常量 |

- 模板中的展示文本应优先使用 `UI_*` 常量（未来 i18n 候选）
- 前端 `SSE_DATA_PREFIX_LEN` 必须用于 `line.slice()` 而非裸数字 `6`

### 3. CSS 变量化

**新增变量时应添加到 `frontend/src/style.css` 的 `:root` 块：**

```css
--white: #ffffff;                    /* 替代所有 #fff */
--status-generating: #f0c040;        /* 会话状态灯颜色 */
--status-pending: #e45a3c;
--status-unknown: #6c7a8d;
```

**现有变量对照表（检查硬编码颜色是否已有对应变量）：**

| 硬编码值 | 应使用的变量 |
|---------|------------|
| `#0d1117` | `var(--code-bg)` |
| `#fff` / `#ffffff` | `var(--white)` |
| `rgba(108, 123, 255, ...)` | 优先 `var(--accent-bg)` / `var(--accent-bg-subtle)`，alpha 不同时添加新变量 |
| `rgba(255, 75, 75, ...)` | 优先 `var(--error-bg)` |
| `rgba(15, 17, 23, 0.92)` | 添加 `--overlay-bg` |

**检查方法：** 在 `.vue` / `.css` 文件中搜索 `#` 和 `rgba(`，对照上表验证。

### 4. 后端代码质量

- **导入清理**：函数内部禁止 re-import（如 finally 块中的 `import asyncio as _asyncio`），统一使用顶层导入
- **角色字符串**：全部使用 `ROLE_USER` / `ROLE_ASSISTANT` / `ROLE_SYSTEM` / `ROLE_TOOL`，禁止裸字符串 `"user"` `"assistant"` `"tool"`
- **魔法数字**：超时、截断长度等移到 `constants.py`，注释需与实际值一致（如注释写 `≤10s` 但实际值为 `8.0` 应修正）
- **异常处理**：避免 `except BaseException: pass`（会吞噬 `CancelledError` 等系统信号），使用 `except Exception:`
- **类型注解**：所有路由处理器应标注返回类型

### 5. 前端代码质量

- **导入顺序**：所有 import 语句集中在文件顶部，不在 import 之间穿插函数定义
- **消除无意义间接引用**：如 `const INTERVAL = HEARTBEAT_INTERVAL` 直接使用原常量即可
- **消除重复常量**：如 `const _DEFY_LIMIT = SCROLL_DEFY_LIMIT` 直接使用原常量
- **提取重复逻辑**：同一正则 / 工具函数在多处使用 → 提取到 `utils/` 或 `composables/`
- **提供 / 注入键**：应使用类型化的 `InjectionKey<T>` Symbol，而非裸字符串（防拼写错误）

### 6. 样式去重

**已知高频重复（重构候选）：**

| 模式 | 涉及文件 | 建议 |
|------|---------|------|
| `.info-block` / `.info-label` / `.info-code` | WorkflowDetail + MediaPreview | 提取到全局样式 |
| `.markdown :deep(...)` 渲染规则 | MessageBubble + MediaPreview | 提取为全局 `.markdown-content` 类 |
| `.tool-btn` / `.attach-btn` / `.think-btn` 圆形按钮 | ChatInput | 合并为基类 + 修饰类 |

**检查方法：** 对比各 SFC 的 `<style scoped>` 块，搜索重复属性组合（display, border-radius, padding 等）。

### 7. 文档同步

- `README.md`：curl 示例版本号、架构图中组件名称、项目结构树
- `CLAUDE.md`：版本号、组件路径（确认 `floating/` 目录）、API 端点列表
- 检查是否有对已删除文件的残留引用（如 `Sidebar.vue` → 应为 `floating/ConversationList.vue`）
- 全面检查注释等文案是否符合现状

## 验证

所有修改完成后必须通过（前后端均零错误）：

```bash
cd backend && uv run pyright --project pyrightconfig.json
cd frontend && pnpm build
```
