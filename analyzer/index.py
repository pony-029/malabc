# -*- coding: utf-8 -*-
"""analyzer/index.py —— 文件级增量索引：只回答「哪些文件变了」。

为什么它是 LSP 的前置：全量分析 62,704 个文件要 600+ 秒，IDE 里每保存一次
都重跑是不可用的。索引先解决「变化集合」，上层再决定重解析哪些。

设计上的三个克制：
- **不解析**。它只算 `(mtime_ns, size, sha256)` 指纹，解析仍由调用方做。
- **不缓存解析结果**。缓存解析结果会引出"缓存与代码版本不一致"这一类 bug；
  先把"哪些变了"做对，再讨论缓存的失效策略。
- **mtime 只是快速路径**。同 mtime 但内容不同（`touch -r`、某些 VCS 检出）
  必须被 `sha256` 抓到 —— 所以两者都存，`mtime+size` 相同才跳过读文件。

用法：

    idx = Index("tests/sample_m")
    d = idx.refresh()        # 首次：全部 added
    d = idx.refresh()        # 立即再跑：全部 unchanged
    d.changed, d.added, d.removed, d.unchanged   # 四个元组，元素是相对路径
"""
import hashlib
import os
from collections import namedtuple

Diff = namedtuple("Diff", "added changed removed unchanged")

_CHUNK = 1 << 20


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


class Index(object):
    """一个目录的指纹表。`refresh()` 返回自上次以来的四类变化。"""

    def __init__(self, root, exts=(".m",)):
        self.root = str(root)
        self.exts = tuple(e.lower() for e in exts)
        self._fp = {}          # rel -> (mtime_ns, size, sha256)

    # ---- 扫描 ----------------------------------------------------------
    def _walk(self):
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() in self.exts:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                    out.append((rel, full))
        return out

    def _fingerprint(self, rel, full, old):
        """mtime+size 不变就复用旧 sha（快速路径）；否则重算。"""
        try:
            st = os.stat(full)
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        if old is not None and old[0] == key[0] and old[1] == key[1]:
            return (key[0], key[1], old[2])
        try:
            return (key[0], key[1], _sha256(full))
        except OSError:
            return None

    # ---- 主入口 --------------------------------------------------------
    def refresh(self):
        """重新扫描，返回 `Diff`；同时把内部指纹表更新成当前状态。"""
        seen = {}
        for rel, full in self._walk():
            fp = self._fingerprint(rel, full, self._fp.get(rel))
            if fp is not None:
                seen[rel] = fp

        added, changed, unchanged = [], [], []
        for rel, fp in seen.items():
            old = self._fp.get(rel)
            if old is None:
                added.append(rel)
            elif old[2] != fp[2]:
                changed.append(rel)
            else:
                unchanged.append(rel)
        removed = [rel for rel in self._fp if rel not in seen]

        self._fp = seen
        return Diff(sorted(added), sorted(changed), sorted(removed),
                    sorted(unchanged))

    def paths(self, rels):
        """相对路径 → 绝对路径（给调用方做解析）。"""
        return [os.path.join(self.root, r.replace("/", os.sep)) for r in rels]

    def __len__(self):
        return len(self._fp)
