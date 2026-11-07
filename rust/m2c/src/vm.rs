//! **MIR 解释器**（Rust 运行时）：直接执行 MIR，不经 C 编译。
//!
//! ## 为什么需要它
//!
//! 每一次"数值是否正确"的判定都要靠 Octave。VM 让"这段 MIR 算出来是多少"
//! 变成一个库调用，用于快速自证与回归。
//!
//! **不是**另一条产物线：C 仍是唯一交付物（嵌入式、静态内存、q15）。
//!
//! ## 值模型（R695 起支持二维）
//!
//! `Val { data, rows, cols }`，**行主序存储**（与 C 运行时的 `mlc_array` 一致），
//! 但**线性下标按 MATLAB 的列主序换算**（`(r,c) -> r + c*rows`）。
//!
//! 这个区分是被实测逼出来的：驱动按行主序把 `1..n` 填进形参
//! （`meancols` 的 A 是 `[1 2 3; 4 5 6]`），而 `A(3)` 在 MATLAB 里是 `(1,2)=2`。
//! 两者混用会让归约和下标同时错，且错得很像对的。

use crate::mir::{Cond, Func, Stmt};
use std::collections::HashMap;

/// 值：行主序存储 + 形状。标量是 1×1。
#[derive(Clone, Debug, Default)]
pub struct Val {
    pub data: Vec<f64>,
    pub rows: usize,
    pub cols: usize,
}

impl Val {
    fn scalar(x: f64) -> Val {
        Val {
            data: vec![x],
            rows: 1,
            cols: 1,
        }
    }

    fn from_vec(v: Vec<f64>) -> Val {
        let n = v.len();
        Val {
            data: v,
            rows: 1,
            cols: n.max(1),
        }
    }

    fn zeros(rows: usize, cols: usize, fill: f64) -> Val {
        Val {
            data: vec![fill; rows.max(1) * cols.max(1)],
            rows: rows.max(1),
            cols: cols.max(1),
        }
    }

    fn numel(&self) -> usize {
        self.data.len()
    }

    fn at(&self, r: usize, c: usize) -> f64 {
        self.data[r * self.cols + c]
    }

    /// 形状兼容的逐元素运算：同形，或一方为 1×1（标量广播）。
    fn ew(&self, other: &Val, f: fn(f64, f64) -> f64) -> Result<Val, String> {
        if self.rows == other.rows && self.cols == other.cols {
            return Ok(Val {
                data: self
                    .data
                    .iter()
                    .zip(&other.data)
                    .map(|(a, b)| f(*a, *b))
                    .collect(),
                rows: self.rows,
                cols: self.cols,
            });
        }
        if other.numel() == 1 {
            let k = other.data[0];
            return Ok(Val {
                data: self.data.iter().map(|a| f(*a, k)).collect(),
                rows: self.rows,
                cols: self.cols,
            });
        }
        if self.numel() == 1 {
            let k = self.data[0];
            return Ok(Val {
                data: other.data.iter().map(|b| f(k, *b)).collect(),
                rows: other.rows,
                cols: other.cols,
            });
        }
        Err(format!(
            "形状不匹配：{:?}x{:?} vs {:?}x{:?}",
            self.rows, self.cols, other.rows, other.cols
        ))
    }
}

pub struct Vm {
    env: HashMap<String, Val>,
}

impl Vm {
    pub fn new() -> Self {
        Vm {
            env: HashMap::new(),
        }
    }

