# Changelog

所有关于本项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，  
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## 0.44.0

### 添加
- **合成器素材查询工具**：`composer_list_videos` 支持 `kind=all/video/image/audio` 与 `limit`，同时返回图片 / 视频 / 音频素材和已完成成片；成片带 `file_url` / `download_url`
- **聊天内媒体预览**：assistant 消息直接展示工具查询到的图片 / 视频 / 音频卡片；图片和视频点击打开 MediaPreview，音频内联播放，成片可下载；实时流、resume 与历史恢复同样解析
- **渲染结果链接**：`GET /api/composer/renders/{id}`、渲染列表 / SSE 与 `composer_render_status` 在完成时返回 `file_url` / `download_url`；`output_ready` 同时要求产物存在

### 变更
- **首开预取**：设置面板启动即预取配置 / 密钥；合成器四个标签页改为常驻挂载（`v-show`），素材 / 项目 / 渲染各自预取；父组件只保留配置与 SSE 订阅，减少重复请求
- **工具文档**：README 工具生态补充 9 个合成器工具与素材查询能力；项目结构加入 `utils/composerMedia.ts`

### 修复
- 修复合成器查询只能拿到成片 / 视频素材、拿不到图片 / 音频素材的问题（`kind` 参数）
- 修复设置 / 合成器标签首次打开时的数据加载与挂载卡顿

## 0.43.1

### 变更
- **README**：移除已完成的「下一步计划」章节（M1–M5 清单与 GA 说明），更新 `ComposerPanel.vue` 的结构说明
- **deploy/README.md**：移除本机状态（当前机器状态列、实测磁盘表、HF 访问状态等）；补充 setup.ps1 的下载/安装位置（`SIDECAR_HOME`、venv、源码、权重、音色、uv 缓存）、启动路径要求（启动器/serve.py/端口/base_url）、默认 `SIDECAR_HOME` 与常见路径错误

## 0.43.0

### 添加
- **本地模型 sidecar 一键启动器**：新增 `deploy/start_sidecars.py`，同时拉起 CosyVoice（9701）与 Stable Audio（9702），等待 `/health` 就绪；已健康运行的 sidecar 复用，不重复启动；日志写入 `logs/sidecars/*.log`；某个退出时继续照看另一个，Ctrl+C 统一停止（`taskkill /T`）；模型保持懒加载
- **后端 sidecar 健康 / 日志接口**：新增 `composer/sidecars.py` 与 `GET /api/composer/sidecars?lines=N`，返回 `reachable` / `model_ok` / `health` / `log_path` / `log_tail`；后端不管理 sidecar 进程，重启或 `--reload` 不受影响
- **合成器动效**：标签页复用 `useTabIndicator` 滑动指示器，内容横向淡入；素材库 TTS/BGM 与项目页「新建项目」平滑折叠展开；分镜/轨道视图交叉淡入；开始页与渲染完成 toast 的浮窗流体展开从被点击按钮矩形开始
- **玻璃收尾**：浮窗形变期间只显示软透镜（模糊），结束后 220ms 内把透镜位移 scale 缓动到满强度；每个浮窗克隆独立透镜滤镜，面板之间互不影响

### 变更
- **玻璃材质简化**：生产浮窗移除 tint / 四点高光 / 扫光 / rim / 1px 边框，只保留 warp（backdrop 模糊 + 透镜位移）+ 外投影；聊天输入框恢复加玻璃前的实色卡片（`--bg-primary` + `--border`，无模糊/阴影）；消息气泡和条目继续使用 tint + inset 高光
- **浮窗形变**：形变期间保留非 none 的滤镜（零位移 scale）以维持 `backdrop-filter` 渲染；软 → 正式透镜改为逐帧 scale 缓动，解决形变中玻璃缺失和结束时透镜突现
- **文档**：README / `deploy/README.md` 更新 sidecar 启动器、健康日志接口和手动启动说明；CLAUDE.md 补充 sidecar 启动方式与模块

### 修复
- **玻璃透明 bug**：移除叠层中的 `mix-blend-mode: screen`，避免 Chromium 在几何动画/透明度过渡时跳过 `backdrop-filter`（浮窗曾表现为完全透明）
- **浮窗形变期间玻璃缺失**：不再把 warp 的滤镜设为 `none`，改用零位移的实例滤镜保持模糊；透镜在形变结束后淡入
- **合成器展开生硬**：标签切换、TTS/BGM 生成面板、新建项目表单、分镜/轨道视图增加平滑过渡
- **浮窗入口动效不同步**：开始页入口此前取不到已隐藏的浮岛胶囊矩形，导致没有流体展开；现在由 ChatPanel 传递触发按钮矩形，toast 也从自身位置展开

## 0.42.0

### 添加
- **开始页**：`/` 路由显示大输入卡 + 快捷提示 + 会话列表 / 视频合成器 / 设置入口；发送首条消息后自动创建会话并进入 `/chat/:id` 正常页；开始页隐藏浮岛按钮与会话列表，进入对话后恢复；支持深/浅主题与现有玻璃效果

### 变更
- **卡片玻璃生产化**：浮窗与输入框的折射从 `feTurbulence` 噪声改为「透镜位移图 → 边缘 mask → RGB 三通道位移 → 中心回填」；新增 `GlassFilters.vue`（全局 SVG 滤镜）与 `utils/glassLens.ts`（Canvas 2D SDF 位移图）；`.glass-card` 拆为 warp（backdrop 模糊 + 滤镜）/ tint（滤镜之上染色）/ rim / body 四层；浮窗流体变形期间临时关闭透镜滤镜
- **浅色主题 / 清透玻璃**：tint 调为深色 28% / 浅色 38%，背景模糊 9px，tint 内缩 12px 留出透镜边缘；新增静态 1.5px 渐变 rim；避免 tint 直接进入滤镜导致发灰
- **环境光背景**：`App.vue` 新增静态 `.app-ambient`（深/浅两套极光色团 + 斜光带 + 细网格），给玻璃边缘提供可折射的结构

### 移除
- 移除 `useGlassPointer` 与 `index.html` 的 `liquid-glass-refraction` 噪声折射滤镜（由透镜位移图方案取代）

## 0.41.0

### 添加
- **浮岛按钮流体变形**：设置 / 视频合成器 / 会话列表 / 会话参数按钮点击后，从按钮矩形以高阻尼二阶弹簧展开为面板；尺寸与圆角按弹簧关键帧联动，内容层固定尺寸、由外壳裁切揭示，展开过程中即可看到卡片内容；关闭时反向收回按钮
- **卡片玻璃 G1（Card Glass）**：`style.css` 新增 `--glass-rim-inner / --glass-tint / --glass-sheen-warm / --glass-dispersion-r/g/b` 明暗 token；新增全局 `.glass-card`（Blur）/ `.glass-card--tint` / `.glass-card__rim` / `.glass-card__body`，固化 REFRACT → SHADOW → TINT → LIGHT 合成顺序；浮窗与输入框换用 `.glass-card`，胶囊按钮降为 Tint 玻璃；四点掠射环境光 + 1px 边缘色散
- **卡片玻璃 G2（推广 + 指针折射）**：用户消息气泡、消息文件卡、会话列表活动条目应用 Tint 玻璃 rim；新增 `useGlassPointer`，指针悬停玻璃时以 12fps 微调 SVG `feTurbulence` 的 `baseFrequency`（触摸 / `prefers-reduced-motion` 跳过；连续掉帧自动退回静态玻璃）

### 变更
- 浮岛入口统一为 56×32 纯图标胶囊，设置 / 视频合成器 / 会话列表尺寸一致；打开对应面板时按钮隐藏，关闭时面板收回按钮位置后再淡入
- 玻璃按用途分级：浮窗 / 输入框为 Blur 玻璃，胶囊 / 用户气泡 / 消息文件卡 / 活动会话条目为 Tint 玻璃；assistant 正文保持无底色，避免聊天区整屏卡片化
- 设置面板打开时隐藏其下方的视频合成器按钮，避免半透明玻璃透出残影

## 0.40.0

### 添加
- **明暗主题**：`useTheme` 支持 dark / light / system 三模式，持久化 localStorage、跟随系统 `prefers-color-scheme`；设置面板新增「外观」标签页；切换时使用 View Transitions 以点击位置为圆心做圆形扩散（不支持时瞬时切换）；代码高亮样式随主题切换
- **前端性能 P3**：Markdown 重依赖（markdown-it / texmath / katex / highlight.js）改为动态加载，首屏主 JS 包 **1.78 MB → 约 260 KB**；WorkflowDetail 仅引入 JSON 语言核心；流式消息 60ms 防抖渲染；图片懒加载；加载/渲染失败降级纯文本
- **会话批量删除**：头部合并为单个「清空」按钮，点击进入多选并默认全选；底部操作栏显示已选数量、全选/取消全选、取消、删除；全部取消后自动收起；多选模式隐藏菜单与重命名
- **工具调用文本兜底**：系统提示词动态注入约束（无工具禁止输出 `<tool_call>`，有工具只允许标准 `tool_calls`）；前端把文本标记替换为友好提示，复制内容同步清洗
- **系统时间注入**：每轮请求在系统提示词副本中追加当前系统时间（含 UTC 偏移与时区），工具循环每轮刷新，不写入持久化历史
- **液态玻璃**：浮窗与底部输入框升级为半透明磨砂 + SVG `feTurbulence/feDisplacementMap` 背景折射（渐进增强）+ 环境光漂移与镜面扫光；浅色主题独立参数
- **动效**：
  - 输入框聚焦时，textarea 底边强调线从中心向两侧展开
  - 会话列表活动高亮框滑动到新位置，移动中沿方向拉伸并在到位回弹，带细高光边
  - 会话参数预设按钮（精确/日常/创作/默认）同款滑动高亮框
  - 设置面板与会话参数面板新增滑动选中框，内容从左侧淡入
  - 复制反馈：图标切换为对勾 + 上方浮出「已复制」，1 秒后恢复
- **浅色主题优化**：整体配色重调、页面轻渐变背景、语义色与阴影适配

### 变更
- 浅色全局边框 `#d9dce8 → #cfd4e3`，玻璃边框改为 `rgba(24,35,70,0.18)`，浅底轮廓更清晰
- 输出内容排版：Markdown 行高 1.8、段落间距 16px、列表 8/4px、标题 22/10px；纯文本气泡行高 1.8
- 滑动高亮框拉伸幅度 1.16 → 1.06，时长 460/420 → 320/300ms，降低抖动
- 复制反馈时长 `COPY_FEEDBACK_DURATION` 2000 → 1000ms

### 修复
- **输入框聚焦双重边框**：全局 `:focus-visible` 与组件 `:focus { border-color }` 叠加，且 `:is()` 提升特异性导致关闭规则失效；重组焦点样式，文本类控件不再进入全局描边规则，按钮/链接/复选框/滑块保留描边

### 文档
- CLAUDE.md 前端架构补充主题/液态玻璃/滑动指示器约定；README 版本与示例同步

## 0.39.1

### 修复
- **Markdown 消息段落"隔行"**：`MessageBubble` 的 `.content` 使用 `white-space: pre-wrap`，该规则同时作用于 Markdown 渲染容器，导致 markdown-it 输出的 HTML 标签间源码换行被渲染为额外空行。Markdown 容器改为 `white-space: normal`，纯文本消息仍保留 `pre-wrap`
- **段距/行距可读性**：Markdown 行高调整为 1.7、段落间距 8px、列表间距 4px/2px，标题上下间距 14px/6px；纯文本行高同步为 1.7

## 0.39.0

### 添加
- **前端无障碍基础（P0）**
  - 全局 `:focus-visible` 焦点样式（键盘 Tab 可见，覆盖组件内 `outline:none`）
  - `@media (prefers-reduced-motion: reduce)` 全局关闭动画/过渡
  - 图标按钮补 `aria-label`：浮窗置顶/关闭、App 浮动按钮、会话菜单、媒体预览、渲染刷新、发送到合成器
  - `FloatingWindow` 增加 `role="dialog"` / `aria-modal` / `aria-label`
  - 折叠控件 `aria-expanded`（原始数据折叠）、设置标签页 `role=tablist/tab` + `aria-selected`；状态点 `role=img` + 描述
- **动效（P1）**
  - 浮窗开合：`opacity + translate(8px) + scale(.98)`，使用独立 transform 属性与定位 `transform` 共存；拖拽时禁用过渡
  - 消息入场：工作流日志/消息气泡淡入 + 上移 4px（仅挂载触发，流式更新不重播）
  - 会话列表按索引交错入场（延迟按 30ms 递增，封顶 12 项）
  - Esc 关闭顶层浮窗：确认 `windowZIndex` 既有实现，回归通过（未重复实现）
- **视觉质感（P2 部分）**
  - 浮窗玻璃拟态：半透明背景（`color-mix` + 实色回退）+ `backdrop-filter: blur(14px)` + 细边框
  - 强调辉光：工具栏激活按钮、生成中状态点

### 变更
- 焦点样式提升优先级（`!important`）以覆盖局部 `outline: none`，不改变元素圆角
- 渲染完成 toast 增加 `role="status"` / `aria-live`

### 文档
- CLAUDE.md 前端架构补充无障碍/动效约定；CHANGELOG 本条

> 未包含：P2 明暗主题（待产品决策）、P3 性能优化（Markdown 懒加载、图片懒加载等，另排期）。

## 0.38.2

### 文档
- **README 本地模型 sidecar 章节补全**（§5）：首次安装命令（`setup.ps1`）、启动命令（`serve.ps1`，端口 9701/9702）、健康检查地址、首次请求加载耗时（CosyVoice ~10s / Stable Audio ~80s）、GPU 与驱动要求（RTX 50 系需 CUDA 12.8+、显存各约 2-3 GB）、不部署时的降级说明，并链接 `deploy/README.md` 完整部署文档

## 0.38.1

### 修复
- **Windows 下渲染秒失败且错误为空**：后端运行在 SelectorEventLoop 时，`asyncio.create_subprocess_exec` 不受支持（抛出空消息 `NotImplementedError`），导致渲染在 preparing 前即失败、`error` 为空、无 ffmpeg 日志。`composer/ffmpeg.py` 的 `run_ffmpeg` 与 `probe_media` 改为 `subprocess.Popen` / `subprocess.run` + 线程读取 stdout/stderr（与 MCP 子进程实现一致），兼容任意事件循环；进度回调经 `loop.call_soon_threadsafe` 回投
- **取消逻辑适配**：`composer/queue.py` 子进程类型改为 `subprocess.Popen`，取消等待改用 `asyncio.to_thread(proc.wait)`，terminate → 宽限 → kill 行为不变
- **空错误诊断**：渲染失败日志增加 `exc_info=True`，同类异常可直接看到完整堆栈

## 0.38.0

