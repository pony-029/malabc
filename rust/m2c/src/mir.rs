//! MIR：MATLAB 的**语句级**中间表示（R434 / Week1；R435 加形状与循环）。
//!
//! 文本格式（行式，故意不用 JSON —— 零依赖下自写 JSON 解析器是负债）：
//!
//! ```text
//! version 2
//! func:addone
//! arg:x:f64:3          # 名字:类型:形状（形状可省略，省略即"未知"）
//! ret:y:f64:3
//! op:OP-ADD:y:x:x
//! end
//! ```
//!
//! 为什么要有形状：`mlc_ops.h` 的约定是**调用方先初始化 out 的 dtype/形状**，
//! 算子只填数据。没有形状，生成的 C 会拿一个未初始化的 `mlc_array` 去写 ——
//! 编译能过、运行是垃圾值。所以形状必须进 MIR，不能靠猜。
//!
//! 设计纪律：
//! * **不认识的行 = 错误**（不静默跳过，否则 MIR 会悄悄变短）；
//! * `unmapped:` 是**一等公民**：显式记录"这段没被确定性映射"，
//!   发射器必须把它变成 TODO + 明确失败，而不是猜一段翻译。

/// 一条算子用例：`op:<OP-ID>:<lhs>:<arg>[:<arg>...]`
#[derive(Debug, Clone, PartialEq)]
pub struct Op {
    pub id: String,
    pub lhs: String,
    pub args: Vec<String>,
}

/// 变量声明：名字 / dtype / 形状（形状为空 = 未知）。
#[derive(Debug, Clone, PartialEq)]
pub struct Var {
    pub name: String,
    pub dtype: String,
    pub shape: Vec<i64>,
}

/// 一个 MATLAB 函数（MIR 的作用域单位）。
#[derive(Debug, Clone, PartialEq)]
pub struct Func {
    pub name: String,
    pub args: Vec<Var>,
    pub rets: Vec<Var>,
    pub ops: Vec<Op>,
    /// `for:<循环变量>:<起>:<止>` 的展开形式：这里只记循环体起点下标。
    pub loops: Vec<Loop>,
    /// `if:<变量>:<比较>:<右值>` 块。
    pub ifs: Vec<If>,
    /// 未能映射的原始语句（保持原文，便于人读与 TODO 注释）。
    pub unmapped: Vec<String>,
}

/// 一个 `if/else`（本版只支持「标量与整数字面量比较」这一种条件）。
///
/// 为什么要这么窄：没有表达式 IR 的时候，把任意条件原样透传成 C 会
/// **把未验证的语义悄悄带进生成物**。这里只收 `== != < <= > >=` 六种，
/// 其余一律 `unmapped` —— 宁可不生成，也不生成一段没把握的代码。
#[derive(Debug, Clone, PartialEq)]
pub struct If {
    pub var: String,
    pub cmp: String,
    pub rhs: String,
    pub then_ops: Vec<Op>,
    pub else_ops: Vec<Op>,
}

/// 一个 `for` 循环（本版只支持 `i = a:b` 的整数步长）。
#[derive(Debug, Clone, PartialEq)]
pub struct Loop {
    pub var: String,
    pub from: String,
    pub to: String,
    /// 该循环体包含的算子（按出现顺序）。
    pub ops: Vec<Op>,
}

impl Func {
    /// 作用域内已声明的名字（参数 + 返回值 + 所有算子输出 + 循环变量）。
    pub fn declared(&self) -> Vec<String> {
        let mut v = Vec::new();
        for a in &self.args {
            v.push(a.name.clone());
        }
        for r in &self.rets {
            v.push(r.name.clone());
        }
        for op in &self.ops {
            v.push(op.lhs.clone());
        }
        for lp in &self.loops {
            v.push(lp.var.clone());
            for op in &lp.ops {
                v.push(op.lhs.clone());
            }
        }
        for blk in &self.ifs {
            for op in blk.then_ops.iter().chain(blk.else_ops.iter()) {
                v.push(op.lhs.clone());
            }
        }
        v.sort();
        v.dedup();
        v
    }

    pub fn var_shape(&self, name: &str) -> Option<Vec<i64>> {
        for a in self.args.iter().chain(self.rets.iter()) {
            if a.name == name {
                return if a.shape.is_empty() { None } else { Some(a.shape.clone()) };
            }
        }
        None
    }

    pub fn var_dtype(&self, name: &str) -> Option<String> {
        for a in self.args.iter().chain(self.rets.iter()) {
            if a.name == name {
                return Some(a.dtype.clone());
            }
        }
        None
    }
}

