<div align="center">

<img src="docs/assets/banner.jpg" alt="malabc" width="820">

# malabc

**Static analysis and deterministic auto-fix engine — MATLAB / Simulink, C·C++ (subset), Python and JavaScript, plus PE / ELF / Mach-O binaries and the CUDA · ROCm · Vulkan GPU content embedded in them**

Turn "reading code" into a "workbench": it does not just map call relationships, it
tells you **where the risks are, how severe they are, how to fix them, and whether a
fix patch / test stub / PR draft can be generated in one shot** — and wires every
conclusion into a **CI quality gate**.

<br>

![Python](https://img.shields.io/badge/Python-3.6.5%2B-3776AB?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-0%20(stdlib%20only)-brightgreen)
![Languages](https://img.shields.io/badge/languages-MATLAB%20%7C%20C%20%7C%20Python%20%7C%20JS-blue)
![Binaries](https://img.shields.io/badge/binaries-PE%20%7C%20ELF%20%7C%20Mach--O-blueviolet)
![GPU](https://img.shields.io/badge/GPU-CUDA%20%7C%20ROCm%20%7C%20Vulkan-orange)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Offline](https://img.shields.io/badge/offline-first-yes-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![CI](https://github.com/pony-029/malabc/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/version-1.16.71-informational)

[Quick Start](#quick-start) · [Core Capabilities](#core-capabilities) · [Architecture](#architecture)
· [Binary & GPU](#binary--gpu-analysis---binary) · [Command Cheatsheet](#command-cheatsheet)
· [CI Gate](#ci-quality-gate) · [Quality Gates](#quality-gates-self-verifying) · [中文文档](README_CN.md)
· [License](#license)

</div>

---

## What Problem It Solves

| Scenario | The old way | With `matlabc` |
| --- | --- | --- |
| Taking over an unfamiliar MATLAB project | Global search + manual jumping, three days to map entry points | `--browse` builds a clickable site; see the whole picture in 10 minutes |
| "Who is affected if I change this function?" | Guess by experience; miss something and find out after the change | Impact / dependency transitive closure + operator impact analysis |
| "Any hidden risks in this code?" | Run MATLAB to find out | Uninitialized / type mismatch / dead code / shape mismatch / taint, all statically |
| "How do I change it safely?" | Edit by hand and risk new bugs | `--gen-apply-patch` generates a deterministic, self-verified patch |
| "How do we stop the rot?" | Rely on reviewers' diligence | SARIF + exit code + trend baseline, enforced in CI |
| "This call resolves to nothing — is it our bug or a library's?" | Guess, or grep the disk | `--binary` + `--binary-symbols`, or the single-command `--binary-attach`: every unresolved name is attributed to a library, a GPU kernel, or `missing` |

> **Zero dependencies, no MATLAB needed, offline by default**: only the Python standard
> library is used; MATLAB / Octave is not required, and no network requests are made
> (offline-first, no CDN references in artifacts) — fully usable on an intranet.

---

## Core Capabilities

```mermaid
mindmap
  root((matlabc))
    Structure Mapping
      Function/class/script parsing
      Call graph
      Class inheritance and collaboration
      Impact/dependency transitive closure
    Interactive Site
      Click-to-jump to definitions
      Full-text/regex search
      --watch daemon re-analysis
      Large-repo --max-nodes guard
    Static Checks
      Uninitialized
      Type mismatch
      Dead code
      Shape mismatch
      Cross-file taint propagation
    Metrics & Governance
      Technical-debt ranking
      Comment completeness
      Duplicate-code fingerprints
      Metric trend Sparkline
    Fix Loop
      Deterministic patch
      Self-verification
      Test-stub generation
      PR description draft
    CI Gate
      SARIF 2.1.0
      Exit-code gate
      Trend/baseline comparison
      One-click CI templates
    Binary & GPU
      PE / ELF / Mach-O containers
      Import table / DT_NEEDED
      Export symbols (dynsym)
      CUDA fatbin → cubin kernel names
      AMD HSA code object
      Vulkan SPIR-V entry points
      Source-side attribution
```

### Multi-Language Support

| Language | Flag | Key capabilities |
| --- | --- | --- |
| **MATLAB** (default) | — | Functions / classes / scripts / nested functions / `arguments` blocks / struct fields / global state, fully parsed |
| **C / C++** | `--lang c`（alias `--lang cpp`） | `.c/.h/.cc/.cpp/.cxx/.hpp/.hh/.hxx`; function calls / `#include` cross-file dependency edges / heuristics for uninitialized pointers, out-of-bounds, use-after-free, double-free, buffer overflow. **Preprocessor-aware for literal `#if 0`**: dead blocks are not analysed (line numbers preserved) while `#else` branches stay live — `#ifdef` / `#if defined` are deliberately left alone rather than guessed. C++ is parsed as a **C subset** (templates / classes / namespaces are not guaranteed) — a disclosed degradation, never a silent drop |
| **Python** | `--lang py` | Functions / calls / static checks (`py_unused_import` / `py_dup_params` / `py_too_many_params` / `py_missing_doc` / `py_eval_usage` / `py_sql_injection`), including a **Python 3.6 syntax-compatibility gate** (`--check-py36`) |
| **JavaScript** | `--lang js` | Functions / calls / static checks (`js_unused_import` / `js_global_var` / `js_too_many_params` / `js_missing_doc` / `js_dangerous_call` / `js_unused_var` / `js_prototype_pollution`) |
| **Mixed (MEX bridge)** | `--mixed` | MATLAB ↔ C cross-language call edges |

**Language boundary (explicit, not silent).** `--lang` covers MATLAB / C·C++ / Python / JavaScript only. TypeScript, Rust, Go, Java, Kotlin, C#, Swift, Scala, Ruby and PHP have **no frontend**: when such files exist but the requested language finds none, the CLI prints a `[warn]` line to stderr naming the language and the files it skipped, instead of quietly reporting `0 files / 0 functions`. A cross-language operator label is only listed in the operator catalog if some code path actually emits it; operators that are deliberately not implemented are registered in `_UNIMPLEMENTED_KINDS` with a stated reason, and `tools/check_operator_impl.py` fails the build if the two ever diverge.

### Binary & GPU Analysis (`--binary`)

Source-side analysis can tell you *that* a call is unresolved. It cannot tell you *why*.
`--binary` closes that loop: point it at the libraries your code actually links against, and
every unresolved name gets an owner.

```mermaid
flowchart LR
    subgraph SRC["Source side"]
        S1["matlabc --json out.json<br/>unresolved call sites"]
    end
    subgraph BIN["Binary side"]
        B1["libfoo.so / bar.dll<br/>PE · ELF · Mach-O"]
        B2["dynamic dependencies<br/>DT_NEEDED / import table"]
        B3["export symbols<br/>dynsym / export directory"]
        B4["embedded GPU content<br/>CUDA fatbin · HSA code object · SPIR-V"]
    end
    S1 --> AT["attribution engine<br/>binfmt/attribute.py"]
    B2 --> AT
    B3 --> AT
    B4 --> AT
    B1 --> B2
    B1 --> B3
    B1 --> B4
    AT --> R1["library<br/>explained by libfoo.so"]
    AT --> R2["gpu_kernel<br/>it is a CUDA / AMD kernel"]
    AT --> R3["missing<br/>genuinely unresolved"]
```

```bash
# What does this library depend on, and what does it export?
python matlabc.py --binary libfoo.so

# Ask the source side and the binary side the same question
python matlabc.py myproj/ --json out.json                    # 1) find unresolved calls
python matlabc.py --binary libcublas.so.12 --binary-symbols out.json   # 2) attribute them

# Machine-readable, for wiring into your own pipeline
python matlabc.py --binary a.dll,b.so --binary-json -
```

| Backend | Where it hides | How it is found | What comes out |
| --- | --- | --- | --- |
| **CUDA** | PE `.nv_fatb` · ELF `.nv_fatbin` · PE/ELF `.nvFatBi` / `.nvFatBin` | fatbin magic `0xba55ed50`; cubin located through the `.text._Z…` section-name table | kernel names + demangled forms, SM targets, code-object counts |
| **ROCm / HIP** | PE/ELF `.hip_fat` / `.hipFatBin` | HSA code object header (`e_ident[7]` = 64, `e_machine` = 224) | trusted code-object count (names are **not** guessed) |
| **Vulkan** | **no dedicated section** — SPIR-V sits in `.rdata` | raw magic scan for `0x03022307` (`OpEntryPoint` decoding) | entry-point names, module count |
| **PTX** | inside the same fatbin segment | `.entry <name>(` with the parenthesis required | *usually nothing* — see the honest limits below |

> **Field note — the 8-byte trap.** PE section names are hard-truncated to eight bytes. The very
> same CUDA section is `.nv_fatbin` in an ELF but `.nv_fatb` in a PE; `.nvFatBin` becomes
> `.nvFatBi`; AMD's `.hip_fatbin` becomes `.hip_fat`. A matcher that only knows the full spelling
> reports **zero** GPU content in every Windows binary — silently, and with no error. Both
> spellings are matched.

> **Field note — cubins are not standard ELF.** A cubin sets `e_type = 0x8000`,
> `e_machine = 0x100`, and parks a `0xCAFE…` sentinel in `e_shoff`. The only trustworthy
> discriminators are `e_ident[7]` (`ELFOSABI_CUDA` = 51) and `e_ident[8]`. Counting `\x7fELF`
> occurrences is a *cheap* signal and is reported under a different field name
> (`suspect_code_objects`) than the strict one (`confidence_code_objects`), so the two can never
> be confused.

**Honest limits (measured, not guessed).**

- **PTX barely yields kernel names.** Requiring `.entry <name>(` on a 692 MB real driver
  distribution leaves ~2 usable names; the rest of the `.entry ` hits are binary metadata. The
  CUDA kernel-name path that actually works is the `.text._Z…` **section-name table** inside each
  cubin — measured **171** distinct kernel names in one vendor BLAS library and **59** in another,
  100% demangle-able.
- **Mach-O is implemented but unvalidated.** No Mach-O sample exists on the development machine;
  the parser says so in the report's `notes` instead of pretending.
- **"Unparseable" is a first-class state.** A GPU blob with no extractable content is reported as
  `NOT-PARSEABLE` **with a written reason** — never as a silent `0 kernels`.
- **Truncation is always visible.** `--binfmt-scan-cap` (default 64 MiB) bounds the scan; when it
  bites, the report prints `[TRUNCATED]`.
- **Run-time binding is out of scope.** `dlopen` / `LoadLibrary` / `dlsym` / `LD_PRELOAD` are not
  traced, and `Makefile` / `CMakeLists.txt` link intent is not parsed (`-lfoo` is only used as a
  candidate-name hint).

#### One command instead of two: `--binary-attach`

`--binary` **short-circuits** — it inspects the binary and exits. `--binary-attach` deliberately
does **not**: it runs the normal source analysis, and then attributes the unresolved calls it just
found — in a single invocation, with no intermediate JSON to shuttle around.

```mermaid
flowchart TB
    subgraph TWO["--binary + --binary-symbols · two steps"]
        T1["step 1<br/>matlabc myproj --json out.json"] --> T2["out.json"]
        T2 --> T3["step 2<br/>matlabc --binary lib.so --binary-symbols out.json"]
    end
    subgraph ONE["--binary-attach · one step"]
        O1["matlabc myproj --binary-attach lib.so --json out.json"]
        O2["same pass: analyse sources + attribute unresolved + write JSON"]
        O1 --> O2
    end
```

| | `--binary` | `--binary-attach` |
| --- | --- | --- |
| Source analysis in the same call | no — binary only | **yes** — then attributes |
| Where the names come from | a `--binary-symbols` file you built earlier | the source side, automatically |

```bash
# One command: analyse myproj, then attribute its unresolved calls against libblas.so
python matlabc.py myproj/ --binary-attach libblas.so --json out.json
```

Only the binaries you explicitly pass are consulted. A library you did **not** pass yields
`missing`, never a guess — a false positive would launder a real defect into "it came from some
library", which is worse than no attribution at all. In JSON the result lands in
`unresolved_attribution` (`{summary, rows}`), and that key is **absent** when the flag is not
given — no empty shell that downstream code could mistake for "attributed, but nothing matched".

When a name still lands in `missing`, it goes one step further: it reads the project's
`Makefile` / `CMakeLists.txt` and lists their **literal** link intents (`-lblas` → candidate
`libblas.so`, `find_package(BLAS)` → a hint too), so you can see *which library to pass next*.
Variable-expanded flags such as `-l$(X)` are reported as an explicit note, never guessed.

### Static Check Rules

| Rule | Description |
| --- | --- |
| `uninitialized` | Read-before-write local variables (distinguishes "uninitialized / maybe uninitialized"; blocks CI only on high confidence) |
| `type_mismatch` | Inconsistent types for the same variable (e.g. a matrix variable assigned a scalar) |
| `dead_code` | Unreachable code after `return` + always-false `if` branches |
| `shape_mismatch` | `A*B` / `A+B` / `A-B` dimension-constraint violations |
| `tainted_sink` | Cross-file taint: user input / file / network → dangerous sinks such as `system` / `eval` / `fprintf` |
| `py_eval_usage` | `--lang py`: bare `eval()` / `exec()` inside a function (code injection / sandbox escape) |
| `py_sql_injection` | `--lang py`: SQL built by concatenation / `%` / `.format()` and then handed to `execute()`; parameterised calls are not reported |
| `c_double_free` | `--lang c`: the same pointer freed twice with no reassignment in between |
| `c_buffer_overflow` | `--lang c`: unbounded `strcpy`/`strcat`/`sprintf`/`gets` (or `memcpy`/`strncpy` without `sizeof(buf)`) into a fixed-size buffer |
| `js_dangerous_call` | `--lang js`: `eval` / `new Function` / `document.write` / `innerHTML` assignment / `insertAdjacentHTML` / string-timer |
| `js_unused_var` | `--lang js`: a simple local declaration never referenced again in the function body |
| `js_prototype_pollution` | `--lang js`: `__proto__` writes, `prototype[<variable>] =`, `constructor.prototype`, or a for-in merge that writes `target[key]` |

**Four levels of warning suppression** (written as source comments, without changing business semantics):

```matlab
% analyzer:ignore uninitialized                 % (1) File level: ignore the whole file
% analyzer:ignore type_mismatch x -- legacy      % (2) Name level: only variable x, reason optional
% analyzer:ignore-next-line shape_mismatch        % (3) Line level: next line only
% analyzer:disable uninitialized                  % (4) Range level: ignore everything inside the block
y = a + b;
% analyzer:enable uninitialized                   %     ↑ end of range
```

---

## Architecture

```mermaid
flowchart TB
    subgraph IN["Input Layer"]
        A1[".m / .c / .py / .js<br/>project directory"]
        A2["analyzer_config.json<br/>or --from-json snapshot"]
    end
    subgraph CORE["matlabc.py · single-file layered kernel"]
        B1["Lexical layer<br/>scrub_source / _logical_statements"]
        B2["Parser layer<br/>parse_file / analyze_calls / resolve_call"]
        B3["Data layer<br/>MatlabFunction / MatlabClass / MatlabFile"]
        B4["Analysis layer<br/>impact · dependency · risk metrics<br/>static checks + taint + duplicate fingerprints"]
        B5["Render layer<br/>render_* (report/browse/json/sarif)"]
        B1 --> B2 --> B3 --> B4 --> B5
    end
    subgraph OUT["Output Layer"]
        C1["Markdown / HTML / Mermaid / DOT"]
        C2["Browsable site --browse"]
        C3["JSON / XML / Doxygen XML"]
        C4["SARIF 2.1.0 / gate snapshot"]
        C5["Patch / test stub / PR draft"]
    end
    subgraph APP["Entry Layer"]
        D1["matlabc.py · CLI analyzer"]
        D2["matlabc_ask.py · Q&A"]
        D3["matlabc_flow.py · fix loop"]
        D4["gui.py · tkinter desktop GUI"]
        D5["matlabc_boot.py · unified entry/packaging"]
    end
    A1 --> B1
    A2 --> B4
    B5 --> C1 & C2 & C3 & C4 & C5
    D1 & D2 & D3 & D4 --> CORE
    D5 --> D1 & D2 & D3 & D4
    C4 --> E1{"CI gate<br/>exit code 0/1"}
```

**Directory structure**

```
malabc/
├─ matlabc.py          # Core analyzer + report rendering (CLI main, ~29k lines, zero deps)
├─ matlabc_boot.py     # Unified entry dispatcher: no args = GUI / ask / flow / else = analyzer
├─ matlabc_ask.py      # Q&A code understanding (BM25 retrieval + intent recognition + LLM)
├─ matlabc_flow.py     # AI fix-loop orchestrator review→fix→apply→verify→report
├─ matlabc_mcp.py      # MCP server (exposes matlabc as tools to AI agents)
├─ binfmt/             # Binary & GPU container analysis (zero-dependency)
│  ├─ model.py         #   unified IR: Section / Symbol / Dependency / GpuBlob / BinaryReport
│  ├─ pe.py  elf.py    #   PE32+ and ELF64/32 streaming parsers (incl. CUDA/AMDGPU classification)
│  ├─ macho.py         #   Mach-O (⚠ implemented, unvalidated — no sample on the dev machine)
│  ├─ gpu.py           #   CUDA fatbin/cubin · HSA code object · SPIR-V entry points
│  ├─ attribute.py     #   attribution: unresolved name → library / gpu_kernel / missing
│  ├─ buildsys.py      #   Makefile / CMakeLists.txt link-intent hints
│  └─ report.py        #   text report (never hides a negative state)
├─ tools/              # Self-verifying static gates (see "Quality Gates")
│  ├─ check_all.py     #   one-shot runner: runs every check_*.py + its own --selftest
│  └─ check_*.py       #   doc-flags · operator-impl · patch-ops · py36-clean ·
│                      #   help-contract · binfmt-fixtures · subprocess-hygiene
├─ ai_cli.py           # Multi-vendor LLM access (offline echo / online answer, graceful degradation)
├─ gui.py              # Zero-dependency tkinter desktop GUI
├─ renderers/          # Report and visualization renderers (report/callgraph/hotspot/sarif/snapshot...)
│  └─ assets/          # Inlined CSS assets (offline-first, no CDN)
├─ tests/              # Tests and samples (test_matlabc.py / eval_ai_fix / sample_m/*.m)
├─ docs/               # Full documentation (usage / features / JSON Schema / delivery report ...)
├─ ci-examples/        # GitHub / GitLab CI template examples
├─ LICENSE             # MIT License (English original, the sole legally binding text)
└─ LICENSE_CN          # MIT License Chinese translation (for reference only)
```

---

## Quick Start

```bash
# (1) Console report (zero install, clone and run)
python matlabc.py my_matlab_project/

# (2) Generate an interactive browsable site (recommended: click-to-jump, full-text search)
python matlabc.py my_matlab_project/ -o report.html --browse

# (3) CI static analysis (SARIF + exit-code gate)
python matlabc.py my_matlab_project/ --checks all --sarif report.sarif \
    --max-warnings 0 --reproducible
```

Requirements: **Python 3.6+** (the tool itself is strictly 3.6.5-compatible; self-check with `--check-py36`).
Optionally install as a command: after `pip install -e .`, use `matlabc <args>` (no args = GUI).

> You can also package it into a single-file executable that needs no Python
> (`build_dist.py` + `build_release.bat/.sh`): double-click = GUI, with args = CLI.

---

## The Four Entry Points

### 1. Analyzer (CLI)

```bash
python matlabc.py myproj/ -o report.md --html report.html --browse \
    --offline --checks all --debt --sarif report.sarif
```

### 2. `ask` — Q&A Code Understanding

Normalizes static-analysis results into three retrievable object classes — "function docs +
call graph + warnings/priority" — then uses BM25 retrieval + intent recognition (who calls X /
what X calls / risk hotspots / explain X) to assemble a prompt for the LLM.

```bash
matlabc ask "who calls main" --dir ./myproj           # packaged unified entry
python matlabc_ask.py "where is the risk highest" --dir ./myproj   # source-mode equivalent
python matlabc_ask.py "what does helper do" --json report.json --provider deepseek
```

> **Offline-first**: without an API key, no model is called; it just echoes a paste-ready prompt
> containing the retrieved real context + the question. After configuring a provider, it answers directly.

### 3. `flow` — AI Fix Loop

```mermaid
flowchart LR
    R["review<br/>AI review / offline prompt"] --> F["fix<br/>deterministic patch engine"]
    F --> AP["apply<br/>git apply or<br/>strict in-process validation"]
    AP --> V["verify<br/>re-scan: no rule warns more"]
    V --> RP["report<br/>summary report"]
    V -.->|failed| F
```

```bash
matlabc flow ./myproj                    # by default only emits a patch + report, changes nothing
matlabc flow ./myproj --auto-apply       # applies the patch and self-verifies
matlabc flow ./myproj --steps review,fix,report --lang c --provider deepseek
```

### 4. GUI (Zero-Dependency Desktop UI)

```bash
python gui.py            # or double-click the packaged matlabc.exe
python gui.py --selftest # headless self-test
```

Pick a directory → tick the artifacts (browsable site / HTML / JSON / SARIF / MD) → choose the AI
timing → one-click analyze with streaming logs.

---

## Output Artifacts

| Artifact | Trigger | Purpose |
| --- | --- | --- |
| Console / Markdown report | `dir` (default) / `-o` | Quick viewing, archived review |
| HTML report | `--html` | Single file, directly shareable |
| Mermaid / Graphviz DOT | `--mermaid` / `--dot` | Embed in Wiki / docs |
| Interactive browsable site | `--browse` (+`--watch` daemon) | Click-to-jump to definitions, full-text search |
| JSON / XML / Doxygen XML | `--json` / `--xml` / `--export-doxygen-xml` | Secondary development, doxygen ecosystem |
| SARIF 2.1.0 | `--sarif` (+`--sarif-base` / `--sarif-diff`) | GitHub / GitLab code scanning |
| Technical debt / trend | `--debt` / `--trend` / `--gate` | Quality metrics and trend gates |
| Fix loop | `--gen-pr` / `--gen-apply-patch` / `--gen-tests-risk` | Fix landing, test-stub skeleton |
| Duplicate-code governance | `--dup-*` (baseline / patch / self-verify / gate) | Copy-paste code-smell governance |
| Binary / GPU report | `--binary` (+`--binary-symbols` / `--binary-json` / `--binfmt-scan-cap`) | Dynamic dependencies, exports, CUDA/ROCm/Vulkan content, and source-side attribution |
| Diff report | `--diff` / `--diff-html` | Full-dimension comparison of two snapshots |

---

## CI Quality Gate

```mermaid
flowchart TD
    S["git push / PR"] --> A["matlabc --git-diff HEAD<br/>incremental analysis"]
    A --> J["--json --sarif<br/>--reproducible"]
    J --> D{"--sarif-diff<br/>compare baseline"}
    D -->|new warnings increase| F["exit 1 blocked"]
    D -->|no increase| P["exit 0 passed"]
```

`ci-examples/` provides ready-to-use GitHub Actions / GitLab CI templates; just copy them in.

## Command Cheatsheet

```bash
# Structure-map report (Markdown)
python matlabc.py myproj/ -o report.md

# Interactive browsable site (click-to-jump + full-text search)
python matlabc.py myproj/ --browse -o site.html

# C project analysis
python matlabc.py myproj/ --lang c --checks all

# Python 3.6 syntax compatibility gate
python matlabc.py myproj/ --lang py --check-py36

# CI gate: fail on any new warning, SARIF output
python matlabc.py myproj/ --checks all --sarif report.sarif \
    --sarif-base baseline.sarif --sarif-diff --max-warnings 0 --reproducible

# Cross-file taint scan
python matlabc.py myproj/ --checks tainted_sink

# Binary analysis: dependencies, exports, GPU content
python matlabc.py --binary libfoo.so

# Attribute unresolved calls: source side ↔ binary side
python matlabc.py myproj/ --json out.json
python matlabc.py --binary libcublas.so.12 --binary-symbols out.json

# ...or do both in one command (no intermediate JSON)
python matlabc.py myproj/ --binary-attach libcublas.so.12 --json out.json

# Generate a deterministic self-verified fix patch
python matlabc flow myproj --auto-apply --gen-apply-patch

# Q&A code understanding (offline => echoes a paste-ready prompt)
python matlabc_ask.py "where is the risk highest" --dir myproj
```

---

## AI Agent Integration (MCP)

`malabc` can run as a **Model Context Protocol (MCP)** tool server, so any MCP-capable AI agent
(CodeBuddy / Cursor / Claude, etc.) can call it out of the box, wiring "code understanding +
static checks + deterministic patches" into the agent's autonomous workflow.

Launch (started automatically by the agent's MCP client; zero third-party dependencies):

```bash
python matlabc_mcp.py
```

The protocol is MCP over stdio (LSP framing, compatible with the official MCP SDK). Exposed tools:

| Tool | Purpose |
| --- | --- |
| `matlabc_analyze` | Static analysis + structure mapping; produces call relationships / risk hotspots / tech-debt report |
| `matlabc_check` | Gated static check (`uninitialized` / `type_mismatch` / `dead_code` / `shape_mismatch` / `tainted_sink`) |
| `matlabc_ask` | Natural-language Q&A code understanding (who calls X / risk hotspots / explain X) |
| `matlabc_gen_patch` | Runs the AI fix loop; generates / applies a deterministic fix patch |
| `matlabc_version` | Returns the engine version and capability list for agent capability negotiation |

> **Design note**: the server reuses the existing `matlabc` CLI via `subprocess` (process isolation,
> consistent behavior); the spawned child process tree is force-reclaimed on server exit / timeout
> (Windows `taskkill /T`, POSIX `killpg`) to avoid orphaned processes running away. Every tool
> returns an `isError` flag for easy agent error branching.

Agent call example (pseudocode):

```json
{"method":"tools/call","params":{"name":"matlabc_check",
 "arguments":{"target":"src/","check":"uninitialized","max_warnings":0}}}
```

---

## Quality Gates (self-verifying)

The project's own claims are enforced by executable gates. One command runs them all:

```bash
python tools/check_all.py        # runs every tools/check_*.py AND its --selftest
```

| Gate | What it stops |
| --- | --- |
| `check_baseline.py` | "Did this change make the suite worse?" — answered by comparing failure **nodeid sets**, not counts. This suite is *not* green, so counts prove nothing: 124 → 123 can be "fixed one" or "fixed two, broke one". `--full` runs both sides; the default mode checks preconditions and self-tests the verdict logic |
| `check_doc_flags.py` | Documentation **or a help screen** advertising a CLI flag that does not exist (this really happened: the README said `--check tainted_sink`, which argparse rejects as an **ambiguous prefix**) |
| `check_operator_impl.py` | "Phantom operators" (a rule in the catalog that no code path emits), contradictions between the catalog and the not-implemented table, and **a "we don't do this" that never reaches `--help`** |
| `check_patch_ops.py` | Patch operators that overwrite a target line instead of inserting before it (which would silently delete source) |
| `check_binfmt_fixtures.py` | Binary / GPU parsers regressing — synthetic PE/ELF/Mach-O fixtures plus contract assertions C1–C9 |
| `check_py36_clean.py` | The repo breaking **its own** Python 3.6.5 promise (it already had: `list[str]` and `from __future__ import annotations` had shipped) |
| `check_subprocess_hygiene.py` | Any subprocess that captures output while inheriting stdin, or that can hang forever |
| `check_help_contract.py` | An exit code that exists in the code but not in `--help`, or in `--help` but never returned; help that lost its usage example, diagram, or exit-code section; **examples that do not actually run**; help that silently shrank or bloated (absolute bound **and** drift from a ratified snapshot); exit codes claimed by the `ci-examples/` templates; and **stale "N gates" numbers in prose** |
| `check_readme_parity.py` | The English and Chinese READMEs drifting apart structurally — section count, and per-section table-row / code-block / mermaid counts. It deliberately does **not** compare line counts, because Chinese is more compact |

**"How many tests fail" proves nothing here — the baseline gate exists to say so.** Because the
suite carries a backlog of failures, a gate that compared counts would happily bless a change
that fixed one test and broke another. So it compares *sets*:

```mermaid
flowchart LR
  H["HEAD tree<br/>(unmodified)"] --> R1["pytest -q"]
  W["working tree<br/>(+ the same test set)"] --> R2["pytest -q"]
  R1 --> C{"nodeid<br/>set difference"}
  R2 --> C
  C -->|"after − before"| X["regressions<br/>→ RED"]
  C -->|"before − after"| F["fixed / renamed<br/>→ informational"]
```

```bash
python tools/check_baseline.py          # preconditions + the gate's own two-way self-test
python tools/check_baseline.py --full    # the real baseline: both sides, minutes
```

Four disciplines make these gates trustworthy rather than decorative:

1. **Every gate proves itself in both directions.** `--selftest` builds *bad* samples that must go
   red **and** *good* samples that must stay green, then prints a machine-readable line
   (`SELFTEST COUNTS {"bad": N, "good": M}`) that the regression tests assert against — using
   **lower bounds**, so silently shrinking the sample set fails the build.
2. **A gate that hangs is worse than no gate.** `check_all.py` gives every child a wall-clock
   timeout and treats a timeout as **red**. This came from a real defect: a gate spawned
   `<script> --help` with its output captured while *inheriting stdin*; the last of the four
   scripts is a stdio MCP server that reads stdin, so it blocked until its own 180 s timeout
   fired — the gate took ~181 s and was killed by the surrounding `timeout 90`, looking like an
   inexplicable freeze. Cutting stdin took the same gate to **3.4 s**, and
   `check_subprocess_hygiene.py` now enforces that lesson repo-wide.
3. **A measurement tool's own bug fabricates bugs in the thing it measures.** Two-way self-test
   must therefore run green **before** you are allowed to announce "0 violations in the real
   repo". This is not a slogan: the exit-code gate's own evidence matcher used `\breturn\s+0\b`,
   which matches inside `return 0.0` (the boundary sits between `0` and `.`) — so a function that
   returns a *float* was accepted as proof of "exits with code 0", and a **stale registry entry
   was laundered as valid**. The gate caught its own bug only because its self-test ran first.
4. **A number in prose is a claim, and nothing fails when it goes stale.** `--help` said "7 gates" <!-- guard-count:historical R42 历史引用：举例引用旧值 -->
   while there were 9; both READMEs said "8 gates". No syntax error, no failing test, no compiler <!-- guard-count:historical R42 历史引用：举例引用旧值 -->
   warning — a stale number is only ever found by someone happening to read it. So
   `check_help_contract.py` now checks every `N 道…护栏` / `N gates` in the current-state docs
   against the real count, and requires the claim to *still exist* (deleting the sentence would
   silently drop the coverage while `rc` stayed 0). Historical documents — the per-round reviews
   and `docs/analysis/**` — are explicitly exempt: their numbers were true when written, and
   "correcting" them would be rewriting history.

Several of these gates map a claim to an executable counter-party rather than to a style rule:
`check_py36_clean.py` feeds this repository's own sources to this repository's own 3.6.5 gate;
`check_help_contract.py` cross-checks the documented exit codes against the codes the source can
actually return, *runs* every documented example command, and holds the `ci-examples/` CI
templates to their own exit codes; `check_baseline.py` compares the working tree against
`git archive HEAD`; `check_readme_parity.py` compares the two READMEs to each other. All are
**two-way**: a stale registry entry fails just as loudly as a missing one, because a registry
that only ever grows stops meaning anything.

---

## Built-in help (illustrated, one story per entry point)

Each entry script's module docstring **is** its `--help` text, and all of them follow the same
skeleton: *what pain it removes → a flow diagram → copy-pasteable examples → exit codes →
honest limits*. `--help` returns immediately and has no side effects — it never opens a window,
never starts an analysis, never hangs.

```bash
python matlabc.py --help          # the analyzer: task-oriented command table + pipeline + limits
python matlabc_flow.py --help     # repair loop: five-station pipeline + five recipes
python matlabc_ask.py --help      # grounded Q&A: how facts become an answer
python matlabc_mcp.py --help      # MCP server: the five tools + why stdin must be cut
python gui.py --help              # GUI: which CLI flag each form field maps to
python tools/check_all.py --help  # gates: what each of the 9 gates stops
```

This is not a verbal promise — `check_help_contract.py` and `check_doc_flags.py` watch it, and
they check more than wording:

- every flag named in an example must really exist;
- every documented exit code must match the codes the source can actually return;
- every example command is **actually executed** (`rc == 0`) and must appear in the help text
  **verbatim**, so it is genuinely copy-pasteable;
- help has a **volume ratchet** with both a floor and a ceiling — a help screen that silently
  shrinks back to bare argparse usage fails just as loudly as one that bloats past what anyone
  would read.

---

## Documents

- [docs/matlabc_USAGE.md](docs/matlabc_USAGE.md) — full command-line usage reference
- [docs/matlabc_FEATURES.md](docs/matlabc_FEATURES.md) — capability details and examples
- [docs/matlabc_JSON_SCHEMA.md](docs/matlabc_JSON_SCHEMA.md) — JSON output schema
- [docs/matlabc_DELIVERY_REPORT.md](docs/matlabc_DELIVERY_REPORT.md) — delivery / packaging notes
- [docs/matlabc_STRUCTURE.md](docs/matlabc_STRUCTURE.md) — code structure overview
- [docs/matlabc_AI_ROADMAP.md](docs/matlabc_AI_ROADMAP.md) — AI roadmap
- [docs/analysis/](docs/analysis/) — deep-analysis reports (six-hats reviews, design comparisons)
- [docs/SUPERPOWER_REVIEW_R31.md](docs/SUPERPOWER_REVIEW_R31.md) — round-by-round review: binary/GPU integration, subprocess hygiene, and the gate that hung
- [docs/SUPERPOWER_REVIEW_R33.md](docs/SUPERPOWER_REVIEW_R33.md) — round review: `--binary-attach`, the README parity gate, executable help examples, and the exit-code matcher that caught its own bug
- [docs/GITHUB_REPO_ABOUT.md](docs/GITHUB_REPO_ABOUT.md) — paste-ready repository About panel text (description / website / topics)

---

## License

[MIT](LICENSE) — see [LICENSE](LICENSE) (English original, the sole legally binding text) and
[LICENSE_CN](LICENSE_CN) (Chinese translation for reference only).

---

> This document has a fully corresponding **Chinese version**: [README_CN.md](README_CN.md).
> The two are kept in sync section by section; do not mix languages within a single file.