### 添加
- **视频合成器 M5：体验完善（GA）**（规划见 PLAN.md §11 M5）
  - **轨道式时间轴**（`TimelineTracks.vue`）：时间标尺、播放头点击定位与素材预览（视频按播放头 seek）、视频块原生拖拽重排、旁白 / BGM / 字幕轨可视化；分镜编辑器新增「分镜 / 轨道」视图切换，共享同一 draft 与防抖保存
  - **项目模板**：`GET /api/composer/templates` 提供产品介绍 / 口播 / 图文混排三套骨架（预设 + 脚本）；前端「从模板新建」自动填充并设置分辨率预设
  - **磁盘 LRU 回收**（`composer/maintenance.py`）：未引用素材（按创建时间升序）→ 旧渲染产物，清理至 `limit × target_ratio`；手动 `POST /maintenance/cleanup` + 渲染完成水位自动清理（默认关闭，可配置开关与目标比例）；`GET /maintenance/usage` 占用快照
  - **对话联动**：WorkflowDetail 工具结果中的媒体 URL 一键「发送到合成器」（自动识别 URL、去重复用）
  - **渲染完成 toast**：SSE 收到 completed 时全局提示，点击打开合成器
- 配置新增 `disk_cleanup_enabled` / `disk_cleanup_target_ratio`

### 变更
- `RenderQueue` 增加「清理磁盘」按钮与结果提示
- README 状态徽章标记 **GA**，功能特性与里程碑全部完成

### 文档
- **README**：API 表补 templates / maintenance 端点、项目结构补 `maintenance.py` / `TimelineTracks.vue`、M5 与 GA 标记
- **CLAUDE.md / PLAN.md**：版本与里程碑状态同步（M1-M5 完成，GA）

> 本版本同时标志着 IRIS VIDEO COMPOSER（0.34.0 → 0.38.0）五个里程碑全部交付：
> 素材管线 → 时间轴与语音/音乐 → 渲染 MVP → 高级合成 → 体验完善。

## 0.37.0

### 添加
- **视频合成器 M4：高级合成**（规划见 PLAN.md §11 M4）
  - **xfade 转场**：fade / dissolve / slide，拼接阶段两两合并（任意段转场 > 0 时走 xfade 链，否则保留 concat 快路径）；成片总时长自动扣除转场重叠
  - **Ken Burns 运镜**：图片镜头 `zoompan`（from/to zoom + 左右上下 pan，2× 预放大），校验缩放范围 [0.5, 3] 且 `to_zoom ≥ from_zoom`
  - **ASS 样式字幕**：内置 default / large / top / minimal 四套样式（字号 / 描边 / 底/顶位置），mux 阶段 `ass=` 烧录；SRT 下载端点不变
  - **音频进阶**：旁白 + BGM 侧链压缩（`sidechaincompress`，旁白出现时自动压低 BGM），BGM 轨新增 `ducking` 开关；保留 loop / fade in/out
  - **TTS 进阶**：长文本（>80 字）按中英文标点自动分句合成 + ffmpeg concat 为单条音频；`segments` 多说话人对话合成（REST 与 `composer_tts` 工具均支持）
  - **编码参数可配置**：`/api/composer/config` 新增 `encoding {preset, crf, audio_bitrate}`，渲染命令实时读取
- 前端分镜编辑器：转场类型下拉、Ken Burns 缩放/平移参数、字幕样式下拉、BGM「旁白时压低」勾选；素材库 TTS「长文本自动分句」勾选
- `deploy/README.md` 补充 ACE-Step 主题曲 sidecar 契约（可选，不新增安装脚本）

### 修复
- **转场路径总时长重复扣减**：xfade 分支已按累计时长计算，修复再次减去转场时长导致成片变短（9s − 1.8s 应为 7.2s，原输出 5.4s）
- **xfade 路径 mux 输入错误**：mux 阶段误用固定 `merged.mp4`，改为使用实际拼接产物（`xfade_*.mp4`）

### 文档
- **README**：M4 能力说明、`tts.py` / `ffmpeg.py` / `queue.py` 模块描述、下一步计划标记 M4 完成

## 0.36.0

### 添加
- **视频合成器 M3：渲染管线 MVP**（规划见 PLAN.md §7）
  - `composer/ffmpeg.py` 扩展渲染引擎：分段规格化（图片 `-loop 1` / 视频 `-ss/-t`，统一 scale/pad/fps/yuv420p + libx264）、concat 拼接、字幕烧录 + 旁白/BGM `amix`（gain / fade / delay / loop 输入）+ `-movflags +faststart`；`run_ffmpeg` 解析 `-progress pipe:1`、stderr 尾部与完整日志、进程注册
  - `composer/queue.py`（新）：渲染队列 FIFO + 并发 worker（`render_concurrency`）、状态机 `queued → preparing → rendering → muxing → completed/failed/canceled`、1s 节流进度、取消（terminate → 3s → kill）、优雅关闭、启动时中断任务标 failed、磁盘水位告警
  - renders 持久化（`store.py` CRUD + active 检查 + 中断恢复）
  - API：`POST /projects/{id}/render`、`GET /renders`、`GET /renders/{id}`、`POST /renders/{id}/cancel`、`GET /renders/{id}/file`（Range + `?download=1`）；SSE `composer_render` / `composer_progress` / `composer_warn`；Range 流式响应对素材与成品复用
  - Agent 工具 `composer_start_render` / `composer_render_status` 接真实现（异步提交，不阻塞等待）
  - 前端 `RenderQueue.vue`：状态灯 + 进度条 + stage、取消、成品预览（MediaPreview）、下载、失败 stderr 折叠、磁盘告警；分镜编辑器「提交渲染」按钮（先保存后提交）；ComposerPanel 四个标签页全部启用
- 渲染常量：状态机、进度权重、编码参数（`veryfast` / `crf 23` / `aac 192k`）、文件命名、告警文案

### 修复
- **损坏素材导致渲染挂起**：图片分段 `-loop 1` 遇到无效图片会无限重试；所有 ffmpeg 命令加 `-xerror` 立即失败，错误进 render.error

### 文档
- **README**：API 一览补 5 个渲染端点、项目结构补 `queue.py` / `RenderQueue.vue`、下一步计划标记 M3 完成

## 0.35.0

### 添加
- **视频合成器 M2：时间轴 + 编排 + 语音/音乐生成**（规划见 PLAN.md）
  - `composer/timeline.py`：时间轴 Schema 校验（逐字段中文错误，供 LLM 自纠）、SRT 生成、引用素材提取、空时间轴骨架；常量覆盖版本 / 轨道 / 角色 / 转场 / 运镜 / 图片时长范围
  - 项目 CRUD：`GET/POST /api/composer/projects`、`GET/PATCH/DELETE /api/composer/projects/{id}`、`GET /projects/{id}/srt`；PATCH 时间轴先校验再入库，素材引用计数随项目增删同步
  - 语音服务层 `composer/tts.py`：local-http（CosyVoice sidecar）→ openai-compat（云端）→ edge-tts 三级降级；`POST /api/composer/assets/tts`
  - 音乐服务层 `composer/music.py`：Stable Audio sidecar；`POST /api/composer/assets/music`，不可用时返回引导信息不阻塞编排
  - `composer/assets.py` 新增 `import_from_bytes`，TTS/BGM 产物复用 hash 去重 + ffprobe 探测管线
  - Agent 八工具（`llm/tools/composer.py`）：创建项目 / URL 导入 / Agnes 轮询入库 / TTS / BGM / 写入时间轴 / 渲染占位 ×2；`Tool.group` 分组机制，`/api/tools` 新增「合成器」工具组
  - 前端：`ProjectList.vue`（新建/选择/删除）、`StoryboardEditor.vue`（镜头卡片 + 字幕列表 + 旁白/BGM 轨，600ms 防抖 PATCH，Agent 外部更新自动同步）、`AssetLibrary` TTS/BGM 快捷生成、`ComposerPanel` 启用项目与时间轴标签页
  - 部署 `deploy/`：CosyVoice 2.5 / Stable Audio Open Small sidecar 安装与启动脚本（国内源、uv 缓存硬链接、Python 3.10 自动安装、Windows 兼容补丁、默认提示音色）

### 变更
- `GET/PUT /api/composer/config` 增加 TTS / 音乐 provider 连通探测（2s 超时）
- 前端 `useComposer` 扩展项目状态 + `composer_project` SSE 本地 upsert；`client.ts` composer 命名空间补 projects / tts / music
- `constants.py` / `constants.ts`：时间轴、provider、工具组、引导文案与 UI 文案常量

### 修复
- **Windows sidecar 兼容**（全部固化进 `deploy/` 脚本，详见 `download.md`）：matcha Cython 扩展免编译（源码内置）、pyworld 可选导入、`torchaudio.load` 改 soundfile、whisper 升级 20250625、torch 降级后重新锁定 cu128、PyWavelets/numpy 2 兼容、rf_denoiser 采样器改 pingpong、numpy 2 随机数溢出规避

### 文档
- **download.md**：完整下载清单（版本 / 国内源 / 校验值）、实测磁盘占用、Windows 兼容问题与处理表
- **deploy/README.md**：sidecar 部署步骤、国内源表、目录约定、前置条件、实测占用
- **README**：API 一览补项目/TTS/BGM/SRT 端点、项目结构更新、下一步计划标记 M1/M2 完成

## 0.34.0

### 添加
- **视频合成器 M1 素材管线（IRIS VIDEO COMPOSER）**：新增 `backend/composer/` 域包（规划见 PLAN.md）——`store.py`（ComposerStore：SQLite 三表 projects/assets/renders + 单写者锁 + 引用计数）、`assets.py`（URL 流式下载 + sha256 去重 + MIME 白名单判型 + ffprobe 探测 + hash 分桶存储）、`ffmpeg.py`（ffmpeg/ffprobe 定位 + 启动探测 + 元数据探测，图片 codec 识别剔除）、`config.py`（`composer_config.json`：ffmpeg 路径 / 磁盘上限 / 渲染并发 / 分辨率预设表）、`router.py`（REST + SSE）
- **素材库 API**：`/api/composer/assets`（列表 kind 过滤 / URL 导入）、`/assets/upload`（500 MB 上限、仅媒体类型）、`/assets/{id}`（详情含探测元数据 / 删除引用计数校验）、`/assets/{id}/file`（HTTP Range 流式播放）、`/status-stream`（SSE 素材事件 + 心跳）、`/config`（配置读写 + ffmpeg 探测结果）
- **前端合成器面板**：`ComposerPanel.vue`（FloatingWindow 主浮窗，素材页启用、项目/时间轴/渲染占位）+ `AssetLibrary.vue`（网格缩略图 + 类型过滤 + 上传 + URL 导入 + 删除）+ `useComposer.ts`（模块级单例 + SSE 断线重连），入口按钮位于右上角；素材预览复用 MediaPreview 本地流播放

### 变更
- **Agent 迭代上限常量化可配置**：`MAX_TOOL_ITERATIONS` 进 `llm/constants.py`，`llm_config.json` 新增 `max_tool_iterations` 键（默认 10），`Agent` 构造处读取配置值。纯重构，无行为变化

### 文档
- **README**：环境要求补 ffmpeg（可选）、快速开始新增 ffmpeg 安装指引、API 一览登记 6 个 composer 端点、项目结构更新、下一步计划标记 M1 完成

## 0.33.1

### 修复
- **Agent 迭代上限空回复**：`Agent.continue_with_results` 达到最大迭代次数（10 轮）时不再返回空 `content`，改为返回明确的中止提示文案（新增常量 `MSG_MAX_ITERATIONS`）
- **自动工具循环空回复兜底**：`router._generate` 流式循环结束后，若最终 assistant 消息 `content` 为空（模型仅输出 reasoning 即停止的场景），注入占位提示（`MSG_EMPTY_REPLY`）并同步推送 SSE `content` 事件，避免前端渲染空气泡
- **pyright exclude 配置缺失**：`pyrightconfig.json` 补充 `venv` 目录排除——实际虚拟环境目录名与配置的 `.venv` 不符，导致项目级类型检查被第三方依赖噪音淹没（全量 2461 errors → 0 errors）

### 文档
- **README 架构图重写为循环结构**：原图为线性 `AGENT → CONTEXT → CLIENT`，与代码中实际存在的双循环不符；改为编号回边（① 每轮压缩请求副本 → ② 发起工具调用 → ③ 结果回传进入下一轮）+ 自定义工具 SSE 暂停 / 手动执行续跑的虚线路径
- **README 循环描述修正**：移除"自动工具循环最多 10 轮迭代"的错误表述——10 轮上限仅作用于自定义工具路径（`Agent.continue_with_results`），自动工具循环为 `while True` 无迭代计数

## 0.33.0

### 修复
- **Agnes MCP 国内站适配**：`mcp/agnes/server.py` 的 Base URL 默认切换为 `https://api.agnes-ai.cn`（海外部署可用 `AGNES_BASE_URL` 覆盖），修复国内分组 token 下"Invalid token / 模型不可用"（此前默认走海外地址 apihub.agnes-ai.com）

### 变更
- **视频工具按国内 API 文档重写**：`agnes_video_create` 新参数集（`mode`: text/keyframe/reference、`seconds` "4"–"12"、`size` 720P/1080P/1K/2K、`aspect_ratio`、首尾帧控制 `first_frame`/`last_frame`、多模态参考 `images`/`audios`/`videos`），旧参数（width/height/num_frames/frame_rate）随海外 API 废弃；`agnes_video_status` 按官方建议携带 `model_name` 查询
- **视频默认模型切换**：`agnes-video-v2.0` → `agnes-video-2.5-flash`（720P 免费，`AGNES_VIDEO_MODEL` 可覆盖）
- **README 全量重构**：功能特性全景展示（对话与推理 / 工具生态 / 会话与数据 / 控制台界面）、API 端点一览表、架构图更新、"下一步计划"新增 IRIS VIDEO COMPOSER（视频合成器）

## 0.32.0

### 添加
- **上下文压缩**（`llm/context.py`）：发送请求前自动压缩超预算的对话历史——超长工具结果截断保留首尾、从最老轮次丢弃完整对话轮（保持 assistant(tool_calls)↔tool 配对）、注入压缩提示；仅作用于请求副本，不改持久化历史；token 启发式估算（CJK 1 字 ≈ 1 token）
- **流式 API 错误详情日志**：`chat_stream_events` 收到 400/5xx 时在流式上下文内读取响应体并记录详情（此前仅记录状态码，无法定位参数错误）

### 修复
- **DeepSeek 思考模式工具调用 400**：`_generate` 自动工具循环每轮构造请求时统一排除末尾空 assistant 占位消息（思考模式模型要求每条 assistant 消息携带 `reasoning_content`，占位消息缺失导致 "The reasoning_content in the thinking mode must be passed back to the API"）
- **Agent 工具轮次 reasoning_content 丢失**：`Agent.continue_with_results` 回传 assistant 消息时保留 `reasoning_content` 字段

### 变更
- **`_build_payload` 思考模式兜底**：`thinking=True` 时对带 `tool_calls` 且缺失 `reasoning_content` 的 assistant 消息补空字符串，兼容 DeepSeek 多轮工具调用校验

## 0.31.6

