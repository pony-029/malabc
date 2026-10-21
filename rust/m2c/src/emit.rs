//! MIR → C 发射器（R434 / Week1；R435 补形状初始化与可运行入口）。
//!
//! 四条纪律：
//! 1. **不猜**：未实现的算子、未知形状、作用域外的名字 → `TODO` + `return MLC_UNIMPLEMENTED`；
//! 2. **确定性**：同样的 MIR 必须产出逐字节相同的 C；
//! 3. **只调 `mlc.h` / `mlc_ops.h` 已有契约**；
//! 4. **谁分配谁释放**：局部临时由本函数 `mlc_array_free`；返回值由调用方释放。

use crate::mir::{Func, If, Loop, Op};

/// 已经有 C 落点的算子（与 `translate/operators.py` 的 `C_IMPLEMENTED` 对齐）。
pub const C_IMPLEMENTED: &[&str] = &[
    "OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV", "OP-SUM", "OP-MEAN", "OP-MAX",
    "OP-MIN", "OP-INDEX",
];

/// 已知但 C 落点仍未实现的算子（诚实边界，发射器要写明）。
pub const C_UNIMPLEMENTED: &[&str] = &["OP-TRANSPOSE", "OP-MATMUL"];

/// 全归约算子：输出形状固定是 `[1]`。
const REDUCTIONS: &[&str] = &["OP-SUM", "OP-MEAN", "OP-MAX", "OP-MIN"];

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

