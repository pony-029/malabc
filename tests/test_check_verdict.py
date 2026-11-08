# -*- coding: utf-8 -*-
"""`check` 的【结论】必须把人分到**该动什么**上，而不是只报"不能生成"。

## 三个分支各自对应一种现实

| 分支 | 现实 | 用户该做什么 |
|---|---|---|
| 先改签名 | 形参是 cell/struct/varargin（实测占大库失败的绝大多数） | 改函数签名 |
| 改写法 | 语句在支持范围外但可改写 | 按逐行建议改 |
| 超出边界 | 字符串字面量这类，改了也不支持 | 放弃这条路 |

判据只认一句：**结论里必须出现该分支的关键词**，且"改完还剩多少"必须说清 ——
否则用户改完签名回来发现还是不能转，那次改动就白费了。
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import check as CK      # noqa: E402

WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

OK_SRC = """function y = f(a)
% @m2c shape a 3
% @m2c shape y 3
y = a .* 2;
end
"""

#: 用 `c{1}` 触发元胞形参（签名级拒绝）—— 只写 `f(c)` 不会触发，判据会误绿
SIG_SRC = """function y = f(c)
y = c{1};
end
"""

BOUND_SRC = """function y = f(a)
% @m2c shape a 3
% @m2c shape y 1
s = 'abc';
y = 1;
end
"""


def _verdict(src):
    d = tempfile.mkdtemp(prefix="cv_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "t.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(src)
    res = CK.diagnose(p)
    return res, CK.render(res)


def test_ok_has_no_verdict_block():
    res, _ = _verdict(OK_SRC)
    assert res["status"] == "ok"


def test_signature_branch_says_what_to_change():
    _, text = _verdict(SIG_SRC)
    assert "【结论】" in text
    assert "先改签名" in text, text[:300]
    # 必须告诉人"改完还剩多少"，否则改完还是不能用
    assert "改完" in text, text[:300]


def test_boundary_branch_is_explicit():
    _, text = _verdict(BOUND_SRC)
    assert "【结论】" in text
    assert ("超出边界" in text) or ("改写法" in text), text[:300]
