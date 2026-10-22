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
    if f.reject.is_some() {
        return false;      // 可变参数：签名无法表达，不参与驱动
    }
    !arrays.is_empty()
        && arrays.iter().all(|a| !a.shape.is_empty())
        && scalars.len() == f.args.len() - arrays.len()
        && !f.rets.is_empty()
        && f.rets.iter().all(|r| {
            r.dtype == "f64"
                // 动态长度的返回值没有声明形状，由算子分配 —— 这是合法的
                && (!r.shape.is_empty()
                    || crate::emit::ret_is_dynamic(f, &r.name))
        })
}

/// 夹具解析器（纯 C，固定容量，避免在生成物里引入 malloc）。
const FIXTURE_C: &str = r#"/* 夹具：按**参数名**给值，例如  x = 10 20 30  */
#define M2C_MAX_NAMES 8
#define M2C_MAX_VALS 32
typedef struct { char name[64]; double vals[M2C_MAX_VALS]; int n; } m2c_rt_fix;
static m2c_rt_fix m2c_rt_fx[M2C_MAX_NAMES];
static int m2c_rt_nfx = 0;

static void m2c_rt_load(const char *path) {
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
        if (m2c_rt_nfx >= M2C_MAX_NAMES) break;
        nm = m2c_rt_fx[m2c_rt_nfx].name;
        while (*p && *p != '=' && *p != ':' && k < 63) nm[k++] = *p++;
        while (k > 0 && (nm[k - 1] == ' ' || nm[k - 1] == '\t')) --k;
        nm[k] = '\0';
        if (*p == '=' || *p == ':') ++p;
        m2c_rt_fx[m2c_rt_nfx].n = 0;
        for (;;) {
            char *end = NULL;
            double v;
            while (*p == ' ' || *p == '\t' || *p == ',') ++p;
            if (*p == '\0' || *p == '\r' || *p == '\n') break;
            v = strtod(p, &end);
            if (end == p) break;
            if (m2c_rt_fx[m2c_rt_nfx].n < M2C_MAX_VALS) {
                m2c_rt_fx[m2c_rt_nfx].vals[m2c_rt_fx[m2c_rt_nfx].n++] = v;
            }
            p = end;
        }
        ++m2c_rt_nfx;
    }
    fclose(fp);
}

