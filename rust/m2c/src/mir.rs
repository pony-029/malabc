//! MIR：MATLAB 的**语句级**中间表示（R434 … R437）。
//!
//! 文本格式（行式，故意不用 JSON —— 零依赖下自写 JSON 解析器是负债）：
//!
//! ```text
//! version 3
//! func:pickbig
//! arg:v:f64:3
//! arg:i:i64
//! ret:r:f64:1
//! if:i:gt:1
//! op:OP-INDEX:r:v:i
//! else
//! op:OP-SUM:r:v
//! end
//! end
//! ```
//!
//! 为什么是**语句树**而不是三个平铺列表：真实函数有嵌套（`for` 里套 `if`，
//! `if` 里再套 `for`）。平铺时"这条语句属于哪个块"只能靠下标猜，
//! 而一旦猜错，生成的 C 语义就变了 —— 且看不出来。
//!
//! 设计纪律：
//! * **不认识的行 = 错误**（不静默跳过）；
//! * `unmapped:` 是一等公民：显式记录"这段没被确定性映射"；
//! * 条件只收「标量与整数/标量」的六种比较 —— 没有表达式 IR 时不透传任意条件。

/// 一条算子用例：`op:<OP-ID>:<lhs>:<arg>[:<arg>...]`
#[derive(Debug, Clone, PartialEq)]
pub struct Op {
    pub id: String,
    pub lhs: String,
    pub args: Vec<String>,
    /// 原始 MATLAB 行号；0 = 未知（不伪造映射）。
    pub src: i64,
}

/// 变量声明：名字 / dtype / 形状（形状为空 = 未知）。
#[derive(Debug, Clone, PartialEq)]
pub struct Var {
    pub name: String,
    pub dtype: String,
    pub shape: Vec<i64>,
}

/// 条件：`<变量> <比较> <右值>`，右值是整数字面量或已声明的标量名。
#[derive(Debug, Clone, PartialEq)]
pub struct Cond {
    pub var: String,
    pub cmp: String,
    pub rhs: String,
}

/// 语句树。
#[derive(Debug, Clone, PartialEq)]
pub enum Stmt {
    Op(Op),
    /// `for:<var>:<起>:<止>` —— 整数步长
    For { var: String, from: String, to: String, body: Vec<Stmt>, src: i64 },
    /// `if:<var>:<cmp>:<rhs>` … [`else`]
    If { cond: Cond, then_body: Vec<Stmt>, else_body: Vec<Stmt>, src: i64 },
    /// `while:<var>:<cmp>:<rhs>`
    While { cond: Cond, body: Vec<Stmt>, src: i64 },
    /// `set:<lhs>:<值>` —— 标量赋值（值：整数字面量，或已声明的 i64 标量名）
    Set { lhs: String, value: String, src: i64 },
    /// `setb:<lhs>:<op>:<a>:<b>` —— 标量二元运算（+ - * /），int64
    SetBin { lhs: String, op: String, a: String, b: String, src: i64 },
    /// `call:<lhs>:<函数名>:<实参...>` —— 调用同文件内的另一个生成函数
    Call { lhs: String, func: String, args: Vec<String>, src: i64 },
    /// `fill:<名字>:<d1,d2,...>:<值>` —— 多维常量（`zeros(3)` / `ones(2,3)`）
    ///
    /// 与 `const` 的区别：`const` 是**标量**（1×1），`fill` 带真实形状。
    /// 真实工程的初值多是矩阵，只有标量常量的话，"给矩阵赋初值"这一步就没法表达。
    Fill { name: String, dims: Vec<i64>, value: String, src: i64 },
    /// `const:<名字>:<数值>` —— 立即数变成形状 `[1]` 的数组
    ///
    /// 为什么需要它：算子签名全是 `mlc_array`，没有标量版本。
    /// `r = r * 2` 要么被拒绝（现状），要么给它造一个 1×1 的数组 ——
    /// 后者是 MATLAB 的真实语义（标量就是 1×1）。
    Const { name: String, value: String, src: i64 },
}

