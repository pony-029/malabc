# malabc architecture (English labels)

This directory holds the **English-label** editions of the 14 architecture diagrams.
They are generated from `en/candidates/*.json` (editable source) with the same
archify renderer used by the Chinese set. Only the **SVG** outputs are committed:
the interactive HTML would duplicate ~10 MB and the Chinese index already covers it.

Build / verify:

```bash
python tools/build_arch_svg_en.py          # validate + render + export all 14 SVGs
python tools/build_arch_svg_en.py --check  # XML presence/parse check
```

| # | Diagram | Type | SVG | Question it answers |
| --- | --- | --- | --- | --- |
| 00 | Overall | architecture | [00-overall.svg](svg/00-overall.svg) | What are the layers and the main trunk? |
| 01 | Entry & CLI | workflow | [01-entry.svg](svg/01-entry.svg) | How does one command reach the analysis core? |
| 02 | MATLAB frontend | workflow | [02-matlab-frontend.svg](svg/02-matlab-frontend.svg) | How does source become functions and call edges? |
| 03 | Multi-language + IR | workflow | [03-multilang-ir.svg](svg/03-multilang-ir.svg) | How are C / Py / JS / asm attributed to one IR? |
| 04 | Analysis engine | architecture | [04-analysis.svg](svg/04-analysis.svg) | How do call graph, impact, deps, taint and checks share one model? |
| 05 | Render & output | workflow | [05-render.svg](svg/05-render.svg) | How does one model produce five exits? |
| 06 | LSP & VS Code | architecture | [06-lsp.svg](svg/06-lsp.svg) | Where do diagnostics, outline and navigation come from? |
| 07 | AI & MCP | architecture | [07-ai-mcp.svg](svg/07-ai-mcp.svg) | How do external agents consume project understanding? |
| 08 | Fix loop | lifecycle | [08-fix-loop.svg](svg/08-fix-loop.svg) | How are fixes verified, reverted, reviewed and remembered? |
| 09 | Gates & CI | workflow | [09-gates.svg](svg/09-gates.svg) | How are 39 gates organized, cached and released? |
| 10 | MATLAB→C porting | architecture | [10-porting.svg](svg/10-porting.svg) | How do contract, operators, fidelity and ledger land MATLAB in C? |
| 11 | Binary analysis | architecture | [11-binary.svg](svg/11-binary.svg) | How do PE/ELF/Mach-O/GPU answer "who owns this name"? |
| 12 | Dataflow | dataflow | [12-dataflow.svg](svg/12-dataflow.svg) | How do three inputs become one model and many consumers? |
| 13 | One LSP request | sequence | [13-sequence.svg](svg/13-sequence.svg) | What happens from opening a file to outline/diagnostics and the 800 ms fallback? |

## Verification (this round)

| Check | Result |
| --- | --- |
| `archify validate` (14 EN candidates) | **14/14 ok** (0 errors) |
| `archify render` (14) | **14/14 success** |
| SVG XML | **14/14 parse** |
| SVG size | **~330 KB total** (15–40 KB each) |
| Chrome smoke (`00-overall`) | 1444×744, **2695 colors / 40.94% non-white** |

> The English editions intentionally omit the long per-diagram cards and any
> Chinese-only sublabels, so the primary labels stay readable. The full narrative
> lives in the Chinese [`../README.md`](../README.md).
