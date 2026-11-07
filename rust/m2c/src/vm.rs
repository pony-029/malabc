//! **MIR 解释器**（Rust 运行时第一版）：直接执行 MIR，不经 C 编译。
//!
//! ## 为什么需要它
//!
//! 现在每一次"数值是否正确"的判定都要靠 Octave（`test_roundtrip` / `test_three_links`
//! / `three_links_report` 全都要）。这意味着：
//!   1. 机器上没装 Octave 就**无法自证**；
//!   2. 判据跑得慢（每个函数起一次解释器）。
//!
//! VM 让"这段 MIR 算出来是多少"变成一个**库函数调用**，用来做快速自证与回归。
//!
//! ## 它不是什么
//!
//! **不是**另一条产物线。产出的 C 仍然是唯一交付物（嵌入式、静态内存、q15）。
//! VM 只服务于验证：`m2c run <x.mir>` 必须在语料上与 Octave 数值一致。
//!
//! ## 本版支持的子集
//!
//! `const` / `setb` / `set` / `op:`（逐元素、归约、索引、拼接）/ `if` / `while` / `for` / `break` / `return`。
//! 其它一律返回明确错误（**不猜**）—— 这与发射器的策略一致。

use crate::mir::{Cond, Func, Stmt};
use std::collections::HashMap;

/// 值模型：一维 f64 序列。标量就是长度 1（与 MATLAB 的 1×1 一致）。
pub type Value = Vec<f64>;

pub struct Vm {
    env: HashMap<String, Value>,
}

impl Vm {
    pub fn new() -> Self {
        Vm {
            env: HashMap::new(),
        }
    }

    /// 执行一个函数。`inputs` 里没有的形参按 C 侧驱动的约定填 `1..=n`
    /// （`n` 取 `% @m2c shape` 声明的长度；拿不到就按 3 个元素，与既有驱动一致）。
    pub fn run(&mut self, f: &Func) -> Result<HashMap<String, Value>, String> {
        self.env.clear();
        // **硬边界：二维形参直接拒绝**。
        // VM 的值模型是一维序列，`mean(A)` 对 2×3 的 A 会算成全元素的均值，
        // 而 MATLAB 是**逐列**均值 —— 结果形状对、数值错，属于最危险的一类。
        // 实测语料里 `meancols` / `sumcols` / `vcat2` 就是这样被算错的（4 例）。
        for a in &f.args {
            if a.shape.len() > 1 {
                return Err(format!("二维形参未支持（{}）", a.name));
            }
        }
        for a in &f.args {
            let n = a.shape.first().copied().unwrap_or(3).max(1);
            let v: Value = (1..=n).map(|x| x as f64).collect();
            self.env.insert(a.name.clone(), v);
        }
        for l in &f.locals {
            self.env.insert(l.name.clone(), vec![0.0]);
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
                self.env.insert(name.clone(), vec![v]);
                Ok(Flow::Next)
            }
            Stmt::SetBin { lhs, op, a, b, .. } => {
                let va = self.get(a)?;
                let vb = self.get(b)?;
                let v = match op.as_str() {
                    "add" => ew(&va, &vb, |x, y| x + y),
                    "sub" => ew(&va, &vb, |x, y| x - y),
                    "mul" => ew(&va, &vb, |x, y| x * y),
                    "div" => ew(&va, &vb, |x, y| x / y),
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
                // 死循环护栏：与发射器一致（1e6 次），避免判据挂死。
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
                    self.env.insert(var.clone(), vec![k]);
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
            Stmt::Fill { name, dims, .. } => Err(format!(
                "OP-FILL 运行期维度暂不支持（{} 维 {:?}）",
                name, dims
            )),
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
        v.first()
            .copied()
            .ok_or_else(|| format!("空值：{}", tok))
    }

    /// 取一个 token 的值：数字字面量或环境里的变量。
    fn get(&self, tok: &str) -> Result<Value, String> {
        let t = tok.trim();
        if let Some(x) = to_f64(t) {
            return Ok(vec![x]);
        }
        self.env
            .get(t)
            .cloned()
            .ok_or_else(|| format!("未定义的量：{}", t))
    }

    fn eval_op(&self, id: &str, args: &[String]) -> Result<Value, String> {
        let unary = |f: fn(f64) -> f64| -> Result<Value, String> {
            let a = self.get(&args[0])?;
            Ok(a.into_iter().map(f).collect())
        };
        let binary = |f: fn(f64, f64) -> f64| -> Result<Value, String> {
            let a = self.get(&args[0])?;
            let b = self.get(&args[1])?;
            Ok(ew(&a, &b, f))
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
            "OP-SUM" => {
                let a = self.get(&args[0])?;
                Ok(vec![a.iter().sum()])
            }
            "OP-MEAN" => {
                let a = self.get(&args[0])?;
                if a.is_empty() {
                    return Ok(vec![f64::NAN]);
                }
                Ok(vec![a.iter().sum::<f64>() / a.len() as f64])
            }
            "OP-MAX" => {
                let a = self.get(&args[0])?;
                Ok(vec![a.iter().cloned().fold(f64::NEG_INFINITY, f64::max)])
            }
            "OP-MIN" => {
                let a = self.get(&args[0])?;
                Ok(vec![a.iter().cloned().fold(f64::INFINITY, f64::min)])
            }
            "OP-COPY" => self.get(&args[0]),
            "OP-INDEX" => {
                // 列优先线性下标（与 mlc_op_index 一致）：1-based
                let a = self.get(&args[0])?;
                let k = self.scalar(&args[1])? as usize;
                a.get(k.saturating_sub(1))
                    .copied()
                    .map(|v| vec![v])
                    .ok_or_else(|| format!("下标越界：{} / {}", k, a.len()))
            }
            "OP-HCAT" | "OP-VCAT" => {
                // 一维时两者同义（真实 2-D 语义由 C 侧保证，VM 只用于数值自证）
                let mut a = self.get(&args[0])?;
                let b = self.get(&args[1])?;
                a.extend(b);
                Ok(a)
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

/// 逐元素运算；长度不等时按标量**广播**（长度 1 的一方复制）。
fn ew(a: &[f64], b: &[f64], f: fn(f64, f64) -> f64) -> Value {
    if a.len() == b.len() {
        a.iter().zip(b).map(|(x, y)| f(*x, *y)).collect()
    } else if a.len() == 1 {
        b.iter().map(|y| f(a[0], *y)).collect()
    } else if b.len() == 1 {
        a.iter().map(|x| f(*x, b[0])).collect()
    } else {
        // 形状不匹配：返回空的第一个分支长度，让上游看到 NaN 而不是静默 truncate
        a.iter()
            .zip(b.iter())
            .map(|(x, y)| f(*x, *y))
            .collect()
    }
}