### 变更
- **后端 MCP 常量化**：`mcp.py` 中所有 JSON-RPC 字段名（`"clientInfo"`、`"result"`、`"error"`、`"content"`、`"isError"` 等）与配置键（`"name"`、`"command"`、`"args"`、`"transport"`、`"url"`、`"disabled"` 等）替换为 `MCP_FIELD_*` / `MCP_KEY_*` / `MCP_TRANSPORT_*` 常量
- **后端常量化补全**：`models.py` 的 `SessionStatus` 枚举值改用 `STATUS_*` 常量；`router.py` 中 SSE 事件类型字符串、响应键 `"ok"`、MCP 配置键 `"mcpServers"` 替换为常量；`sessions.py` SQL 默认值使用 `STATUS_COMPLETED` 常量插值
- **前端 CSS 变量化**：`ImageViewer`、`MessageBubble`、`SessionSettingsPanel`、`WorkflowLog`、`ConversationList`、`SettingsPanel` 中的硬编码 `border-radius` 值替换为 `var(--radius)` / `var(--radius-sm)`
- **前端字符串常量化**：`ChatPanel` 中 `"tool"` → `ROLE_TOOL`；`MessageBubble` 中 `"assistant"` → `ROLE_ASSISTANT`；`WorkflowLog` 中 `"think"` → `WF_THINK`
- **WorkflowDetail 代码复用**：提取 `escapeHtml()` 和 `highlightJsonOrEscape()` 函数，消除 `renderedResult` 与 `highlightedRaw` 中的重复 HTML 转义与 JSON 高亮逻辑
- **前端导入清理**：`SettingsPanel` 中 `discoverTools` 以别名 `refreshTools` 导入，移除冗余中间变量
- **字体样式微调**：`.info-code` 移除等宽字体（数字读取更舒适）；`.info-value` 新增等宽字体

### 修复
- **README curl 示例版本号**：响应示例中 `0.31.1` → `0.31.5`，与当前实际版本一致

## 0.31.5

### 变更
- **项目描述务实化**：README.md 移除展期设想描述，替换为现状功能描述；删除"项目愿景"章节
- **文档精简**：CLAUDE.md 从 ~130 行压缩至 ~45 行，保留核心命令、概念与设计模式
- **后端描述更新**：`pyproject.toml` 与 `backend/README.md` 描述从"多模态桥接 Agent"改为"LLM Chat + Agent 控制台"

## 0.31.4

### 添加
- **MCP 配置文件监听**：健康检查循环每 3s 检测 `mcp.json` 的 mtime 变更，直接编辑文件即可自动热重载，无需通过 API
- **MCP 重载统计日志**：重载完成后输出 `+N 新增 / N 移除 / N 复活` 汇总，便于排查
- **前端 MCP 重连指示器**：服务器标签页 MCP 状态旁显示 "重连中…" 加载提示

### 变更
- **前端工具发现架构重构**：`discoverTools()` + `toolGroups` 从 ChatPanel 局部提升到 `toolMetadata.ts` 模块级单例，兄弟组件直接 import 调用，不再依赖 provide/inject
- **MCP 热重载 API 改进**：`PUT /api/mcp/config` 后台任务包装异常日志，返回 `reloading` 状态字段；`_last_errors` 追踪启动失败的服务器名称与错误原因
- **前端 MCP 重载反馈**：SettingsPanel 保存 MCP 配置后轮询 `GET /api/mcp/status`（1s 间隔），状态连续 2 次不变即确认为重载完成并刷新工具列表，替代旧的 1.5s + 4s 盲等 `setTimeout`

### 修复
- **stdio MCP 过早 ready**：`MCPServerProcess.is_running` 在子进程启动时立即为 `True`，但 initialize 握手与 `tools/list` 尚未完成。新增 `_initialized` 标志，仅在完整握手成功后报告运行中
- **前端工具栏不更新**：SettingsPanel ↔ ChatPanel 兄弟组件间 `provide/inject` 跨 Teleport 无效，`inject(REFRESH_TOOLS_KEY)` 一直返回空函数，导致 MCP 配置变更后工具按钮从不刷新
- **MCP 并发重入保护**：`MCPManager.reload()` 增加 `_reloading` 守卫，跳过重复重载请求

## 0.31.3

### 修复
- **DeepSeek API 兼容**：`ROLE_SYSTEM` 从 OpenAI 新规范 `"developer"` 回退为 `"system"`（DeepSeek 不支持 developer 角色）
- **API 路径适配**：`/v1/chat/completions` → `/chat/completions`，`/v1/models` → `/models`（匹配 DeepSeek 文档）
- **`is_error` 泄露**：`_build_payload()` 的内部字段过滤增加 `is_error`，避免内部状态标记发送给 LLM
- **流式 400 响应体**：不再尝试读取已关闭的流式响应体，改为记录请求摘要
- **前端 SSE_ERROR 状态同步**：后端异常终止时前端同步设置 `streamDone = true`，停止加载动画
- **系统提示词硬编码兜底移除**：`create_conversation` 不再在 `system_prompt=None` 时回退到 `SYSTEM_PROMPT`，出厂默认由 `session_settings.json` 提供

## 0.31.2

### 添加
- **后端日志系统**：根 logger 设 INFO 级别，新增控制台 + 文件双输出；HTTP 请求日志中间件（方法/路径/状态/耗时）；50+ 关键路径日志点覆盖 9 个此前无日志的模块（`client.py`、`agent.py`、`chat.py`、`uploads.py`、`info.py` 等），session ID 前缀 `[sess:abc123]` 实现全链路追踪
- **常量化扩充**：新增 50+ 后端常量（JSON-RPC 协议字符串、MCP 字段名、配置键、MIME 类型、SSE dict 键、中文提示消息），`config.py` / `client.py` / `uploads.py` 中的硬编码字符串全部替换
- **`InjectionKey` 类型化 provide/inject**：新增 `composables/injectionKeys.ts`，5 个类型化 Symbol 替换 13 处裸字符串 provide/inject 调用
- **全局 CSS 类提取**：`.markdown-content`（3 组件 ~180 行去重）、`.circle-btn-lg`（ChatInput 按钮）、`.raw-toggle`（2 组件共 28 行去重）、`--white-18` 变量
- **图片扩展名单源**：`utils/index.ts` 从 `markdown.ts` 导入 `IMG_EXTS`，删除重复数组

### 变更
- **`[错误]` 前缀全面废除**：`calculator.py` / `open_url.py` / `web_search.py` 从返回错误字符串改为抛出异常（`ValueError` / `RuntimeError`），`ToolExecutor` 统一捕获并设置 `is_error=True`；`router.py` SSE_ERROR 内容移除前缀；`constants.py` 删除 `ERROR_PREFIX`
- **异常处理规范化**：`router.py` 2× `except BaseException: pass` → `except asyncio.CancelledError`
- **魔法数字常量化**：`[:200]` → `MCP_SSE_TRUNCATE`、`"data:"` → `SSE_DATA_PREFIX`、`_HEALTH_CHECK_INTERVAL` → `MCP_HEALTH_CHECK_INTERVAL`、`timeout=30` → `MCP_RELOAD_TIMEOUT`、`busy_timeout=2000` → `SQLITE_BUSY_TIMEOUT`
- **导入规范化**：`router.py` `import time as _time` 移至模块顶部；`config.py` 8 处 `except: pass` + `sessions.py` 3 处 + `mcp.py` 2 处 + `uploads.py` 1 处全部替换为带上下文的 `logger.warning/debug`
- **双重调用修复**：`_read_project_meta()` 调用一次缓存结果，不再解析 pyproject.toml 两次
- **类型注解补全**：`info.py` 4 个路由处理器全部添加返回类型
- **文档同步**：`README.md` 项目树更新（+`router.ts`/`ToolGroupPanel.vue`，-`tools/`，移动 `SessionSettingsPanel`）；`CLAUDE.md` 工具描述与心跳逻辑更新
- **tool-creation 技能更新**：错误处理约定改为抛异常，注册格式改为 `{"mcpServers": {...}}`，前端元数据改为 `composables/toolMetadata.ts`

### 修复
- **CSS Bug**：`--white-03: var(--white-03)` 自引用 → `rgba(255, 255, 255, 0.03)`，修复 `.code-header` 背景不可见
- `chat_stream_events()` 新增可选 `session_id` 参数，日志可追溯

## 0.31.1

### 变更
- **后端常量化**：新增 `SSE_STATUS`、`STATUS_UNKNOWN`、`STATUS_REPLACED` 常量；`router.py` 全部状态字符串与事件类型常量化；`sessions.py` 注释修正
- **前端常量化**：所有 `.vue` 模板中的 `"user"`/`"assistant"`/`"tool_call"`/`"tool_result"`/`"think"` 替换为 `ROLE_*` / `WF_*` 常量；`ConversationList` SSE 解析字符串常量化
- **CSS 变量化**：新增 14 个设计令牌（`--accent-bg-mid`、`--error-border`、`--shadow-sm`、`--white-03`~`--white-95` 等），消除 19 处硬编码 rgba 值
- **CSS 复用化**：`.tab-btn` 和 `.info-*` 系列从组件 scoped 样式提取到全局 `style.css`；`.tab-btn` 使用 CSS nesting

### 移除
- **死代码**：删除 `backend/llm/tools.py`（380 行，被 `tools/` 包完全遮蔽）；移除 `App.vue` 未使用的 `useRoute`；移除 `DEFAULT_SESSION_SETTINGS`、`UI_SETTINGS` 等未使用导出
- **未使用导入**：移除 `ChatPanel.vue` 中未使用的 `UI_INPUT_PLACEHOLDER` 导入

## 0.31.0

### 添加
- **工具结果 Markdown 渲染**：WorkflowDetail 返回结果通过 `markdown-it` 渲染，支持标题、列表、代码块（含语言标签 + 复制按钮）、表格等完整 Markdown 语法
- **JSON-RPC / MCP 结构解析**：WorkflowDetail 识别 MCP content 数组、JSON-RPC result/error、`isError` 标志，提取文本内容并结构化展示
- **参数键值对展示**：tool_call 参数展示为 key-value 列表，长文本/JSON 值自动语法高亮（`highlight.js`）
- **全局代码块复制按钮**：所有 Markdown 代码块统一注入语言标签 + 复制按钮（`navigator.clipboard`），全局委托事件处理
- **`ChatMessage.is_error` 字段**：工具执行错误作为结构化布尔值持久化到 SQLite，刷新后 WorkflowLog 正确区分成功/失败

### 变更
- **错误信号结构化**：后端不再将 `[错误]` 文本混入原始数据。`ToolExecutor.execute()` / `MCPServerProcess.call_tool()` / `MCPHttpClient.call_tool()` 返回 `tuple[str, bool]`，SSE `tool_result` 事件新增 `is_error` 字段
- **系统提示词追加语义**：变更时在消息历史末尾追加新系统消息（而非替换开头旧消息），`chat.system_prompt` 追踪最近一次生效值以防重复追加
- **会话参数脱离草稿**：`SessionSettings` 不再属于 `DraftData`（草稿为内存态，刷新即丢）。会话参数走后端权威持久化——新建会话从 `session_settings.json` 初始化，刷新从 `ConversationDetail.settings` 恢复
- **`apply_settings` 全量同步**：移除 `None` 跳过逻辑。`null` 端到端语义统一——不设该参数，由模型/后端自定
- **`WorkflowEntry.isError` 字段**：前端 WorkflowLog 条目新增错误状态，失败结果图标与文字变红（`--error`），展示文本区分"执行完成"/"执行失败"
- **WorkflowDetail 原始数据还原**：`rawDataText` 直返后端原始字符串，不再二次格式化

