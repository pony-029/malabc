//! MIR → C 发射器（R434 … R437）。
//!
//! 四条纪律：
//! 1. **不猜**：未实现的算子、未知形状、作用域外的名字 → `TODO` + `return MLC_UNIMPLEMENTED`；
//! 2. **确定性**：同样的 MIR 必须产出逐字节相同的 C；
//! 3. **只调 `mlc.h` / `mlc_ops.h` 已有契约**；
//! 4. **谁分配谁释放**：局部临时由本函数 `mlc_array_free`；返回值由调用方释放。

use crate::mir::{walk_stmts, Cond, Func, Op, Stmt};

/// 已经有 C 落点的算子（与 `translate/operators.py` 的 `C_IMPLEMENTED` 对齐）。
pub const C_IMPLEMENTED: &[&str] = &[
    "OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV", "OP-SUM", "OP-MEAN", "OP-MAX",
    "OP-MIN", "OP-INDEX",
];

/// 已知但 C 落点仍未实现的算子（诚实边界）。
pub const C_UNIMPLEMENTED: &[&str] = &["OP-TRANSPOSE", "OP-MATMUL"];

/// 全归约算子：输出形状固定 `[1]`。
const REDUCTIONS: &[&str] = &["OP-SUM", "OP-MEAN", "OP-MAX", "OP-MIN"];

pub fn is_implemented(id: &str) -> bool {
    C_IMPLEMENTED.contains(&id)
}

/// C 标识符清洗。
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

fn c_dtype(dt: &str) -> Option<&'static str> {
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

fn is_scalar_dt(dt: &str) -> bool {
    dt == "i64" || dt == "i32"
}

fn sanitize_comment(s: &str) -> String {
    s.replace("*/", "* /").replace('\n', " ")
}

pub fn op_c_name(id: &str) -> String {
    id.trim_start_matches("OP-").to_lowercase().replace('-', "_")
}

fn is_int_literal(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_ascii_digit())
}

/// 按尾维对齐的广播；不可广播返回 None。与 `mlc_ops.c` / `fidelity.py` 同规则。
pub fn bcast_shape(a: &[i64], b: &[i64]) -> Option<Vec<i64>> {
    let n = a.len().max(b.len());
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let da = if i + a.len() >= n { a[i + a.len() - n] } else { 1 };
        let db = if i + b.len() >= n { b[i + b.len() - n] } else { 1 };
        if da != db && da != 1 && db != 1 {
            return None;
        }
        out.push(da.max(db));
    }
    Some(out)
}

/// 函数原型。
pub fn proto(f: &Func) -> String {
    let mut params: Vec<String> = Vec::new();
    for a in &f.args {
        if is_scalar_dt(&a.dtype) {
            params.push(format!("int64_t {}", ident(&a.name)));
        } else {
            params.push(format!("mlc_array {}", ident(&a.name)));
        }
    }
    for r in &f.rets {
        if is_scalar_dt(&r.dtype) {
            params.push(format!("int64_t *{}", ident(&r.name)));
        } else {
            params.push(format!("mlc_array *{}", ident(&r.name)));
        }
    }
    if params.is_empty() {
        params.push("void".to_string());
    }
    format!("mlc_status m2c_{}({});", ident(&f.name), params.join(", "))
}

fn shape_literal(shape: &[i64]) -> String {
    let dims: Vec<String> = shape.iter().map(|d| d.to_string()).collect();
    format!("(int64_t[]){{{}}}", dims.join(", "))
}

fn init_call(var: &str, dtype: &str, shape: &[i64], is_ptr: bool) -> Option<String> {
    let dt = c_dtype(dtype)?;
    let target = if is_ptr { var.to_string() } else { format!("&{}", var) };
    Some(format!(
        "    if (mlc_array_init({}, {}, {}, {}) != MLC_OK) {{ return MLC_ERR; }}",
        target,
        dt,
        shape.len(),
        shape_literal(shape)
    ))
}

fn out_shape(f: &Func, op: &Op) -> Option<Vec<i64>> {
    if REDUCTIONS.contains(&op.id.as_str()) || op.id == "OP-INDEX" {
        return Some(vec![1]);
    }
    let s0 = f.var_shape(&op.args[0]);
    if op.args.len() == 2 {
        let s1 = f.var_shape(&op.args[1]);
        if let (Some(a), Some(b)) = (s0.clone(), s1.clone()) {
            return bcast_shape(&a, &b);
        }
    }
    s0
}

