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
    arrays.len() == 1
        && scalars.len() == f.args.len() - 1
        && !f.rets.is_empty()
        && f.rets.iter().all(|r| r.dtype == "f64" && !r.shape.is_empty())
        && !arrays[0].shape.is_empty()
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
        let arr = f.args.iter().find(|a| a.dtype == "f64").unwrap();
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
        out.push(format!("        mlc_array_free(&{});", an));
        for rn in &ret_names {
            out.push(format!("        mlc_array_free(&{});", rn));
        }
        out.push("    }".to_string());
    }
    out.push("    return 0;".to_string());
    out.push("}".to_string());
    out.join("\n")
}

/// 整个项目：头 + 源 + main + CMakeLists。顺序固定（确定性）。
pub fn emit_project(funcs: &[Func], name: &str) -> Result<Vec<(String, String)>, String> {
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
        c.push(emit_func(f)?);
        c.push(String::new());
    }

    let cmake = vec![
        "cmake_minimum_required(VERSION 3.10)".to_string(),
        format!("project({} C)", ident(name)),
        "set(CMAKE_C_STANDARD 99)".to_string(),
        String::new(),
        "add_library(m2c_gen STATIC src/gen.c".to_string(),
        "        ${MLC_RUNTIME}/src/mlc_runtime.c".to_string(),
        "        ${MLC_RUNTIME}/src/mlc_ops.c)".to_string(),
        "target_include_directories(m2c_gen PUBLIC include)".to_string(),
        "target_include_directories(m2c_gen PUBLIC ${MLC_RUNTIME}/include)".to_string(),
        String::new(),
        "add_executable(demo src/main.c)".to_string(),
        "target_link_libraries(demo PRIVATE m2c_gen)".to_string(),
    ];

    Ok(vec![
        (format!("include/{}.h", name), h.join("\n") + "\n"),
        ("src/gen.c".to_string(), c.join("\n") + "\n"),
        ("src/main.c".to_string(), emit_main(funcs, name) + "\n"),
        ("CMakeLists.txt".to_string(), cmake.join("\n") + "\n"),
    ])
}