### 修复
- **`_load_all` 未还原采样参数**：服务重启后从 SQLite 加载会话时 `Chat` 实例的 temperature/max_tokens 等全部为 None，现已调用 `chat.apply_settings(loaded_settings)`
- **`isError` 刷新丢失**：`loadHistory` 从持久化的 tool 消息读取 `is_error`，传入 `ToolCallRecord.isError` → `WorkflowEntry.isError`
- **Markdown 渲染被 `[错误]` 阻塞**：`[错误]` 方括号被 markdown-it 解析为快捷参考链接，吞掉同行后续 `###`/` ``` ` 等块级语法（已随错误信号结构化一同解决）
- **创建会话时空字符串系统提示词被吞**：`settings.system_prompt or SYSTEM_PROMPT` → `is not None` 判断

### 添加
- **HTTP MCP 传输支持**：新增 `MCPHttpClient` 类，通过 Streamable HTTP 与远程 MCP 服务器通信（如 GitHub Copilot MCP）。支持 SSE 响应解析、JSON-RPC 请求/通知、工具发现与调用。`MCPManager` 统一管理 stdio 与 HTTP 两种传输类型
- **GitHub MCP 服务器预设**：`mcp.json` 新增 GitHub Copilot MCP 配置模板（HTTP 类型 + `${GITHUB_MCP_PAT}` 密钥引用）

### 变更
- **浮窗 Escape 全局管理**：`windowZIndex.ts` 集中处理 Escape 按键，仅关闭最高层级可见浮窗。新增 `setVisible()` 跟踪窗口可见性，隐藏窗口不响应 Escape；移除各 FloatingWindow 实例的独立 keydown 监听
- **UI 文案统一**："会话默认设定" → "默认参数"，"会话设定" → "会话参数"
- **工具栏按钮顺序调整**：附件（📎）→ 设定（🎚️）→ 思考（💡）→ 发送（▶️）
- **工具组部分启用样式**：部分启用胶囊样式收敛为主题色圆点指示，文字与边框保持默认暗色
- **会话设定按钮行为**：点击仅显现 SessionSettingsPanel（不切换），与会话列表按钮行为一致
- **MCP 管理器重构**：`_add_server()` 拆分为 `_add_server`（stdio）+ `_add_http_server`（HTTP）+ `_register_server_tools`，消除重复的工具注册逻辑

## 0.29.0

### 添加
- **会话参数面板**：新增 `SessionSettingsPanel.vue` 浮窗，支持按会话独立配置系统提示词与 LLM 采样参数（温度、最大输出 Token、Top-P、Top-K、存在惩罚、频率惩罚、重复惩罚）。未设字段自动回退为后端会话默认设定
- **默认参数持久化**：`backend/data/session_settings.json` 持久化默认会话设定，SettingsPanel 新增"默认参数"标签页，修改后实时同步到 SessionSettingsPanel 的"默认"预设按钮
- **内置会话参数预设**：精确/日常/创作三组预设胶囊，一键快速切换典型参数组合
- **ConversationList 清空与清理**：头部 `actions` 插槽新增"清空"（删除全部会话）和"清理"（删除当前会话下方的所有会话）按钮，二次点击确认 + 3 秒自动重置

### 移除
- **seed 参数**：从前后端全部移除 `seed` 字段（`SessionSettings`、`ChatRequest`、`Chat.__init__`、`Agent.__init__`、`_build_payload`、前端 UI 与类型定义）

### 修复
- **默认预设不同步**：SettingsPanel 修改会话默认设定后 SessionSettingsPanel 的"默认"按钮未能反映最新值，现通过 `provide/inject` + `refreshDefaultSettings()` 实时同步
- **新会话初始化竞态**：`restoreDraft(null)` 同步执行时 `defaultSettings` 尚未从后端加载完毕，ChatInput 新增 watcher 在 `defaultSettings` 就绪后补发设定
- **新会话设定未应用**：`run()` 新建会话时 `_activate(sid)` 因 `SessionState.settings` 为 null 回退到默认设定，覆盖用户修改。现于 `onSessionCreated` 前将 `currentSettings` 存入 SessionState

## 0.28.1

### 移除
- **会话自动驱逐**：移除 LRU 驱逐（100 上限）与 TTL 过期（1 小时闲置），会话仅由用户手动删除
- **Agent 会话 TTL 清理**：移除 `_cleanup_stale_agent_sessions()` 及 `AGENT_SESSION_TTL` 常量

### 变更
- **会话生命周期简化**：`SessionStore` 不再自动删除任何会话，`create()` / `register()` / `list_all()` 移除驱逐检查

## 0.28.0

### 添加
- **MCP 服务器状态 API**：`GET /api/mcp/status` 端点，返回各服务器 running/stopped/error 状态 ID
- **ToolGroupPanel 工具组管理浮窗**：工具栏胶囊按钮旁新增 `+` 展开按钮，点击弹出浮窗管理组内单独工具开关
- **设置面板服务器监控仪表盘**：MCP 服务器状态列表、LLM 网关状态（中文文案 + 彩色图标）、并发限制、运行信息（uptime/Python/平台）
- **后端工具 UI 元数据**：`Tool` 基类新增 `icon`/`label`/`order` 类属性，后端成为工具元数据的唯一权威源

### 变更
- **工具元数据后端权威化**：前端删除 `tools/registry.ts` 及 `tools/builtin/` 目录，所有工具元数据（图标、标签、排序、描述）由 `GET /api/tools` 返回。新增 `composables/toolMetadata.ts` 统一查询，WorkflowLog 和 useAgent 均通过此模块获取工具信息
- **工具组统一为胶囊开关**：内置工具与 MCP 服务器在 ChatInput 工具栏中统一为胶囊按钮（`[◖ 组名 ◗]` + 展开按钮），不再区分独立工具按钮与 MCP 服务器按钮。后端 `GET /api/tools` 返回 `groups` 字段替代 `mcp_servers`
- **MCP diff-based 重载**：保存 MCP 配置时仅重启变更的服务器，未变更服务器保持连接不中断。`MCPServerProcess` 增加 `is_running` 属性
- **MCP 后台健康检查**：每 30s 检测进程存活，意外退出自动清理工具并记录 warning
- **状态 ID 架构三层分离**：后端常量（`HEALTH_HEALTHY` 等）→ 前端映射表（`HEALTH_STATUS_LABEL` / `MCP_STATUS_LABEL`）→ 模板展示（中文文案）。状态 ID 用于 `:class` 逻辑，映射常量用于展示文字，为未来 i18n 奠定基础
- **设置面板中文字体修复**：`.info-value` 移除等宽字体，新增 `.info-value.mono` 修饰符仅对技术值（地址、模型名、版本号、平台名）应用 monospace
- **MCP 启动超时策略**：lifespan 中 MCP 初始化超时后不再全量重试，依赖后台健康检查自动恢复
- **面板高度调整**：`.settings-layout` 从 340px 增加到 400px 以容纳新增状态卡片

### 移除
- **前端工具元数据硬编码**：删除 `tools/registry.ts`、`tools/builtin/calculator.ts`、`tools/builtin/open-url.ts`、`tools/builtin/web-search.ts`

## 0.27.0

### 添加
- **标准 MCP 协议支持**：JSON-RPC 2.0 over stdio 子进程传输，兼容 Claude Desktop 配置格式 `{"mcpServers": {...}}`。MCP 服务器作为子进程启动，通过 stdin/stdout 换行分隔 JSON 消息通信，自动完成 `initialize` 握手 → `tools/list` 发现 → 注册到 ToolExecutor。
- **MCP 服务器胶囊开关**：工具栏新增胶囊形 MCP 服务器开关（`[◖ server_name ◗]`），点击一键启用/关闭整组工具。状态指示：蓝 accent 全开 / 黄 warning 部分开 / 灰 全关。
- **Tool 抽象基类**：`llm/tools/base.py` — `Tool` 基类（`definition` + `execute()`），新增内置工具只需创建子类并放入 `llm/tools/` 目录。

### 变更
- **大重构工具架构**：后端 `llm/tools/` 包（每工具独立模块：`web_search.py` / `calculator.py` / `open_url.py`），前端 `tools/builtin/` 目录（每工具独立元数据），删除旧的单体 `tools.py` 和集中式 `registry.ts` 定义。
- **MCP 配置独立**：从 `llm_config.json` 剥离，存储为 `data/mcp.json`（标准 `{"mcpServers": {"name": {"command": "...", "args": [...]}}}` 格式），支持 `${VAR}` 密钥替换。前端设置面板 MCP 标签页改为 JSON 源码编辑器 + 实时语法校验。
- **默认不启用任何工具**：`DEFAULT_ENABLED_TOOLS` 改为空数组。内置 + MCP 工具均需用户在工具栏手动开启。MCP 工具启动时自动发现但默认不启用。
- **MCP 工具自动发现**：`GET /api/tools` 响应新增 `mcp_servers` 字段（服务器→工具名列表映射），前端启动时拉取 + 延迟重试（2s/5s/10s），SettingsPanel 保存 MCP 配置后触发刷新。

### 移除
- **删除旧 MCP 服务器**：`mcp_servers/github_server.py`（6 个工具）、`agnes_server.py`（3 个工具）—— 旧的非标准 HTTP 协议实现已全部移除。

### 修复
- **Windows 全平台兼容**：MCP 子进程改用 `subprocess.Popen` + 线程 I/O 桥接（`call_soon_threadsafe`），兼容 `SelectorEventLoop`（uvicorn `--reload` 在 Windows 上创建的默认事件循环）。`npx.cmd` 路径通过 `shutil.which()` 解析。
- MCP 初始化超时提升至 60s（首次 npx 下载包）。错误信息附上 stderr 尾部 10 行辅助诊断。

## 0.26.1

### 变更
- **配置版本控制**：`llm_config.json` 纳入 Git 版本控制（auth_token 已使用 `${LLM_TOKEN}` 占位符），`.gitignore` 仅屏蔽 `secrets.json` 密钥文件。

## 0.26.0

### 添加
- **密钥/变量管理器**：设置面板新增"密钥"标签页，支持定义键值对变量。LLM auth_token、MCP URL 等配置字段中使用 `${变量名}` 引用密钥，实际请求时自动替换为真实值。密钥存储于独立 `secrets.json`，GET API 仅返回 key 名称列表不泄露值。
- **MCP 服务器密钥库接入**：`github_server.py` / `agnes_server.py` 通过 `get_secret()` 优先从密钥库读取 API Key，环境变量作为回退方案。

### 变更
- **auth_token 配置字段**：LLM 标签页的 auth_token 改为普通文本框（原 password 隐藏），支持 `${变量名}` 脱密管理。后台 API 返回 `auth_token` 原始值替换 `auth_configured` 布尔值。

### 修复
- **ChatInput 高度不恢复**：发送大段文字后 textarea 高度通过 `nextTick` 自动重置。
- **MCP 连接阻塞**：FastAPI lifespan 启动和 MCP 配置保存时的 `connect_mcp_servers()` 改为 `asyncio.create_task` 后台执行，避免 MCP 服务器不可达时阻塞数十秒。

## 0.25.2

### 修复
- **ChatInput textarea 高度重置**：发送消息后 textarea 高度未重置导致输入框异常增高。发送后通过 `nextTick` 将 textarea 高度重置为 `auto`。

## 0.25.1

### 变更
- **版本号动态读取**：`IRISFLOW_USER_AGENT` 不再硬编码，改为 `get_user_agent()` 从 `pyproject.toml` 动态生成。
- **后端硬编码字符串常量化**：`agent.py` / `client.py` 中的角色字符串（`"user"` / `"assistant"` / `"tool"`）替换为 `ROLE_*` 常量；`mcp.py` 的 HTTP 错误截断长度改用 `ERROR_RESULT_TRUNCATE`。
- **后端导入清理**：`router.py` 移除 finally 块中的冗余 `import asyncio as _asyncio`，将 `llm.client.chat`、`ToolDefinition` 等内联导入提升到顶层。
- **CSS 变量化**：新增 `--white`、`--status-generating`、`--status-pending`、`--status-unknown` 四个 CSS 变量，替换跨 7 个组件的硬编码颜色值（`#fff` / `#0d1117` / 状态灯颜色）。
- **前端代码质量**：`App.vue` 修复导入顺序；`ChatPanel.vue` 移除 `_DEFY_LIMIT` 无意义间接引用；`constants.ts` 中 `DEFAULT_ENABLED_TOOLS` 增加 MCP 工具注释。
- **工具函数提取**：新增 `stripCodeFence()` 到 `utils/index.ts`，消除 `MediaPreview.vue` 和下载逻辑中重复的正则匹配。
- **常量使用规范化**：`ConversationList.vue` 的 `line.slice(6)` 改为使用 `SSE_DATA_PREFIX_LEN`。

### 修复
- **README 过时引用**：curl 示例版本号 `0.24.0` → `0.25.0`；架构图中 `Sidebar` → `ConversationList`。

## 0.25.0

### 添加
- **MediaPreview 统一媒体预览** (`floating/MediaPreview.vue`)：合并 ImagePreview + FilePreview，支持图片/视频/网页/文件四种类型。图片/视频/网页通过 iframe 渲染（天然沙箱隔离），文件通过 markdown-it 直接渲染。FloatingWindow `#actions` 插槽支持下载和在新标签页打开。
- **链接卡片系统** (`utils/markdown.ts`)：markdown-it 插件自动检测图片/视频/网页链接，渲染为富预览卡片（缩略图、标题、域名徽章），替换纯文本链接。
- **后端 `download_suffix` 字段**：文件上传响应新增 `download_suffix`（文本文件返回原始扩展名，文档 MarkItDown 转换后返回 `.md`），前端据此使用正确的文件扩展名下载。

### 变更
- **浮窗架构重构**：`Sidebar.vue` → `floating/ConversationList.vue`、`SettingsModal.vue` → `floating/SettingsPanel.vue`、`ToolSidebar.vue` → `floating/WorkflowDetail.vue`。所有浮窗子窗体集中到 `components/floating/` 目录，统一基于 FloatingWindow 框架。
- **FloatingWindow 增强**：新增 `#actions` 插槽，头部栏可放置操作按钮（下载、外部打开等）。
- **全局 `.btn-icon` 样式提取**：各组件中重复的图标按钮样式提取到 `style.css` 全局类。
- **类型重命名**：`SidebarPreview` → `PreviewPayload`，新增 `video` / `webpage` kind，`FileAttachment` 新增 `download_suffix` 字段。
- **常量注释同步**：组件引用注释更新为新的浮窗组件名称。

### 修复
- **Markdown 文件预览渲染**：后端对 `.md` 文件包裹 ````markdown` 围栏，前端预览时自动脱壳渲染为格式化 Markdown，而非显示为代码块。
- **文件下载扩展名**：下载文件时剥离后端 ````lang` 围栏并使用 `download_suffix` 确保正确的文件扩展名。

## 0.24.0

### 添加
- **GitHub MCP 服务器** (`backend/mcp_servers/github_server.py`)：6 个 GitHub API 工具（仓库搜索、仓库详情、文件读取、代码搜索、Issue 列表、PR 列表），支持 `GITHUB_TOKEN` + `GITHUB_PROXY` 环境变量认证与代理。
- **Agnes AI MCP 服务器** (`backend/mcp_servers/agnes_server.py`)：3 个 AI 生成工具（文生图、文生视频、视频进度轮询），API Key 自动清洗（移除不可见字符）。
- **`GET /api/tools` 端点**：返回所有已注册工具名称列表，前端据此动态发现 MCP 工具，无需硬编码。
	- **图片预览浮窗**：点击消息中的图片调起 ToolSidebar 浮窗预览，统一图片/文件预览入口。
- **工具分组工具栏**：ChatInput 工具按钮支持分组总开关（一键全开/关）+ 展开单独开关，总开关三态显示（全选/半选/全关）。
- **工具创建工作流 Skill** (`.claude/skills/tool-creation/SKILL.md`)：外部 API 转 MCP 工具的完整开发 → 测试 → 注册工作流，含模板与参考实现。

### 变更
- **MCP 工具超时延长**：`MCP_CALL_TOOL_TIMEOUT` 8s → 120s，`TOOL_EXECUTION_TIMEOUT` 30s → 180s，适配图片/视频生成等长时任务。
- **CORS 全面开放**：`allow_origins` 改为 `["*"]`，支持局域网访问；Vite 与 MCP 服务器监听 `0.0.0.0`。
- **Agnes 图片生成超时**：HTTP 请求超时 15s → 120s；移除代理配置（代理长连接会断开）。

### 修复
- **MCP 工具 definition 字段名**：`parameters` → `inputSchema`，符合 IrisFlow MCP 客户端读取约定，解决工具参数 Schema 为空的问题。
- **API Key 非法 HTTP Header**：Agnes MCP 服务器自动清洗 Key 中的零宽空格、换行、控制字符等不可见字符。
- **MCP 工具 LLM 不可见**：前端启动时通过 `GET /api/tools` 动态发现工具并自动加入启用列表。

## 0.23.1

### 变更
- **文档精简**：删除 README、CLAUDE.md 中所有脆弱的硬编码数字（端点数量、组件数量、API 函数数量等），改为无数字描述。
- **markdown-it 实例共享**：MessageBubble 与 ToolSidebar 的重复 markdown-it + texmath + highlight.js 初始化代码提取到 `utils/markdown.ts` 模块级单例。
- **CSS 变量化**：新增 `--accent-bg`、`--accent-bg-subtle`、`--error-bg`、`--code-bg` 四个 CSS 变量，替换跨组件的重复硬编码颜色值。
- **IRISFLOW_USER_AGENT 版本号**：从 `0.10.0` 更新为 `0.23.0`（此前遗漏）。

### 移除
- **`UI_UNCONFIGURED` 常量**：已无引用，从 `backend/llm/constants.py` 删除。
- **`backend/README.md` 过时指令**：删除已废弃的 `cp .env.example .env` 步骤。
- **未使用 CSS**：Sidebar.vue 的 `.conv-meta` 类、ChatInput.vue 的重复注释块。

### 修复
- **README 项目结构**：补充缺失的 `FloatingWindow.vue` 条目；修复过时的 MCP `.env` 描述。

## 0.23.0

### 添加
- **可配置后端地址**：前端新增服务器地址输入框（设置面板 + 断连遮罩），`localStorage` 持久化。所有 API 调用改用绝对 URL，不再依赖 Vite 代理。
- **MCP 配置端点**：新增 `GET/PUT /api/mcp/config`，支持运行时增删 MCP 服务器并自动重连。
- **设置面板标签页重构**：四标签页布局（服务器 / LLM / MCP / 关于），关于页展示后端版本、Python、平台、架构、FastAPI 版本信息。
- **MCP 管理界面**：SettingsModal 新增 MCP 标签页，支持可视化添加/删除 MCP 服务器。
- **FloatingWindow 视口约束**：浏览器窗口 resize 后自动将越界浮窗拉回可见区域（至少露出 60px）；隐藏的浮窗在重新显示时也会执行约束。
- **前端 API 扩展**：新增 `getAppInfo()`、`getVersionInfo()`、`getMCPConfig()`、`updateMCPConfig()`、`getServerUrl()`、`setServerUrl()`。
- **断连遮罩地址修改**：断连占屏新增服务器地址输入框，支持断连时直接修改后端地址。

