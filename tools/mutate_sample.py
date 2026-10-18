# -*- coding: utf-8 -*-
"""变异抽样：把实现**改坏一处**，看判据会不会红。

为什么需要它
============

一套判据最危险的状态不是「红」，而是「**永远绿**」—— 它和没有判据等价，
但看起来更让人放心。而「加了判据」这件事本身无法证明它有效：

    def test():
        assert field_refs("x")["writes"] == writes      # 看起来对
        # 但若把实现里的 writes 换成 reads，这条仍然过？

所以抽样做**变异测试**：复制一份 `matlabc_lsp.py`，把某处的语义改坏，
再跑对应判据组。**判据红了才算数**；没红说明它挡不住这种退化。

三条纪律
--------

1. **绝不改仓库里的文件**：改的是临时副本，跑完即弃。
2. 每个变异都要**断言替换真的发生了**（否则样本没改动，判据当然不红）。
3. 判据红还不够，**要红在对应的那条**（按判据 id 找），
   否则可能只是别处先崩了 —— 那说明不了这一条有效。

用法：
    python tools/mutate_sample.py

退出码：
    0  = 每个变异都被对应判据抓到
    1  = 有变异"存活"（判据没红，或红在别的判据上）
    2  = 缺输入（找不到判据脚本或被测文件）
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SELFTEST = os.path.join(HERE, "lsp_selftest.py")
LSP = os.path.join(ROOT, "matlabc_lsp.py")

#: (名字, 原文, 改坏成, 组, 期望红的判据 id 前缀)
MUTATIONS = [
    ("字段读写不再区分",
     'writes = norm(ent.get("writes"))',
     'writes = norm(ent.get("reads"))',
     "--doc", "doc/field-refs-split"),
    ("字段基名恒为空",
     '"bases": bases}',
     '"bases": []}',
     "--doc", "doc/field-refs-bases"),
    ("跨语言不再报告未解析",
     '"unresolved": sorted(still),',
     '"unresolved": [],',
     "--doc", "doc/cbridge-lists-unresolved"),
]


def run_mutation(name, old, new, group, expect_id):
    """复制副本 -> 改坏 -> 跑判据组 -> 判定。返回 (ok, detail)。

    ⚠ 副本必须放在**仓库根目录**（换个文件名），不能放临时目录：
    `matlabc_lsp.py` 启动时要 `import analyzer` / `import matlabc`，
    而子进程的 `sys.path[0]` 是**脚本所在目录** —— 放临时目录就 import 不到，
    服务端起不来，判据会以 OSError 崩掉。第一版就是这么"全绿"的：
    它把崩溃当成了"没红"。
    """
    dst = os.path.join(ROOT, "_mut_matlabc_lsp.py")
    try:
        src = io.open(LSP, "r", encoding="utf-8").read()
        if old not in src:
            return False, "变异未应用：原文在 %s 里找不到（样本过期）" % (
                os.path.basename(LSP),)
        io.open(dst, "w", encoding="utf-8", newline="").write(
            src.replace(old, new, 1))

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["MALABC_LSP"] = dst
        log = os.path.join(tempfile.gettempdir(), "mut_out_%d.txt" % os.getpid())
        with io.open(log, "w", encoding="utf-8") as fh:
            try:
                subprocess.run([sys.executable, SELFTEST, group],
                               cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=fh, stderr=subprocess.STDOUT,
                               env=env, timeout=300)
            except subprocess.TimeoutExpired:
                return False, "判据组超时（300s）"
        out = io.open(log, "r", encoding="utf-8", errors="replace").read()
        if "FAIL" not in out:
            return False, "变异存活：判据全绿，说明它挡不住这种退化"
        hit = [ln for ln in out.splitlines()
               if "FAIL" in ln and expect_id in ln]
        if not hit:
            first = [ln for ln in out.splitlines() if "FAIL" in ln][:1]
            return False, "红了，但不是 %s（先红的是：%s）" % (
                expect_id, (first[0].strip() if first else "?"))
        return True, hit[0].strip()[:90]
    finally:
        # 副本用完就删：它躺在仓库根下，留着会被 git status / 门看见。
        try:
            os.remove(dst)
        except OSError:
            pass


def main():
    for p in (SELFTEST, LSP):
        if not os.path.isfile(p):
            print("mutate_sample: 缺输入（%s）" % p)
            return 2
    bad = 0
    for name, old, new, group, expect in MUTATIONS:
        ok, detail = run_mutation(name, old, new, group, expect)
        print("  [%s] %-16s %s" % ("抓到" if ok else "存活", name, detail))
        if not ok:
            bad += 1
    print("mutate_sample: %d 个变异，抓到 %d 个%s"
          % (len(MUTATIONS), len(MUTATIONS) - bad,
             "" if not bad else "，**%d 个存活**" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
