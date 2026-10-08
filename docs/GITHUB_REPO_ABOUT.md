# GitHub 仓库 About 面板 —— 待粘贴内容

> 本文件是**给 GitHub 仓库设置页用的现成文案**，不是代码文档。
> 背景：GitHub 仓库首页右侧那个 About 面板（截图里显示
> 「*No description, website, or topics provided.*」）需要填写三样东西：
> **Description / Website / Topics**。填完之后，搜索结果、社交卡片、
> 目录列表里都会用这段简介 —— 它是**唯一一处比 README 更早被人看到**的文字。

---

## 1. Description（简介）

GitHub 限制 **350 字符**以内。下面这条 **148 字符**，中英各一版，**推荐用英文**
（英文简介能被更广的搜索命中，且与 README 主语言一致）。

### 推荐（英文，148 chars）

```
Static analysis & deterministic auto-fix for MATLAB / C·C++ / Python / JS — plus PE/ELF/Mach-O binary and GPU (CUDA / ROCm / Vulkan) analysis. Zero dependencies.
```

### 备选（中文，74 字）

```
MATLAB / C·C++ / Python / JS 静态分析与确定性自动修复引擎，附带 PE/ELF/Mach-O 二进制与 CUDA / ROCm / Vulkan GPU 内容分析。零依赖、默认离线。
```

---

## 2. Website（可选）

留空即可。若要填，建议指向仓库内最有信息量的一页，而不是外部站点：

```
https://github.com/pony-029/malabc/blob/main/docs/matlabc_USAGE.md
```

---

## 3. Topics（主题标签）

GitHub 允许 **最多 20 个**，每个 ≤ 50 字符，只能小写字母 / 数字 / 连字符。
下面正好 20 个，按「语言 → 能力 → 生态 → 本仓独有」的顺序排列：

```
matlab
static-analysis
c
cpp
python
javascript
call-graph
code-visualization
sarif
ci
mcp
binary-analysis
elf
pe
cuda
rocm
spir-v
linter
code-quality
zero-dependency
```

> 为什么把 `cuda` / `rocm` / `spir-v` / `elf` / `pe` / `binary-analysis` 也列上：
> 这是本仓与同类 MATLAB 静态分析工具**最不一样**的地方 —— 它能把源码侧
> 「未解析调用」与二进制侧「导出符号 / GPU 算子」对账（见 README 的
> *Binary & GPU Analysis* 一节）。标签里体现这一点，才有人搜得到。

---

## 4. 如何应用

### 方式 A：网页手动填写（本机推荐）

仓库页右上角 **⚙（齿轮）** → 填 Description / Website / Topics → **Save changes**。

### 方式 B：用 GitHub API 一键设置

需要一个带 `repo` 权限的 Personal Access Token（本机 **HTTPS:443 被墙**、
且**未安装 `gh`**，所以只能在你网络可达的环境里执行）：

```bash
TOKEN=<你的 PAT>
OWNER=pony-029
REPO=malabc

curl -sS -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$OWNER/$REPO" \
  -d '{"description":"Static analysis & deterministic auto-fix for MATLAB / C·C++ / Python / JS — plus PE/ELF/Mach-O binary and GPU (CUDA / ROCm / Vulkan) analysis. Zero dependencies."}'

curl -sS -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$OWNER/$REPO/topics" \
  -d '{"names":["matlab","static-analysis","c","cpp","python","javascript","call-graph","code-visualization","sarif","ci","mcp","binary-analysis","elf","pe","cuda","rocm","spir-v","linter","code-quality","zero-dependency"]}'
```

### 方式 C：社交预览图（可选，锦上添花）

GitHub 会为仓库生成一张社交卡片。若想自定义，在仓库里放
`.github/social-preview.png`（1280×640）；不提供就用默认。

---

## 5. 顺带核对：About 面板里的自动项是否都已满足

| 面板项 | 状态 | 依据 |
| --- | --- | --- |
| **Readme** | ✅ 已满足 | `README.md` 存在（中文版 `README_CN.md`，两版按章节一一对应） |
| **MIT license** | ✅ 已满足 | 根目录 `LICENSE` 为 MIT 正文（英文正本，逐字未改）；`LICENSE_CN` 为中文译本。GitHub 的 licensee 靠 **许可正文**识别，所以正文一个字都不能动 —— 本项目专属说明一律放在正文之后的 *Appendix* 里，并明确标注「不修改上述条款」 |
| **Contributing** | ✅ 已满足 | `CONTRIBUTING.md` 存在 |
| **Description / Website / Topics** | ⬜ **待填** | 本文件第 1–3 节即现成文案 |
