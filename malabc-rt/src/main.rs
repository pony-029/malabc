//! malabc-rt —— M 语义参考实现的**最小骨架**。
//!
//! 只做一件事：标量 `double` 的四则运算（`+ - * /`、括号、一元正负号），
//! 并按 MATLAB 的显示习惯格式化（整数不带小数点、`Inf` / `-Inf` / `NaN`）。
//!
//! **边界写死，不许漂移**：其它一切输入都以退出码 2 报 `unimplemented`，
//! 绝不返回一个"看起来对"的值 —— 这是本项目「假阳性比漏报更糟」的底线。
//!
//! 判据（`cargo test` 五组 + 三条命令）：
//!   cargo test
//!   malabc-rt eval "1+2*3"    -> 7
//!   malabc-rt eval "1/0"      -> Inf
//!   malabc-rt eval "a+1"      -> 退出码 1（不是 0，也不是一个 NaN 值）

use std::env;
use std::process::ExitCode;

#[derive(Debug, Clone, Copy, PartialEq)]
enum Token {
    Num(f64),
    Plus,
    Minus,
    Star,
    Slash,
    LParen,
    RParen,
}

struct Lexer<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> Lexer<'a> {
    fn new(src: &'a str) -> Self {
        Lexer { s: src.as_bytes(), i: 0 }
    }

    fn tokens(&mut self) -> Result<Vec<Token>, String> {
        let mut out = Vec::new();
        while self.i < self.s.len() {
            let c = self.s[self.i];
            match c {
                b' ' | b'\t' | b'\n' | b'\r' => self.i += 1,
                b'+' => {
                    out.push(Token::Plus);
                    self.i += 1;
                }
                b'-' => {
                    out.push(Token::Minus);
                    self.i += 1;
                }
                b'*' => {
                    out.push(Token::Star);
                    self.i += 1;
                }
                b'/' => {
                    out.push(Token::Slash);
                    self.i += 1;
                }
                b'(' => {
                    out.push(Token::LParen);
                    self.i += 1;
                }
                b')' => {
                    out.push(Token::RParen);
                    self.i += 1;
                }
                b'0'..=b'9' | b'.' => {
                    let start = self.i;
                    while self.i < self.s.len() {
                        let d = self.s[self.i];
                        if d.is_ascii_digit() || d == b'.' || d == b'e' || d == b'E' {
                            self.i += 1;
                        } else {
                            break;
                        }
                    }
                    let txt = std::str::from_utf8(&self.s[start..self.i])
                        .map_err(|_| "bad utf8 in number".to_string())?;
                    let v = txt
                        .parse::<f64>()
                        .map_err(|e| format!("bad number {:?}: {}", txt, e))?;
                    out.push(Token::Num(v));
                }
                other => {
                    return Err(format!(
                        "unimplemented token: {:?} (只支持数字与 + - * / ( ))",
                        other as char
                    ))
                }
            }
        }
        Ok(out)
    }
}

struct Parser {
    t: Vec<Token>,
    i: usize,
}

impl Parser {
    fn peek(&self) -> Option<Token> {
        self.t.get(self.i).copied()
    }

    fn expr(&mut self) -> Result<f64, String> {
        let mut v = self.term()?;
        loop {
            match self.peek() {
                Some(Token::Plus) => {
                    self.i += 1;
                    v += self.term()?;
                }
                Some(Token::Minus) => {
                    self.i += 1;
                    v -= self.term()?;
                }
                _ => break,
            }
        }
        Ok(v)
    }

    fn term(&mut self) -> Result<f64, String> {
        let mut v = self.unary()?;
        loop {
            match self.peek() {
                Some(Token::Star) => {
                    self.i += 1;
                    v *= self.unary()?;
                }
                Some(Token::Slash) => {
                    self.i += 1;
                    v /= self.unary()?;
                }
                _ => break,
            }
        }
        Ok(v)
    }

    fn unary(&mut self) -> Result<f64, String> {
        match self.peek() {
            Some(Token::Minus) => {
                self.i += 1;
                Ok(-self.unary()?)
            }
            Some(Token::Plus) => {
                self.i += 1;
                self.unary()
            }
            _ => self.primary(),
        }
    }

