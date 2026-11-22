"""把 matcha 源码内置到 sidecar venv（绕过 Cython 编译）。

matcha-tts 的 Cython 扩展（monotonic_align）仅在训练路径使用，推理只需
matcha.models.components / matcha.hifigan。本脚本从清华 PyPI 镜像下载 sdist，
复制 matcha 包到 site-packages，并做两处最小补丁：

1. 清空 matcha/utils/__init__.py（原文件会导入 hydra/lightning 训练栈）
2. 替换 matcha/utils/pylogger.py（去掉 lightning 的 rank_zero_only 依赖）

用法: python vendor_matcha.py <venv 的 site-packages 路径>
"""

from __future__ import annotations

import io
import pathlib
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

SIMPLE_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple/matcha-tts/"
PACKAGE_VERSION = "0.0.7.2"

PYLOGGER_PATCH = """import logging


def get_pylogger(name: str = __name__):
    return logging.getLogger(name)
"""


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python vendor_matcha.py <site-packages>", file=sys.stderr)
        return 2
    site_packages = pathlib.Path(sys.argv[1])
    dst = site_packages / "matcha"
    if dst.exists():
        print(f"matcha 已存在: {dst}")
        return 0

    page = urllib.request.urlopen(SIMPLE_INDEX, timeout=60).read().decode("utf-8", "replace")
    match = re.search(
        rf'href="([^"]*matcha[-_]tts-{re.escape(PACKAGE_VERSION)}\.tar\.gz[^"]*)"',
        page,
    )
    if not match:
        print("镜像索引中未找到 matcha-tts sdist", file=sys.stderr)
        return 1
    url = urllib.parse.urljoin(SIMPLE_INDEX, match.group(1))
    print(f"下载 {url}")
    data = urllib.request.urlopen(url, timeout=180).read()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(tmp_path)
        src = next(tmp_path.glob("matcha*/matcha"))
        shutil.copytree(src, dst)

    (dst / "utils" / "__init__.py").write_text("", encoding="utf-8")
    (dst / "utils" / "pylogger.py").write_text(PYLOGGER_PATCH, encoding="utf-8")
    print(f"matcha 已内置并打补丁: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
