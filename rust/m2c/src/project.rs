//! 工程级产物：头 + 源 + 可运行的 main + CMakeLists（R435 / R436 / R437）。
//!
//! main 的输入规则：
//! * **夹具文件**（`demo fixture.txt`）按**参数名**给值：
//!   ```
//!   x = 10 20 30
//!   i = 3
//!   ```
//!   这样每个参数各自有名字，不再靠"参数按位置排"这种隐式约定。
//! * 没给夹具、或某个名字缺失时退化为 `a[i] = i+1` / 标量 `2`（确定、可复现）。
//!
//! 输出：`名字: v1 v2 …`，多返回值用 ` | ` 分隔。

use crate::emit::{emit_func, ident, proto};
use std::collections::BTreeMap;

/// 一组测试夹具：按参数名给值 + 这组输入下的期望输出。
#[derive(Debug, Clone, Default)]
pub struct Case {
    pub name: String,
    pub args: BTreeMap<String, Vec<f64>>,
    pub expect: BTreeMap<String, String>,
}

use crate::mir::Func;

fn c_dtype_name(dt: &str) -> Option<&'static str> {
    match dt {
        "f64" => Some("MLC_F64"),
        "f32" => Some("MLC_F32"),
        "i64" => Some("MLC_I64"),
        "i32" => Some("MLC_I32"),
        "u8" => Some("MLC_U8"),
        "bool" => Some("MLC_BOOL"),
        _ => None,
    }
}

/// 能否被 demo main 驱动：1 个数组入参 + 任意个 i64 标量 + 至少一个数组返回。
fn drivable(f: &Func) -> bool {
    let arrays: Vec<_> = f.args.iter().filter(|a| a.dtype == "f64").collect();
    let scalars: Vec<_> = f.args.iter().filter(|a| a.dtype == "i64").collect();
    // 数组入参可以是多个（矩阵乘需要 A、B）；每个都必须有形状 ——
    // 没形状就不知道该分配多大，那是"猜"，不是"生成"。
    !arrays.is_empty()
        && arrays.iter().all(|a| !a.shape.is_empty())
        && scalars.len() == f.args.len() - arrays.len()
        && !f.rets.is_empty()
        && f.rets.iter().all(|r| r.dtype == "f64" && !r.shape.is_empty())
}

/// 夹具解析器（纯 C，固定容量，避免在生成物里引入 malloc）。
const FIXTURE_C: &str = r#"/* 夹具：按**参数名**给值，例如  x = 10 20 30  */
#define M2C_MAX_NAMES 8
#define M2C_MAX_VALS 32
typedef struct { char name[64]; double vals[M2C_MAX_VALS]; int n; } m2c_fix;
static m2c_fix m2c_fx[M2C_MAX_NAMES];
static int m2c_nfx = 0;

static void m2c_load(const char *path) {
    FILE *fp = fopen(path, "r");
    char line[1024];
    if (fp == NULL) {
        printf("fixture: cannot open %s\n", path);
        return;
    }
    while (fgets(line, sizeof(line), fp) != NULL) {
        char *p = line;
        char *nm;
        int k = 0;
        while (*p == ' ' || *p == '\t') ++p;
        if (*p == '#' || *p == '\0' || *p == '\r' || *p == '\n') continue;
        if (m2c_nfx >= M2C_MAX_NAMES) break;
        nm = m2c_fx[m2c_nfx].name;
        while (*p && *p != '=' && *p != ':' && k < 63) nm[k++] = *p++;
        while (k > 0 && (nm[k - 1] == ' ' || nm[k - 1] == '\t')) --k;
        nm[k] = '\0';
        if (*p == '=' || *p == ':') ++p;
        m2c_fx[m2c_nfx].n = 0;
        for (;;) {
            char *end = NULL;
            double v;
            while (*p == ' ' || *p == '\t' || *p == ',') ++p;
            if (*p == '\0' || *p == '\r' || *p == '\n') break;
            v = strtod(p, &end);
            if (end == p) break;
            if (m2c_fx[m2c_nfx].n < M2C_MAX_VALS) {
                m2c_fx[m2c_nfx].vals[m2c_fx[m2c_nfx].n++] = v;
            }
            p = end;
        }
        ++m2c_nfx;
    }
    fclose(fp);
}

