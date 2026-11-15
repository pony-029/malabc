# -*- coding: utf-8 -*-
"""`binfmt/macho.py`：**依赖指令的归类**（用合成 thin 夹具，不需要真实 Mach-O 样本）。

Mach-O 的依赖信息分散在六种 load command 里，归错类的后果都是"报表看起来正常"：

* `LC_ID_DYLIB` 是**本库的身份**（install name），不是依赖 —— 把它当依赖，
  每个 dylib 都会"依赖自己"；
* `LC_LOAD_WEAK_DYLIB`（缺了也能跑）也是依赖，漏掉会让"缺库"报告漏一条；
* `@rpath/…` / `@loader_path/…` 是**安装名语义**，必须原样保留 ——
  过早解析成绝对路径，就再也无法和源码侧的引用对上。

本机没有 Mach-O 样本，所以用 32 字节头 + 手工 load command 造夹具。
"""
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

MH_MAGIC_64 = 0xFEEDFACF
LC_ID_DYLIB = 0xD
LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018      # 带 LC_REQ_DYLD 高位
CPU_ARM64 = 0x0100000C


def _dylib_cmd(cmd, name):
    raw = name.encode() + b"\x00"
    size = 24 + len(raw)
    size += (-size) % 8                      # 64 位下按 8 字节对齐
    body = struct.pack("<IIIIII", cmd, size, 24, 0, 0x10000, 0x10000)
    return body + raw + b"\x00" * (size - 24 - len(raw))


def _macho(cmds, filetype=6):
    body = b"".join(cmds)
    hdr = struct.pack("<IIIIIIII", MH_MAGIC_64, CPU_ARM64, 0, filetype,
                      len(cmds), len(body), 0, 0)
    return hdr + body


def _parse(cmds, filetype=6):
    """把构造好的字节写进临时文件并 `parse()`。"""
    from binfmt import macho as M

    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="macho_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    try:
        p = os.path.join(d, "libx.dylib")
        with open(p, "wb") as f:
            f.write(_macho(cmds, filetype))
        return M.parse(p)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_id_dylib_is_identity_not_dependency():
    """`LC_ID_DYLIB` 是本库的 install name，**不能**算成依赖。"""
    rep = _parse([_dylib_cmd(LC_ID_DYLIB, "@rpath/libself.dylib")])
    kinds = [d.kind for d in rep.dependencies]
    assert "load_dylib" not in kinds, "把自己当成了依赖：%r" % (kinds,)
    assert "id_dylib" in kinds, "install name 没被认出来：%r" % (kinds,)


def test_load_dylib_keeps_install_name():
    """`LC_LOAD_DYLIB` → `load_dylib`，且 `@rpath` 前缀**原样保留**。"""
    rep = _parse([_dylib_cmd(LC_LOAD_DYLIB, "@rpath/libbar.dylib")])
    deps = [d for d in rep.dependencies if d.kind == "load_dylib"]
    assert len(deps) == 1, "强依赖没被记下来：%r" % ([d.kind for d in rep.dependencies],)
    assert deps[0].name == "@rpath/libbar.dylib", \
        "安装名被改写了（无法再与源码侧对上）：%r" % (deps[0].name,)


def test_weak_dylib_still_counts_as_dependency():
    """弱依赖（缺了也能跑）**仍然是依赖** —— 漏掉会让"缺库"报告少一条。"""
    rep = _parse([_dylib_cmd(LC_LOAD_WEAK_DYLIB, "@rpath/libweak.dylib")])
    names = [d.name for d in rep.dependencies if d.kind == "load_dylib"]
    assert "@rpath/libweak.dylib" in names, \
        "弱依赖没被归为 load_dylib：%r" % ([d.kind for d in rep.dependencies],)


def test_no_dylib_commands_no_deps():
    """**反向**：没有任何依赖指令时不能凭空造出依赖（也不能崩）。"""
    rep = _parse([], filetype=1)             # 1 = MH_OBJECT
    assert list(rep.dependencies) == [], \
        "无指令却报出依赖：%r" % ([d.name for d in rep.dependencies],)
    assert rep.bits == 64 and rep.arch == "aarch64", \
        "头信息解析不对：%r/%r" % (rep.bits, rep.arch)