    /// 执行一个函数。形参按**行主序**填 `1..=n`（与 C 驱动一致）。
    ///
    /// `shapes` 可覆盖形参形状（`--shape x=2,3`）：回译出的 `.m'` 往往**没有**
    /// `% @m2c shape` 注解，若不做覆盖，两侧输入就不同形 —— 而"输入不同"
    /// 会被误判成"回译算错了"（实测 5 个函数因此假红）。
    pub fn run(
        &mut self,
        f: &Func,
        shapes: &HashMap<String, Vec<i64>>,
    ) -> Result<HashMap<String, Val>, String> {
        self.env.clear();
        let mut effective = Vec::new();
        for a in &f.args {
            let sh = shapes.get(&a.name).cloned().unwrap_or_else(|| a.shape.clone());
            effective.push((a.name.clone(), sh));
        }
        for (name, sh) in &effective {
            let a = crate::mir::Var {
                name: name.clone(),
                dtype: "f64".into(),
                shape: sh.clone(),
            };
            let a = &a;
            // **一维声明按 1×N**（行向量）。这与 C 驱动、Octave 真值的打印口径一致；
            // 若按 N×1 处理，`size(x)` 会返回 `[N 1]` 而不是 `[1 N]`（实测 sizeall 就是这样错的）。
            let single = a.shape.len() < 2;
            let rows = a.shape.first().copied().unwrap_or(3).max(1) as usize;
            let cols = if single {
                rows
            } else {
                a.shape.get(1).copied().unwrap_or(1).max(1) as usize
            };
            let rows = if single { 1 } else { rows };
            let n = rows * cols;
            let v: Vec<f64> = (1..=n).map(|x| x as f64).collect();
            self.env.insert(
                a.name.clone(),
                Val {
                    data: v,
                    rows,
                    cols,
                },
            );
        }
        for l in &f.locals {
            self.env.insert(l.name.clone(), Val::scalar(0.0));
        }
        self.exec_block(&f.body)?;
        let mut out = HashMap::new();
        for r in &f.rets {
            out.insert(
                r.name.clone(),
                self.env.get(&r.name).cloned().unwrap_or_default(),
            );
        }
        Ok(out)
    }

    fn exec_block(&mut self, body: &[Stmt]) -> Result<Flow, String> {
        for st in body {
            match self.exec_stmt(st)? {
                Flow::Next => {}
                f => return Ok(f),
            }
        }
        Ok(Flow::Next)
    }

    fn exec_stmt(&mut self, st: &Stmt) -> Result<Flow, String> {
        match st {
            Stmt::Const { name, value, .. } => {
                let v = to_f64(value).ok_or_else(|| format!("const 不是数字：{}", value))?;
                self.env.insert(name.clone(), Val::scalar(v));
                Ok(Flow::Next)
            }
            Stmt::SetBin { lhs, op, a, b, .. } => {
                let va = self.get(a)?;
                let vb = self.get(b)?;
                let v = match op.as_str() {
                    "add" => va.ew(&vb, |x, y| x + y)?,
                    "sub" => va.ew(&vb, |x, y| x - y)?,
                    "mul" => va.ew(&vb, |x, y| x * y)?,
                    "div" => va.ew(&vb, |x, y| x / y)?,
                    other => return Err(format!("未知 setb 运算：{}", other)),
                };
                self.env.insert(lhs.clone(), v);
                Ok(Flow::Next)
            }
            Stmt::Set { lhs, value, .. } => {
                let v = self.get(value)?;
                self.env.insert(lhs.clone(), v);
                Ok(Flow::Next)
            }
            Stmt::Op(op) => {
                // `y(i) = v` 是**就地写**：要读回 `op.lhs` 当前的值，再改一个元素。
                // 这类算子不能只靠 args 求值（args 里没有被写的数组本身）。
                // `A(i,j) = v`：二维就地写（偏移换算与 OP-INDEX 的列主序一致）
                if op.id == "OP-SETIDX2" {
                    let cur = self
                        .env
                        .get(&op.lhs)
                        .cloned()
                        .ok_or_else(|| format!("setidx2 的目标未定义：{}", op.lhs))?;
                    let i = self.scalar(&op.args[0])? as i64;
                    let j = self.scalar(&op.args[1])? as i64;
                    let v = self.scalar(&op.args[2])?;
                    if i < 1 || j < 1
                        || (i as usize) > cur.rows
                        || (j as usize) > cur.cols
                    {
                        return Err(format!(
                            "setidx2 越界：({},{}) / {}x{}",
                            i, j, cur.rows, cur.cols
                        ));
                    }
                    let mut newv = cur.clone();
                    let pos = (i as usize - 1) * newv.cols + (j as usize - 1);
                    if let Some(slot) = newv.data.get_mut(pos) {
                        *slot = v;
                    }
                    self.env.insert(op.lhs.clone(), newv);
                    return Ok(Flow::Next);
                }
                if op.id == "OP-SETIDX" {
                    let cur = self
                        .env
                        .get(&op.lhs)
                        .cloned()
                        .ok_or_else(|| format!("setidx 的目标未定义：{}", op.lhs))?;
                    let v = self.scalar(&op.args[0])?;
                    let k = self.scalar(&op.args[1])? as i64;
                    if k < 1 || (k as usize) > cur.numel() {
                        return Err(format!("setidx 越界：{} / {}", k, cur.numel()));
                    }
                    let k = (k - 1) as usize;
                    let (r, c) = (k % cur.rows.max(1), k / cur.rows.max(1));
                    let mut newv = cur.clone();
                    let pos = r * newv.cols.max(1) + c;
                    if let Some(slot) = newv.data.get_mut(pos) {
                        *slot = v;
                    }
                    self.env.insert(op.lhs.clone(), newv);
                    return Ok(Flow::Next);
                }
                let v = self.eval_op(&op.id, &op.args)?;
                self.env.insert(op.lhs.clone(), v);
                Ok(Flow::Next)
            }
            Stmt::If {
                cond,
                then_body,
                else_body,
                ..
            } => {
                if self.test(cond)? {
                    self.exec_block(then_body)
                } else {
                    self.exec_block(else_body)
                }
            }
            Stmt::While { cond, body, .. } => {
                let mut guard = 0u64;
                while self.test(cond)? {
                    guard += 1;
                    if guard > 1_000_000 {
                        return Err("while 迭代超过 1e6（疑似死循环）".into());
                    }
                    match self.exec_block(body)? {
                        Flow::Break => break,
                        Flow::Return => return Ok(Flow::Return),
                        Flow::Next => {}
                    }
                }
                Ok(Flow::Next)
            }
            Stmt::For {
                var,
                from,
                to,
                body,
                ..
            } => {
                let a = self.scalar(from)?;
                let b = self.scalar(to)?;
                let mut k = a;
                let mut guard = 0u64;
                while k <= b + 1e-12 {
                    guard += 1;
                    if guard > 1_000_000 {
                        return Err("for 迭代超过 1e6".into());
                    }
                    self.env.insert(var.clone(), Val::scalar(k));
                    match self.exec_block(body)? {
                        Flow::Break => break,
                        Flow::Return => return Ok(Flow::Return),
                        Flow::Next => {}
                    }
                    k += 1.0;
                }
                Ok(Flow::Next)
            }
            Stmt::Break { .. } => Ok(Flow::Break),
            Stmt::Return { .. } => Ok(Flow::Return),
            Stmt::Fail { .. } => Err("MIR 里显式标记了 Fail（该路径不支持）".into()),
            Stmt::Call { func, .. } | Stmt::Call2 { func, .. } => {
                Err(format!("调用未内联的函数：{}（VM 不做链接）", func))
            }
            Stmt::Fill {
                name,
                dims,
                value,
                ..
            } => {
                let rows = dims.first().copied().unwrap_or(0).max(0) as usize;
                let cols = dims.get(1).copied().unwrap_or(1).max(0) as usize;
                let v = to_f64(value).ok_or_else(|| format!("fill 的值不是数字：{}", value))?;
                if rows == 0 || cols == 0 {
                    self.env.insert(
                        name.clone(),
                        Val {
                            data: vec![],
                            rows: 1,
                            cols: 0,
                        },
                    );
                } else {
                    self.env.insert(name.clone(), Val::zeros(rows, cols, v));
                }
                Ok(Flow::Next)
            }
        }
    }

