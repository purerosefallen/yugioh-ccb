#!/usr/bin/env python3
# build.py — 自动化调用 PyInstaller 以生成精简版可执行文件

import subprocess
import sys
import shutil
import os
from pathlib import Path

# ========== 配置区 ==========
# 入口脚本
ENTRY_SCRIPT = "guess_card_game.py"
# 要打包的数据库文件
DB_FILE = "cards.cdb"
# 要打包的模板目录
TEMPLATE_DIR = "templates"
# 输出目录
DIST_DIR = "dist"
BUILD_DIR = "build"
SPEC_FILE = ENTRY_SCRIPT.replace(".py", ".spec")
# UPX 可执行文件所在路径（Windows 下一般安装在 C:\Program Files\upx-5.0.0-win64）
UPX_DIR = r"C:\Program Files\upx-5.0.0-win64"
# 要排除的模块列表
EXCLUDE_MODULES = [
    "tkinter", "pytest", "unittest", "pdb",
    "numpy.tests", "pandas.tests",
]
# =============================

def run(cmd):
    print(f">>> {' '.join(cmd)}")
    res = subprocess.run(cmd, shell=False)
    if res.returncode != 0:
        sys.exit(res.returncode)

def main():
    # 1. 清理上次 build
    for path in (BUILD_DIR, DIST_DIR, SPEC_FILE):
        p = Path(path)
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()

    # 2. 检查 UPX
    if not Path(UPX_DIR).exists():
        print(f"[!] 没找到 UPX：{UPX_DIR}，将跳过 UPX 压缩")
        upx_arg = []
    else:
        upx_arg = ["--upx-dir", UPX_DIR]

    # 3. 构造 PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--clean",
        *upx_arg,
    ]

    # 3.1 把 cards.cdb 和 templates 目录都加入到可执行文件数据区
    #    os.pathsep 在 Windows 下是 ';'，在 macOS/Linux 下是 ':'
    data_entries = [
        f"{DB_FILE}{os.pathsep}.",
        f"{TEMPLATE_DIR}{os.pathsep}{TEMPLATE_DIR}",
    ]
    for entry in data_entries:
        cmd += ["--add-data", entry]

    # 3.2 排除不需要的模块
    for mod in EXCLUDE_MODULES:
        cmd += ["--exclude-module", mod]

    # 3.3 最后加上入口脚本
    cmd += [ENTRY_SCRIPT]

    # 4. 运行打包
    run(cmd)
    print("\n✅ 打包完成！可执行文件在", Path(DIST_DIR) / Path(ENTRY_SCRIPT).stem)

if __name__ == "__main__":
    main()