/* 返回该名字的值个数（0 = 没给）。 */
static int m2c_get(const char *name, double *out, int max) {
    int i, k;
    for (i = 0; i < m2c_nfx; ++i) {
        if (strcmp(m2c_fx[i].name, name) == 0) {
            for (k = 0; k < m2c_fx[i].n && k < max; ++k) out[k] = m2c_fx[i].vals[k];
            return k;
        }
    }
    return 0;
}
"#;

fn emit_main(funcs: &[Func], name: &str) -> String {
    let mut out: Vec<String> = Vec::new();
    out.push("/* 由 m2c 生成的演示入口。".to_string());
    out.push("   输入优先级：夹具文件（按参数名）> 默认 a[i]=i+1 / 2。 */".to_string());
    out.push(format!("#include \"{}.h\"", name));
    out.push("#include <stdio.h>".to_string());
    out.push("#include <stdlib.h>".to_string());
    out.push("#include <string.h>".to_string());
    out.push(String::new());
    out.push(FIXTURE_C.to_string());
    out.push("static void m2c_print(const mlc_array *a) {".to_string());
    out.push("    int64_t n = mlc_array_numel(a);".to_string());
    out.push("    for (int64_t i = 0; i < n; ++i) {".to_string());
    out.push("        printf(\" %.10g\", ((const double *)a->data)[i]);".to_string());
    out.push("    }".to_string());
    out.push("}".to_string());
    out.push(String::new());
    out.push("int main(int argc, char **argv) {".to_string());
    out.push("    if (argc > 1) m2c_load(argv[1]);".to_string());
    out.push("    double vals[M2C_MAX_VALS];".to_string());

    for f in funcs {
        if !drivable(f) {
            out.push(format!(
                "    printf(\"{}: skipped (no shape)\\n\");",
                ident(&f.name)
            ));
            continue;
        }
        let arrays: Vec<&crate::mir::Var> =
            f.args.iter().filter(|a| a.dtype == "f64").collect();
        let arr = arrays[0];
        let dims: Vec<String> = arr.shape.iter().map(|d| d.to_string()).collect();
        let dt = c_dtype_name(&arr.dtype).unwrap_or("MLC_F64");
        let shape_lit = format!("(int64_t[]){{{}}}", dims.join(", "));
        let an = ident(&arr.name);
        out.push("    {".to_string());
        out.push(format!("        mlc_array {};", an));
        out.push(format!(
            "        if (mlc_array_init(&{}, {}, {}, {}) != MLC_OK) {{ return 1; }}",
            an,
            dt,
            arr.shape.len(),
            shape_lit
        ));
        out.push(format!(
            "        int got_{} = m2c_get(\"{}\", vals, M2C_MAX_VALS);",
            an, arr.name
        ));
        out.push(format!(
            "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{",
            an
        ));
        out.push(format!(
            "            ((double *){}.data)[i] = (i < got_{}) ? vals[i] : (double)(i + 1);",
            an, an
        ));
        out.push("        }".to_string());
        for s in f.args.iter().filter(|a| a.dtype == "i64") {
            let sn = ident(&s.name);
            out.push(format!(
                "        int got_{0} = m2c_get(\"{1}\", vals, M2C_MAX_VALS);",
                sn, s.name
            ));
            out.push(format!(
                "        int64_t {} = (got_{} > 0) ? (int64_t)vals[0] : 2;",
                sn, sn
            ));
        }
        // 其余数组入参：夹具里给了值就用，否则 a[i] = i+1
        for extra in arrays.iter().skip(1) {
            let en = ident(&extra.name);
            let edims: Vec<String> =
                extra.shape.iter().map(|d| d.to_string()).collect();
            out.push(format!("        mlc_array {};", en));
            out.push(format!(
                "        if (mlc_array_init(&{}, {}, {}, (int64_t[]){{{}}}) != MLC_OK) {{ return 1; }}",
                en, dt, extra.shape.len(), edims.join(", ")));
            out.push(format!(
                "        int got_{0} = m2c_get(\"{1}\", vals, M2C_MAX_VALS);",
                en, extra.name));
            out.push(format!(
                "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{", en));
            out.push(format!(
                "            ((double *){}.data)[i] = (i < got_{}) ? vals[i] : (double)(i + 1);",
                en, en));
            out.push("        }".to_string());
        }
        let mut ret_names: Vec<String> = Vec::new();
        for r in &f.rets {
            let rn = ident(&r.name);
            out.push(format!("        mlc_array {};", rn));
            out.push(format!(
                "        mlc_array_init(&{}, MLC_F64, 1, (int64_t[]){{1}});",
                rn
            ));
            ret_names.push(rn);
        }
        let mut call_args: Vec<String> = f.args.iter().map(|a| ident(&a.name)).collect();
        for rn in &ret_names {
            call_args.push(format!("&{}", rn));
        }
        out.push(format!(
            "        mlc_status st = m2c_{}({});",
            ident(&f.name),
            call_args.join(", ")
        ));
        out.push("        if (st != MLC_OK) {".to_string());
        out.push(format!(
            "            printf(\"{}: %s\\n\", mlc_status_string(st));",
            ident(&f.name)
        ));
        out.push("        } else {".to_string());
        out.push(format!("            printf(\"{}:\");", ident(&f.name)));
        for (k, rn) in ret_names.iter().enumerate() {
            if k > 0 {
                out.push("            printf(\" |\");".to_string());
            }
            out.push(format!("            m2c_print(&{});", rn));
        }
        out.push("            printf(\"\\n\");".to_string());
        out.push("        }".to_string());
        for a2 in &arrays {
            out.push(format!("        mlc_array_free(&{});", ident(&a2.name)));
        }
        for rn in &ret_names {
            out.push(format!("        mlc_array_free(&{});", rn));
        }
        out.push("    }".to_string());
    }
    out.push("    return 0;".to_string());
    out.push("}".to_string());
    out.join("\n")
}


