# 交互图出图配方（archify → `flow/figures/`）

本目录存**候选规格**（`*.candidate.json`）。渲染成功的图会被收进 `flow/figures/<dir>/`，
并被 `flow/index.html` 引用；**只留候选、不留产物**是允许的（候选在门外，不影响门禁）。

## 一条命令

```bash
cd <候选所在目录>
node D:\project\archify\archify\bin\archify.mjs finalize architecture \
     candidate.json <输出>.html --quality showcase --json \
     --repo-root e:\matlabc\malabc
```

## 四个必踩项（每一次都在这四处断）

| # | 报错 | 含义 | 修法 |
|---|---|---|---|
| 1 | `meta/repository/revision must match ^[a-fA-F0-9]{40}$` | 不认短 sha | `git rev-parse HEAD` 取完整 40 位 |
| 2 | `repository-evidence/root-required` | 声明了 `sources[]` 就必须让 archify 去核对 | 加 `--repo-root <仓库根>` |
| 3 | `architecture/component-sublabel-overflow` | sublabel 太长，6px 下放不进去 | **sublabel ≤ 12 个汉字宽**（英文按 2 倍算） |
| 4 | `viewer/evidence-path-conflict` | 同一路径已有上次的 browser-check 证据 | 换输出名，或先清 `*.browser-check.json` |

## 入库 `flow/figures/` 的四件套

```
flow/figures/<dir>/
  ├── candidate.json                 ← 规格（locale 必须 zh-CN）
  ├── <name>.html                    ← 产物
  └── <name>.delivery.json           ← 交付回执（FF7 要求，缺则红）
```

同时必须：

1. 在 `flow/index.html` 加一张卡：`<h3><span class="id">F<nn></span>标题</h3>` + `href`；
2. **编号 ≥14 的卡片数 = `figures/` 目录数**（FF4 的数量等式，加一张图加一张卡）；
3. `candidate.json` 是手写物 → **必须 CRLF**（EO1）；
4. 索引页自带 `viewport` + `prefers-color-scheme`，且**不含 `<script>`、不含外链**（FF5）。

## 已有图集

| 编号 | 内容 |
|---|---|
| F30 | 工程级降维平台：五层 × 原子步骤（总览） |
| F31 | MATLAB → MIR：逐语句原子决策 |
| F32 | MIR → C 工程：装配与三条硬边界（含跨文件 call 断点） |
| F33 | C → MIR 反推与四路哈希自证 |

> 出图前先在**仓库外**渲染通过，再收进 `flow/figures/` ——
> 半成品落在受门禁管辖的目录里，会让 FF2/FF3/FF4 同时变红（R722 踩过）。
