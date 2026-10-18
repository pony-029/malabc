# -*- coding: utf-8 -*-
"""手工构造 .vsix（本质是 zip + 一个 manifest），不依赖 node/vsce。

R204：**把分析器一起打包**。

之前 `.vsix` 里只有 JS，`matlabc_lsp.py` 要用户自己在设置里指路 ——
实测用户就是卡在这一步（截图里那条「找不到 matlabc_lsp.py」）。

现在把 `matlabc_lsp.py` + `matlabc.py` + `analyzer/` 都放进
`extension/`，扩展启动时优先用**自己带的**那份，**零配置**。
`E:\matlabc\malabc` 那种工作区仍然可以用自己的路径（设置里显式指定时优先）。
"""
import io
import json
import os
import zipfile

# **路径从脚本位置推导**（R332）：以前写死 `e:\matlabc\malabc` 与
# `C:\temp`，换一台机器或换一个检出位置就跑不了。归档目录也要跟着仓库走，
# 否则「离线包放哪」又变成一句口头约定。
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "vscode")

with io.open(os.path.join(SRC, "package.json"), "r", encoding="utf-8") as fh:
    pkg = json.load(fh)

OUT_DIR = os.path.join(REPO, "releases", "vsix")
OUT = os.path.join(OUT_DIR,
                   "matlabc-lsp-%s.vsix" % pkg.get("version", "0.0.0"))

name = pkg.get("name", "matlabc-lsp")
version = pkg.get("version", "0.1.0")
publisher = pkg.get("publisher", "malabc")
display = pkg.get("displayName", name)
desc = pkg.get("description", "")
engine = (pkg.get("engines") or {}).get("vscode", "^1.80.0")

MANIFEST = u"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="%s" Version="%s" Publisher="%s" />
    <DisplayName>%s</DisplayName>
    <Description>%s</Description>
    <Tags>matlab,lsp,diagnostics,definition,references</Tags>
    <Categories>Programming Languages,Linters</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="%s" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
  </Assets>
</PackageManifest>
""" % (name, version, publisher, display, desc, engine)

CONTENT_TYPES = u"""<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
 <Default Extension=".png" ContentType="image/png"/>
<Default Extension=".gif" ContentType="image/gif"/>
  <Default Extension=".py" ContentType="text/x-python"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""

JS_FILES = ("package.json", "extension.js", "lspClient.js",
            "language-configuration.json", "README.md", "CHANGELOG.md",
            "icon.png")

#: 扩展侧的静态资源目录（TextMate 语法等）。R206 之前漏了它，
#: 于是「注册了 matlab 语言却没有语法」——VSCode 用空语法覆盖掉
#: 原来别处提供的高亮，整个文件变成白字。
ASSET_DIRS = ("syntaxes", "icons", "data", "media")

#: 分析器侧：LSP 入口 + CLI + 包目录（`analyzer/` 只有 3 个源文件）
#: `matlabc.py` 的依赖链是**逐步暴露**的：先缺 `frontends`，补上后缺
#: `pyast_frontend`……与其一个个试，不如把根目录所有 `.py` 都带上。
#: 代价约 2 MB（压缩后 ~250 KB），换来「装了就一定能跑」。
PY_FILES = tuple(sorted(
    n for n in os.listdir(REPO)
    if n.endswith(".py") and os.path.isfile(os.path.join(REPO, n))
))
#: 同上；`tests` / `tools` / `ci-examples` 不进包（不是运行时需要的）。
PY_DIRS = ("analyzer", "binfmt", "frontends", "harness",
           "renderers", "translate")

SKIP_DIRS = ("__pycache__",)


def add_bytes(z, path, arcname):
    with io.open(path, "rb") as fh:
        z.writestr(arcname, fh.read())


if os.path.exists(OUT):
    os.remove(OUT)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", CONTENT_TYPES.encode("utf-8"))
    z.writestr("extension.vsixmanifest", MANIFEST.encode("utf-8"))

    for fn in JS_FILES:
        p = os.path.join(SRC, fn)
        if not os.path.isfile(p):
            print("skip missing:", fn)
            continue
        z.write(p, "extension/" + fn)

    for fn in PY_FILES:
        p = os.path.join(REPO, fn)
        if not os.path.isfile(p):
            print("skip missing:", fn)
            continue
        z.write(p, "extension/" + fn)

    for d in ASSET_DIRS:
        base = os.path.join(SRC, d)
        if not os.path.isdir(base):
            print("skip missing dir:", d)
            continue
        for dirpath, dirnames, names in os.walk(base):
            for n in sorted(names):
                full = os.path.join(dirpath, n)
                rel = os.path.relpath(full, SRC).replace("\\", "/")
                z.write(full, "extension/" + rel)

    for d in PY_DIRS:
        base = os.path.join(REPO, d)
        for dirpath, dirnames, names in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for n in sorted(names):
                if not n.endswith(".py"):
                    continue
                full = os.path.join(dirpath, n)
                rel = os.path.relpath(full, REPO).replace("\\", "/")
                z.write(full, "extension/" + rel)

print("built %s %d bytes" % (OUT, os.path.getsize(OUT)))
with zipfile.ZipFile(OUT) as z:
    for n in z.namelist():
        print("  ", n)