/* 返回该名字的值个数（0 = 没给）。 */
static int m2c_rt_get(const char *name, double *out, int max) {
    int i, k;
    for (i = 0; i < m2c_rt_nfx; ++i) {
        if (strcmp(m2c_rt_fx[i].name, name) == 0) {
            for (k = 0; k < m2c_rt_fx[i].n && k < max; ++k) out[k] = m2c_rt_fx[i].vals[k];
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
    out.push("static void m2c_rt_print(const mlc_array *a) {".to_string());
    out.push("    int64_t n = mlc_array_numel(a);".to_string());
    out.push("    for (int64_t i = 0; i < n; ++i) {".to_string());
    out.push("        printf(\" %.10g\", ((const double *)a->data)[i]);".to_string());
    out.push("    }".to_string());
    out.push("}".to_string());
    out.push(String::new());
    // 逐函数跑 → 抽成函数，main 才能对**多个夹具**各跑一遍
    out.push("static double vals[M2C_MAX_VALS];".to_string());
    out.push(String::new());
    out.push("static int m2c_rt_run_all(void) {".to_string());

    for f in funcs {
        if !drivable(f) {
            // 被 reject 的（cell / varargin）与"缺形状"是两件事：
            // 前者永远转不了，后者补注解就行 —— 输出里必须分开，否则读者会去补注解。
            match &f.reject {
                Some(reason) => out.push(format!(
                    "    printf(\"{}: skipped (reject:{})\\n\");",
                    ident(&f.name), reason)),
                None => out.push(format!(
                    "    printf(\"{}: skipped (no shape)\\n\");",
                    ident(&f.name))),
            }
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
            "        int got_{} = m2c_rt_get(\"{}\", vals, M2C_MAX_VALS);",
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
                "        int got_{0} = m2c_rt_get(\"{1}\", vals, M2C_MAX_VALS);",
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
                "        int got_{0} = m2c_rt_get(\"{1}\", vals, M2C_MAX_VALS);",
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
            let rn = crate::emit::ret_cname(f, &r.name);
            if crate::emit::ret_is_dynamic(f, &r.name) {
                // 长度数据相关：算子自己分配；零初始化以保证 free 安全
                out.push(format!("        mlc_array {} = {{0}};", rn));
            } else {
                out.push(format!("        mlc_array {};", rn));
                out.push(format!(
                    "        mlc_array_init(&{}, MLC_F64, 1, (int64_t[]){{1}});",
                    rn
                ));
            }
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
            out.push(format!("            m2c_rt_print(&{});", rn));
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
    out.push(String::new());
    out.push("int main(int argc, char **argv) {".to_string());
    out.push("    if (argc <= 1) {".to_string());
    out.push("        return m2c_rt_run_all();   /* 无夹具：默认输入 a[i]=i+1 */".to_string());
    out.push("    }".to_string());
    out.push("    for (int fi = 1; fi < argc; ++fi) {".to_string());
    out.push("        if (argc > 2) printf(\"=== %s\\n\", argv[fi]);".to_string());
    out.push("        m2c_rt_nfx = 0;            /* 每个夹具重新开始 */".to_string());
    out.push("        m2c_rt_load(argv[fi]);".to_string());
    out.push("        int rc = m2c_rt_run_all();".to_string());
    out.push("        if (rc != 0) return rc;".to_string());
    out.push("    }".to_string());
    out.push("    return 0;".to_string());
    out.push("}".to_string());
    out.join("\n")
}



/// 夹具样例：按**参数名**给出可直接用的值。
///
/// 为什么不能只在 README 里写格式：读文档要动手抄，而"抄错一个逗号"的成本
/// 比"复制一个文件"高得多。
fn gen_fixture_example(funcs: &[Func]) -> String {
    let mut out: Vec<String> = Vec::new();
    out.push("# 夹具样例：按参数名给值，可直接 `./build/demo fixture.example.txt`".to_string());
    out.push("# 数组按 numel 给足；标量给一个整数。".to_string());
    let mut seen: Vec<String> = Vec::new();
    for f in funcs {
        if !drivable(f) {
            continue;
        }
        for a in &f.args {
            if seen.iter().any(|x| x == &a.name) {
                continue;
            }
            seen.push(a.name.clone());
            if a.dtype == "i64" {
                out.push(format!("{} = 2", a.name));
            } else if a.shape.is_empty() {
                continue;
            } else {
                let n: i64 = a.shape.iter().product();
                let vals: Vec<String> =
                    (1..=n.min(16)).map(|i| i.to_string()).collect();
                out.push(format!("{} = {}", a.name, vals.join(" ")));
            }
        }
    }
    out.join("\n") + "\n"
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
    out.push("夹具样例就在本目录：`fixture.example.txt`（复制改名即可）。".to_string());
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
/// 把 `@sdpvar/sort.m` 变成可用文件名 `sdpvar_sort`。
///
/// 不能直接用原路径：`@` `+` `.` 在构建工具里不友好；保留目录段是为了
/// 区分 `a/util.m` 与 `b/util.m` 这类同名不同目录。
fn c_file_stem(srcfile: &str) -> String {
    let mut out = String::new();
    for ch in srcfile.chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch.to_ascii_lowercase());
        } else if !out.ends_with('_') && !out.is_empty() {
            out.push('_');
        }
    }
    let trimmed = out.trim_matches('_').to_string();
    if trimmed.is_empty() {
        "gen_part".to_string()
    } else {
        trimmed
    }
}

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

    // **按源文件拆分**：真实工程里 2MB 的单文件没法定位编译错误，
    // 也没法"改一个 .m 只看一个 .c"。没有 srcfile 时保持原来的单文件输出。
    let split = funcs.iter().any(|f| !f.srcfile.is_empty());
    let mut parts: Vec<(String, Vec<&Func>)> = Vec::new();
    if split {
        for f in funcs {
            let key = if f.srcfile.is_empty() {
                "_unknown.m".to_string()
            } else {
                f.srcfile.clone()
            };
            match parts.iter_mut().find(|(k, _)| *k == key) {
                Some(slot) => slot.1.push(f),
                None => parts.push((key, vec![f])),
            }
        }
    }

    let mut c = vec![
        format!("/* {} —— 由 m2c 生成，勿手改 */", name),
        format!("#include \"{}.h\"", name),
        String::new(),
    ];
    let mut extra: Vec<(String, String)> = Vec::new();
    if split {
        for (srcfile, fs) in &parts {
            let stem = c_file_stem(srcfile);
            let mut body = vec![
                format!("/* {} ← 源文件：{} */", stem, srcfile),
                format!("#include \"{}.h\"", name),
                String::new(),
            ];
            for f in fs {
                body.push(emit_func(f, funcs)?);
                body.push(String::new());
            }
            extra.push((format!("src/gen/{}.c", stem), body.join("\n") + "\n"));
            // 总装文件只做 include：编译单元仍是一个，符号不会重复
            c.push(format!("#include \"gen/{}.c\"", stem));
        }
    } else {
        for f in funcs {
            c.push(emit_func(f, funcs)?);
            c.push(String::new());
        }
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

    let mut files_out = vec![
        (format!("include/{}.h", name), h.join("\n") + "\n"),
        ("src/gen.c".to_string(), c.join("\n") + "\n"),
        ("src/main.c".to_string(), emit_main(funcs, name) + "\n"),
        ("src/selftest.c".to_string(), emit_selftest(funcs, name, cases) + "\n"),
        ("CMakeLists.txt".to_string(), cmake.join("\n") + "\n"),
        ("README.md".to_string(), gen_readme(name)),
        ("fixture.example.txt".to_string(), gen_fixture_example(funcs)),
        // 用户很可能把生成工程直接提交：默认就把构建产物挡在外面
        (".gitignore".to_string(),
         concat!("build/\n", "*.exe\n", "*.o\n", "*.obj\n", "*.a\n",
                "*.lib\n", "CMakeCache.txt\n", "CMakeFiles/\n")
             .to_string()),
    ];
    files_out.extend(extra);
    Ok(files_out)
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
    out.push("static int m2c_rt_fail = 0;".to_string());
    out.push(String::new());
    out.push("static void m2c_rt_check(const char *cname, const char *fname,".to_string());
    out.push("                      const mlc_array *a, const char *want,".to_string());
    out.push("                      int64_t want_n) {".to_string());
    out.push("    /* 先比长度：动态形状下「长度对但内容错」与「长度就错」要分开报 */".to_string());
    out.push("    if (mlc_array_numel(a) != want_n) {".to_string());
    out.push("        printf(\"FAIL [%s] %s: 元素个数 %lld，期望 %lld\\n\",".to_string());
    out.push("               cname, fname, (long long)mlc_array_numel(a),".to_string());
    out.push("               (long long)want_n);".to_string());
    out.push("        m2c_rt_fail = 1;".to_string());
    out.push("        return;".to_string());
    out.push("    }".to_string());
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
    out.push("        m2c_rt_fail = 1;".to_string());
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
                let rn = crate::emit::ret_cname(f, &r.name);
                if crate::emit::ret_is_dynamic(f, &r.name) {
                    out.push(format!("        mlc_array {} = {{0}};", rn));
                } else {
                    out.push(format!("        mlc_array {};", rn));
                    out.push(format!("        mlc_array_init(&{}, MLC_F64, 1, (int64_t[]){{1}});", rn));
                }
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
            // 期望值是状态词时断言**状态**：这正是"该拒的确实拒了"。
            // 以前一律 `if (st == MLC_OK) 比数值`，于是 cellish 这类负面夹具
            // 被静默跳过 —— 负面判据从没被执行过。
            let fname_c = ident(&f.name);
            let stv = format!("st_{}", fname_c);
            // C 侧 main 里没有 `cname` 变量（它只是 m2c_rt_check 的形参），
            // 这里要写**字符串字面量**。
            let clit = format!("\"{}\"", cname);
            let status_checks: Option<Vec<String>> = if want == "unimplemented" {
                Some(vec![
                    format!("        if ({0} != MLC_UNIMPLEMENTED) {{", stv),
                    format!("            printf(\"FAIL [%s] {0}: 期望 unimplemented，实得 %d\\n\",",
                            f.name),
                    format!("                   {1}, (int){0});", stv, clit),
                    "            m2c_rt_fail = 1;".to_string(),
                    "        } else {".to_string(),
                    format!("            printf(\"ok   [%s] {0}: unimplemented\\n\", {1});",
                            f.name, clit),
                    "        }".to_string(),
                ])
            } else if want == "error" {
                Some(vec![
                    format!("        if ({0} == MLC_OK) {{", stv),
                    format!("            printf(\"FAIL [%s] {0}: 期望失败但成功了\\n\", {1});",
                            f.name, clit),
                    "            m2c_rt_fail = 1;".to_string(),
                    "        } else {".to_string(),
                    format!("            printf(\"ok   [%s] {0}: error\\n\", {1});",
                            f.name, clit),
                    "        }".to_string(),
                ])
            } else {
                None
            };
            if let Some(lines) = status_checks {
                out.extend(lines);
            } else if parts.len() == rets.len() && !want.is_empty() {
                for (k, rn) in rets.iter().enumerate() {
                    out.push(format!(
                        "        if (st_{} == MLC_OK) m2c_rt_check(\"{}\", \"{}.{}\", &{}, \"{}\", {});",
                        ident(&f.name), cname, f.name, f.rets[k].name, rn,
                        parts[k].replace('\\', "\\\\").replace('"', "\\\""),
                        parts[k].split_whitespace().count() as i64));
                }
            } else {
                out.push(format!("        /* {} 在这组夹具里没有期望值，跳过比较 */",
                                 f.name));
            }
            // 期望是数值，但调用失败 —— 这是**必须红**的：
            // 以前这里只有 `if (st == MLC_OK) 比数值`，失败时整段被跳过，
            // 于是"把 unimplemented 写成数字"这种错期望仍然是绿的。
            if want != "unimplemented" && want != "error" && !want.is_empty() {
                out.push(format!(
                    "        if (st_{0} != MLC_OK) {{ printf(\"FAIL [%s] {1}: 期望数值，实得状态 %d\\n\", {2}, (int)st_{0}); m2c_rt_fail = 1; }}",
                    ident(&f.name), f.name, clit));
            }
            out.push(format!("        (void)st_{};", ident(&f.name)));
            out.push(format!("        mlc_array_free(&{});", an));
            for rn in &rets {
                out.push(format!("        mlc_array_free(&{});", rn));
            }
            out.push("    }".to_string());
        }
    }
    out.push("    return m2c_rt_fail;".to_string());
    out.push("}".to_string());
    out.join("\n")
}