/// 某个名字的形状：取**最后一条写它**的算子的输出形状（含嵌套块）。
fn out_shape_for(f: &Func, name: &str) -> Option<Vec<i64>> {
    let mut shape = None;
    walk_stmts(&f.body, &mut |s| {
        if let Stmt::Op(op) = s {
            if op.lhs == name {
                shape = out_shape(f, op).or_else(|| shape.clone());
            }
        }
    });
    shape
}

/// 作为**输入**使用一个名字时的 C 写法：
/// * `i64` 标量 → 名字本身
/// * 返回值（`mlc_array *` 形参）→ 名字本身（已经是指针）
/// * 局部临时（`mlc_array` 值）→ `&名字`
fn arg_ref(f: &Func, name: &str) -> String {
    if f.var_dtype(name).map(|d| is_scalar_dt(&d)).unwrap_or(false) {
        return ident(name);
    }
    if f.rets.iter().any(|r| r.name == name) {
        return ident(name);
    }
    format!("&{}", ident(name))
}

fn emit_op(f: &Func, op: &Op, out_is_ptr: bool, indent: &str) -> Vec<String> {
    let mut out = Vec::new();
    let pad = indent.to_string();
    let lhs = ident(&op.lhs);
    let dst = if out_is_ptr { lhs.clone() } else { format!("&{}", lhs) };

    if !is_implemented(&op.id) {
        let why = if C_UNIMPLEMENTED.contains(&op.id.as_str()) {
            "C 落点未实现（诚实边界）"
        } else {
            "未知算子"
        };
        out.push(format!("{}/* {}: {} */", pad, op.id, why));
        out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
        return out;
    }

    for a in &op.args {
        let declared = f.declared().iter().any(|d| d == a);
        let lit = is_int_literal(a);
        if !declared && !(lit && op.id == "OP-INDEX") {
            out.push(format!(
                "{}/* TODO(arg): {} 不在作用域内（参数/返回值/已映射输出里都没有）*/",
                pad,
                sanitize_comment(a)
            ));
            out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
            return out;
        }
    }

    let arg0 = arg_ref(f, &op.args[0]);
    if op.id == "OP-INDEX" {
        if op.args.len() != 2 {
            out.push(format!("{}/* TODO(OP-INDEX): 需要 2 个参数，实际 {} */",
                             pad, op.args.len()));
            out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
            return out;
        }
        let idx = &op.args[1];
        if !is_int_literal(idx) {
            let dt = f.var_dtype(idx).unwrap_or_default();
            if !is_scalar_dt(&dt) {
                out.push(format!(
                    "{}/* TODO(OP-INDEX): 索引 {} 不是 i64 标量（mlc_op_index 要 int64_t）*/",
                    pad,
                    sanitize_comment(idx)
                ));
                out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
                return out;
            }
        }
        let idx_c = if is_int_literal(idx) {
            format!("(int64_t){}", idx)
        } else {
            ident(idx)
        };
        out.push(format!("{}st = mlc_op_index({}, {}, {});", pad, arg0, idx_c, dst));
    } else if op.args.len() == 1 {
        out.push(format!("{}st = mlc_op_{}({}, {});", pad, op_c_name(&op.id), arg0, dst));
    } else if op.args.len() == 2 {
        let arg1 = arg_ref(f, &op.args[1]);
        out.push(format!(
            "{}st = mlc_op_{}({}, {}, {});",
            pad,
            op_c_name(&op.id),
            arg0,
            arg1,
            dst
        ));
    } else {
        out.push(format!("{}/* TODO({}): 参数个数 {} 超出本版能力 */",
                         pad, op.id, op.args.len()));
        out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
        return out;
    }
    out.push(format!("{}if (st != MLC_OK) {{ return st; }}", pad));
    out
}

fn cmp_c(op: &str) -> &'static str {
    match op {
        "eq" => "==",
        "ne" => "!=",
        "lt" => "<",
        "le" => "<=",
        "gt" => ">",
        _ => ">=",
    }
}