### 变更
- **配置持久化方案重构**：后端移除 `.env` / `python-dotenv` 依赖，全部配置（LLM + MCP）通过前端设置面板保存到 `data/llm_config.json`。删除 `.env.example` 文件。
- **MCP 配置传递**：`connect_mcp_servers()` 改为接收解析后的列表而非 JSON 字符串，配置统一从 `config.py` 的 `get_mcp_servers()` 获取。
- **最大并发数上限**：`MAX_CONCURRENT_UPPER` 从 10 提高到 20。
- **设置按钮位置**：从左下角移至右上角。
- **右键菜单位置**：从会话项右下方移至左侧，避免被 FloatingWindow 裁剪。
- **消息气泡布局**：图片和文件附件改为右对齐（`justify-content: flex-end`），附件展示顺序调整为图片 → 文件 → 文字。
- **文件上传预览分组**：图片附件与文档附件分为两行独立展示。
- **ToolSidebar 文案**："文件详情" → "文件预览"。
- **`/version` 端点**：新增 `description` 字段。

### 移除
- **`.env.example`**：配置文件不再需要，全部配置通过前端 UI 管理。
- **`python-dotenv` 依赖**：后端不再读取 `.env` 文件。
- **`UI_UNCONFIGURED` 常量**：LLM 配置端点不再返回占位字符串。

## 0.22.0

### 添加
- **FloatingWindow.vue**：通用可拖拽浮窗组件。支持 Teleport 渲染、标题栏拖动、置顶、Escape/中键关闭、8 个初始位置（center/top/bottom/left/right/四角）。统一头部操作按钮（置顶·主题色 / 关闭·红色系），无遮罩设计。
- **windowZIndex.ts**：共享层级管理模块（ES 模块级单例）。四档活跃层级（204→201）+ 不活跃层级（200），tick-based 排序，`focusWindow` 聚焦提前，支持置顶穿透（PINNED_Z=9999）。

### 变更
- **统一浮窗框架**：Sidebar、SettingsModal、ToolSidebar 全部使用 FloatingWindow 包裹，移除各组件的独立遮罩与 positioning CSS。
- **App.vue 浮窗管理体系**：持久浮窗（Sidebar/SettingsModal，v-model 驱动，关闭仅隐藏不销毁）+ 动态浮窗（ToolSidebar，v-for 渲染，点击 WorkflowLog 条目/文件/图片即创建，关闭即销毁）。
- **会话列表/设置按钮语义变更**：按钮改为显现已有窗口（不可重复创建），而非 v-if 条件渲染。按钮始终可见，不再因窗口打开而消失。
- **SETTINGS 品牌信息内移**：版本号与 IrisFlow 名称从 Sidebar 移入 SettingsModal。

### 移除
- **App.vue 遮罩机制**：移除 `.panel-backdrop`、`.sidebar-backdrop` 及对应 `<Transition>` 与 CSS。浮窗通过 z-index 层级自然叠加，无遮罩遮挡。

## 0.21.2

### 修复
- **工具可靠性加固**：`web_search` / `open_url` / MCP 工具调用增加重试机制（瞬态故障自动重试 1-2 次），httpx 超时精确控制（网络请求 ≤10s），异常按类型分类（超时 / 连接拒绝 / HTTP 错误），`ToolExecutor.execute()` 增加 `asyncio.wait_for` 30s 防 hung 护盾。
- **DuckDuckGo 搜索容错**：Instant Answer API 超时后自动回退 HTML 搜索，整体搜索失败重试一次。

## 0.21.1

### 变更
- **前后端硬编码常量化**：将散落在各模块中的魔法数字（超时时长、轮询间隔、截断长度）、硬编码字符串（API 路径、状态值、UI 文案）集中提取到 `constants.py` 和 `constants.ts`。后端新增约 40 个常量覆盖 9 个分类，前端新增约 60 个常量。19 个文件完成符号替换。
- **UI 文案 i18n 预备**：所有面向用户的界面文字统一以 `UI_*` 前缀命名并集中于 constants 文件「UI 文案」分组下，未来引入国际化框架时可直接批量替换为 `$t()` 调用。

## 0.21.0

### 变更
- **配置统一来源**：`AppConfig.version` 和 `description` 从 `pyproject.toml` 自动读取，版本更新只需改一处。
- **Chat 类精简为纯数据容器**：移除 `send()`、`send_stream()` 等全部方法，仅保留 `__init__()` 和 `messages` 列表。
- **Agent 类精简**：移除 `run()`、`run_auto()`、`run_stream()`，仅保留 `__init__()` + `continue_with_results()`。
- **待调度队列状态灯颜色调整**：`pending` 状态点从亮红色（`var(--error)`）改为朱红色（`#e45a3c`）。

### 移除
- **`lifecycle.py`**：`AppLifecycle` 状态机全模块删除。`accepts_requests` 无任何消费方，`begin_shutdown()` 退化为空操作。
- **12 个死端点与方法**：`simple_chat()`、`simple_chat_stream()`、`send_message()`、`agent_chat()`、`upload_accept()`、`_handle_llm_errors()`（router）；`send()`（sessions）；`chat_stream()`（client）；`build_accept_string()`（uploads）；`register()` source 参数（tools/mcp）。
- **14 个死类型与常量**：`MessageStatus`、`AgentRequest`、`AgentEvent`、`ChatMessageWithUsage`、`ToolDefinition.source`（models）；`TOOL_SOURCE_*`、`CONFIG_MAX_CONCURRENT`（constants）。
- **前端死代码**：`useChat.ts` composable（全文件 134 行）；`sendChat()`、`sendChatStream()`、`agentChat()`、`sendMessage()`、`getUploadAccept()`、`requestStream()`（client.ts）；`ChatMessageRequest`、`AgentRequest`、`ConversationMessageRequest`、`ChatResponse`、`StreamEvent`（types/api.ts）；`MSG_COMPLETED`、`HTTP_429`（constants.ts）。
- **localStorage 描述清除**：README 技术栈表和技术选型表中不再提及 localStorage（前端已无任何 localStorage 使用）。

## 0.20.0

### 变更
- **会话处理逻辑统一**：所有会话一律入队，由统一的出队处理器在检查 LLM 健康与并发容量后调度。消除「有空位→立即启动 / 满→入队」双路径。
- **取消红灯（UNREACHABLE）状态**：LLM 错误不再设置特殊会话状态，统一为 `COMPLETED`。消息层面标记 `aborted` 并在内容中展示错误信息。
- **新增 LLM ping**：`llm_ping()` 轻量连通性检查（GET /v1/models），用于出队健康门控。LLM 不可达时不出队，启动后台轮询（5s 间隔）；恢复后自动出队。
- **`_GenerationState` 移除 `errored` 字段**：不再需要区分 LLM 错误以决定会话状态。
- **前端移除 unreachable 状态灯**：四色状态灯（绿 idle / 黄 generating / 蓝 pending / 灰 unknown），删除红色。

## 0.19.4

### 变更
- **WorkflowLog 思考/快速模式判定重构**：移除基于 `entries` 扫描 `type === "think"` 的启发式判定（`hasThink`），改用后端权威的 `thinking` 字段。新增 `isWorkDone` 计算属性（`hasContent || streamDone`）统一驱动展开/折叠与标签文案。`UIMessage` 新增 `thinking?: boolean` 字段，`useAgent.ts` 在消息创建与历史加载时写入。终止路径 `abort()` 中 `streamDone` 改为内容条件赋值（保留中断思考的展开展示）。

## 0.19.3

### 修复
- **SSE 流上屏概率中断**：`AbortSignal.timeout(30s)` 挂到 SSE 流式 `fetch()` 上后持续作用于整个流生命周期（连接 + body 读取），长思考/工具调用超过 30s 即 abort reader 导致流无声中断。改为 `Promise.race` 仅作用于连接建立阶段，不影响 body reader；流读取超时仍由 `readWithTimeout(120s)` 控制。同时清理 `useAgent.ts` 中不再使用的 `_combineSignals` 死代码。

## 0.19.2

### 修复
- **刷新后双重 WorkflowLog**：自动工具调用循环产生多条 assistant 消息（首条含 tool_calls，后续含正文），后端仅将最后一条标记为终态，导致页面刷新后非主 assistant 残留 `generating` 状态，前端渲染出两个 WorkflowLog（一个"处理中"、一个"已思考"）。后端 `_resolve_assistant_statuses()` 替代 `_set_last_assistant_status()`，遍历所有 assistant 并标记终态；前端 `loadHistory()` 新增 `_auxiliary` Set 防御层，跳过已合并的非主 assistant。
- **刷新后终止会话显示"已思考"**：`loadHistory` 映射后端消息时遗漏 `message_status` 和 `thinking` 字段，导致 MSG_ABORTED 未被识别。已在 `ChatPanel.vue` 的消息映射中补全。

## 0.19.1

### 添加
- **启动门控**：`App.vue` 启动时先 ping 后端（`GET /api/ping`，5s 超时），通过后才挂载 Sidebar 等子组件。未通过 → 显示"无法连接后端"+ 重试按钮。
- **连接断线占屏遮罩**：运行时每 3s 心跳，连续 3 次失败触发全屏 overlay（仅"刷新页面"可消除）。任意组件 fetch 网络失败（TypeError / TimeoutError）→ 统一触发占屏，通过 `provide/inject` 传递 `onConnectionLost` 回调：App.vue → 所有子组件 + useAgent。
- **HTTP 状态码附加**：`api/client.ts` 的 `request()` 和 `requestStream()` 在抛出 Error 时附加 `status` 字段，使调用方可区分 404 / 400 / 429 / 500 / 502。
- **404 自动恢复**：`ChatPanel` 加载会话 404 → `router.push("/")` 跳转新建对话；`useAgent` 的 `run()` / `resumeStream()` / `continueWithResults()` 收到 404 → 触发 `onSessionNotFound` 回调。
- **SSE 覆盖式订阅**：`/api/sessions/status-stream` 新连接替换同一会话的旧订阅（发送 `replaced` 哨兵唤醒旧 SSE 连接退出），防止旧连接残留。
- **ConversationListItem 模型**：会话列表不含 `status` 字段，状态仅通过 SSE 订阅获取。`ConversationInfo` 保留含状态版本供内部使用。

### 变更
- **错误处理分层**：三层异常分类 — `AbortError`（用户取消 → 标记 aborted）、`TypeError` / `TimeoutError`（网络断连 → 占屏遮罩）、HTTP 错误（后端可达 → 静默忽略，404 跳转首页）。
- **移除组件级错误状态**：`ChatInput` 错误横幅、`ChatPanel.loadError`、`SettingsModal.saveError`、`Sidebar.loadFailed`、`useChat` error 赋值全部移除，统一由连接断线占屏接管。
- **Sidebar 状态初始化**：会话列表全部初始化为 `unknown`（灰色），等待 SSE 订阅点亮。
- **SSE 连接版本号控制**：递增 `_statusConnectionId`，旧连接的 `pump()` 回调自动忽略重连逻辑，避免被 abort 的旧连接错误触发新订阅。

### 修复
- **404 错误处理缺失**：页面加载、发送消息、重连 SSE 三条路径的 404 均正确处理——不再触发占屏，而是跳转新建对话页面。
- **Stale SSE 连接竞态**：覆盖式订阅修复多标签页/页面刷新时旧 SSE 连接残留导致的状态重复推送。
- **上传失败错误处理**：HTTP 错误静默忽略（后端可达），仅网络层失败触发占屏。

## 0.19.0

### 添加
- **fetch 超时机制**：所有 HTTP 请求和 SSE 流读取增加超时控制。连接超时 30s，SSE 流读取超时 120s（token 间隔），状态 SSE 订阅超时 300s。支持 `AbortSignal.any()` 组合用户信号与超时信号，不支持的浏览器自动降级为手动转发。
- **错误信息持久化**：LLM 调用异常时，后端将错误信息写入最后一条 assistant 消息，确保页面刷新后错误可恢复。
- **ChatInput 错误横幅**：输入框上方新增橙色错误横幅，显示发送/加载失败信息，8 秒自动消失，可手动关闭。
- **SettingsModal 保存反馈**：保存失败时显示红色错误提示并保留在弹窗内，保存中禁用按钮并显示"保存中…"。
- **Sidebar 连接状态**：后端不可达时侧边栏显示"无法连接后端"红色空状态提示。

### 变更
- **会话状态语义重构**：`aborted` 状态移除，拆分为两种情况——用户主动终止 → 会话保持 `completed`（正常完成，绿色状态灯）；LLM 内部错误 → 新状态 `unreachable`（红色状态灯，需等待服务恢复）。前后端常量、枚举、类型定义全部同步更新。`SessionStatus` 枚举值：`generating` / `completed` / `pending` / `unreachable`。
- **优雅关闭顺序优化**：`shutdown_generations()` 增加 `_shutting_down` 全局标志，先置标志再清队列，阻止 finally 块中的 `_dequeue_and_start` 启动新任务；延迟清理任务（`_cleanup_generation_state` 的 300s sleep）统一追踪并在关闭时取消；SSE 订阅者推送提前到 Task 取消之前，尽早解阻塞 `queue.get()`。
- **启动清理语义同步**：`lifespan` 启动和 `SessionStore._load_all` 中将残留 generating/pending 会话重置为 `completed`（原为 `aborted`），与优雅关闭一致。
- **前端错误处理分层**：`useAgent.run()` 和 `resumeStream()` 区分三种异常——`AbortError`（用户取消，保持 `completed`）、`TimeoutError`（超时，状态设为 `unknown`）、网络错误（状态设为 `unknown`）。`UNREACHABLE` 由后端 `SSE_ERROR` 事件权威设置，前端绝不自行推断。
- **WorkflowLog 状态指示**：`STATUS_UNREACHABLE` → 红色禁止图标"已终止"，`completed` → "已思考/已完成"，与五色状态灯语义一致。

### 修复
- **SSE 连接无限挂起**：流读取无超时导致网络异常或后端无响应时连接永久挂起，现通过 `readWithTimeout` 保护所有 SSE 读取点。
- **abort() 覆盖 LLM 错误状态**：用户手动终止时 `abort()` 无条件覆盖会话状态，现改为检查是否已有 `UNREACHABLE`（由 `SSE_ERROR` 先到达），避免将错误状态误标为正常完成。
- **优雅关闭竞态**：原 `shutdown_generations` 先取消 task 再清队列，finally 块中 `_dequeue_and_start` 在 `_shutting_down` 标志之前执行，可能从队列取出新会话启动生成。现已通过先置标志再清队列的顺序消除竞态窗口。
- **设置保存失败静默**：SettingsModal 保存失败时无任何反馈（静默吞错），现已显示红色错误提示并保留在弹窗内，用户可修正后重试。

## 0.18.0

### 添加
- **文件/图片侧边栏预览**：点击消息中的图片或文件卡片，在 ToolSidebar 中展示完整预览。新增 `SidebarPreview` 可辨识联合类型（`{ kind: "image" }` | `{ kind: "file" }`），事件通过 `ChatInput`/`MessageBubble` → `ChatPanel` → `App` → `ToolSidebar` 链式传递。
- **文件内容 Markdown 渲染**：ToolSidebar 集成 markdown-it + markdown-it-texmath（KaTeX）+ highlight.js，文件内容支持富文本渲染（代码高亮、公式、表格等）。
- **原始数据可查看**：图片和文件预览中新增可折叠"原始数据"区域（默认展开），图片展示 base64 data URL，文件展示原始 `text_content`。

