//! 工程级产物：头 + 源 + 可运行的 main + CMakeLists（R435）。
//!
//! main.c 不再是空壳：它按 MIR 里的形状构造输入（`a[i] = i+1`，规则写死且确定），
//! 调用每个生成函数并打印结果 —— 这样"生成物能不能算出正确数值"才能被门验证。

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

/// 一个函数能否被 demo main 直接驱动（1 个数组入参 + 1 个数组返回 + 可选 i64 标量）。
fn drivable(f: &Func) -> bool {
    let arrays: Vec<_> = f.args.iter().filter(|a| a.dtype == "f64").collect();
    let scalars: Vec<_> = f.args.iter().filter(|a| a.dtype == "i64").collect();
    arrays.len() == 1
        && scalars.len() == f.args.len() - 1
        && f.rets.len() == 1
        && f.rets[0].dtype == "f64"
        && !arrays[0].shape.is_empty()
}

fn emit_main(funcs: &[Func], name: &str) -> String {
    let mut out: Vec<String> = Vec::new();
    out.push("/* 由 m2c 生成的演示入口：".to_string());
    out.push("   输入按 a[i] = i+1 构造（确定性规则），打印每个函数的结果。 */".to_string());
    out.push(format!("#include \"{}.h\"", name));
    out.push("#include <stdio.h>".to_string());
    out.push(String::new());
    out.push("static void m2c_print(const char *name, const mlc_array *a) {".to_string());
    out.push("    int64_t n = mlc_array_numel(a);".to_string());
    out.push("    printf(\"%s:\", name);".to_string());
    out.push("    for (int64_t i = 0; i < n; ++i) {".to_string());
    out.push("        printf(\" %.10g\", ((const double *)a->data)[i]);".to_string());
    out.push("    }".to_string());
    out.push("    printf(\"\\n\");".to_string());
    out.push("}".to_string());
    out.push(String::new());
    out.push("int main(void) {".to_string());

    for f in funcs {
        if !drivable(f) {
            out.push(format!(
                "    /* {}：形状/签名不满足演示条件，跳过 */", f.name));
            continue;
        }
        let arr = f.args.iter().find(|a| a.dtype == "f64").unwrap();
        let dims: Vec<String> = arr.shape.iter().map(|d| d.to_string()).collect();
        let dt = c_dtype_name(&arr.dtype).unwrap_or("MLC_F64");
        let shape_lit = format!("(int64_t[]){{{}}}", dims.join(", "));
        // 变量名必须与被调函数的形参名一致 —— 写死 x/y 时，`pick(v, i)` 里的
        // `v` 在 main 中根本不存在（gcc: 'v' undeclared）。
        let an = ident(&arr.name);
        let rn = ident(&f.rets[0].name);
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
            "        for (int64_t i = 0; i < mlc_array_numel(&{}); ++i) {{ ((double *){}.data)[i] = (double)(i + 1); }}",
            an, an
        ));
        for s in f.args.iter().filter(|a| a.dtype == "i64") {
            out.push(format!("        int64_t {} = 2;  /* 演示值 */", ident(&s.name)));
        }
        out.push(format!("        mlc_array {};", rn));
        out.push(format!("        mlc_array_init(&{}, MLC_F64, 1, (int64_t[]){{1}});", rn));
        let mut call_args: Vec<String> = Vec::new();
        for a in &f.args {
            call_args.push(ident(&a.name));
        }
        call_args.push(format!("&{}", rn));
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
        out.push(format!("            m2c_print(\"{}\", &{});", ident(&f.name), rn));
        out.push("        }".to_string());
        out.push(format!("        mlc_array_free(&{});", an));
        out.push(format!("        mlc_array_free(&{});", rn));
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
        // 算子原型在 mlc_ops.h —— 少了它，生成代码会报 implicit declaration。
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
        "# 生成代码依赖 mlc 运行时（仓库里的 c_runtime/）。".to_string(),
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
