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
                   "matlabc-%s.vsix" % pkg.get("version", "0.0.0"))

name = pkg.get("name", "matlabc")
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
<Default Extension=".html" ContentType="text/html"/>
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
ASSET_DIRS = ("syntaxes", "icons", "data")

#: 额外映射进包的文件：**来源在仓库里只有一份**，打包时改个落点。
#: 使用导览的源文件在 `releases/demo/`（和 GIF、JSON 放在一起，方便单独分发），
#: 但扩展要能打开它，所以包内路径是 `extension/media/tour.html`。
#: 不在 `vscode/media` 里放副本 —— 两份同样的 HTML 迟早会分叉。
EXTRA_FILES = (
    (os.path.join(REPO, "releases", "demo", "matlabc-tour.html"),
     "extension/media/tour.html"),
    # 用户手册：**只讲怎么用**，不含发版与实现。挂在包根，由
    # `matlabc: 打开使用说明` 用 Markdown 预览打开（不像导览那样在 media/，
    # 因为它不是网页，交给 VS Code 的预览更合适）。
    (os.path.join(REPO, "releases", "docs", "USER_GUIDE.md"),
     "extension/USER_GUIDE.md"),
    # 同一份手册的 PDF 版：图直接看得见，也方便转发。
    (os.path.join(REPO, "releases", "docs", "matlabc-guide.pdf"),
     "extension/USER_GUIDE.pdf"),
)

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

    # 手册里的示意图：**整目录**映射，与 USER_GUIDE.md 的相对路径
    # （`figures/x.png`）保持一致 —— 手册解开后图能直接显示。
    # 手册与图**同目录**（releases/docs），包内也保持相对结构：
    # extension/USER_GUIDE.md 里写 `figures/x.png`，图就在 extension/figures/。
    _figdir = os.path.join(REPO, "releases", "docs", "figures")
    if os.path.isdir(_figdir):
        for _n in sorted(os.listdir(_figdir)):
            if _n.lower().endswith(".png"):
                z.write(os.path.join(_figdir, _n),
                        "extension/figures/" + _n)

    for src_path, arc in EXTRA_FILES:
        if not os.path.isfile(src_path):
            # **缺了就吵**：导览进不了包，命令点开会是空白页，
            # 而那种失败在打包日志里完全看不见。
            print("MISSING extra file:", src_path)
            continue
        z.write(src_path, arc)

print("built %s %d bytes" % (OUT, os.path.getsize(OUT)))
with zipfile.ZipFile(OUT) as z:
    for n in z.namelist():
        print("  ", n)

# **只保留最新一个安装包**（R374）。
# 仓库里堆了 42 个 vsix（44.6 MB）—— 要旧版本的人应当看 CHANGELOG，
# 而不是克隆一份 150 MB 的仓库。每次打包后清理同目录的其它包，
# **只删自己产出目录里的**，不碰别处。
_out_dir = os.path.dirname(OUT)
_keep = os.path.basename(OUT)
_pruned = 0
try:
    for _n in os.listdir(_out_dir):
        if not _n.lower().endswith(".vsix") or _n == _keep:
            continue
        try:
            os.remove(os.path.join(_out_dir, _n))
            _pruned += 1
        except OSError:
            pass
except OSError:
    pass
if _pruned:
    print("pruned %d older .vsix (only the newest is kept)" % _pruned)

# **只把最新一个入库**（R374）：`.gitignore` 里放一条 `!<当前文件名>`。
# 这样 clone 下来就直接能装，不必先跑构建；旧版本从 CHANGELOG 查，
# 需要时 checkout 对应提交重新打包。规则由脚本维护，避免每次发布手改。
_gi = os.path.join(_out_dir, ".gitignore")
try:
    io.open(_gi, "w", encoding="utf-8", newline="").write(
        u"# 离线安装包是构建产物（每个约 1MB）。\n"
        u"# **只把最新一个入库**：clone 下来就能装，不必先跑构建；\n"
        u"# 旧版本留在 CHANGELOG 里，需要时 checkout 对应提交重新打包。\n"
        u"*.vsix\n"
        u"!%s\n" % _keep)
    print("gitignore allows only %s" % _keep)
except OSError as _exc:
    print("WARN 无法写 %s：%r" % (_gi, _exc))

# 安装命令**按平台给**（R365）：这个脚本本身两边都能跑，但 `code.cmd`
# 只在 Windows 上存在；Linux/macOS 上写 `code`。照抄错的命令会得到
# "command not found"，而人第一反应是"包做坏了"。
if os.name == "nt":
    print("install: code.cmd --install-extension \"%s\"" % OUT)
else:
    print("install: code --install-extension \"%s\"" % OUT.replace("\\", "/"))
