//! MIR → C 发射器（R434 / Week1）。
//!
//! 三条纪律（都来自 ADR-005「未验证是一等状态」）：
//! 1. **不猜**：没有 C 落点的算子、作用域里没声明的参数 → `TODO` +
//!    `return MLC_UNIMPLEMENTED`，绝不生成一段"看起来对"的代码；
//! 2. **确定性**：同样的 MIR 必须产出逐字节相同的 C（门会跑两次比对）；
//! 3. **只调 `mlc.h` 已有契约**：`mlc_op_*(const mlc_array*, ..., mlc_array*)`。
//!
//! 参数传递规则（照 `mlc_ops.h` 的真实签名来，不自己发明）：
//! * 数组参数按**值**传 `mlc_array`（小结构体），调用时取 `&名称`；
//! * 数组返回值用 `mlc_array *`，调用时同样取 `&名称`；
//! * `int64_t` 标量（索引）按值传，调用时不取地址，也不声明成 `mlc_array`。

use crate::mir::{Func, Op};

/// 已经有 C 落点的算子（与 `translate/operators.py` 的 `C_IMPLEMENTED` 对齐）。
pub const C_IMPLEMENTED: &[&str] = &[
    "OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV", "OP-SUM", "OP-MEAN", "OP-MAX",
    "OP-MIN", "OP-INDEX",
];

/// 已知但 C 落点仍未实现的算子（诚实边界，发射器要写明）。
pub const C_UNIMPLEMENTED: &[&str] = &["OP-TRANSPOSE", "OP-MATMUL"];

pub fn is_implemented(id: &str) -> bool {
    C_IMPLEMENTED.contains(&id)
}

/// C 标识符清洗：非字母数字下划线 → `_`；首字符是数字则前置 `_`。
pub fn ident(name: &str) -> String {
    let mut out = String::new();
    for (i, c) in name.chars().enumerate() {
        let ok = c.is_ascii_alphanumeric() || c == '_';
        let c2 = if ok { c } else { '_' };
        if i == 0 && c2.is_ascii_digit() {
            out.push('_');
        }
        out.push(c2);
    }
    if out.is_empty() {
        "_".to_string()
    } else {
        out
    }
}

/// 名字 → C 类型：`i64` 是标量，其余一律 `mlc_array`（本版只支持两类）。
fn c_type(dtype: &str) -> &'static str {
    match dtype {
        "i64" => "int64_t",
        _ => "mlc_array",
    }
}

fn is_scalar(dtype: &str) -> bool {
    c_type(dtype) == "int64_t"
}

/// 函数原型（头文件里那一行）。
pub fn proto(f: &Func) -> String {
    let mut params: Vec<String> = Vec::new();
    for (n, t) in &f.args {
        params.push(format!("{} {}", c_type(t), ident(n)));
    }
    for (n, t) in &f.rets {
        params.push(format!("{} *{}", c_type(t), ident(n)));
    }
    if params.is_empty() {
        params.push("void".to_string());
    }
    format!("mlc_status m2c_{}({});", ident(&f.name), params.join(", "))
}

fn sanitize_comment(s: &str) -> String {
    s.replace("*/", "* /").replace('\n', " ")
}

/// `OP-ADD` → `add`（对应 `mlc_op_add`）
pub fn op_c_name(id: &str) -> String {
    id.trim_start_matches("OP-").to_lowercase().replace('-', "_")
}

/// 表达式：三类名字取地址规则不同 ——
/// * 输入参数按值传 `mlc_array` → `&x`
/// * 返回值已经是 `mlc_array *` → 直接用 `y`（再取地址就是双重指针）
/// * 局部临时按值声明 → `&t`
/// * 标量（`int64_t`）一律按值，不取地址
fn operand(name: &str, scalars: &[String], outs: &[String]) -> String {
    let id = ident(name);
    if scalars.iter().any(|s| s == name) {
        return id;
    }
    if outs.iter().any(|s| s == name) {
        return id; // 已经是指针
    }
    format!("&{}", id)
}

