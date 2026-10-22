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
    "OP-MIN", "OP-INDEX", "OP-MATMUL", "OP-TRANSPOSE", "OP-SLICE",
    "OP-FLATTEN", "OP-MASK", "OP-FIND", "OP-SETIDX",
];

/// 已知但 C 落点仍未实现的算子（诚实边界）。
//: 目前没有"已知但未实现"的算子了；保留这个清单是为了让"诚实边界"仍然可表达。
pub const C_UNIMPLEMENTED: &[&str] = &[];

/// 全归约算子：输出形状固定 `[1]`。
const REDUCTIONS: &[&str] = &["OP-SUM", "OP-MEAN", "OP-MAX", "OP-MIN"];

pub fn is_implemented(id: &str) -> bool {
    C_IMPLEMENTED.contains(&id)
}

/// C89/C99 关键字：MATLAB 里 `auto`、`int`、`register` 都是合法变量名。
const C_KEYWORDS: &[&str] = &[
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
    "int", "long", "register", "restrict", "return", "short", "signed",
    "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned",
    "void", "volatile", "while", "bool", "true", "false",
];

/// 返回值的 C 名字：与任一参数重名时加 `_out` 后缀。
/// MATLAB 允许 `function x = f(x)`（原地变换），C 里参数不能同名。
pub fn ret_cname(f: &Func, name: &str) -> String {
    let base = ident(name);
    let mut cand = base.clone();
    let mut n = 0;
    loop {
        let clash_arg = f.args.iter().any(|a| ident(&a.name) == cand);
        let clash_ret = f
            .rets
            .iter()
            .any(|r| r.name != name && ident(&r.name) == cand);
        if !clash_arg && !clash_ret {
            return cand;
        }
        n += 1;
        cand = if n == 1 {
            format!("{}_out", base)
        } else {
            format!("{}_out{}", base, n)
        };
    }
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
        return "_".to_string();
    }
    if C_KEYWORDS.contains(&out.as_str()) {
        out.push('_');            /* `auto` -> `auto_` */
    }
    out
}

/// 输出长度**数据相关**的算子：不能由调用方预先 init，
/// 必须由算子自己分配（`*_alloc` 变体），调用方负责 free。
pub const DYNAMIC_OPS: &[&str] = &["OP-MASK", "OP-FIND"];

pub fn op_is_dynamic(id: &str) -> bool {
    DYNAMIC_OPS.contains(&id)
}

