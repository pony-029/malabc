# -*- coding: utf-8 -*-
"""`translate` 包 —— R82/T4（规则驱动的 C ↔ MATLAB 互转）的落地位置。

Phase 0 只放**规则表**（`rules.py`）；后续阶段追加：
  * `m2c.py`   MATLAB → C 的确定性段
  * `c2m.py`   C → MATLAB 的确定性段
  * `fidelity.py`  双语对照执行器（**保真度的唯一裁判**）

设计上的**默认姿态是「不可信」**（R82 §7.5）：没有跑过双语对照的翻译一律
`unverified`，不是「大概对」。
"""