fn is_scalar(dt: &str) -> bool {
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

/// 函数原型。
pub fn proto(f: &Func) -> String {
    let mut params: Vec<String> = Vec::new();
    for a in &f.args {
        if is_scalar(&a.dtype) {
            params.push(format!("int64_t {}", ident(&a.name)));
        } else {
            params.push(format!("mlc_array {}", ident(&a.name)));
        }
    }
    for r in &f.rets {
        if is_scalar(&r.dtype) {
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

/// 按尾维对齐的广播：逐维取 max；某维既不相等、也不含 1 → 不可广播（返回 None）。
/// 与 `mlc_ops.c::mlc_bcast_shape` 和 `fidelity._bcast_shape` **必须同规则**，
/// 否则"生成出来能编译、跑起来报 ERR"这类错会反复出现。
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

/// 输出形状推断：命中不了就 None（调用方发 TODO）。
fn out_shape(f: &Func, op: &Op) -> Option<Vec<i64>> {
    if REDUCTIONS.contains(&op.id.as_str()) || op.id == "OP-INDEX" {
        return Some(vec![1]);
    }
    // 元素级：按尾维对齐求广播形状（与 mlc_ops.c 的 mlc_bcast_shape 同规则）。
    let s0 = f.var_shape(&op.args[0]);
    if op.args.len() == 2 {
        let s1 = f.var_shape(&op.args[1]);
        if let (Some(a), Some(b)) = (s0.clone(), s1.clone()) {
            return bcast_shape(&a, &b);
        }
    }
    s0
}

fn shape_literal(shape: &[i64]) -> String {
    let dims: Vec<String> = shape.iter().map(|d| d.to_string()).collect();
    format!("(int64_t[]){{{}}}", dims.join(", "))
}

fn init_call(var: &str, dtype: &str, shape: &[i64], is_ptr: bool) -> Option<String> {
    let dt = c_dtype(dtype)?;
    // 返回值是 `mlc_array *`，直接传；局部临时是值，取地址。
    // （早先一律写 `&var`，结果 `&y` 变成 `mlc_array **` —— gcc 的
    //  incompatible-pointer-types 当场报出来，比运行时的野写便宜得多。）
    let target = if is_ptr {
        var.to_string()
    } else {
        format!("&{}", var)
    };
    Some(format!(
        "    if (mlc_array_init({}, {}, {}, {}) != MLC_OK) {{ return MLC_ERR; }}",
        target,
        dt,
        shape.len(),
        shape_literal(shape)
    ))
}

/// 生成一条算子的 C 语句（不含初始化）。
fn emit_op(f: &Func, op: &Op, out_is_ptr: bool) -> Vec<String> {
    let mut out = Vec::new();
    let lhs = ident(&op.lhs);
    let dst = if out_is_ptr {
        lhs.clone()
    } else {
        format!("&{}", lhs)
    };

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

    // 参数合法性：必须是已声明名字或整数字面量（仅 OP-INDEX 允许字面量）
    for a in &op.args {
        let declared = f.declared().iter().any(|d| d == a);
        let lit = is_int_literal(a);
        if !declared && !(lit && op.id == "OP-INDEX") {
            out.push(format!(
                "    /* TODO(arg): {} 不在作用域内（参数/返回值/已映射输出里都没有）*/",
                sanitize_comment(a)
            ));
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
    }

    let arg0 = ident(&op.args[0]);
    if op.id == "OP-INDEX" {
        if op.args.len() != 2 {
            out.push(format!("    /* TODO(OP-INDEX): 需要 2 个参数，实际 {} */", op.args.len()));
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
        let idx = &op.args[1];
        if !is_int_literal(idx) {
            let dt = f.var_dtype(idx).unwrap_or_default();
            if !is_scalar(&dt) {
                out.push(format!(
                    "    /* TODO(OP-INDEX): 索引 {} 不是 i64 标量（mlc_op_index 要 int64_t）*/",
                    sanitize_comment(idx)
                ));
                out.push("    return MLC_UNIMPLEMENTED;".to_string());
                return out;
            }
        }
        let idx_c = if is_int_literal(idx) {
            format!("(int64_t){}", idx)
        } else {
            ident(idx)
        };
        out.push(format!("    st = mlc_op_index(&{}, {}, {});", arg0, idx_c, dst));
    } else if op.args.len() == 1 {
        out.push(format!("    st = mlc_op_{}(&{}, {});", op_c_name(&op.id), arg0, dst));
    } else if op.args.len() == 2 {
        let arg1 = ident(&op.args[1]);
        out.push(format!(
            "    st = mlc_op_{}(&{}, &{}, {});",
            op_c_name(&op.id),
            arg0,
            arg1,
            dst
        ));
    } else {
        out.push(format!("    /* TODO({}): 参数个数 {} 超出本版能力 */", op.id, op.args.len()));
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        return out;
    }
    out.push("    if (st != MLC_OK) { return st; }".to_string());
    out
}

fn emit_loop(f: &Func, lp: &Loop) -> Vec<String> {
    let mut out = Vec::new();
    let var = ident(&lp.var);
    // 起止必须是整数字面量或已声明标量；不猜
    let bound = |s: &str| -> Option<String> {
        if is_int_literal(s) {
            return Some(s.to_string());
        }
        match f.var_dtype(s) {
            Some(dt) if is_scalar(&dt) => Some(ident(s)),
            _ => None,
        }
    };
    let (a, b) = match (bound(&lp.from), bound(&lp.to)) {
        (Some(a), Some(b)) => (a, b),
        _ => {
            out.push("    /* TODO(for): 循环边界必须是整数字面量或 i64 标量 */".to_string());
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
    };
    out.push(format!("    for (int64_t {} = {}; {} <= {}; ++{}) {{", var, a, var, b, var));
    for op in &lp.ops {
        // 与循环外同一条规则：写返回值时目标已是指针（`y`），写临时才取地址（`&t`）。
        let is_ret = f.rets.iter().any(|r| r.name == op.lhs);
        for line in emit_op(f, op, is_ret) {
            out.push(format!("    {}", line.trim_start()));
        }
    }
    out.push("    }".to_string());
    out
}

/// 某个名字（返回值 / 临时）的形状：取**最后一条写它**的算子的输出形状。
fn out_shape_for(f: &Func, name: &str) -> Option<Vec<i64>> {
    let mut shape = None;
    for op in &f.ops {
        if op.lhs == name {
            shape = out_shape(f, op).or(shape);
        }
    }
    for lp in &f.loops {
        for op in &lp.ops {
            if op.lhs == name {
                shape = out_shape(f, op).or(shape);
            }
        }
    }
    for blk in &f.ifs {
        for op in blk.then_ops.iter().chain(blk.else_ops.iter()) {
            if op.lhs == name {
                shape = out_shape(f, op).or(shape);
            }
        }
    }
    shape
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

fn emit_if(f: &Func, blk: &If) -> Vec<String> {
    let mut out = Vec::new();
    let var = ident(&blk.var);
    // 左值必须是已声明的标量；右值只收整数字面量或标量名（不猜表达式）
    let ok_var = f.var_dtype(&blk.var).map(|d| is_scalar(d.as_str())).unwrap_or(false);
    if !ok_var {
        out.push(format!(
            "    /* TODO(if): 条件变量 {} 不是 i64 标量（本版只支持标量比较）*/",
            sanitize_comment(&blk.var)
        ));
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        return out;
    }
    let rhs = if is_int_literal(&blk.rhs) {
        blk.rhs.clone()
    } else if f.var_dtype(&blk.rhs).map(|d| is_scalar(d.as_str())).unwrap_or(false) {
        ident(&blk.rhs)
    } else {
        out.push(format!(
            "    /* TODO(if): 右值 {} 既不是整数字面量也不是 i64 标量 */",
            sanitize_comment(&blk.rhs)
        ));
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        return out;
    };
    out.push(format!("    if ({} {} {}) {{", var, cmp_c(&blk.cmp), rhs));
    let mut term = false;
    for op in &blk.then_ops {
        let is_ret = f.rets.iter().any(|r| r.name == op.lhs);
        for line in emit_op(f, op, is_ret) {
            term |= line.trim().starts_with("return ");
            out.push(format!("    {}", line.trim_start()));
        }
    }
    if !blk.else_ops.is_empty() {
        out.push("    } else {".to_string());
        for op in &blk.else_ops {
            let is_ret = f.rets.iter().any(|r| r.name == op.lhs);
            for line in emit_op(f, op, is_ret) {
                term |= line.trim().starts_with("return ");
                out.push(format!("    {}", line.trim_start()));
            }
        }
    }
    out.push("    }".to_string());
    let _ = term;
    out
}

/// 一个函数的 C 定义（支持多返回值）。
pub fn emit_func(f: &Func) -> Result<String, String> {
    if f.rets.is_empty() {
        return Err(format!("函数 {} 没有 ret（本版只支持有返回值的函数）", f.name));
    }

    let mut out: Vec<String> = Vec::new();
    out.push(format!("/* 由 m2c 从 MIR 生成 —— 勿手改；来源函数：{} */", f.name));
    out.push(proto(f).replace(';', " {"));
    out.push("    mlc_status st = MLC_OK;".to_string());
    out.push("    (void)st;".to_string());

    // 每个返回值都按自己的形状初始化（mlc.h 要求调用方 init）
    for ret in &f.rets {
        if is_scalar(&ret.dtype) {
            continue;
        }
        let name = ident(&ret.name);
        let shape = match out_shape_for(f, &ret.name) {
            Some(sh) => sh,
            None => {
                if !f.unmapped.is_empty() {
                    out.push("    /* 以下语句未能确定性映射（不是猜测的翻译）： */".to_string());
                    for u in &f.unmapped {
                        out.push(format!("    /* TODO(unmapped): {} */", sanitize_comment(u)));
                    }
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

    // 局部临时
    let mut need_free: Vec<String> = Vec::new();
    for op in &f.ops {
        let is_arg = f.args.iter().any(|x| x.name == op.lhs);
        let is_ret = f.rets.iter().any(|x| x.name == op.lhs);
        if is_arg || is_ret {
            continue;
        }
        let t = ident(&op.lhs);
        if need_free.contains(&t) {
            continue;
        }
        out.push(format!("    mlc_array {};", t));
        let shape = out_shape(f, op).unwrap_or_else(|| vec![1]);
        let dt = "f64".to_string();
        match init_call(&t, &dt, &shape, false) {
            Some(l) => out.push(l),
            None => out.push(format!("    /* TODO({}): 不支持的 dtype */", t)),
        }
        need_free.push(t);
    }

    let mut terminated = false;
    for op in &f.ops {
        if terminated {
            break;
        }
        let is_ret = f.rets.iter().any(|x| x.name == op.lhs);
        let block = emit_op(f, op, is_ret);
        terminated = block.iter().any(|l| l.trim().starts_with("return "));
        out.extend(block);
    }
    for lp in &f.loops {
        if terminated {
            break;
        }
        let block = emit_loop(f, lp);
        terminated = block.iter().any(|l| l.trim().starts_with("return "));
        out.extend(block);
    }
    for blk in &f.ifs {
        if terminated {
            break;
        }
        let block = emit_if(f, blk);
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

/// 返回值的形状：取"最后一条写 ret 的算子"的输出形状。
fn out_shape_last(f: &Func) -> Option<Vec<i64>> {
    let ret_name = &f.rets[0].name;
    let mut shape = None;
    for op in &f.ops {
        if &op.lhs == ret_name {
            shape = out_shape(f, op).or(shape);
        }
    }
    for lp in &f.loops {
        for op in &lp.ops {
            if &op.lhs == ret_name {
                shape = out_shape(f, op).or(shape);
            }
        }
    }
    shape
}