### 变更
- **文件预览卡片风格统一**：`MessageBubble` 和 `ChatInput` 使用一致的垂直卡片布局（图标 + 文件名 + 文本预览），替代旧的水平 chip 风格。
- **共享工具函数提取**：`fileIcon()` 和 `filePreview()` 从 `ChatInput`/`MessageBubble` 提取至 `utils/index.ts`，消除重复。
- **全界面 emoji 替换**：所有 UI emoji 替换为 Font Awesome 矢量图标（`<i class="fa-solid fa-...">`）。
- **ImageViewer 精简**：移除内置 Lightbox（Teleport + 键盘处理），改为纯缩略图组件。点击事件冒泡至父组件统一走侧边栏预览。
- **图片侧边栏全宽显示**：ToolSidebar 中图片 `width: 100%`，无包裹背景。
- **SettingsModal 图标化**：标题和关闭按钮改用 FA 图标。
- **WorkflowLog 图标化**：折叠标题和状态指示改用 FA 图标。

### 移除
- **ToolBar.vue**：死代码，无任何组件引用。
- **ToolCallCard.vue**：死代码，无任何组件引用。

## 0.17.0

### 添加
- **会话状态实时推送**：新增 `GET /api/sessions/status-stream` SSE 端点，客户端订阅已访问会话的状态变更，替代 3 秒轮询。前端 `Sidebar.vue` 通过 SSE 实时接收状态更新，支持指数退避重连。
- **待调度队列系统**：新增 `SessionStatus.PENDING` 状态。并发满时不再返回 429，而是将请求加入 FIFO 队列（蓝色状态灯），SSE 连接保持打开。当前一个生成完成后自动取出队首并启动生成。
- **五色状态灯**：侧边栏会话状态灯统一为五色——绿色（可发送）、黄色脉冲（生成中）、蓝色（排队待调度）、红色（连接失败）、灰色（状态未知）。所有会话（包括 idle/completed）均显示状态灯。
- **启动时清理**：服务启动时自动将残留的 PENDING/GENERATING 会话重置为 ABORTED，防止上次异常中断导致的卡死状态。

### 变更
- `SessionStatus.BLOCKED` → `SessionStatus.PENDING`（前后端常量同步更新）
- 前端 3 秒轮询机制移除，改为 SSE 状态订阅
- `_generate()` 从 `send_message_stream` 闭包提取为模块级独立函数，供队列系统复用
- 所有 `session_store.update_status()` 调用统一为 `_update_and_broadcast()`，确保状态变更实时推送

### 移除
- `SessionStatus.BLOCKED` 状态枚举值及前后端常量（从未被设置过，现由 PENDING 替代）
- 前端 HTTP 429 错误处理（后端不再返回 429）

### 修复
- **排队中终止状态错误**：`abort()` 未清除 `queued` 标记，导致 WorkflowLog 终止后排队的会话仍显示"队列中"（旋转图标）而非"已终止"（禁止图标）。
- **排队中会话 SSE 挂起**：后端 `abort_generation` 终止 pending 会话时未唤醒阻塞在 `condition.wait()` 的 `_event_stream`，导致 SSE 连接挂起未关闭。
- **刷新后 pending 会话"队列中"指示消失**：`loadHistory` 未处理 `STATUS_PENDING` → 末条 assistant 设置 `queued: true`；`ChatPanel` 未在 `"pending"` 时触发 `resumeStream`；`resumeStream` 覆盖 `STATUS_GENERATING` 并缺失 `SSE_STATUS` 事件处理。
- **上传图片双重渲染**：`run()` 将图片同时放入 `files` 和 `images`，导致 MessageBubble 同时显示文件卡片与图片预览。修复为 `files` 仅包含文本文档，图片单独走 `images`。

## 0.16.0

### 添加
- **完整草稿持久化**：会话输入区草稿现在保存全部状态——文字、上传文件（含图片预览与文档文本）、思考模式开关、工具选择。草稿通过 `localStorage`（key: `irisflow-drafts`）持久化，页面刷新后自动恢复。`beforeunload` 事件确保关闭前写入。
- `ChatInput.vue` 新增 `DraftData` 接口与 `loadAllDrafts` / `saveAllDrafts` / `saveDraft` / `restoreDraft` 辅助函数。
- `ChatPanel.vue` 新增 `saveTools` / `loadTools` 辅助函数，工具开关按会话持久化。

### 修复
- TypeScript 流分析误报：`s.status !== STATUS_ABORTED` 比较强制 cast 为 `string`，消除 `vue-tsc --noEmit` 类型错误。

## 0.15.1

### 修复
- **页面刷新后终止状态丢失**：`loadHistory()` 在 `status === "aborted"` 时硬编码 `streamDone: true`，导致无内容的中途终止消息错误显示为"已思考"并自动折叠。现与 `abort()` / `run()` catch 路径一致：有内容才设 `streamDone = true`，无内容保持展开让用户看到思考过程。

## 0.15.0

### 添加
- **生成流重连**：新增 `GET /api/conversations/{session_id}/stream` 端点。后台生成 Task 独立于 HTTP 请求生命周期，`_GenerationState` 事件注册表集中管理 SSE 事件流。页面刷新后可订阅续传 SSE 流，恢复实时上屏，无需等待生成结束。
- **生成终止（后端取消）**：新增 `POST /api/conversations/{session_id}/abort` 端点。后台 Task 引用保存至 `_GenerationState.task`，`task.cancel()` 立即取消 asyncio Task——httpx HTTP 连接关闭、LLM 流中断。
- **`aborted` 会话状态**：新增 `SessionStatus.ABORTED`（前后端常量同步），用户主动终止后保留已生成内容。侧边栏实时感知 aborted 状态（蓝灯）。
- **Vue Router History 模式**：新增 `frontend/src/router.ts`，`/`（新对话）和 `/chat/:sessionId`（会话）两条路由。组件 prop drilling 替换为 `useRoute()` / `useRouter()`，浏览器前进/后退、深层链接、SPA 回退全部支持。
- **`utils/index.ts`**：新工具模块，从 `App.vue` 提取 `parseFileBlocks` 为独立函数。
- **`asyncio.shield()` 保护**：流式端点 `finally` 块持久化操作（`register` + `update_status`）使用 `asyncio.shield()` 包裹，取消信号不中断状态落盘。

### 变更
- **`App.vue` 精简为布局壳**：删除所有会话管理逻辑（`activeSessionId`、`handleSessionCreated`、`handleSelectConversation` 等），跨组件通信改用 `provide/inject`（`remove-session-cache`、`refresh-sidebar`）。
- **`Sidebar.vue`**：删除 `activeSessionId` prop 和 `selectConversation`/`newChat`/`deletedActive` emit，改用 `useRoute()` + `useRouter()`。删除活跃会话时自动跳转至 `/`。
- **`ChatPanel.vue`**：删除 `activeSessionId` prop 和 `sessionCreated`/`titleGenerated`/`sidebarRefresh` emit，新增 `useRoute()`、`useRouter()`、`inject('refresh-sidebar')`，会话加载逻辑从 `App.vue` 移入。
- **`ChatInput.vue`**：删除 `sessionId` prop，改用 `useRoute()` 获取当前会话 ID。
- **`vite.config.ts`**：显式设置 `appType: 'spa'`，确保 history 模式正确回退到 `index.html`。

### 修复
- **前端终止无效**：之前 `abort()` 仅断开前端 SSE 连接（`AbortController.abort()`），后端 LLM 调用继续运行。现在同时调用 `abortGeneration(sid)` → `POST /api/conversations/{sid}/abort` → `task.cancel()` 取消 asyncio Task，httpx 连接立即关闭。
- **页面刷新后实时上屏不恢复**：`loadHistory()` 增加 Vue 响应式代理 rebind（`s.messages = messages.value`），确保 `resumeStream` 通过 Proxy 修改属性触发 UI 更新。
- **`resumeStream` 无法被终止**：`subscribeGenerationStream()` 新增 `AbortSignal` 参数，fetch 可被 `abortController.abort()` 取消。
- **`simple_chat_stream` 终止后状态未落盘**：`finally` 块增加 `asyncio.shield()` 保护，确保客户端断开后状态正确更新。
- **SQLite 持久化失败静默吞错**：`SessionStore._persist_to_db()` 异常增加 warning 日志。
- **`WorkflowLog` aborted 状态**：新增「已终止」标题文案，与 completed 的「已思考/已完成」区分。

## 0.14.0

### 添加
- **会话状态机**：generating / completed / blocked 三态贯穿前后端，侧边栏实时显示状态指示灯。
- **多会话并行隔离**：每个会话独立 Agent 状态与消息数组，切换会话时流式保持不中断，返回后自动恢复。
- **并发限制**：`max_concurrent` 配置（默认 1），超出返回 429，前端红色 blocked 指示灯 + Settings 面板可调。
- **常量模块**：新增 `backend/llm/constants.py` 和 `frontend/src/constants.ts`，集中管理全模块共享的字符串常量、枚举值、配置键。

### 变更
- **状态灯语义分离**：红色 = blocked（并发满），蓝色 = aborted（终止），消除歧义。
- **LLM 配置端点扩展**：`PUT /api/llm/config` 支持 `max_concurrent` 字段运行时更新。
- **移除 ToolEditor**：删除 `ToolEditor.vue` 自定义工具编辑器，工具管理简化为内置工具开关。

### 修复
- **响应式代理穿透**：`SessionStore.messages` rebind 到 Vue 响应式代理，修复流式内容上屏中断。
- **上屏流路由**：流式内容写入正确的会话消息数组，侧边栏列表同步刷新。
- **新建会话拦截**：修复空 session_id 导致新会话首条消息被静默丢弃。
- **shallowRef → ref**：修复流式消息丢失与新会话迁移后界面异常。
- **会话创建延迟**：新会话首条消息发送后才创建，避免空壳会话残留。
- **`register()` 状态保护**：保留已有会话的 status/title，避免 GENERATING 被覆盖为 COMPLETED。
- **自定义工具等待态**：等待手动执行时保留 GENERATING 状态，直到工具结果回传。
- **Agent 会话 ID**：使用 conversation 的 session_id 而非随机 UUID，确保正确关联。
- **`_cleanup_stale_agent_sessions` 误删**：agent session 与 conversation 生命周期解耦。
- **会话排序**：`list_all` 和 `_load_all` 统一按 `last_access DESC` 排序。
- **切换会话污染**：`useAgent.finally` 块不再将后台会话的消息/状态覆盖到前台活跃会话。
- **`_deactivate` 空壳**：使用 `get()` 替代 `_ensure()`，避免 `__new__` 迁移后产生空状态。
- **typing 指示器消失**：`streamingSessionId` 在 `__new__` 迁移到真实 ID 时同步更新。
- **会话删除残留**：新增 `removeSession()` 清理本地 `_states` Map 缓存。
- **Sidebar 轮询竞态**：防重入保护，网络延迟不再造成重叠请求。
- **删除事件传播**：统一触发 `deleted` + `deletedActive`，App.vue 清理任意被删除会话的本地缓存。


## 0.13.1

### 变更
- **输入框增高**：默认 3 行，最大高度 40vh（原 2 行 / 160px 固定）。
- 输入卡内部元素水平间距微调统一。

## 0.13.0

### 添加
- **上传客户端预检**：文件扩展名与大小在上传前根据 `GET /api/upload/config` 校验，上传失败显示红色可关闭错误横幅。
- **滚动自动跟随**：生成中自动跟滚到底；用户上滚 2 次后停跟，滚回底部自动恢复；typing 加载点作为锚点使用 `scrollIntoView`（`block: center`）解决大段文本脱离问题；程序化滚动门控避免自触发误判。
- **无条件滚底**：发送消息、切换会话时强制滚底 + 120ms 延迟补一次覆盖高度跳变。

### 变更
- **工具按钮仅图标**：输入框工具栏三个圆形图标按钮，去掉文字标签。
- **按钮样式统一**：`attach-btn` 从 `<label>` 改为 `<button>`，三种按钮共享相同圆形 border + transition + hover/.on 样式。
- **输入区布局一致**：`.input-tools` 间距与 `.input-actions` 统一为 10px。
- **附件按钮 on 状态**：上传完成后保持高亮（`hasFiles`）。
- **前端 accept 由后端决定**：`ChatInput` 的 `accept` 从 `GET /api/upload/config` 动态获取并组装。
- **助手气泡占满宽**：`.bubble.assistant` 增加 `max-width: none` 覆盖基类 85% 限制。
- **WorkflowLog 预览全文**：折叠标题用 CSS `text-overflow` 截断替代 JS 60 字符切片。

### 修复
- 流式生成中因 `scrollHeight` 快照过期、程序化滚动误触发违抗计数等导致自动跟滚意外停止。
- 切换会话后未滚动到底部。

## 0.12.9

### 添加
- **上传配置端点**：`GET /api/upload/config` 返回支持的文件类型分组（images / text / documents）；`GET /api/upload/accept` 返回 HTML accept 属性字符串。后端是文件类型支持的唯一来源。
- **uploads 独立模块**：`backend/llm/uploads.py`，从 router 中提取所有文件类型映射、`process_upload()` 核心逻辑、配置查询函数。

### 变更
- **工具栏按钮仅图标**：输入框底部三个工具按钮改为 32×32 圆形图标，与附件/思考按钮风格一致。
- **按钮样式统一**：`.attach-btn` 从 `<label>` 改为 `<button>`，三种按钮共享相同的圆形 border + transition + hover/.on 样式。
- **布局间距一致**：`.input-tools` 间距从 2px 改为 10px，与 `.input-actions` 对齐。
- **附件按钮 on 状态**：上传完成后附件按钮保持高亮（`hasFiles`），而非仅上传中。
- **前端 accept 属性由后端决定**：ChatInput 的 `accept` 从 `GET /api/upload/accept` 动态获取，不再硬编码 90+ 扩展名。

## 0.12.8

### 变更
- **工具默认启用调整**：`open_url` 和 `calculator` 默认关闭，仅 `web_search` 默认开启。三个工具在输入框底部独立切换。
- **工具指引解耦**：`web_search` 和 `open_url` 的 system prompt 指引不再互相引用，各工具独立描述其使用场景。

### 修复
- **README 修正**：前端技术栈从 Nuxt 4 修正为 Vite + Vue 3；端点数量从 27 修正为 20；架构图、项目结构、组件列表、Composable 清单与当前代码一致。
- **CLAUDE.md 同步**：补充 `tools.py`、`mcp.py`、SQLite 持久化、`PUT /api/llm/config` 运行时配置覆盖、MCP_SERVERS 环境变量等模块与设计模式。

## 0.12.7

### 变更
- **复制按钮移至气泡下方**：靠两侧对齐，始终显现，成功态改用 accent 色。
- Markdown 各元素间距减半。
- Markdown 字号统一继承基值。
- 助手气泡宽度修正。

### 修复
- `<li>` 内 `<p>` 块级换行导致标记分离。

## 0.12.6

### 添加
- **会话菜单**：⋮ 三点按钮，展开置顶/重命名/删除。
- **WorkflowLog 左列重构**：图标 + border-left 竖线连接。

### 变更
- **Markdown 渲染引擎**：`marked` → `markdown-it` + `markdown-it-texmath`, KaTeX 原生解析。
- 全站字号增大。
- 切换会话后自动滚至页尾。