/// 一个 MATLAB 函数。
#[derive(Debug, Clone, PartialEq)]
pub struct Func {
    pub name: String,
    pub args: Vec<Var>,
    pub rets: Vec<Var>,
    /// 局部标量声明（`var:n:i64`）。数组临时仍由算子输出隐式产生。
    pub locals: Vec<Var>,
    pub body: Vec<Stmt>,
    pub unmapped: Vec<String>,
    /// 原始 `.m` 内容的 sha256；空 = 没提供（不伪造）。
    pub source_hash: String,
    /// 来源 `.m` 的相对路径（空 = 未知/单文件模式）。
    /// 有了它才能"一个 .m 对应一个 .c"，否则 2MB 的单文件没法定位编译错误。
    pub srcfile: String,
    /// 显式拒绝的原因（如 `varargin`）：签名本身无法用 C 表达。
    /// 有值时**不生成实现**，只留桩 —— 而不是按 f64 硬套。
    pub reject: Option<String>,
}

impl Func {
    /// 作用域内已声明的名字（参数 + 返回值 + 所有算子输出 + 循环变量）。
    /// 是否是 `for` 的循环变量 —— 它在 C 里天然就是 int64_t。
    ///
    /// 没有它的话，`y(i) = x(i)` 里的 i 会被判成"非 i64 标量"，
    /// 而真实代码里用循环变量取下标的写法到处都是。
    pub fn is_loop_var(&self, name: &str) -> bool {
        let mut hit = false;
        walk_stmts(&self.body, &mut |s| {
            if let Stmt::For { var, .. } = s {
                if var == name {
                    hit = true;
                }
            }
        });
        hit
    }

    pub fn declared(&self) -> Vec<String> {
        let mut v: Vec<String> = Vec::new();
        for a in &self.args {
            v.push(a.name.clone());
        }
        for r in &self.rets {
            v.push(r.name.clone());
        }
        for l in &self.locals {
            v.push(l.name.clone());
        }
        walk_stmts(&self.body, &mut |s| match s {
            Stmt::Op(op) => v.push(op.lhs.clone()),
            Stmt::Const { name, .. } => v.push(name.clone()),
            Stmt::Fill { name, .. } => v.push(name.clone()),
            Stmt::For { var, .. } => v.push(var.clone()),
            _ => {}
        });
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
        for a in self.args.iter().chain(self.rets.iter()).chain(self.locals.iter()) {
            if a.name == name {
                return Some(a.dtype.clone());
            }
        }
        None
    }
}