fn emit_op(op: &Op, declared: &[String], scalars: &[String],
           outs: &[String]) -> Vec<String> {
    let mut out = Vec::new();
    let lhs = ident(&op.lhs);

    for a in &op.args {
        if !declared.iter().any(|d| d == a) {
            out.push(format!(
                "    /* TODO(arg): {} 不在作用域内（参数/返回值/已映射输出里都没有）*/",
                sanitize_comment(a)
            ));
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
    }

    if !is_implemented(&op.id) {
        let why = if C_UNIMPLEMENTED.contains(&op.id.as_str()) {
            "C 落点未实现（诚实边界）"
        } else {
            "未知算子"
        };
        out.push(format!("    /* {}: {} */", op.id, why));
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        return out;
    }

    let arg0 = operand(&op.args[0], scalars, outs);
    if op.id == "OP-INDEX" {
        if op.args.len() != 2 {
            out.push(format!("    /* TODO(OP-INDEX): 需要 2 个参数，实际 {} */",
                             op.args.len()));
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
        if !scalars.iter().any(|s| s == &op.args[1]) {
            out.push(format!(
                "    /* TODO(OP-INDEX): 索引 {} 不是 i64 标量（mlc_op_index 要 int64_t）*/",
                sanitize_comment(&op.args[1])
            ));
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
        let idx = ident(&op.args[1]);
        let dst = if outs.iter().any(|s| s == &op.lhs) { lhs.clone() }
                  else { format!("&{}", lhs) };
        out.push(format!("    st = mlc_op_index({}, {}, {});", arg0, idx, dst));
    } else if op.args.len() == 1 {
        let dst = if outs.iter().any(|s| s == &op.lhs) { lhs.clone() }
                  else { format!("&{}", lhs) };
        out.push(format!("    st = mlc_op_{}({}, {});", op_c_name(&op.id), arg0, dst));
    } else if op.args.len() == 2 {
        let arg1 = operand(&op.args[1], scalars, outs);
        let dst = if outs.iter().any(|s| s == &op.lhs) { lhs.clone() }
                  else { format!("&{}", lhs) };
        out.push(format!("    st = mlc_op_{}({}, {}, {});",
                         op_c_name(&op.id), arg0, arg1, dst));
    } else {
        out.push(format!("    /* TODO({}): 参数个数 {} 超出本版能力 */",
                         op.id, op.args.len()));
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        return out;
    }
    out.push("    if (st != MLC_OK) { return st; }".to_string());
    out
}

/// 一个函数的 C 定义。
pub fn emit_func(f: &Func) -> Result<String, String> {
    if f.rets.is_empty() {
        return Err(format!("函数 {} 没有 ret（本版只支持有返回值的函数）", f.name));
    }
    if f.rets.len() > 1 {
        return Err(format!("函数 {} 有多个返回值（本版只支持单返回）", f.name));
    }

    let declared = f.declared();
    let mut scalars: Vec<String> = Vec::new();
    for (n, t) in f.args.iter().chain(f.rets.iter()) {
        if is_scalar(t) {
            scalars.push(n.clone());
        }
    }

    let mut out: Vec<String> = Vec::new();
    out.push(format!("/* 由 m2c 从 MIR 生成 —— 勿手改；来源函数：{} */", f.name));
    out.push(proto(f).replace(';', " {"));

    let arg_names: Vec<&str> = f.args.iter().map(|(n, _)| n.as_str()).collect();
    let ret_names: Vec<&str> = f.rets.iter().map(|(n, _)| n.as_str()).collect();
    let out_names: Vec<String> = f.rets.iter().map(|(n, _)| n.clone()).collect();
    let mut temps: Vec<String> = Vec::new();
    for op in &f.ops {
        if !arg_names.contains(&op.lhs.as_str()) && !ret_names.contains(&op.lhs.as_str()) {
            let t = ident(&op.lhs);
            if !temps.contains(&t) {
                temps.push(t);
            }
        }
    }
    if !temps.is_empty() {
        out.push(format!("    mlc_array {}; /* 局部临时 */", temps.join(", ")));
    }
    out.push("    mlc_status st = MLC_OK;".to_string());

    let mut terminated = false;
    for op in &f.ops {
        if terminated {
            break;
        }
        let block = emit_op(op, &declared, &scalars, &out_names);
        terminated = block.iter().any(|l| l.trim().starts_with("return "));
        out.extend(block);
    }

    if !terminated {
        if !f.unmapped.is_empty() {
            out.push("    /* 以下语句未能确定性映射（不是猜测的翻译）： */".to_string());
            for u in &f.unmapped {
                out.push(format!("    /* TODO(unmapped): {} */", sanitize_comment(u)));
            }
            out.push("    /* 该函数是**部分实现**：调用方应视为未完成。 */".to_string());
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
        } else {
            out.push("    return st;".to_string());
        }
    }
    out.push("}".to_string());
    Ok(out.join("\n"))
}

/// 整个项目：头 + 源 + CMakeLists + main 骨架。
/// 返回 (相对路径, 内容)，**顺序固定**（确定性的一部分）。
pub fn emit_project(funcs: &[Func], name: &str) -> Result<Vec<(String, String)>, String> {
    let guard = format!("M2C_{}_H", ident(name).to_uppercase());
    let mut h = vec![
        format!("/* {} —— 由 m2c 生成，勿手改 */", name),
        format!("#ifndef {}", guard),
        format!("#define {}", guard),
        String::new(),
        "#include \"mlc.h\"".to_string(),
        // 算子原型在 mlc_ops.h —— 少了它，生成代码会报 implicit declaration
        // （这就是"生成物能不能编译"这类门存在的意义：光看代码是像对的）。
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

    let main_c = vec![
        "/* 由 m2c 生成的入口骨架。".to_string(),
        "   TODO(entry): 真实调用尚未接线（工程骨架任务）。 */".to_string(),
        format!("#include \"{}.h\"", name),
        String::new(),
        "int main(void) {".to_string(),
        "    return 0;".to_string(),
        "}".to_string(),
    ];

    Ok(vec![
        (format!("include/{}.h", name), h.join("\n") + "\n"),
        ("src/gen.c".to_string(), c.join("\n") + "\n"),
        ("src/main.c".to_string(), main_c.join("\n") + "\n"),
        ("CMakeLists.txt".to_string(), cmake.join("\n") + "\n"),
    ])
}