/// 生成物自带的说明：拿到工程的人第一眼就知道该敲什么。
fn gen_readme(name: &str) -> String {
    let mut out: Vec<String> = Vec::new();
    out.push(format!("# {}（由 m2c 生成）", name));
    out.push(String::new());
    out.push("## 构建与自测".to_string());
    out.push(String::new());
    out.push("```bash".to_string());
    out.push("# mlc 运行时：不传会自动按 ../../c_runtime 等位置猜".to_string());
    out.push("cmake -S . -B build -DMLC_RUNTIME=<path-to>/c_runtime".to_string());
    out.push("cmake --build build".to_string());
    out.push("ctest --test-dir build --output-on-failure".to_string());
    out.push("```".to_string());
    out.push(String::new());
    out.push("### 找不到 c_runtime 时".to_string());
    out.push(String::new());
    out.push("```bash".to_string());
    out.push("# 在 matlabc 仓库里找它的位置".to_string());
    out.push("find .. -maxdepth 4 -name c_runtime -type d 2>/dev/null | head -1".to_string());
    out.push("# Windows PowerShell: Get-ChildItem -Recurse -Directory -Filter c_runtime".to_string());
    out.push("```".to_string());
    out.push(String::new());
    out.push("也可以用环境变量：`MLC_RUNTIME=/path/to/c_runtime cmake -S . -B build`".to_string());
    out.push(String::new());
    out.push("## 跑一遍看数值".to_string());
    out.push(String::new());
    out.push("```bash".to_string());
    out.push("./build/demo                 # 默认输入（a[i] = i+1）".to_string());
    out.push("./build/demo fixture.txt     # 夹具输入：按参数名给值".to_string());
    out.push("```".to_string());
    out.push(String::new());
    out.push("夹具格式（每行一个参数）：".to_string());
    out.push(String::new());
    out.push("```text".to_string());
    out.push("x = 10 20 30".to_string());
    out.push("i = 3".to_string());
    out.push("```".to_string());
    out.push(String::new());
    out.push("## 这些文件是生成的".to_string());
    out.push(String::new());
    out.push("| 文件 | 来源 |".to_string());
    out.push("| --- | --- |".to_string());
    out.push("| `src/gen.c` / `include/*.h` | MIR 发射 |".to_string());
    out.push("| `src/main.c` / `src/selftest.c` | 演示入口与自测 |".to_string());
    out.push("| `CMakeLists.txt` | 构建脚本 |".to_string());
    out.push(String::new());
    out.push("**勿手改**：改 `.m` 再重新生成，否则下次生成会覆盖。".to_string());
    out.join("\n") + "\n"
}