fn parse_var(spec: &str) -> Result<Var, String> {
    let parts: Vec<&str> = spec.split(':').map(|x| x.trim()).collect();
    if parts.len() < 2 {
        return Err(format!("变量声明至少要有 名字:类型：{}", spec));
    }
    let mut shape = Vec::new();
    if parts.len() >= 3 && !parts[2].is_empty() {
        for d in parts[2].split(',') {
            let v: i64 = d
                .trim()
                .parse()
                .map_err(|_| format!("形状不是整数：{}", spec))?;
            if v <= 0 {
                return Err(format!("形状必须为正：{}", spec));
            }
            shape.push(v);
        }
    }
    Ok(Var {
        name: parts[0].to_string(),
        dtype: parts[1].to_string(),
        shape,
    })
}

fn parse_op(rest: &str) -> Result<Op, String> {
    let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
    if parts.len() < 3 {
        return Err(format!("op 至少要有 id/lhs/一个参数：{}", rest));
    }
    let args: Vec<String> = parts[2..]
        .iter()
        .filter(|x| !x.is_empty())
        .map(|x| x.to_string())
        .collect();
    if args.is_empty() {
        return Err(format!("op 参数为空：{}", rest));
    }
    Ok(Op {
        id: parts[0].to_string(),
        lhs: parts[1].to_string(),
        args,
    })
}

/// 解析 MIR 文本。任何不认识的构造都是错误 —— 宁可红，不要静默丢语句。
pub fn parse(text: &str) -> Result<Vec<Func>, String> {
    let mut funcs: Vec<Func> = Vec::new();
    let mut cur: Option<Func> = None;
    let mut loop_cur: Option<Loop> = None;
    let mut if_cur: Option<If> = None;
    let mut in_else = false;
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
            if v != 1 && v != 2 {
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
                loops: Vec::new(),
                ifs: Vec::new(),
                unmapped: Vec::new(),
            });
            continue;
        }
        if line == "else" {
            if if_cur.is_none() {
                return Err(format!("第 {} 行：多余的 else", lineno + 1));
            }
            in_else = true;
            continue;
        }
        if line == "end" {
            if let Some(blk) = if_cur.take() {
                if let Some(f) = cur.as_mut() {
                    f.ifs.push(blk);
                }
                in_else = false;
                continue;
            }
            if let Some(lp) = loop_cur.take() {
                // `end` 关的是循环体
                if let Some(f) = cur.as_mut() {
                    f.loops.push(lp);
                }
                continue;
            }
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
            f.args.push(parse_var(rest)?);
        } else if let Some(rest) = line.strip_prefix("ret:") {
            f.rets.push(parse_var(rest)?);
        } else if let Some(rest) = line.strip_prefix("for:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 3 {
                return Err(format!("for 需要 变量:起:止：{}", rest));
            }
            loop_cur = Some(Loop {
                var: parts[0].to_string(),
                from: parts[1].to_string(),
                to: parts[2].to_string(),
                ops: Vec::new(),
            });
        } else if let Some(rest) = line.strip_prefix("if:") {
            if if_cur.is_some() {
                return Err(format!("第 {} 行：if 不支持嵌套（本版）", lineno + 1));
            }
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 3 {
                return Err(format!("if 需要 变量:比较:右值：{}", rest));
            }
            if !["eq", "ne", "lt", "le", "gt", "ge"].contains(&parts[1]) {
                return Err(format!("不支持的比较符：{}", parts[1]));
            }
            if_cur = Some(If {
                var: parts[0].to_string(),
                cmp: parts[1].to_string(),
                rhs: parts[2].to_string(),
                then_ops: Vec::new(),
                else_ops: Vec::new(),
            });
        } else if let Some(rest) = line.strip_prefix("op:") {
            let op = parse_op(rest)?;
            if let Some(blk) = if_cur.as_mut() {
                if in_else {
                    blk.else_ops.push(op);
                } else {
                    blk.then_ops.push(op);
                }
            } else {
                match loop_cur.as_mut() {
                    Some(lp) => lp.ops.push(op),
                    None => f.ops.push(op),
                }
            }
        } else if let Some(rest) = line.strip_prefix("unmapped:") {
            f.unmapped.push(rest.to_string());
        } else {
            return Err(format!("第 {} 行：不认识的构造：{}", lineno + 1, line));
        }
    }

    if if_cur.is_some() {
        return Err("文件结束时仍有未收束的 if".to_string());
    }
    if loop_cur.is_some() {
        return Err("文件结束时仍有未收束的 for".to_string());
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
