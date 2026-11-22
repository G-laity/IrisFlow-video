"""IRIS VIDEO COMPOSER —— 视频合成器域包。

脚本 → 素材生成 → 时间轴编排 → 合成渲染 → 预览下载。

子模块：
- ``config`` — 合成器配置（data/composer_config.json，AppConfig 模式）
- ``store`` — ComposerStore：SQLite 持久化（projects / assets / renders 三表）
- ``assets`` — 素材服务：URL 下载 + hash 去重 + MIME 判型 + ffprobe 探测
- ``ffmpeg`` — ffmpeg / ffprobe 探测与调用（M3 扩展命令构建与渲染）
- ``router`` — REST + SSE 路由（/api/composer）
"""
