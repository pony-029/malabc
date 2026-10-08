# -*- coding: utf-8 -*-
"""matlabc 统一入口（P225-H 合并版）。

把「命令行分析器」与「图形界面」合并为**单个可执行文件**：

    matlabc.exe           # Windows
    matlabc               # Linux / macOS

用法区分（按是否带参数自动分流）：
    - 双击（无参数）   → 启动图形界面
    - 带参数运行       → 作为命令行分析器（等价原 matlabc）
    - --selftest       → 运行图形界面自检（无界面；便于 CI 验证）

源码由 PyInstaller 全部打包进这一个文件；对外分发时**只需这一个 exe**，
不需要、也不提供任何 .py 源码。
"""
import sys

APP_NAME = "matlabc"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # --selftest 走 GUI 自检（无界面）
    if "--selftest" in argv:
        import gui
        return gui.main(["--selftest"])
    # 无参数：启动图形界面
    if len(argv) == 0:
        import gui
        return gui.main([])
    # ask 子命令：基于静态分析结果的问答式理解（P0 检索/grounding 底座）
    if argv[0] == "ask":
        import matlabc_ask
        return matlabc_ask.main(argv[1:])
    # flow 子命令：AI 修复闭环编排器（P1，驱动 ai_config.flow）
    if argv[0] == "flow":
        import matlabc_flow
        return matlabc_flow.main(argv[1:])
    # 其余：交给命令行分析器
    import matlabc
    return matlabc.main(argv)


if __name__ == "__main__":
    sys.exit(main())