### 修复
- 加载历史 WorkflowLog 显示「思考中」。
- 行内公式渲染为 HTML 源码。

## 0.12.6

### 添加
- **会话菜单**：会话右侧 ⋮ 三点按钮，展开【置顶、重命名、删除】菜单。置顶持久化到 localStorage，置顶分组显示于列表最前。
- **WorkflowLog 左列重构**：wf-entry 分为左列（图标 + 绝对定位 border-left 竖线连接）与右列（文本）。

### 变更
- **Markdown 渲染引擎**：`marked` → `markdown-it` + `markdown-it-texmath`，KaTeX 公式由插件原生解析，不再需要正则 hack + 占位符。
- 全站字号整体增大（基础 14px → ~16px）。
- 助手气泡 padding 收紧、消息间距减少。
- `li > p` 边距重置，避免列表编号与正文之间空行。
- 切换会话后自动滚至页尾。

### 修复
- 加载历史会话时 WorkflowLog 错误显示「思考中」→ 修正为「已思考」。
- 行内公式渲染为 HTML 源码（`marked` 转义问题）→ 换用 `markdown-it-texmath` 解决。

## 0.12.5

### 添加
- **多类型文件上传**：支持 90+ 种文件类型（图片 / 纯文本 / 代码 / PDF / Office / ePub / ipynb）。
- **MarkItDown 集成**：PDF、Office 文档、ePub 等自动转为 Markdown 文本输入。
- **文件附件卡片**：对话中文件以图标 + 文件名卡片展示（与发送框一致），不展全文。加载历史会话同样恢复卡片。
- 非图片文件自动按类型：代码文件用 `` ```lang `` 包裹，纯文本原样保留。

### 变更
- 后端版本号：0.12.4 → **0.12.5**。
- 前端版本号：0.12.4 → **0.12.5**。

### 修复
- 加载历史会话时文件卡片丢失：`loadHistory` 补全 `files` 字段透传。

## 0.12.4

### 添加
- **思考模式切换按钮**：附件按钮旁圆形按钮，默认开（蓝色），关（灰色）时发 `thinking: false` 禁止推理。

### 变更
- 后端版本号：0.12.3 → **0.12.4**。
- 前端版本号：0.12.3 → **0.12.4**。

## 0.12.3

### 添加
- **会话标题自动生成**：新会话默认「无标题」，首轮流式结束后后端调用 LLM 生成 ≤15 字标题，SSE 推送前端刷新。
- `reasoning_effort: "none"`：非思考模式显式禁用推理 token 消耗。

### 变更
- 后端版本号：0.12.2 → **0.12.3**。
- 前端版本号：0.12.2 → **0.12.3**。

## 0.12.2

### 添加
- **文件/图片上传**：`POST /api/upload` 端点，📎 圆形按钮上传图片。base64 编码后即删原文件。OpenAI 多模态格式 `[{type:"text", text:"..."}, {type:"image_url", image_url:{url:"data:..."}}]`。
- **图片预览与历史恢复**：输入框缩略图预览（可移除）；用户消息内嵌图片展示；加载会话时恢复图片。
- **有图无文也可发送**：仅上传图片时允许发送空文本。

### 修复
- 多模态消息导致会话后续无响应：`ChatMessage.content` 支持 `str | list`，`model_dump` 直接输出，无需转换层。
- 图文消息双重渲染：`v-if/v-else-if/v-if` 链修正。

### 变更
- 后端版本号：0.12.1 → **0.12.2**。
- 前端版本号：0.12.1 → **0.12.2**。

## 0.12.1

### 添加
- **终止生成**：生成中发送按钮变为 ■ 停止按钮，点击中止 SSE 流。
- 后端版本号：0.12.0 → **0.12.1**。
- 前端版本号：0.12.0 → **0.12.1**。

## 0.12.0

### 添加
- **open_url 工具**：打开指定网址提取正文，使用 trafilatura 智能抓取并输出 Markdown。
- **页尾跳转按钮**：非底部时显示 ↓ 按钮，点击跳回页尾。

### 变更
- 取消自动跟随滚动，仅保留手动跳底。
- 思考状态切换：首次 content 事件即切换「思考中」→「已思考」。
- 默认启用 open_url 工具。
- 后端版本号：0.11.4 → **0.12.0**。
- 前端版本号：0.11.4 → **0.12.0**。

### 移除
- Playwright 无头浏览器（Python 3.14 on Windows ProactorEventLoop 不支持子进程）。

## 0.11.4

### 添加
- **KaTeX 数学公式渲染**：`$$...$$` 和 `$...$` 自动渲染为数学公式。
- **WorkflowLog 折叠**：生成中展开 → 完成后自动折叠为「⚡ 思考中 / 已思考 ˅ 摘要」。
- **ToolSidebar 详情**：调用说明 + 返回结果 + 可折叠原始 JSON + 搜索链接。
- **brand-ver 自动更新**：从 `package.json` 读取版本号注入构建。

### 变更
- 侧边栏「新建对话」全宽按钮替换旧 header。
- 思考图标改用 `fa-bolt`。
- 后端版本号：0.11.3 → **0.11.4**。
- 前端版本号：0.11.3 → **0.11.4**。

### 修复
- 思考完成后未自动折叠（watch `streamDone`）。
- 侧边栏展开时横向滚动条闪现（`overflow-x: hidden`）。
- WorkflowLog chevron 位置修正。

## 0.11.3

### 添加
- **代码语法高亮**：引入 `highlight.js`，Markdown 代码块自动上色，右上角显示语言标签。
- **Font Awesome 本地化**：从 CDN 改为 `@fortawesome/fontawesome-free` pnpm 本地依赖。

### 变更
- 默认启用计算辅助（calculator）。
- 思考文本 `white-space: pre-wrap` 保留换行。
- 后端版本号：0.11.2 → **0.11.3**。
- 前端版本号：0.11.2 → **0.11.3**。

### 修复
- 代码块 HTML 被转义显示：改用 `marked.use({ renderer: { code } })` 直接覆写。
- `marked-highlight` 依赖移除。

## 0.11.2

### 修复
- **思考过程异常**：流式端点空 assistant 占位消息被纳入 LLM 请求上下文，导致模型行为异常。改为请求前排除占位消息，请求后恢复。
- 回退 0.11.1 中的错误修复（`stream_options` 移除、thinkContent 回退展示、calculator 过度强硬指引）。
- 后端版本号：0.11.1 → **0.11.2**。
- 前端版本号：0.11.1 → **0.11.2**。

## 0.11.1

### 修复
- **思考过程无法展现**：移除 `_build_payload` 中非标准 `stream_options.include_reasoning` 参数。（后确认该参数实则正常，0.11.2 回退）
- 后端版本号：0.11.0 → **0.11.1**。
- 前端版本号：0.11.0 → **0.11.1**。

## 0.11.0

### 添加
- **Function Calling 自动执行**：新增 `ToolExecutor` 工具注册表，内置 `web_search`（DuckDuckGo）和 `calculator`，后端自动执行并回传结果。
- **MCP 支持**：新增 `MCPClient` 轻量客户端，HTTP 协议连接外部工具服务器，自动发现并注册工具。
- **会话 SQLite 持久化**：`SessionStore` 新增 SQLite 存储，重启后自动恢复全部会话。
- **工作流日志**：新增 `WorkflowLog.vue`，以图标+文字有序展示 Agent 每一步行为，思考流实时上屏。
- **工具侧边栏**：新增 `ToolSidebar.vue`，点击工作流条目在右侧展开工具详情与搜索链接。
- **工具注册表**：新增 `tools/registry.ts`，统一管理工具图标、标签、展示模板、system prompt 指引。
- **Font Awesome 7.3 图标**：全界面 emoji 替换为 FA 矢量图标。
- **会话列表日期分组**：侧边栏按今天/昨天/7天内/30天内/月份分组，每轮对话刷新时间。

### 变更
- **界面重构**：输入框两段式（上文字区+下工具栏+发送按钮），工具栏并入输入框；助手回复取消气泡占满宽度；复制按钮靠内始终展现；取消角色标注与时间。
- **工具管理简化**：移除自定义工具编辑器、ToolEditor、ToolCallCard；工具启停通过输入框按钮。
- **滚动条移至 chat-panel**：输入框 sticky 固定底部；布局左侧栏+chat-panel+右侧栏，100vw×100vh。
- 后端版本号：0.10.1 → **0.11.0**。
- 前端版本号：0.10.1 → **0.11.0**。

### 修复
- 流式过程中消息实时写入 `chat.messages`，GET 端点可返回部分生成内容，支持断线恢复。
- system prompt 重复注入修复（Chat 构造 + 显式 append）。
- 工具指引误用 FA class → 修正为纯文本。
- 会话注册覆盖 `created_at` → 保留原始创建时间。

## 0.10.1

### 添加
- **消息复制按钮**：用户和助手消息悬停时底部显示 📋 复制按钮，统一适配亮/暗两种气泡背景色。

### 变更
- **消息操作精简**：移除分支管理、编辑、重新生成功能，统一仅保留复制按钮。
- 后端版本号：0.10.0 → **0.10.1**。
- 前端版本号：0.10.0 → **0.10.1**。

## 0.10.0

### 添加
- **Think 过程展现**：后端 `chat_stream_events()` 从 SSE 流中提取 `reasoning_content`，前端 MessageBubble 实时展示思考过程（流式时滚动末三行，完成后自动折叠为 "💭 思考过程（N 行）" 可展开）。
- **流式工具调用**：`POST /api/chat/stream` 接受 `tools` 参数，流式累积 `delta.tool_calls`，流结束前 yield `tool_calls` 事件 + 自动创建 Agent 会话。
- **上下文感知流式会话**：新增 `POST /api/conversations/{id}/messages/stream` 端点——从 SessionStore 取 Chat 实例，携带完整历史 + 新消息流式返回，自动追加 assistant 回复到历史。
- **消息角色切换**：ChatInput 左侧新增 👤/⚙️ 按钮，每条消息可独立设为 system 或 user 角色。
- **Markdown 渲染**：助手消息通过 `marked` 库渲染 Markdown（代码块、表格、链接等），带深色代码背景样式。
- **消息复制按钮**：助手消息悬停显示 📋 复制按钮（`navigator.clipboard.writeText`）。
- **会话重命名**：侧边栏会话双击可内联编辑标题 → 调用 `PATCH /api/conversations/{id}`。
- **会话标题自动生成**：新建会话时从首条用户消息或 assistant 回复截取前 30 字作为标题。
- **Agent 会话 TTL 清理**：`_agent_sessions` 增加 1 小时 TTL，定期清理过期实例并同步清理 SessionStore。
- **`SessionStore.register()`** — 接受外部 Chat/Agent 实例注册到会话存储，桥接 Agent 与会话列表。

### 变更
- **取消对话/智能体模式划分**：移除 `Mode` 类型和模式切换按钮，始终使用 Agent composable。系统提示栏替换为每条消息的角色选择器，工具定义始终可用。
- **会话创建延迟**：新建对话不立即创建会话——首条消息发出后由后端自动创建并注册到 SessionStore，前端自动选中 + 刷新侧边栏。
- **流式端点重构**：`chat_stream_events()` 增加 tool_calls 累积（按 index 合并 delta），返回类型改为 `AsyncIterator[dict[str, object]]`。
- **会话模型扩展**：`ConversationInfo` 新增 `title`、`mode` 字段；`ConversationCreateRequest` 新增 `title`、`mode`；`ConversationMessageRequest` 新增 `role`、`thinking`、`tools`。
- **ChatMessageWithUsage** 新增 `thinking`、`tools` 字段。
- **ChatRequest / ChatResponse** 新增 `thinking` / `reasoning_content` 字段。
- 后端版本号：0.9.0 → **0.10.0**。
- 前端版本号：0.9.0 → **0.10.0**。

### 修复
- **会话上下文丢失**：`POST /api/chat/stream` 仅在 tool_calls 时才创建会话 → 纯文本回复无会话导致后续消息丢失上下文。改为流结束后无条件创建会话并 emit `session` 事件。
- **会话端点字段名不匹配**：前端发送 `message` 字段到 `/api/conversations/{id}/messages/stream`，但端点要求 `content`。根据端点分别使用正确字段名。
- **Sidebar 模式不同步**：Sidebar 本地 `activeMode` 与 App 的 `mode` 不同步 → 改为接受 `mode` prop。
- **ToolEditor computed 副作用**：`parsedTools` computed 中写 `error.value` → 改用 `watch`。
- **ChatPanel 冗余 deep watch**：`watch(allMessages, ..., {deep: true})` → 移除 `deep`。
- **Sidebar 版本号硬编码 v0.8** → 修正为 `v0.9.0`。

## 0.9.0

### 添加
- **初版 Agent 前端**（`frontend/`）：采用 Vite + Vue 3 + TypeScript 构建，为 Agent 后端提供 Web 交互界面。
  - **对话模式**：`POST /api/chat/stream` SSE 流式渲染，消息逐字上屏。
  - **智能体模式**：`POST /api/agent/chat` + `/continue` 工具调用循环，用户可手动输入或跳过工具结果。
  - **工具定义编辑器**：JSON 编辑 + 计算器/网页搜索预设模板，支持动态增减工具。
  - **会话管理侧边栏**：列出活跃会话、切换模式（对话/智能体）、删除会话。
  - **设置面板**：查看 LLM 网关地址、认证状态、网关健康探活结果。
  - **暗色主题**：专为 AI 工具优化的深色配色方案。
  - **全中文化界面**：所有文案、标签、提示均已汉化。
- **Vite API 代理**：前端 `/api` 请求自动转发至后端 `localhost:8000`，开发时无需跨域配置。

### 修复
- **Chat 模式消息未能上屏**：`useChat.addMessage()` 返回原始对象而非 Vue 响应式代理，导致流式内容追加不触发视图更新。改为返回 `messages.value[last]`（响应式代理）。

### 变更
- 后端 CORS 已允许 `localhost:3000`（前端默认端口）。
- 后端版本号：0.8.0 → **0.9.0**。
- 前端版本号：**0.9.0**（新增）。

## 0.8.0

### 添加
- **Chat 类**（`llm/chat.py`）：LLM 对话基类，封装消息历史管理 + 流式/非流式调用，作为 Agent 的基础设施。
- **Agent 类**（`llm/agent.py`）：继承 Chat，增加工具定义注入与 think→act→observe 推理循环，支持多轮工具调用。
- **流式对话**：`POST /api/chat/stream` — SSE 逐 token 流式返回模型回复。
- **Agent 端点**：
  - `POST /api/agent/chat` — 发送消息 + 工具定义，模型可请求工具调用。
  - `POST /api/agent/chat/continue` — 回传工具执行结果，继续推理循环。
- **LLM 配置端点**：`GET /api/llm/config` — 返回当前网关地址、默认模型、令牌配置状态。
- **简洁 Chat API**：`POST /api/chat` — 单字段消息输入（无需手动拼接 messages 数组）。
- **环境变量 `LLM_DEFAULT_MODEL`**：替换旧的 `MODEL` 数组方案，直接指定默认模型 ID。

### 变更
- **LLM 模块完全重构**：环境变量从 `MODEL`（模型白名单数组）改为 `LLM_DEFAULT_MODEL`（单个模型 ID）。模型白名单校验机制已移除——任何兼容 OpenAI 协议的模型均可使用。
- **环境变量加载集中化**：`core/config.py` 统一加载 `.env` 并导出 `LLM_BASE_URL`、`LLM_AUTH_TOKEN`、`LLM_DEFAULT_MODEL`，消除 llm/client.py 中的重复 `load_dotenv()` 调用。
- **会话管理重构**：`SessionStore` 内部改用 `Chat` 类管理消息历史，逻辑更清晰。
- **项目骨架精简**：依赖从 `numpy` + `scikit-learn` + `sentence-transformers` + `httpx` + `fastapi` 精简为 `fastapi[standard]` + `httpx` + `python-dotenv`。
- 后端版本号：0.7.0 → **0.8.0**。

### 移除
- **`MODEL` 环境变量**（模型白名单数组），替换为 `LLM_DEFAULT_MODEL`。
- **`GET /api/llm/models`** 端点（模型列表）。
- **connectors / scout / prism / pipeline 模块**：此次重构聚焦 LLM Chat/Agent 基础设施，情报采集与管线模块将在后续版本中基于新架构重建。

## 0.7.0

### 添加
- **IRIS LLM 模块**：新增 `backend/llm/`，提供统一的内部 LLM 调用能力，为 IRIS OPTIMIZER 等下游模块做好准备。
  - `POST /api/llm/chat` — 无状态对话接口（模型白名单校验 + OpenAI-compatible 网关通信）
  - `POST /api/llm/conversations` — 创建会话，返回 session_id
  - `POST /api/llm/conversations/{id}/messages` — 会话式对话，**服务端自动维护上下文**
  - `GET /api/llm/conversations/{id}` — 获取会话详情（完整消息历史）
  - `GET /api/llm/conversations` — 列出所有活跃会话
  - `DELETE /api/llm/conversations/{id}` — 删除会话
  - `GET /api/llm/models` — 已许可模型列表
  - `GET /api/llm/health` — LLM 网关连通性探活
- **会话存储**：`sessions.py` 实现内存会话管理（OrderedDict LRU 驱逐 + TTL 自动过期 + asyncio.Lock 并发安全）
- **模型白名单**：从 `.env` MODEL 变量解析已许可模型，支持 JSON 数组 / 方括号 / 纯逗号分隔三种格式
- **后端日志文件写入**：`main.py` 根 logger 新增 `FileHandler`，所有模块日志（lifecycle、pipeline、prism 等）自动写入 `logs/backend.log`（UTF-8 编码，格式：`时间 级别 模块名 消息`）。
- **前端日志脚本**：`package.json` 新增 `dev:log` 脚本，通过 `tee` 将 Nuxt 开发服务器输出同步写入 `logs/frontend.log`。
- **日志目录**：新增 `logs/` 目录及 `.gitkeep` 占位文件。

### 变更
- `main.py` 新增 `llm_router` 挂载（`/api` 前缀）
- **环境变量加载**：`llm/client.py` 显式调用 `load_dotenv()`，确保 FastAPI auto-reload 模式下可靠读取 `.env`
- **README.md 状态更新**：前端部分 Phase 1 标记为"✅ 已实现"，项目结构中页面、组件、Composable、Store 的 Phase 标记同步刷新
- **分支合并**：整合 LLM 模块（本地）与前端 Phase 1 管线控制台 + 日志系统（远程）
- 后端版本号：0.6.0 → **0.7.0**
- 前端版本号：0.6.0 → **0.7.0**

## 0.6.0

### 添加
- **IRIS OBSERVATORY Phase 1 — 管线控制台**：6 个页面，覆盖 PIPELINE / Core / Connectors 全部已实现功能。
  - **仪表盘** (`/`)：系统概况、信源健康指示器、生命周期状态、最近运行列表。
  - **管线控制台** (`/pipeline`)：一键运行管线、实时状态轮询（2 秒间隔）、取消运行、运行历史表格。
  - **运行详情** (`/pipeline/:id`)：SCOUT 原始采集结果与 PRISM 精炼结果并排对比展示。
  - **管线配置** (`/config`)：关键词标签编辑器（增删改）、信源开关、采集参数调节、配置持久化保存。
  - **信源管理** (`/sources`)：三方信源健康探测面板 + 原始 API 查询浏览器（支持 GitHub / arXiv / HuggingFace 动态查询）。
  - **系统管理** (`/admin`)：应用生命周期管理（挂起 / 恢复 + 确认对话框）。
- **通用组件库**（5 个）：`AppSidebar`（侧边栏导航，按模块分组）、`AppHeader`（顶栏 + 生命周期状态指示灯）、`StatusBadge`（彩色胶囊状状态标签）、`LoadingSpinner`（加载动画）、`EmptyState`（空数据占位）。
- **Composables 层**（6 个）：`useApi`（`$fetch` 封装，get / post / put / del）、`usePolling`（通用轮询 Hook，自动清理）、`useHealth`（健康检查）、`usePipeline`（管线 5 端点）、`useConfig`（配置读写）、`useAdmin`（挂起 / 恢复）。
- **Pinia 状态管理**（3 个 Store）：`pipeline`（当前运行 ID / 状态 / 历史）、`config`（管线配置 CRUD 与后端同步）、`sources`（健康状态缓存）。
- **TypeScript 类型定义**：`types/api.ts`，22 个接口完整映射后端 Pydantic 模型（AppInfo / HealthResult / ScoutConfig / PipelineRunDetail / PrismReport 等）。
- **布局系统**：`layouts/default.vue` — 240px 深色侧边栏 + 56px 顶栏 + 可滚动内容区 Flexbox 布局，四大模块导航分组（总览 / 管线 / 情报 / 生成）。
- **管线实时状态轮询**：`GET /api/pipeline/runs/{id}/status` 定时轮询，运行完成 / 失败 / 取消时自动停止，页面刷新后自动恢复对运行中任务的监控。
- **README.md 前端架构重写**：从"未实现设想"替换为完整 13 页规划，包含分层架构图、路由-API 映射表、组件树、数据流图、11 个 Composable / 5 个 Store 清单、Phase 1-3 分阶段路线图。

### 变更
- **前端依赖升级**：新增 `pinia` + `@pinia/nuxt` 状态管理。
- **app.vue 重写**：从 `<NuxtWelcome />` 替换为 `<NuxtLayout>` + `<NuxtPage>`，启用文件路由与布局系统。
- **nuxt.config.ts 增强**：注册 `@pinia/nuxt` 模块，新增 `runtimeConfig.public.apiBase` 配置后端地址。
- **后端 CORS 支持**：`main.py` 新增 `CORSMiddleware`，允许 `http://localhost:3000` 跨域请求。
- 后端版本号：0.5.2 → **0.6.0**。
- 前端版本号：0.5.2 → **0.6.0**。