/// 整个项目：头 + 源 + main + CMakeLists。顺序固定（确定性）。
pub fn emit_project(funcs: &[Func], name: &str, cases: &[Case],
) -> Result<Vec<(String, String)>, String> {
    let guard = format!("M2C_{}_H", ident(name).to_uppercase());
    let mut h = vec![
        format!("/* {} —— 由 m2c 生成，勿手改 */", name),
        format!("#ifndef {}", guard),
        format!("#define {}", guard),
        String::new(),
        "#include \"mlc.h\"".to_string(),
        "#include \"mlc_ops.h\"".to_string(),
        String::new(),
    ];
    for f in funcs {
        h.push(proto(f));
    }
    h.push(String::new());
    h.push(format!("#endif /* {} */", guard));

    let mut c = vec![
        format!("/* {} —— 由 m2c 生成，勿手改 */", name),
        format!("#include \"{}.h\"", name),
        String::new(),
    ];
    for f in funcs {
        c.push(emit_func(f, funcs)?);
        c.push(String::new());
    }

    let cmake = vec![
        "cmake_minimum_required(VERSION 3.10)".to_string(),
        format!("project({} C)", ident(name)),
        "set(CMAKE_C_STANDARD 99)".to_string(),
        String::new(),
        "# mlc 运行时的位置：-DMLC_RUNTIME=... > 环境变量 > 按常见相对位置猜。".to_string(),
        "# 少了它，第一次 cmake 就会失败，而错误信息通常只说找不到 mlc.h。".to_string(),
        "if(NOT DEFINED MLC_RUNTIME AND DEFINED ENV{MLC_RUNTIME})".to_string(),
        "  set(MLC_RUNTIME \"$ENV{MLC_RUNTIME}\")".to_string(),
        "endif()".to_string(),
        "if(NOT DEFINED MLC_RUNTIME)".to_string(),
        "  foreach(_cand \"${CMAKE_CURRENT_SOURCE_DIR}/../../c_runtime\"".to_string(),
        "                \"${CMAKE_CURRENT_SOURCE_DIR}/../c_runtime\"".to_string(),
        "                \"${CMAKE_CURRENT_SOURCE_DIR}/c_runtime\")".to_string(),
        "    if(EXISTS \"${_cand}/include/mlc.h\")".to_string(),
        "      set(MLC_RUNTIME \"${_cand}\")".to_string(),
        "      break()".to_string(),
        "    endif()".to_string(),
        "  endforeach()".to_string(),
        "endif()".to_string(),
        "if(NOT DEFINED MLC_RUNTIME)".to_string(),
        "  message(FATAL_ERROR \"找不到 mlc 运行时：请用 -DMLC_RUNTIME=<c_runtime 路径> 指定\")".to_string(),
        "endif()".to_string(),
        String::new(),
        "add_library(m2c_gen STATIC src/gen.c".to_string(),
        "        ${MLC_RUNTIME}/src/mlc_runtime.c".to_string(),
        "        ${MLC_RUNTIME}/src/mlc_ops.c)".to_string(),
        "target_include_directories(m2c_gen PUBLIC include)".to_string(),
        "target_include_directories(m2c_gen PUBLIC ${MLC_RUNTIME}/include)".to_string(),
        String::new(),
        "add_executable(demo src/main.c)".to_string(),
        "target_link_libraries(demo PRIVATE m2c_gen)".to_string(),
        String::new(),
        "# 生成物自带测试：不依赖 Python，`ctest` 就能验默认输入下的数值。".to_string(),
        "enable_testing()".to_string(),
        "add_executable(m2c_selftest src/selftest.c)".to_string(),
        "target_link_libraries(m2c_selftest PRIVATE m2c_gen)".to_string(),
        "add_test(NAME default_case COMMAND m2c_selftest)".to_string(),
    ];

    Ok(vec![
        (format!("include/{}.h", name), h.join("\n") + "\n"),
        ("src/gen.c".to_string(), c.join("\n") + "\n"),
        ("src/main.c".to_string(), emit_main(funcs, name) + "\n"),
        ("src/selftest.c".to_string(), emit_selftest(funcs, name, cases) + "\n"),
        ("CMakeLists.txt".to_string(), cmake.join("\n") + "\n"),
        ("README.md".to_string(), gen_readme(name)),
    ])
}

