# -*- coding: utf-8 -*-
"""`ai_cli.py`（仓根，691 行）：**凭据脱敏**。

## 为什么这条判据是安全相关的

`redact()` 的唯一职责是"别把密钥打印到 stderr / 报告 / 日志里"。它一旦漏一种
形态，就等于给了一个**假保障** —— 人们看到有 `redact` 就以为安全了。

R851 实测的缺口：旧模式只有 `sk-` / `Bearer` / `api_key` 三类，

```
redact("password=hunter2")  ->  'password=hunter2'     ← 原样返回
```

而 `password=` / `token=` / `secret=` 是同样常见的泄露形态。现在已补齐，
判据按"每种常见形态都必须被遮"来守。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_all_common_credential_forms_are_redacted():
    """六种常见凭据形态都必须被遮，且**原文不能残留**。"""
    import ai_cli as A

    cases = [
        ("password=hunter2", "hunter2"),
        ("api_key=sk-abc123", "sk-abc123"),
        ("token=abc123456", "abc123456"),
        ("secret: s3cr3t", "s3cr3t"),
        ("Authorization: Bearer abc.def", "abc.def"),
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("sk-abcdef123456", "abcdef123456"),
    ]
    for text, secret in cases:
        out = A.redact(text)
        assert "****" in out, "没被脱敏：%r -> %r" % (text, out)
        assert secret not in out, "原文残留：%r 里还有 %r" % (out, secret)


def test_plain_text_is_untouched():
    """普通文本不能被改动（误伤会让人关掉脱敏）。"""
    import ai_cli as A

    for text in ("普通文本没有秘密", "y = x + 1;", ""):
        assert A.redact(text) == text, "误伤了普通文本：%r" % (text,)


def test_bare_mention_is_not_redacted():
    """**只提及变量名、没有值**时不该遮 —— 否则日志会被涂得到处是 ****。"""
    import ai_cli as A

    text = "变量名 password 只是提及，没有赋值"
    assert A.redact(text) == text, "无值的提及被误遮：%r" % (A.redact(text),)