/// 这个返回值是不是由动态长度算子产生的。
pub fn ret_is_dynamic(f: &Func, name: &str) -> bool {
    let mut dyn_out = false;
    walk_stmts(&f.body, &mut |s| {
        if let Stmt::Op(op) = s {
            if op.lhs == name && op_is_dynamic(&op.id) {
                dyn_out = true;
            }
        }
    });
    dyn_out
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
        let rn = ret_cname(f, &r.name);
        if is_scalar_dt(&r.dtype) {
            params.push(format!("int64_t *{}", rn));
        } else {
            params.push(format!("mlc_array *{}", rn));
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

/// 若名字其实是**返回值**或**入参**，返回 (实际 C 标识符, 是否指针)。
///
/// 指针 = 返回值（`mlc_array *y`）；非指针 = 入参（`mlc_array x`，按值）。
fn bind_target(f: &Func, name: &str) -> Option<(String, bool)> {
    if let Some(r) = f.rets.iter().find(|r| ident(&r.name) == name) {
        return Some((ret_cname(f, &r.name), true));
    }
    if let Some(a) = f.args.iter().find(|a| ident(&a.name) == name) {
        return Some((ident(&a.name), false));
    }
    None
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
    if op.id == "OP-SUM" && op.args.len() == 1 {
        // MATLAB 的 sum 默认沿**第一个非单例维**；2-D 的 2x3 -> 1x3。
        let s = f.var_shape(&op.args[0])?;
        if s.len() == 1 {
            return Some(vec![1]);
        }
        if s.len() == 2 {
            if s[0] > 1 {
                return Some(vec![1, s[1]]);
            }
            return Some(vec![1]);
        }
        return None; // 3-D+ 暂不推断，避免猜错
    }
    // y(i)=v 是**就地写**：形状沿用目标数组，不产生新对象
    if op.id == "OP-SETIDX" {
        return f.var_shape(&op.lhs);
    }

    if REDUCTIONS.contains(&op.id.as_str()) || op.id == "OP-INDEX" {
        return Some(vec![1]);
    }
    // A(:)：展平成 numel，确定
    if op.id == "OP-FLATTEN" && op.args.len() == 1 {
        let sa = f.var_shape(&op.args[0])?;
        let n: i64 = sa.iter().product();
        return Some(vec![n]);
    }
    // x(x>k)：命中数是**数据相关**的，生成期算不出来 —— 用声明形状，
    // 由 C 侧在运行时校验"命中数 == out 长度"，不符就 MLC_ERR。
    if op.id == "OP-MASK" || op.id == "OP-FIND" {
        return None;   /* 长度数据相关：由算子分配，运行时才知道 */
    }
    // 切片：1-D，长度 = to - from + 1（边界是字面量才算得出）
    if op.id == "OP-SLICE" && op.args.len() == 3 {
        let sa = f.var_shape(&op.args[0])?;
        if sa.len() != 1 {
            return None;
        }
        let from: i64 = op.args[1].parse().ok()?;
        let to: i64 = op.args[2].parse().ok()?;
        if from < 1 || to < from || to > sa[0] {
            return None;
        }
        return Some(vec![to - from + 1]);
    }
    // 转置：形状是 [n, m]
    if op.id == "OP-TRANSPOSE" && op.args.len() == 1 {
        let s = f.var_shape(&op.args[0])?;
        if s.len() != 2 {
            return None;
        }
        return Some(vec![s[1], s[0]]);
    }
    // 矩阵乘：形状是 [a.m, b.n]，不是广播结果（广播会把 2x3 与 3x2 判成不可广播）
    if op.id == "OP-MATMUL" && op.args.len() == 2 {
        let sa = f.var_shape(&op.args[0])?;
        let sb = f.var_shape(&op.args[1])?;
        if sa.len() != 2 || sb.len() != 2 || sa[1] != sb[0] {
            return None;
        }
        return Some(vec![sa[0], sb[1]]);
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
#[cfg(test)]
mod tests {
    use super::*;
    use crate::mir::parse;

    #[test]
    fn sum_2d_shape_is_row_vector() {
        let f = &parse(concat!(
            "version 3\nfunc:f\narg:x:f64:2,3\n",
            "ret:s:f64:1,3\nop:OP-SUM:s:x\nend\n"))
            .unwrap()[0];
        match &f.body[0] {
            Stmt::Op(op) => assert_eq!(out_shape(f, op), Some(vec![1, 3])),
            _ => panic!("expected op"),
        }
    }

    #[test]
    fn op_keeps_source_line() {
        let f = &parse(concat!(
            "version 3\nfunc:f\narg:a:f64:2\n",
            "# src:42\nop:OP-ADD:a:a:a\n# src:55\nop:OP-SUM:a:a\nend\n"))
            .unwrap()[0];
        match &f.body[0] {
            Stmt::Op(op) => assert_eq!(op.src, 42),
            _ => panic!("expected op"),
        }
        match &f.body[1] {
            Stmt::Op(op) => assert_eq!(op.src, 55),
            _ => panic!("expected op"),
        }
    }

    #[test]
    fn non_op_stmt_keeps_source_line() {
        let f = &parse(concat!(
            "version 3\nfunc:f\narg:a:f64:2\n",
            "# src:7\nset:i:1\n# src:9\ncall:a:a\nend\n"))
            .unwrap()[0];
        match &f.body[0] {
            Stmt::Set { src, .. } => assert_eq!(*src, 7),
            _ => panic!("expected set"),
        }
        match &f.body[1] {
            Stmt::Call { src, .. } => assert_eq!(*src, 9),
            _ => panic!("expected call"),
        }
    }

    #[test]
    fn dynamic_mask_shape_is_unknown() {
        let f = &parse(concat!(
            "version 3\nfunc:f\narg:v:f64:3\nret:z:f64:2\n",
            "op:OP-MASK:z:v:0:1\nend\n"))
            .unwrap()[0];
        match &f.body[0] {
            Stmt::Op(op) => assert_eq!(out_shape(f, op), None),
            _ => panic!("expected op"),
        }
    }

}


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
        return ret_cname(f, name);
    }
    format!("&{}", ident(name))
}

fn emit_op(f: &Func, op: &Op, out_is_ptr: bool, indent: &str) -> Vec<String> {
    let mut out = Vec::new();
    let pad = indent.to_string();
    // 给扩展/调试器留可读的源码行号；没有行号就不写，绝不伪造。
    if op.src > 0 {
        out.push(format!("{}/* @m2c src:{} */", pad, op.src));
    }
    let lhs = ident(&op.lhs);
    let dst = if out_is_ptr { lhs.clone() } else { format!("&{}", lhs) };

    // 矩阵乘的约束在**生成时**就校验：留给运行时报错等于把问题推迟到用户那边，
    // 而这里形状是已知的 —— 已知就该拒绝。
    if op.id == "OP-MATMUL" {
        let sa = f.var_shape(&op.args[0]);
        let sb = f.var_shape(&op.args[1]);
        let bad = match (&sa, &sb) {
            (Some(a), Some(b)) => {
                a.len() != 2 || b.len() != 2 || a[1] != b[0]
            }
            _ => false, // 形状未知：交给运行时（out_shape 会发 TODO）
        };
        if bad {
            out.push(format!(
                "    /* TODO(OP-MATMUL): 形状 {:?} x {:?} 不是可乘的 2-D */",
                sa.unwrap_or_default(),
                sb.unwrap_or_default()
            ));
            out.push("    return MLC_UNIMPLEMENTED;".to_string());
            return out;
        }
    }

    // 切片的约束在生成时校验：越界不截断（截断会让错误静默通过）
    if op.id == "OP-SLICE" && op.args.len() == 3 {
        let shape = f.var_shape(&op.args[0]);
        let from: Option<i64> = op.args[1].parse().ok();
        let to: Option<i64> = op.args[2].parse().ok();
        let bad = match (shape, from, to) {
            (Some(sh), Some(a), Some(b)) => {
                sh.len() != 1 || a < 1 || b < a || b > sh[0]
            }
            _ => false, // 形状/边界不全是字面量：交给 out_shape 发 TODO
        };
        if bad {
            out.push(format!(
                "    /* TODO(OP-SLICE): 边界 {}:{} 与形状 {:?} 不匹配 */",
                op.args[1], op.args[2],
                f.var_shape(&op.args[0]).unwrap_or_default()
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
        out.push(format!("{}/* {}: {} */", pad, op.id, why));
        out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
        return out;
    }

    for a in &op.args {
        let declared = f.declared().iter().any(|d| d == a);
        let lit = is_int_literal(a);
        // 作用域检查针对的是**名字**：数值字面量没有作用域可言，
        // 任何算子位置都放行。早先按算子白名单（先 OP-INDEX、后补 OP-SLICE），
        // 每加一个带常量的算子就要再补一次 —— 那是把原则写成了特例。
        if !declared && !lit {
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
            if !is_scalar_dt(&dt) && !f.is_loop_var(idx) {
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
    } else if op.id == "OP-MASK" && op.args.len() == 3 {
        let cmp = &op.args[1];
        let k = &op.args[2];
        let ok = cmp.parse::<i64>().is_ok() && k.parse::<f64>().is_ok();
        if !ok {
            out.push(format!("{}/* TODO(OP-MASK): 比较码/阈值必须是字面量 */", pad));
            out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
            return out;
        }
        // 动态长度：调用 _alloc 变体，dst 直接是 out（由算子分配）
        out.push(format!("{}st = mlc_op_mask_alloc({}, {}, {}, {});",
                         pad, arg0, cmp, k, dst));
    } else if op.id == "OP-FIND" && op.args.len() == 3 {
        let cmp = &op.args[1];
        let k = &op.args[2];
        let ok = cmp.parse::<i64>().is_ok() && k.parse::<f64>().is_ok();
        if !ok {
            out.push(format!("{}/* TODO(OP-FIND): 比较码/阈值必须是字面量 */", pad));
            out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
            return out;
        }
        out.push(format!("{}st = mlc_op_find_alloc({}, {}, {}, {});",
                         pad, arg0, cmp, k, dst));
    } else if op.id == "OP-SLICE" && op.args.len() == 3 {
        let from = &op.args[1];
        let to = &op.args[2];
        let ok_bounds = from.parse::<i64>().is_ok() && to.parse::<i64>().is_ok();
        if !ok_bounds {
            out.push(format!("{}/* TODO(OP-SLICE): 边界必须是整数字面量 */", pad));
            out.push(format!("{}return MLC_UNIMPLEMENTED;", pad));
            return out;
        }
        out.push(format!(
            "{}st = mlc_op_slice({}, {}, {}, {});",
            pad, arg0, from, to, dst));
    } else if op.id == "OP-SETIDX" && op.args.len() == 2 {
        // args = (右值, 下标)；目标数组就是 dst（就地写，不分配）
        let val = arg_ref(f, &op.args[0]);
        let idx = &op.args[1];
        let idx_c = if is_int_literal(idx) {
            format!("(int64_t){}", idx)
        } else {
            ident(idx)
        };
        out.push(format!(
            "{}st = mlc_op_setidx({}, {}, {});", pad, dst, val, idx_c));
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

fn src_comment(src: i64, indent: &str) -> Option<String> {
    if src > 0 {
        Some(format!("{}/* @m2c src:{} */", indent, src))
    } else {
        None
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
            Stmt::For { var, from, to, body, src } => {
                if let Some(c) = src_comment(*src, indent) { out.push(c); }
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
            // const / fill 的值在函数开头就填好了，这里不再产出语句
            Stmt::Const { .. } | Stmt::Fill { .. } => {}
            Stmt::Set { lhs, value, src } => {
                if let Some(c) = src_comment(*src, indent) { out.push(c); }
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
            Stmt::SetBin { lhs, op, a, b, src } => {
                if let Some(c) = src_comment(*src, indent) { out.push(c); }
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
            Stmt::Call { lhs, func, args, src } => {
                if let Some(c) = src_comment(*src, indent) { out.push(c); }
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
                            call_args.push(format!("*{}", ret_cname(f, a)))
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
            Stmt::While { cond, body, src } => {
                if let Some(c) = src_comment(*src, indent) { out.push(c); }
                match cond_expr(f, cond) {
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
                }
            },
            Stmt::If { cond, then_body, else_body, src } => {
                if let Some(c) = src_comment(*src, indent) { out.push(c); }
                match cond_expr(f, cond) {
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
                }
            },
        }
    }
    (out, terminated)
}

/// 一个函数的 C 定义（支持多返回值与嵌套块）。
pub fn emit_func(f: &Func, known: &[Func]) -> Result<String, String> {
    if let Some(reason) = &f.reject {
        // 签名本身无法用 C 表达（varargin/varargout 是 cell、个数可变）。
        // 按 f64 硬套是**静默变义** —— 宁可只给桩，并写清原因。
        let mut out: Vec<String> = Vec::new();
        out.push(format!("/* 由 m2c 从 MIR 生成 —— 来源函数：{} */", f.name));
        out.push(proto(f).replace(';', " {"));
        out.push(format!("    /* TODO(reject): {} 无法用固定签名表达 */", reason));
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        out.push("}".to_string());
        return Ok(out.join("\n"));
    }
    if f.rets.is_empty() {
        // 真实工程里到处是"过程"（无返回值）。整体失败会让整个工程生成不出来，
        // 所以生成一个**明确的桩**：能编译、调用会返回 UNIMPLEMENTED，不假装成功。
        let mut out: Vec<String> = Vec::new();
        out.push(format!("/* 由 m2c 从 MIR 生成 —— 来源函数：{} */", f.name));
        if !f.source_hash.is_empty() {
            out.push(format!("/* @m2c source_sha256:{} */", f.source_hash));
        }
        out.push(proto(f).replace(';', " {"));
        out.push("    /* TODO(void): 无返回值的函数本版不生成实现 */".to_string());
        out.push("    return MLC_UNIMPLEMENTED;".to_string());
        out.push("}".to_string());
        return Ok(out.join("\n"));
    }

    let mut out: Vec<String> = Vec::new();
    out.push(format!("/* 由 m2c 从 MIR 生成 —— 勿手改；来源函数：{} */", f.name));
    if !f.source_hash.is_empty() {
        out.push(format!("/* @m2c source_sha256:{} */", f.source_hash));
    }
    out.push(proto(f).replace(';', " {"));
    out.push("    mlc_status st = MLC_OK;".to_string());
    out.push("    (void)st;".to_string());

    for ret in &f.rets {
        if is_scalar_dt(&ret.dtype) {
            continue;
        }
        let name = ret_cname(f, &ret.name);
        if ret_is_dynamic(f, &ret.name) {
            // 长度数据相关：由算子分配（`*_alloc`）。
            // 注意返回值是**形参指针**（`mlc_array *y`），不能在这里再声明一个同名局部；
            // 调用方负责把它初始化为 {0}，否则 free 会碰到野指针。
            continue;
        }
        // 形状来源：先看"哪条语句写了它"，否则用 ret 上声明的形状。
        // （`call:` 写出的返回值没有单条算子可查，但它有声明。）
        // 形状谎言检测：声明与推断都在时，必须一致。
        // 不一致说明"人写的注解"和"代码真实行为"已经分叉 —— 那是最难查的一类错。
        if let (Some(inferred), Some(declared)) =
            (out_shape_for(f, &ret.name), f.var_shape(&ret.name))
        {
            if inferred != declared {
                out.push(format!(
                    "    /* WARN(shape): {} 声明 {:?} 与推断 {:?} 不一致，按推断执行 */",
                    ret.name, declared, inferred));
                eprintln!(
                    "warn: {} 的 {} 声明形状 {:?} 与推断 {:?} 不一致",
                    f.name, ret.name, declared, inferred);
            }
        }
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
    let mut temps: Vec<(String, Option<Vec<i64>>)> = Vec::new();
    // 立即数也要有实体：算子签名只认 mlc_array
    let mut consts: Vec<(String, String, i64)> = Vec::new();
    // 多维常量：(名字, 形状, 值, 源行)
    let mut fills: Vec<(String, Vec<i64>, String, i64)> = Vec::new();
    walk_stmts(&f.body, &mut |s| match s {
        Stmt::Const { name, value, src } => {
            let n = ident(name);
            if !consts.iter().any(|(x, _, _)| x == &n) {
                consts.push((n, value.clone(), *src));
            }
        }
        Stmt::Fill { name, dims, value, src } => {
            let n = ident(name);
            if !fills.iter().any(|(x, _, _, _)| x == &n) {
                fills.push((n, dims.clone(), value.clone(), *src));
            }
        }
        _ => {}
    });
    walk_stmts(&f.body, &mut |s| {
        // **算子的输出**和**函数调用的输出**都可能是局部数组 ——
        // 只收集前者会让后者的名字从未声明，生成的 C 直接编不过
        // （真实工程里 "B = getbase(Y)" 这种中间变量到处都是）。
        let (lhs, shape) = match s {
            Stmt::Op(op) => {
                let sh = out_shape(f, op);
                // 动态分配型算子由 *_alloc 负责 init；先 init 会泄漏旧 buffer。
                let dynamic = op.id == "OP-MASK" || op.id == "OP-FIND";
                let sh = if sh.is_none() && dynamic {
                    None
                } else {
                    Some(sh.unwrap_or_else(|| vec![1]))
                };
                (op.lhs.clone(), sh)
            }
            Stmt::Call { lhs, .. } => (lhs.clone(), Some(vec![1])),
            _ => return,
        };
        let is_arg = f.args.iter().any(|x| x.name == lhs);
        let is_ret = f.rets.iter().any(|x| x.name == lhs);
        if is_arg || is_ret {
            return;
        }
        let t = ident(&lhs);
        if need_free.contains(&t) {
            return;
        }
        need_free.push(t.clone());
        temps.push((t, shape));
    });
    for (t, shape) in &temps {
        out.push(format!("    mlc_array {};", t));
        if let Some(sh) = shape {
            if let Some(l) = init_call(t, "f64", sh, false) {
                out.push(l);
            }
        }
    }
    // `y = zeros(...)` 里 y 可能是**返回值**或**入参**（它们已经是形参）。
    // 再 `mlc_array y;` 是与形参重定义 —— gcc 直接报 redeclared。
    // 对这两种：不声明、直接往既有对象里 init + 填值。
    for (n, v, src) in &consts {
        if let Some(c) = src_comment(*src, "    ") { out.push(c); }
        let bound = bind_target(f, n);
        let ptr = bound.as_ref().map(|(_, p)| *p).unwrap_or(false);
        let nm = bound.as_ref().map(|(t, _)| t.clone())
            .unwrap_or_else(|| n.clone());
        if bound.is_none() {
            out.push(format!("    mlc_array {};", n));
        }
        if let Some(l) = init_call(&nm, "f64", &[1], ptr) {
            out.push(l);
        }
        if ptr {
            out.push(format!("    ((double *){}->data)[0] = {};", nm, v));
        } else {
            out.push(format!("    ((double *){}.data)[0] = {};", nm, v));
        }
        if bound.is_none() { need_free.push(n.clone()); }
    }
    for (n, dims, v, src) in &fills {
        if let Some(c) = src_comment(*src, "    ") { out.push(c); }
        let bound = bind_target(f, n);
        let ptr = bound.as_ref().map(|(_, p)| *p).unwrap_or(false);
        let nm = bound.as_ref().map(|(t, _)| t.clone())
            .unwrap_or_else(|| n.clone());
        if bound.is_none() {
            out.push(format!("    mlc_array {};", n));
        }
        if let Some(l) = init_call(&nm, "f64", dims, ptr) {
            out.push(l);
        }
        let access = if ptr { format!("{}->data", nm) }
                     else { format!("{}.data", nm) };
        let numel = if ptr { format!("mlc_array_numel({})", nm) }
                    else { format!("mlc_array_numel(&{})", nm) };
        out.push(format!(
            "    for (int64_t i = 0; i < {}; ++i) {{ ((double *){})[i] = {}; }}",
            numel, access, v));
        if bound.is_none() { need_free.push(n.clone()); }
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