    fn primary(&mut self) -> Result<f64, String> {
        match self.peek() {
            Some(Token::Num(v)) => {
                self.i += 1;
                Ok(v)
            }
            Some(Token::LParen) => {
                self.i += 1;
                let v = self.expr()?;
                match self.peek() {
                    Some(Token::RParen) => {
                        self.i += 1;
                        Ok(v)
                    }
                    _ => Err("missing )".to_string()),
                }
            }
            Some(t) => Err(format!("unexpected token: {:?}", t)),
            None => Err("unexpected end of input".to_string()),
        }
    }
}

fn eval(src: &str) -> Result<f64, String> {
    let mut lx = Lexer::new(src);
    let toks = lx.tokens()?;
    let mut p = Parser { t: toks, i: 0 };
    let v = p.expr()?;
    if p.i != p.t.len() {
        return Err("trailing tokens after expression".to_string());
    }
    Ok(v)
}

/// MATLAB `format short` 的近似：整数不带小数点，小数 4 位，末尾零省略。
fn fmt(v: f64) -> String {
    if v.is_nan() {
        return "NaN".to_string();
    }
    if v.is_infinite() {
        return if v > 0.0 { "Inf" } else { "-Inf" }.to_string();
    }
    if v.fract() == 0.0 && v.abs() < 1e15 {
        return format!("{}", v as i64);
    }
    let s = format!("{:.4}", v);
    let t = s.trim_end_matches('0').trim_end_matches('.');
    t.to_string()
}

fn print_usage() {
    println!("malabc-rt {} —— M 语义参考实现的最小骨架", env!("CARGO_PKG_VERSION"));
    println!();
    println!("用法：");
    println!("  malabc-rt eval <expr>   标量 double 的四则 + 括号 + 一元正负号");
    println!("  malabc-rt --version");
    println!("  malabc-rt --help");
    println!();
    println!("边界：只支持 double 标量四则；其它一律退出码 2（unimplemented），");
    println!("      不返回错误的值。这是与 matlabc.py 同一套「不撒谎」纪律。");
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() {
        print_usage();
        return ExitCode::SUCCESS;
    }
    match args[0].as_str() {
        "--version" | "-V" => {
            println!("malabc-rt {}", env!("CARGO_PKG_VERSION"));
            ExitCode::SUCCESS
        }
        "--help" | "-h" => {
            print_usage();
            ExitCode::SUCCESS
        }
        "eval" => {
            if args.len() < 2 {
                eprintln!("malabc-rt: eval 需要一个表达式");
                return ExitCode::from(2);
            }
            let src = args[1..].join(" ");
            match eval(&src) {
                Ok(v) => {
                    println!("{}", fmt(v));
                    ExitCode::SUCCESS
                }
                Err(e) => {
                    eprintln!("malabc-rt: {}: {}", e, src);
                    ExitCode::from(1)
                }
            }
        }
        other => {
            eprintln!("malabc-rt: unimplemented: {}（只支持 eval / --version / --help）", other);
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn precedence() {
        assert_eq!(fmt(eval("1+2*3").unwrap()), "7");
        assert_eq!(fmt(eval("(1+2)*3").unwrap()), "9");
        assert_eq!(fmt(eval("8/2/2").unwrap()), "2");
        assert_eq!(fmt(eval("10-2-3").unwrap()), "5");
    }

    #[test]
    fn unary_and_paren() {
        assert_eq!(fmt(eval("-2+5").unwrap()), "3");
        assert_eq!(fmt(eval("-(2+3)").unwrap()), "-5");
        assert_eq!(fmt(eval("--3").unwrap()), "3");
    }

    #[test]
    fn division_edges() {
        assert_eq!(fmt(eval("1/0").unwrap()), "Inf");
        assert_eq!(fmt(eval("-1/0").unwrap()), "-Inf");
        assert_eq!(fmt(eval("0/0").unwrap()), "NaN");
    }

    #[test]
    fn rejects_garbage() {
        assert!(eval("1+").is_err());
        assert!(eval("1 2").is_err());
        assert!(eval("a+1").is_err());
        assert!(eval("(1+2").is_err());
    }

    #[test]
    fn formatting() {
        assert_eq!(fmt(0.5), "0.5");
        assert_eq!(fmt(1.0 / 3.0), "0.3333");
        assert_eq!(fmt(7.0), "7");
    }
}
完成上一次下一步的全部任务，每一次都可以使用superpower skill，联动的必要的skill深度思考，按照下一步建议实现保证每一次都是真正的实现，并且持续规划30轮，60分钟不断修复和改进，并且最后完整后给出下一次建设性的意见