/// 自测程序：按**每组夹具**跑每个可驱动函数，与嵌入的期望串逐字比较。
///
/// 为什么嵌进 C：拿生成工程走的人未必有 Python；
/// 而"这堆生成代码算得对不对"这个问题，应该在工程内就能回答。
/// 为什么支持多组：只有默认输入时，`if`/`while` 的分支很可能永远没走到。
fn emit_selftest(funcs: &[Func], name: &str, cases: &[Case]) -> String {
    let mut out: Vec<String> = Vec::new();
    out.push("/* 由 m2c 生成的 C 自测（ctest）。 */".to_string());
    out.push(format!("#include \"{}.h\"", name));
    out.push("#include <stdio.h>".to_string());
    out.push("#include <string.h>".to_string());
    out.push(String::new());
    out.push("static int m2c_fail = 0;".to_string());
    out.push(String::new());
    out.push("static void m2c_check(const char *cname, const char *fname,".to_string());
    out.push("                      const mlc_array *a, const char *want) {".to_string());
    out.push("    char got[512];".to_string());
    out.push("    size_t off = 0;".to_string());
    out.push("    int64_t n = mlc_array_numel(a);".to_string());
    out.push("    got[0] = 0;".to_string());
    out.push("    for (int64_t i = 0; i < n; ++i) {".to_string());
    out.push("        off += (size_t)snprintf(got + off, sizeof(got) - off,".to_string());
    out.push("                                \" %.10g\", ((const double *)a->data)[i]);".to_string());
    out.push("        if (off >= sizeof(got)) break;".to_string());
    out.push("    }".to_string());
    out.push("    const char *trimmed = got;".to_string());
    out.push("    while (*trimmed == ' ') ++trimmed;".to_string());
    out.push("    if (strcmp(trimmed, want) != 0) {".to_string());
    out.push("        printf(\"FAIL [%s] %s: got[%s] want[%s]\\n\",".to_string());
    out.push("               cname, fname, trimmed, want);".to_string());
    out.push("        m2c_fail = 1;".to_string());
    out.push("    } else {".to_string());
    out.push("        printf(\"ok   [%s] %s:%s\\n\", cname, fname, trimmed);".to_string());
    out.push("    }".to_string());
    out.push("}".to_string());
    out.push(String::new());
    out.push("int main(void) {".to_string());

    for (ci, case) in cases.iter().enumerate() {
        let cname = if case.name.is_empty() {
            format!("case{}", ci + 1)
        } else {
            case.name.clone()
        };
        out.push(format!("    /* 夹具：{} */", cname));
        for f in funcs {
            if !drivable(f) {
                continue;
            }
            let arrays: Vec<&crate::mir::Var> =
                f.args.iter().filter(|a| a.dtype == "f64").collect();
            let arr = arrays[0];
            let dims: Vec<String> = arr.shape.iter().map(|d| d.to_string()).collect();
            let shape_lit = format!("(int64_t[]){{{}}}", dims.join(", "));
            let an = ident(&arr.name);
            let numel: i64 = arr.shape.iter().product();
            out.push("    {".to_string());
            out.push(format!("        mlc_array {};", an));
            out.push(format!(
                "        if (mlc_array_init(&{}, MLC_F64, {}, {}) != MLC_OK) return 2;",
                an, arr.shape.len(), shape_lit));
            // 夹具给了值就按值填，否则 a[i]=i+1
            match case.args.get(&arr.name) {
                Some(vals) if vals.len() >= numel as usize => {
                    let lits: Vec<String> = vals.iter().map(|v| format!("{:.17}", v))
                        .collect();
                    out.push(format!("        double {}v[] = {{{}}};",
                                     an, lits.join(", ")));
                    out.push(format!(
                        "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{ ((double *){}.data)[i] = {}v[i]; }}",
                        an, an, an));
                }
                _ => {
                    out.push(format!(
                        "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{ ((double *){}.data)[i] = (double)(i + 1); }}",
                        an, an));
                }
            }
            for sc in f.args.iter().filter(|a| a.dtype == "i64") {
                let v = case
                    .args
                    .get(&sc.name)
                    .and_then(|v| v.first().copied())
                    .map(|x| format!("{}", x as i64))
                    .unwrap_or_else(|| "2".to_string());
                out.push(format!("        int64_t {} = {};", ident(&sc.name), v));
            }
            // 其余数组入参（矩阵乘等）：给值就用，否则 i+1
            for extra in arrays.iter().skip(1) {
                let en = ident(&extra.name);
                let edims: Vec<String> =
                    extra.shape.iter().map(|d| d.to_string()).collect();
                let enumer: i64 = extra.shape.iter().product();
                out.push(format!("        mlc_array {};", en));
                out.push(format!(
                    "        if (mlc_array_init(&{}, MLC_F64, {}, (int64_t[]){{{}}}) != MLC_OK) return 2;",
                    en, extra.shape.len(), edims.join(", ")));
                match case.args.get(&extra.name) {
                    Some(vals) if vals.len() >= enumer as usize => {
                        let lits: Vec<String> =
                            vals.iter().map(|v| format!("{:.17}", v)).collect();
                        out.push(format!("        double {}v[] = {{{}}};",
                                         en, lits.join(", ")));
                        out.push(format!(
                            "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{ ((double *){}.data)[i] = {}v[i]; }}",
                            en, en, en));
                    }
                    _ => {
                        out.push(format!(
                            "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{ ((double *){}.data)[i] = (double)(i + 1); }}",
                            en, en));
                    }
                }
            }
            let mut rets: Vec<String> = Vec::new();
            for r in &f.rets {
                let rn = ident(&r.name);
                out.push(format!("        mlc_array {};", rn));
                out.push(format!("        mlc_array_init(&{}, MLC_F64, 1, (int64_t[]){{1}});", rn));
                rets.push(rn);
            }
            let mut call_args: Vec<String> = f.args.iter().map(|a| ident(&a.name)).collect();
            for rn in &rets {
                call_args.push(format!("&{}", rn));
            }
            out.push(format!("        mlc_status st_{} = m2c_{}({});",
                             ident(&f.name), ident(&f.name), call_args.join(", ")));
            let want = case.expect.get(&f.name).cloned().unwrap_or_default();
            let parts: Vec<&str> = want.split('|').map(|x| x.trim()).collect();
            if parts.len() == rets.len() && !want.is_empty() {
                for (k, rn) in rets.iter().enumerate() {
                    out.push(format!(
                        "        if (st_{} == MLC_OK) m2c_check(\"{}\", \"{}\", &{}, \"{}\");",
                        ident(&f.name), cname, f.name, rn,
                        parts[k].replace('\\', "\\\\").replace('"', "\\\"")));
                }
            } else {
                out.push(format!("        /* {} 在这组夹具里没有期望值，跳过比较 */",
                                 f.name));
            }
            out.push(format!("        (void)st_{};", ident(&f.name)));
            out.push(format!("        mlc_array_free(&{});", an));
            for rn in &rets {
                out.push(format!("        mlc_array_free(&{});", rn));
            }
            out.push("    }".to_string());
        }
    }
    out.push("    return m2c_fail;".to_string());
    out.push("}".to_string());
    out.join("\n")
}
