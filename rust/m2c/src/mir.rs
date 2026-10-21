//! MIR：MATLAB 的**语句级**中间表示（R434 / Week1）。
//!
//! 为什么要有 MIR：Python 侧已经有「一行 → 一个算子」的映射（`translate/operators.py`），
//! 但那只能表达 `y = a + b;`。真实函数有参数、多个语句、变量复用、控制流。
//! MIR 就是这中间那一层：**能被机械校验**，也能被机械发射成 C。
//!
//! 文本格式（行式，故意不用 JSON —— 零依赖下自己写 JSON 解析器是负债）：
//!
//! ```text
//! version 1
//! func:solver
//! arg:x:f64
//! ret:y:f64
//! op:OP-ADD:y:x:x
//! op:OP-SUM:t:x
//! unmapped:y = foo(x) * 2;
//! end
//! ```
//!
//! 设计纪律：
//! * **不认识的行 = 错误**（不静默跳过，否则 MIR 会悄悄变短）；
//! * `unmapped:` 是**一等公民**：它是"这段没被确定性映射"的显式记录，
//!   发射器必须把它变成 C 里的 TODO + 明确失败，而不是猜一段翻译。

/// 一条算子用例：`op:<OP-ID>:<lhs>:<arg>[:<arg>]`
#[derive(Debug, Clone, PartialEq)]
pub struct Op {
    pub id: String,
    pub lhs: String,
    pub args: Vec<String>,
}

/// 一个 MATLAB 函数（MIR 的作用域单位）。
#[derive(Debug, Clone, PartialEq)]
pub struct Func {
    pub name: String,
    pub args: Vec<(String, String)>,
    pub rets: Vec<(String, String)>,
    pub ops: Vec<Op>,
    /// 未能映射的原始语句（保持原文，便于人读与 TODO 注释）。
    pub unmapped: Vec<String>,
}

impl Func {
    /// 作用域内已声明的名字（参数 + 返回值 + 所有算子输出）。
    pub fn declared(&self) -> Vec<String> {
        let mut v = Vec::new();
        for (n, _) in &self.args {
            v.push(n.clone());
        }
        for (n, _) in &self.rets {
            v.push(n.clone());
        }
        for op in &self.ops {
            v.push(op.lhs.clone());
        }
        v.sort();
        v.dedup();
        v
    }
}

fn split_colon<'a>(line: &'a str, want: usize) -> Result<Vec<&'a str>, String> {
    let parts: Vec<&str> = line.splitn(want + 1, ':').collect();
    if parts.len() != want + 1 {
        return Err(format!("字段数不对（期望 {}）：{}", want, line));
    }
    Ok(parts)
}

/// 解析 MIR 文本。任何不认识的构造都是错误 —— 宁可红，不要静默丢语句。
pub fn parse(text: &str) -> Result<Vec<Func>, String> {
    let mut funcs: Vec<Func> = Vec::new();
    let mut cur: Option<Func> = None;
    let mut seen_version = false;

    for (lineno, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix("version ") {
            let v: u32 = rest
                .trim()
                .parse()
                .map_err(|_| format!("第 {} 行：version 不是整数", lineno + 1))?;
            if v != 1 {
                return Err(format!("不支持的 MIR 版本：{}", v));
            }
            seen_version = true;
            continue;
        }
        if let Some(name) = line.strip_prefix("func:") {
            if cur.is_some() {
                return Err(format!("第 {} 行：func 未以 end 收束", lineno + 1));
            }
            cur = Some(Func {
                name: name.trim().to_string(),
                args: Vec::new(),
                rets: Vec::new(),
                ops: Vec::new(),
                unmapped: Vec::new(),
            });
            continue;
        }
        if line == "end" {
            match cur.take() {
                Some(f) => funcs.push(f),
                None => return Err(format!("第 {} 行：多余的 end", lineno + 1)),
            }
            continue;
        }

        let f = match cur.as_mut() {
            Some(f) => f,
            None => return Err(format!("第 {} 行：语句出现在 func 之外", lineno + 1)),
        };

        if let Some(rest) = line.strip_prefix("arg:") {
            let p = split_colon(rest, 1)?;
            f.args.push((p[0].to_string(), p[1].to_string()));
        } else if let Some(rest) = line.strip_prefix("ret:") {
            let p = split_colon(rest, 1)?;
            f.rets.push((p[0].to_string(), p[1].to_string()));
        } else if let Some(rest) = line.strip_prefix("op:") {
            // op:<id>:<lhs>:<a1>[:<a2>...] —— **参数用冒号分隔**（不是空格）。
            // 早期实现按空格切，于是 `OP-ADD:y:x:x` 被解析成一个参数 `x:x`，
            // 发射出的 C 里出现 `&x:x` 这种非法标识符 —— 自证当场抓到。
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() < 3 {
                return Err(format!(
                    "第 {} 行：op 至少要有 id/lhs/一个参数：{}",
                    lineno + 1,
                    line
                ));
            }
            let id = parts[0].to_string();
            let lhs = parts[1].to_string();
            let args: Vec<String> = parts[2..]
                .iter()
                .filter(|x| !x.is_empty())
                .map(|x| x.to_string())
                .collect();
            if args.is_empty() {
                return Err(format!("第 {} 行：op 参数为空", lineno + 1));
            }
            f.ops.push(Op { id, lhs, args });
        } else if let Some(rest) = line.strip_prefix("unmapped:") {
            f.unmapped.push(rest.to_string());
        } else {
            return Err(format!("第 {} 行：不认识的构造：{}", lineno + 1, line));
        }
    }

    if cur.is_some() {
        return Err("文件结束时仍有未收束的 func".to_string());
    }
    if !seen_version {
        return Err("缺少 version 行".to_string());
    }
    if funcs.is_empty() {
        return Err("没有任何 func".to_string());
    }
    Ok(funcs)
}