    fn test(&self, c: &Cond) -> Result<bool, String> {
        let a = self.scalar(&c.var)?;
        let b = self.scalar(&c.rhs)?;
        Ok(match c.cmp.as_str() {
            "lt" => a < b,
            "le" => a <= b,
            "gt" => a > b,
            "ge" => a >= b,
            "eq" => (a - b).abs() < 1e-12,
            "ne" => (a - b).abs() >= 1e-12,
            other => return Err(format!("未知比较：{}", other)),
        })
    }

    fn scalar(&self, tok: &str) -> Result<f64, String> {
        let v = self.get(tok)?;
        v.data
            .first()
            .copied()
            .ok_or_else(|| format!("空值：{}", tok))
    }

    fn get(&self, tok: &str) -> Result<Val, String> {
        let t = tok.trim();
        if let Some(x) = to_f64(t) {
            return Ok(Val::scalar(x));
        }
        self.env
            .get(t)
            .cloned()
            .ok_or_else(|| format!("未定义的量：{}", t))
    }

    /// 沿第 1 维（列）归约 —— MATLAB 的默认行为。结果是 **1×cols**。
    fn reduce_cols(&self, a: &Val, f: fn(&[f64]) -> f64) -> Val {
        // **沿第一个非单维归约**（MATLAB 规则）：
        // 行向量（rows==1）→ 全部元素归约成一个标量；否则逐列归约。
        // 少了这条，`sum([1 4 9])` 会返回 `1 4 9`（每列只有一个元素），
        // 实测让 `dotp`/`dynsum`/`fir_lp` 等 5 个函数同时算错。
        if a.rows == 1 {
            return Val::scalar(f(&a.data));
        }
        let mut out = Vec::with_capacity(a.cols);
        for c in 0..a.cols {
            let col: Vec<f64> = (0..a.rows).map(|r| a.at(r, c)).collect();
            out.push(f(&col));
        }
        Val::from_vec(out)
    }