## 0.5.2

### 变更
- **Pylance Strict 类型合规**：新增 `backend/pyrightconfig.json`，启用项目级 strict 类型检查。修复全部 30 个源文件的类型问题：私有访问控制、缺失类型参数、可选成员访问、未使用导入清理。
- **公共 API 清理**：`TaskInfo._task` → `task`（公开 asyncio.Task 引用）；`pipeline/router.py` 模块级单例移除 `_` 前缀（被 `main.py` 外部导入）。
- **健康检查类型增强**：`_PROBES` 改用 `TypedDict` 获得完整类型安全。
- 后端版本号：0.5.1 → **0.5.2**。

## 0.5.1

### 变更
- **预设数据集中管理**：新增 `scout/presets.py`，将关键词列表、关键词批次、评分权重、信源默认参数等预设常量集中管理，消除 `ScoutConfig`（12 个关键词）与 `DEFAULT_KEYWORDS`（98 个关键词）之间的不一致。
- **评分常量命名化**：`collector.py` 中的评分魔法数字替换为命名常量（`GITHUB_STAR_WEIGHT`、`HF_DOWNLOAD_WEIGHT` 等），提高可维护性。
- **PipelineStore 解耦**：`pipeline/store.py` 的 fallback 值改为从 `scout.presets` 导入，不再内联硬编码。
- 后端版本号：0.5.0 → **0.5.1**。

## 0.5.0

### 添加
- **应用配置集中管理**：新增 `core/config.py`，`AppConfig` 作为应用名、版本、描述等元数据的唯一来源，消除 `main.py` 与 `core/info.py` 中的多处硬编码。
- **生命周期状态机**：新增 `core/lifecycle.py`，`AppLifecycle` 管理应用级运行状态（running / suspended / shutting_down），使用异步锁保护状态切换的并发安全。
- **管理接口**：`POST /api/admin/suspend`、`POST /api/admin/resume`、`GET /api/admin/status` 端点，支持运行时挂起与恢复应用。

### 变更
- **消除硬编码**：`core/info.py` 和 `main.py` 中的应用元数据改为从 `AppConfig` 统一读取，未来版本更新只需修改 `core/config.py` 一处。
- **挂起保护**：`POST /api/pipeline/run` 在应用挂起时返回 503，阻止新的管线任务提交。
- **健康检查增强**：`GET /api/health` 在非运行状态下额外返回 `mode` 字段（如 `"suspended"`）。
- **优雅关闭增强**：lifespan shutdown 阶段先通过 `AppLifecycle.begin_shutdown()` 标记关闭状态，再执行资源清理。
- 后端版本号：0.4.0 → **0.5.0**。

## 0.4.0

### 添加
- **Pipeline 异步后台执行**：`POST /api/pipeline/run` 改为非阻塞模式，立即返回 `{run_id, status: "running"}`，管线在后台 asyncio.Task 中执行。
- **任务取消**：`DELETE /api/pipeline/runs/{run_id}` 端点，可取消正在运行的管线任务。
- **实时状态查询**：`GET /api/pipeline/runs/{run_id}/status` 端点，返回当前阶段（scout/prism）、状态、错误信息。
- **模块结果缓存**：`GET /api/pipeline/results/{module}` 端点，获取 SCOUT 或 PRISM 的最后一次有效运行结果。
- **TaskManager**：`pipeline/task_manager.py` — 后台任务生命周期管理、取消、状态追踪。

### 变更
- **模型层共享**：新增 `backend/models.py`，`IntelligenceItem` 移至共享层，PRISM 不再从 SCOUT 模块导入。
- **异步化**：`prism/embeddings.py`、`prism/terms.py`、`prism/dedup.py`、`prism/store.py` 中所有 ML 推理（sentence-transformers、sklearn TF-IDF）移至 `asyncio.to_thread()` 线程池执行，释放事件循环。
- **PRISM 签名重构**：`refine()` 改为接收 `list[IntelligenceItem]` 而非 `ScoutReport`，切断对 SCOUT 模块的类型依赖。
- **Pipeline 独立管理 TermStore**：Pipeline 不再从 `prism.router` 导入 `_term_store`，自行创建并管理术语存储。
- **优雅关闭**：`main.py` 添加 lifespan handler，关闭时取消所有后台任务并关闭数据库连接。
- **PipelineStore 解耦**：`pipeline/store.py` 不再从 `scout.collector` 导入 `DEFAULT_KEYWORDS`，改用 `ScoutConfig().keywords`。

### 破坏性变更
- `POST /api/pipeline/run` 不再阻塞返回完整结果。客户端需改用 `GET /api/pipeline/runs/{run_id}/status` 轮询 + `GET /api/pipeline/runs/{run_id}` 获取结果。
- `POST /api/prism/refine` 请求体改为 `list[IntelligenceItem]`（原为 `ScoutReport`，其中 `items` 字段已直接提升为顶层数组）。
- `prism/embeddings.py` 的 `embed_texts()` 和 `cosine_similarity_matrix()` 改为异步函数。

## 0.3.0

### 添加
- **GitHub README 获取**：`GET /api/github/readme` 端点，通过 GitHub Contents API 获取仓库 README 内容（base64 解码），丰富情报分析数据。
- **HuggingFace README 获取**：`GET /api/huggingface/readme` 端点，直接获取模型卡片 Markdown 原文，用于深度术语提取。
- **SCOUT README 批量采集**：`_fetch_readmes_batch()` — 在采集阶段自动拉取高分条目的 README/模型卡片内容（并发控制、5k 字符截断），存入 `metadata.readme` 供 PRISM 使用。
- **PIPELINE 配置持久化**：`GET /api/pipeline/config` + `PUT /api/pipeline/config` 端点，支持管线参数的持久化存储与部分更新。
- **PIPELINE 运行历史**：`GET /api/pipeline/runs` + `GET /api/pipeline/runs/{run_id}` 端点，支持查询历史运行记录（摘要列表 + 完整详情）。
- **PipelineStore**：`backend/pipeline/store.py` — SQLite 持久化存储层，管理配置 (key-value) 与运行历史 (runs + run_results 双表)。
- **PipelineModels**：`backend/pipeline/models.py` — 管线配置更新与运行历史的 Pydantic 模型定义。

### 变更
- **PRISM 富文本增强**：`_build_rich_text()` 纳入 `metadata.readme` 内容，提升术语提取与去重的准确率。
- **PIPELINE 路由重构**：`POST /api/pipeline/run` 自动持久化配置与运行结果，响应中附带 `run_id` 供后续查询。
- **SCOUT 采集器增强**：GitHub 和 HuggingFace 采集完成后自动获取高分条目 README，丰富下游分析数据。
- 后端版本号：0.2.0 → **0.3.0**。
- 前端版本号：→ **0.3.0**。

## 0.2.0

### 添加
- **IRIS SCOUT（窥远仪）**：多轮多关键词并发采集引擎，覆盖 100+ 前沿 AI/ML 关键词，支持 GitHub / arXiv / HuggingFace 三大信源的多批次查询与热度评分。
- **IRIS PRISM（析光仪）**：语义去重（sentence-transformers 嵌入 + 余弦相似度）、技术术语提取（130+ 正则模式 + TF-IDF）、术语分类（known / variant / novel）、术语共现图谱构建、重要性重评分。
- **IRIS PIPELINE（引流渠）**：SCOUT → PRISM 总调度管线，一站式情报采集与精炼。
- **Core 模块**：系统信息 `/`、版本 `/version`、运行状态 `/status` 接口。
- **Health 接口**：`/api/health` 三方数据源并发可用性探测。
- **数据源接口**：GitHub（search + trending）、arXiv（search + latest）、HuggingFace（search + trending）。
- **CLAUDE.md**：项目架构与开发命令文档。

### 变更
- `README.md` 更新为正式快速开始指南与当前项目结构。
- `.gitignore` 完善（uv、Claude Code、Windows 系统文件、PRISM 数据目录）。
- 后端版本号：0.1.0 → **0.2.0**。
- 前端版本号：→ **0.2.0**。
- Python 依赖新增：`sentence-transformers`, `scikit-learn`, `numpy`。

## 0.0.1

### 添加
- 可运行 demo（FastAPI 骨架 + Nuxt 4 前端骨架）。
- GitHub / Hugging Face / arXiv 等数据源连接器接口。

## 0.0.0

### 添加
- 项目架构设计与五大核心模块定义：IRIS PIPELINE（引流渠）、IRIS SCOUT（窥远仪）、IRIS PRISM（析光仪）、IRIS OPTIMIZER（显影仪）、IRIS OBSERVATORY（观象台）。
- 项目许可证 Apache License 2.0。
- 贡献者指南 `CONTRIBUTING.md`。
- 初始 `README.md`，包含项目目标、架构与核心工作流。