/// 条件 → C 表达式；不合法返回 None（调用方发 TODO）。
fn cond_expr(f: &Func, c: &Cond) -> Option<String> {
    if !f.var_dtype(&c.var).map(|d| is_scalar_dt(&d)).unwrap_or(false) {
        return None;
    }
    let rhs = if is_int_literal(&c.rhs) {
        c.rhs.clone()
    } else if f.var_dtype(&c.rhs).map(|d| is_scalar_dt(&d)).unwrap_or(false) {
        ident(&c.rhs)
    } else {
        return None;
    };
    Some(format!("{} {} {}", ident(&c.var), cmp_c(&c.cmp), rhs))
}

/// 标量右值 → C 表达式。只接受整数字面量与已声明的 i64 标量。
fn scalar_expr(f: &Func, tok: &str) -> Option<String> {
    if is_int_literal(tok) {
        return Some(tok.to_string());
    }
    match f.var_dtype(tok) {
        Some(dt) if is_scalar_dt(&dt) => Some(ident(tok)),
        _ => None,
    }
}

fn c_bin(op: &str) -> &'static str {
    match op {
        "add" => "+",
        "sub" => "-",
        "mul" => "*",
        _ => "/",
    }
}

/// 递归发射一段语句。返回 (行列表, 是否已终止)。
fn emit_block(f: &Func, stmts: &[Stmt], indent: &str,
              known: &[Func]) -> (Vec<String>, bool) {
    let mut out: Vec<String> = Vec::new();
    let mut terminated = false;
    for s in stmts {
        if terminated {
            break;
        }
        match s {
            Stmt::Op(op) => {
                let is_ret = f.rets.iter().any(|r| r.name == op.lhs);
                let block = emit_op(f, op, is_ret, indent);
                terminated = block.iter().any(|l| l.trim().starts_with("return "));
                out.extend(block);
            }
            Stmt::For { var, from, to, body } => {
                let bound = |x: &str| -> Option<String> {
                    if is_int_literal(x) {
                        return Some(x.to_string());
                    }
                    match f.var_dtype(x) {
                        Some(dt) if is_scalar_dt(&dt) => Some(ident(x)),
                        _ => None,
                    }
                };
                match (bound(from), bound(to)) {
                    (Some(a), Some(b)) => {
                        let v = ident(var);
                        out.push(format!("{}for (int64_t {} = {}; {} <= {}; ++{}) {{",
                                         indent, v, a, v, b, v));
                        let (inner, t) = emit_block(f, body, &format!("{}    ", indent), known);
                        out.extend(inner);
                        out.push(format!("{}}}", indent));
                        terminated = t;
                    }
                    _ => {
                        out.push(format!("{}/* TODO(for): 循环边界必须是整数字面量或 i64 标量 */",
                                         indent));
                        out.push(format!("{}return MLC_UNIMPLEMENTED;", indent));
                        terminated = true;
                    }
                }
            }
            Stmt::Set { lhs, value } => {
                let ok_lhs = f
                    .var_dtype(lhs)
                    .map(|d| is_scalar_dt(&d))
                    .unwrap_or(false)
                    || f.locals.iter().any(|v| &v.name == lhs);
                match (ok_lhs, scalar_expr(f, value)) {
                    (true, Some(v)) => {
                        out.push(format!("{}{} = {};", indent, ident(lhs), v))
                    }
                    _ => {
                        out.push(format!(
                            "{}/* TODO(set): {} = {} 不是合法的标量赋值 */",
                            indent,
                            sanitize_comment(lhs),
                            sanitize_comment(value)
                        ));
                        out.push(format!("{}return MLC_UNIMPLEMENTED;", indent));
                        terminated = true;
                    }
                }
            }
            Stmt::SetBin { lhs, op, a, b } => {
                match (scalar_expr(f, a), scalar_expr(f, b)) {
                    (Some(x), Some(y)) => out.push(format!(
                        "{}{} = {} {} {};",
                        indent,
                        ident(lhs),
                        x,
                        c_bin(op),
                        y
                    )),
                    _ => {
                        out.push(format!(
                            "{}/* TODO(setb): {} 的操作数不是 i64 标量 */",
                            indent,
                            sanitize_comment(lhs)
                        ));
                        out.push(format!("{}return MLC_UNIMPLEMENTED;", indent));
                        terminated = true;
                    }
                }
            }
            Stmt::Call { lhs, func, args } => {
                // 只调用**同文件内**的生成函数，并且要**签名对得上**：
                // 名字存在但参数个数/类型不符，是比"名字不存在"更隐蔽的错 ——
                // C 编译器会替你挡一部分，但 mlc_array 与 int64_t 的混用它也可能只是警告。
                let callee = known.iter().find(|k| k.name == *func);
                let mut sig_err: Option<String> = None;
                if let Some(c) = callee {
                    if c.args.len() != args.len() {
                        sig_err = Some(format!(
                            "参数个数不符：{} 要 {} 个，实际 {} 个",
                            func, c.args.len(), args.len()));
                    } else if c.rets.len() != 1 {
                        sig_err = Some(format!(
                            "{} 有 {} 个返回值（本版只支持单返回）",
                            func, c.rets.len()));
                    } else {
                        for (actual, formal) in args.iter().zip(c.args.iter()) {
                            let a_scalar = f
                                .var_dtype(actual)
                                .map(|d| is_scalar_dt(&d))
                                .unwrap_or(false);
                            if a_scalar != is_scalar_dt(&formal.dtype) {
                                sig_err = Some(format!(
                                    "参数类型不符：{} 形参 {} 是 {}，实参 {} 是 {}",
                                    func, formal.name, formal.dtype, actual,
                                    f.var_dtype(actual).unwrap_or_default()));
                                break;
                            }
                        }
                    }
                }
                let known_names = callee.is_some() && sig_err.is_none();
                let mut call_args: Vec<String> = Vec::new();
                let mut ok = known_names;
                // 形参一律**按值**（`mlc_array x` / `int64_t i`），
                // 所以实参直接写名字；只有"输出参数"才取地址。
                for a in args {
                    match f.var_dtype(a) {
                        // 形参按值传：返回值是指针，要解引用；其余直接写名字
                        Some(dt) if !is_scalar_dt(&dt)
                            && f.rets.iter().any(|r| &r.name == a) =>
                        {
                            call_args.push(format!("*{}", ident(a)))
                        }
                        Some(_) => call_args.push(ident(a)),
                        None => {
                            ok = false;
                            call_args.push(ident(a));
                        }
                    }
                }
                let is_ret = f.rets.iter().any(|r| &r.name == lhs);
                call_args.push(if is_ret {
                    ident(lhs)
                } else {
                    format!("&{}", ident(lhs))
                });
                if !ok {
                    ok = false;
                }
                if ok {
                    out.push(format!(
                        "{}st = m2c_{}({});",
                        indent,
                        ident(func),
                        call_args.join(", ")
                    ));
                    out.push(format!("{}if (st != MLC_OK) {{ return st; }}", indent));
                } else {
                    let why = match sig_err {
                        Some(e) => format!("TODO(call): {}", e),
                        None => format!("TODO(call): {} 不是本文件里已生成的函数",
                                        func),
                    };
                    out.push(format!("{}{}*/", indent, format!("/* {} ", why)));
                    out.push(format!("{}return MLC_UNIMPLEMENTED;", indent));
                    terminated = true;
                }
            }
            Stmt::While { cond, body } => match cond_expr(f, cond) {
                Some(expr) => {
                    out.push(format!("{}while ({}) {{", indent, expr));
                    let (inner, t) = emit_block(f, body, &format!("{}    ", indent), known);
                    out.extend(inner);
                    out.push(format!("{}}}", indent));
                    terminated = t;
                }
                None => {
                    out.push(format!("{}/* TODO(while): 条件只支持标量与整数/标量比较 */",
                                     indent));
                    out.push(format!("{}return MLC_UNIMPLEMENTED;", indent));
                    terminated = true;
                }
            },
            Stmt::If { cond, then_body, else_body } => match cond_expr(f, cond) {
                Some(expr) => {
                    out.push(format!("{}if ({}) {{", indent, expr));
                    let (a, t1) = emit_block(f, then_body, &format!("{}    ", indent), known);
                    out.extend(a);
                    if !else_body.is_empty() {
                        out.push(format!("{}}} else {{", indent));
                        let (b, t2) = emit_block(f, else_body, &format!("{}    ", indent), known);
                        out.extend(b);
                        terminated = t1 && t2;
                    } else {
                        terminated = t1;
                    }
                    out.push(format!("{}}}", indent));
                }
                None => {
                    out.push(format!("{}/* TODO(if): 条件只支持标量与整数/标量比较 */",
                                     indent));
                    out.push(format!("{}return MLC_UNIMPLEMENTED;", indent));
                    terminated = true;
                }
            },
        }
    }
    (out, terminated)
}