    fn eval_op(&self, id: &str, args: &[String]) -> Result<Val, String> {
        let unary = |f: fn(f64) -> f64| -> Result<Val, String> {
            let a = self.get(&args[0])?;
            Ok(Val {
                data: a.data.iter().map(|x| f(*x)).collect(),
                rows: a.rows,
                cols: a.cols,
            })
        };
        let binary = |f: fn(f64, f64) -> f64| -> Result<Val, String> {
            let a = self.get(&args[0])?;
            let b = self.get(&args[1])?;
            a.ew(&b, f)
        };
        match id {
            "OP-ADD" => binary(|x, y| x + y),
            "OP-SUB" => binary(|x, y| x - y),
            "OP-MUL" => binary(|x, y| x * y),
            "OP-DIV" => binary(|x, y| x / y),
            "OP-ABS" => unary(f64::abs),
            "OP-SQRT" => unary(f64::sqrt),
            "OP-LOG10" => unary(f64::log10),
            "OP-SIN" => unary(f64::sin),
            "OP-FLOOR" => unary(f64::floor),
            // ---- 归约：沿列（MATLAB 默认）----
            "OP-SUM" => Ok(self.reduce_cols(&self.get(&args[0])?, |v| v.iter().sum())),
            "OP-MEAN" => Ok(self.reduce_cols(&self.get(&args[0])?, |v| {
                if v.is_empty() {
                    f64::NAN
                } else {
                    v.iter().sum::<f64>() / v.len() as f64
                }
            })),
            "OP-MAX" => Ok(self.reduce_cols(&self.get(&args[0])?, |v| {
                v.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
            })),
            "OP-MIN" => Ok(self.reduce_cols(&self.get(&args[0])?, |v| {
                v.iter().cloned().fold(f64::INFINITY, f64::min)
            })),
            // ---- 谓词/尺寸 ----
            "OP-ISEMPTY" => Ok(Val::scalar(if self.get(&args[0])?.numel() == 0 {
                1.0
            } else {
                0.0
            })),
            "OP-NUMEL" => Ok(Val::scalar(self.get(&args[0])?.numel() as f64)),
            "OP-LENGTH" => {
                let a = self.get(&args[0])?;
                Ok(Val::scalar(a.rows.max(a.cols) as f64))
            }
            "OP-ANY" => Ok(Val::scalar(if self.get(&args[0])?.data.iter().any(|x| *x != 0.0) {
                1.0
            } else {
                0.0
            })),
            "OP-ALL" => Ok(Val::scalar(if self.get(&args[0])?.data.iter().all(|x| *x != 0.0) {
                1.0
            } else {
                0.0
            })),
            "OP-NNZ" => Ok(Val::scalar(
                self.get(&args[0])?
                    .data
                    .iter()
                    .filter(|x| **x != 0.0)
                    .count() as f64,
            )),
            // ---- 尺寸查询 ----
            "OP-SIZE" => {
                let a = self.get(&args[0])?;
                if args.len() >= 2 {
                    let d = self.scalar(&args[1])? as usize;
                    let v = if d == 1 { a.rows } else { a.cols };
                    Ok(Val::scalar(v as f64))
                } else {
                    Ok(Val::from_vec(vec![a.rows as f64, a.cols as f64]))
                }
            }
            "OP-COPY" => self.get(&args[0]),
            // ---- 转置 ----
            "OP-TRANSPOSE" => {
                let a = self.get(&args[0])?;
                let mut data = vec![0.0; a.numel()];
                for r in 0..a.rows {
                    for c in 0..a.cols {
                        data[c * a.rows + r] = a.at(r, c);
                    }
                }
                Ok(Val {
                    data,
                    rows: a.cols,
                    cols: a.rows,
                })
            }
            // ---- 矩阵乘（行向量 × 列向量时退化为内积）----
            "OP-MATMUL" => {
                let a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                if a.cols != b.rows {
                    return Err(format!(
                        "矩阵乘维度不匹配：{}x{} * {}x{}",
                        a.rows, a.cols, b.rows, b.cols
                    ));
                }
                let mut data = vec![0.0; a.rows * b.cols];
                for r in 0..a.rows {
                    for c in 0..b.cols {
                        let mut acc = 0.0;
                        for k in 0..a.cols {
                            acc += a.at(r, k) * b.at(k, c);
                        }
                        data[r * b.cols + c] = acc;
                    }
                }
                Ok(Val {
                    data,
                    rows: a.rows,
                    cols: b.cols,
                })
            }
            // ---- 相等判定（逐元素全等）----
            "OP-ISEQUAL" | "OP-ISEQUALK" => {
                let a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                let same = a.numel() == b.numel()
                    && a
                        .data
                        .iter()
                        .zip(&b.data)
                        .all(|(x, y)| (x - y).abs() < 1e-12);
                Ok(Val::scalar(if same { 1.0 } else { 0.0 }))
            }
            // ---- 集合差：a 中不在 b 里的元素，去重升序 ----
            "OP-SETDIFF" => {
                let a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                let mut out: Vec<f64> = a
                    .data
                    .iter()
                    .cloned()
                    .filter(|x| !b.data.iter().any(|y| (y - x).abs() < 1e-12))
                    .collect();
                out.sort_by(|x, y| x.partial_cmp(y).unwrap_or(std::cmp::Ordering::Equal));
                out.dedup_by(|x, y| (*x - *y).abs() < 1e-12);
                Ok(Val::from_vec(out))
            }
            // ---- 展平：按**列主序**拉成 1×N（MATLAB 的 `A(:)`）----
            "OP-FLATTEN" => {
                let a = self.get(&args[0])?;
                let mut out = Vec::with_capacity(a.numel());
                for c in 0..a.cols {
                    for r in 0..a.rows {
                        out.push(a.at(r, c));
                    }
                }
                Ok(Val::from_vec(out))
            }
            // ---- 按运行期维度造数组：`alloc.fill:dst:m:n:v` ----
            "OP-FILLA" => {
                let m = self.scalar(&args[0])?.max(0.0) as usize;
                let n = self.scalar(&args[1])?.max(0.0) as usize;
                let v = self.scalar(&args[2])?;
                if m == 0 || n == 0 {
                    Ok(Val {
                        data: vec![],
                        rows: 1,
                        cols: 0,
                    })
                } else {
                    Ok(Val::zeros(m, n, v))
                }
            }
            // ---- `find(a cmp b)`：逐元素比较两个数组，返回线性下标 ----
            "OP-FIND2" => {
                let a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                let sym = cmp_sym(&args[2])?;
                let mut out = Vec::new();
                for c in 0..a.cols.max(b.cols) {
                    for r in 0..a.rows.max(b.rows) {
                        if sym(a.at(r, c), b.at(r, c)) {
                            out.push((r + c * a.rows.max(1) + 1) as f64);
                        }
                    }
                }
                Ok(Val::from_vec(out))
            }
            // ---- `find(cond, n)`：前 n 个满足条件的线性下标 ----
            "OP-FIND3" => {
                let a = self.get(&args[0])?;
                let sym = cmp_sym(&args[1])?;
                let k = self.scalar(&args[2])?;
                let n = self.scalar(&args[3])? as usize;
                let mut out = Vec::new();
                for c in 0..a.cols {
                    for r in 0..a.rows {
                        if sym(a.at(r, c), k) {
                            out.push((r + c * a.rows + 1) as f64);
                            if out.len() >= n {
                                return Ok(Val::from_vec(out));
                            }
                        }
                    }
                }
                Ok(Val::from_vec(out))
            }
            // ---- 线性下标：**列主序换算**（与 MATLAB 一致）----
            "OP-INDEX" => {
                let a = self.get(&args[0])?;
                let k = self.scalar(&args[1])? as i64;
                if k < 1 || (k as usize) > a.numel() {
                    return Err(format!("下标越界：{} / {}", k, a.numel()));
                }
                let k = (k - 1) as usize;
                let (r, c) = (k % a.rows, k / a.rows);
                Ok(Val::scalar(a.at(r, c)))
            }
            // ---- 切片（1-based 闭区间，按线性下标）----
            "OP-SLICE" => {
                let a = self.get(&args[0])?;
                let from = self.scalar(&args[1])? as i64;
                let to = self.scalar(&args[2])? as i64;
                let n = a.numel() as i64;
                let (lo, hi) = (from.max(1), to.min(n));
                if lo > hi {
                    return Ok(Val::from_vec(vec![]));
                }
                // 线性区间按列主序取，再还原行主序
                let mut out = Vec::new();
                for k in (lo - 1)..hi {
                    let k = k as usize;
                    out.push(a.at(k % a.rows, k / a.rows));
                }
                Ok(Val::from_vec(out))
            }
            // ---- 行/列切片 ----
            "OP-ROW" => {
                let a = self.get(&args[0])?;
                let r = self.scalar(&args[1])? as usize;
                if r < 1 || r > a.rows {
                    return Err(format!("行越界：{} / {}", r, a.rows));
                }
                let mut out = Vec::with_capacity(a.cols);
                for c in 0..a.cols {
                    out.push(a.at(r - 1, c));
                }
                Ok(Val::from_vec(out))
            }
            "OP-COLRANGE" => {
                let a = self.get(&args[0])?;
                let from = self.scalar(&args[1])? as i64;
                let to_tok = args[2].trim();
                let to = if to_tok == "-1" {
                    a.cols as i64
                } else {
                    self.scalar(to_tok)? as i64
                };
                let (lo, hi) = (from.max(1), to.min(a.cols as i64));
                if lo > hi {
                    return Ok(Val::zeros(a.rows, 0, 0.0));
                }
                let mut out = vec![0.0; a.rows * (hi - lo + 1) as usize];
                for r in 0..a.rows {
                    for (i, c) in (lo..=hi).enumerate() {
                        out[r * (hi - lo + 1) as usize + i] = a.at(r, (c - 1) as usize);
                    }
                }
                Ok(Val {
                    data: out,
                    rows: a.rows,
                    cols: (hi - lo + 1) as usize,
                })
            }
            // ---- 逻辑下标选值（结果变短）----
            "OP-MASK" => {
                let a = self.get(&args[0])?;
                let k = self.scalar(&args[2])?;
                let sym = cmp_sym(&args[1])?;
                Ok(Val::from_vec(
                    a.data.iter().cloned().filter(|x| sym(*x, k)).collect(),
                ))
            }
            // ---- 查找：满足条件的 1-based 线性下标（列主序）----
            "OP-FIND" => {
                let a = self.get(&args[0])?;
                let k = self.scalar(&args[2])?;
                let sym = cmp_sym(&args[1])?;
                let mut out = Vec::new();
                for c in 0..a.cols {
                    for r in 0..a.rows {
                        if sym(a.at(r, c), k) {
                            out.push((r + c * a.rows + 1) as f64);
                        }
                    }
                }
                Ok(Val::from_vec(out))
            }
            // ---- 拼接 ----
            "OP-HCAT" => {
                let a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                if a.rows != b.rows {
                    return Err("水平拼接行数不同".into());
                }
                let cols = a.cols + b.cols;
                let mut out = Vec::with_capacity(a.rows * cols);
                for r in 0..a.rows {
                    for c in 0..a.cols {
                        out.push(a.at(r, c));
                    }
                    for c in 0..b.cols {
                        out.push(b.at(r, c));
                    }
                }
                Ok(Val {
                    data: out,
                    rows: a.rows,
                    cols,
                })
            }
            "OP-VCAT" => {
                let a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                if a.cols != b.cols {
                    return Err("竖直拼接列数不同".into());
                }
                let mut data = a.data.clone();
                data.extend(b.data.clone());
                Ok(Val {
                    data,
                    rows: a.rows + b.rows,
                    cols: a.cols,
                })
            }
            other => Err(format!("VM 未实现该算子：{}", other)),
        }
    }
}

enum Flow {
    Next,
    Break,
    Return,
}

fn to_f64(t: &str) -> Option<f64> {
    t.trim().parse::<f64>().ok()
}

/// 掩码/查找的比较码 → 判定函数。**取值来自 C 的 `mlc_mask_test`**。
fn cmp_sym(code: &str) -> Result<fn(f64, f64) -> bool, String> {
    Ok(match code.trim() {
        "0" => |a, b| a > b,
        "1" => |a, b| a >= b,
        "2" => |a, b| a < b,
        "3" => |a, b| a <= b,
        "4" => |a, b| (a - b).abs() < 1e-12,
        "5" => |a, b| (a - b).abs() >= 1e-12,
        o => return Err(format!("未知比较码：{}", o)),
    })
}