/// 前序遍历所有语句（含嵌套）。
pub fn walk_stmts<F: FnMut(&Stmt)>(stmts: &[Stmt], f: &mut F) {
    for s in stmts {
        f(s);
        match s {
            Stmt::Op(_) | Stmt::Set { .. } | Stmt::SetBin { .. } | Stmt::Call { .. }
            | Stmt::Const { .. } | Stmt::Fill { .. } => {}
            Stmt::For { body, .. } => walk_stmts(body, f),
            Stmt::If { then_body, else_body, .. } => {
                walk_stmts(then_body, f);
                walk_stmts(else_body, f);
            }
            Stmt::While { body, .. } => walk_stmts(body, f),
        }
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
    Ok(Var { name: parts[0].to_string(), dtype: parts[1].to_string(), shape })
}

fn parse_op(rest: &str, src: i64) -> Result<Op, String> {
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
    Ok(Op { id: parts[0].to_string(), lhs: parts[1].to_string(),
            args, src })
}

fn parse_cond(rest: &str, kw: &str) -> Result<Cond, String> {
    let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
    if parts.len() != 3 {
        return Err(format!("{} 需要 变量:比较:右值：{}", kw, rest));
    }
    if !["eq", "ne", "lt", "le", "gt", "ge"].contains(&parts[1]) {
        return Err(format!("不支持的比较符：{}", parts[1]));
    }
    Ok(Cond { var: parts[0].to_string(), cmp: parts[1].to_string(),
              rhs: parts[2].to_string() })
}

enum Frame {
    For { var: String, from: String, to: String, body: Vec<Stmt>, src: i64 },
    If { cond: Cond, then_body: Vec<Stmt>, else_body: Vec<Stmt>, in_else: bool,
         src: i64 },
    While { cond: Cond, body: Vec<Stmt>, src: i64 },
}

fn frame_stmts(f: &mut Frame) -> &mut Vec<Stmt> {
    match f {
        Frame::For { body, .. } => body,
        Frame::If { then_body, else_body, in_else, .. } => {
            if *in_else { else_body } else { then_body }
        }
        Frame::While { body, .. } => body,
    }
}

fn finish_frame(f: Frame) -> Stmt {
    match f {
        Frame::For { var, from, to, body, src } => {
            Stmt::For { var, from, to, body, src }
        }
        Frame::If { cond, then_body, else_body, src, .. } => {
            Stmt::If { cond, then_body, else_body, src }
        }
        Frame::While { cond, body, src } => Stmt::While { cond, body, src },
    }
}

/// 解析 MIR 文本。任何不认识的构造都是错误 —— 宁可红，不要静默丢语句。
pub fn parse(text: &str) -> Result<Vec<Func>, String> {
    let mut funcs: Vec<Func> = Vec::new();
    let mut cur: Option<Func> = None;
    let mut stack: Vec<Frame> = Vec::new();
    let mut seen_version = false;
    let mut pending_src: i64 = 0;
    let mut pending_hash = String::new();
    let mut pending_srcfile = String::new();

    macro_rules! push_stmt {
        ($st:expr) => {{
            let st = $st;
            match stack.last_mut() {
                Some(fr) => frame_stmts(fr).push(st),
                None => match cur.as_mut() {
                    Some(f) => f.body.push(st),
                    None => return Err("语句出现在 func 之外".to_string()),
                },
            }
        }};
    }

    for (lineno, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if let Some(rest) = line.strip_prefix("# source_sha256:") {
            pending_hash = rest.trim().to_string();
            continue;
        }
        if let Some(rest) = line.strip_prefix("# src:") {
            pending_src = rest.trim().parse().unwrap_or(0);
            continue;
        }
        if let Some(p) = line.strip_prefix("# srcfile:") {
            pending_srcfile = p.trim().to_string();
            continue;
        }
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix("version ") {
            let v: u32 = rest
                .trim()
                .parse()
                .map_err(|_| format!("第 {} 行：version 不是整数", lineno + 1))?;
            if !(1..=3).contains(&v) {
                return Err(format!("不支持的 MIR 版本：{}", v));
            }
            seen_version = true;
            continue;
        }
        if let Some(rsn) = line.strip_prefix("reject:") {
            match cur.as_mut() {
                Some(f) => {
                    f.reject = Some(rsn.trim().to_string());
                    continue;
                }
                None => {
                    return Err(format!(
                        "第 {} 行：reject 出现在 func 之前", lineno + 1))
                }
            }
        }
        if let Some(name) = line.strip_prefix("func:") {
            if cur.is_some() {
                return Err(format!("第 {} 行：func 未以 end 收束", lineno + 1));
            }
            cur = Some(Func {
                name: name.trim().to_string(),
                args: Vec::new(),
                rets: Vec::new(),
                locals: Vec::new(),
                body: Vec::new(),
                unmapped: Vec::new(),
                source_hash: pending_hash.clone(),
                srcfile: pending_srcfile.clone(),
                reject: None,
            });
            continue;
        }
        if line == "else" {
            match stack.last_mut() {
                Some(Frame::If { in_else, .. }) => *in_else = true,
                _ => return Err(format!("第 {} 行：多余的 else", lineno + 1)),
            }
            pending_src = 0;
            continue;
        }
        if line == "end" {
            if let Some(fr) = stack.pop() {
                push_stmt!(finish_frame(fr));
                pending_src = 0;
                continue;
            }
            match cur.take() {
                Some(f) => funcs.push(f),
                None => return Err(format!("第 {} 行：多余的 end", lineno + 1)),
            }
            continue;
        }

        if cur.is_none() {
            return Err(format!("第 {} 行：语句出现在 func 之外", lineno + 1));
        }

        if let Some(rest) = line.strip_prefix("arg:") {
            let v = parse_var(rest)?;
            if let Some(f) = cur.as_mut() {
                f.args.push(v);
            }
        } else if let Some(rest) = line.strip_prefix("ret:") {
            let v = parse_var(rest)?;
            if let Some(f) = cur.as_mut() {
                f.rets.push(v);
            }
        } else if let Some(rest) = line.strip_prefix("for:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 3 {
                return Err(format!("for 需要 变量:起:止：{}", rest));
            }
            stack.push(Frame::For {
                var: parts[0].to_string(),
                from: parts[1].to_string(),
                to: parts[2].to_string(),
                body: Vec::new(),
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("while:") {
            let cond = parse_cond(rest, "while")?;
            stack.push(Frame::While { cond, body: Vec::new(), src: pending_src });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("if:") {
            let cond = parse_cond(rest, "if")?;
            stack.push(Frame::If {
                cond,
                then_body: Vec::new(),
                else_body: Vec::new(),
                in_else: false,
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("op:") {
            let op = parse_op(rest, pending_src)?;
            pending_src = 0;
            push_stmt!(Stmt::Op(op));
        } else if let Some(rest) = line.strip_prefix("var:") {
            let v = parse_var(rest)?;
            if let Some(f) = cur.as_mut() {
                f.locals.push(v);
            }
        } else if let Some(rest) = line.strip_prefix("set:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 2 {
                return Err(format!("set 需要 左值:值：{}", rest));
            }
            push_stmt!(Stmt::Set {
                lhs: parts[0].to_string(),
                value: parts[1].to_string(),
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("setb:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 4 {
                return Err(format!("setb 需要 左值:运算:左:右：{}", rest));
            }
            if !["add", "sub", "mul", "div"].contains(&parts[1]) {
                return Err(format!("不支持的标量运算：{}", parts[1]));
            }
            push_stmt!(Stmt::SetBin {
                lhs: parts[0].to_string(),
                op: parts[1].to_string(),
                a: parts[2].to_string(),
                b: parts[3].to_string(),
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("call:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() < 2 {
                return Err(format!("call 需要 左值:函数名：{}", rest));
            }
            let args: Vec<String> = parts[2..]
                .iter()
                .filter(|x| !x.is_empty())
                .map(|x| x.to_string())
                .collect();
            push_stmt!(Stmt::Call {
                lhs: parts[0].to_string(),
                func: parts[1].to_string(),
                args,
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("fill:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 3 {
                return Err(format!("fill 需要 名字:形状:值：{}", rest));
            }
            let mut dims = Vec::new();
            for d in parts[1].split(',') {
                let v: i64 = d
                    .trim()
                    .parse()
                    .map_err(|_| format!("fill 的形状不是整数：{}", rest))?;
                if v <= 0 {
                    return Err(format!("fill 的形状必须为正：{}", rest));
                }
                dims.push(v);
            }
            if dims.is_empty() {
                return Err(format!("fill 缺形状：{}", rest));
            }
            if parts[2].parse::<f64>().is_err() {
                return Err(format!("fill 的值不是数字：{}", rest));
            }
            push_stmt!(Stmt::Fill {
                name: parts[0].to_string(),
                dims,
                value: parts[2].to_string(),
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("const:") {
            let parts: Vec<&str> = rest.split(':').map(|x| x.trim()).collect();
            if parts.len() != 2 {
                return Err(format!("const 需要 名字:数值：{}", rest));
            }
            if parts[1].parse::<f64>().is_err() {
                return Err(format!("const 的数值不是数字：{}", rest));
            }
            push_stmt!(Stmt::Const {
                name: parts[0].to_string(),
                value: parts[1].to_string(),
                src: pending_src,
            });
            pending_src = 0;
        } else if let Some(rest) = line.strip_prefix("unmapped:") {
            if let Some(f) = cur.as_mut() {
                f.unmapped.push(rest.to_string());
            }
            pending_src = 0;
        } else {
            return Err(format!("第 {} 行：不认识的构造：{}", lineno + 1, line));
        }
    }

    if !stack.is_empty() {
        return Err("文件结束时仍有未收束的块".to_string());
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