/// 一个函数的 C 定义（支持多返回值与嵌套块）。
pub fn emit_func(f: &Func, known: &[Func]) -> Result<String, String> {
    if f.rets.is_empty() {
        return Err(format!("函数 {} 没有 ret（本版只支持有返回值的函数）", f.name));
    }

    let mut out: Vec<String> = Vec::new();
    out.push(format!("/* 由 m2c 从 MIR 生成 —— 勿手改；来源函数：{} */", f.name));
    out.push(proto(f).replace(';', " {"));
    out.push("    mlc_status st = MLC_OK;".to_string());
    out.push("    (void)st;".to_string());

    for ret in &f.rets {
        if is_scalar_dt(&ret.dtype) {
            continue;
        }
        let name = ident(&ret.name);
        // 形状来源：先看"哪条语句写了它"，否则用 ret 上声明的形状。
        // （`call:` 写出的返回值没有单条算子可查，但它有声明。）
        let shape = match out_shape_for(f, &ret.name).or_else(|| f.var_shape(&ret.name)) {
            Some(sh) => sh,
            None => {
                for u in &f.unmapped {
                    out.push(format!("    /* TODO(unmapped): {} */", sanitize_comment(u)));
                }
                out.push(format!(
                    "    /* TODO(ret): 推断不出 {} 的形状（需要形状标注）*/",
                    ret.name
                ));
                out.push("    return MLC_UNIMPLEMENTED;".to_string());
                out.push("}".to_string());
                return Ok(out.join("\n"));
            }
        };
        match init_call(&name, &ret.dtype, &shape, true) {
            Some(l) => out.push(l),
            None => {
                out.push(format!("    /* TODO(ret): 不支持的 dtype {} */", ret.dtype));
                out.push("    return MLC_UNIMPLEMENTED;".to_string());
                out.push("}".to_string());
                return Ok(out.join("\n"));
            }
        }
    }

    // 局部临时：所有"既不是参数也不是返回值"的算子输出
    let mut need_free: Vec<String> = Vec::new();
    let mut temps: Vec<(String, Vec<i64>)> = Vec::new();
    walk_stmts(&f.body, &mut |s| {
        if let Stmt::Op(op) = s {
            let is_arg = f.args.iter().any(|x| x.name == op.lhs);
            let is_ret = f.rets.iter().any(|x| x.name == op.lhs);
            if is_arg || is_ret {
                return;
            }
            let t = ident(&op.lhs);
            if need_free.contains(&t) {
                return;
            }
            need_free.push(t.clone());
            temps.push((t, out_shape(f, op).unwrap_or_else(|| vec![1])));
        }
    });
    for (t, shape) in &temps {
        out.push(format!("    mlc_array {};", t));
        if let Some(l) = init_call(t, "f64", shape, false) {
            out.push(l);
        }
    }

    for l in &f.locals {
        out.push(format!("    int64_t {} = 0;", ident(&l.name)));
    }
    let (body, terminated) = emit_block(f, &f.body, "    ", known);
    out.extend(body);

    if !terminated {
        if !f.unmapped.is_empty() {
            out.push("    /* 以下语句未能确定性映射（不是猜测的翻译）： */".to_string());
            for u in &f.unmapped {
                out.push(format!("    /* TODO(unmapped): {} */", sanitize_comment(u)));
            }
            out.push("    /* 该函数是**部分实现**：调用方应视为未完成。 */".to_string());
            for t in &need_free {
                out.push(format!("    mlc_array_free(&{});", t));
            }
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
        } else {
            for t in &need_free {
                out.push(format!("    mlc_array_free(&{});", t));
            }
            out.push("    return st;".to_string());
        }
    }
    out.push("}".to_string());
    Ok(out.join("\n"))
}
