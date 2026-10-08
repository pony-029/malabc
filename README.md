# malabc

MATLAB/Simulink 静态分析与确定性自动修复引擎（matlabc）。

- `matlabc.py`：核心分析器（CLI + 可视化报告）
- `matlabc_ask.py`：基于分析结果的问答式代码理解
- `matlabc_flow.py`：AI 修复闭环编排器
- `matlabc_boot.py`：统一入口
- `renderers/`：报告/可视化渲染器
- `gui.py`：图形界面入口

运行：

    python matlabc.py ./your_project --json report.json
    python matlabc.py ask -q "main 被谁调用" --dir ./your_project
    python matlabc.py flow ./your_project

测试：

    python tests/test_matlabc.py

完整文档见 [docs/](docs/)。
