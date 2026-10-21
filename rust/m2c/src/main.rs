//! `m2c`：MIR → C 的发射器（R434）。
//!
//! 用法：
//!   m2c build --mir out.mir --out gen/ --name solver
//!   m2c emit  --mir out.mir            # 打到 stdout，便于对拍
//!   m2c --selftest                     # 门里用，不依赖 cargo test
//!
//! 退出码：0 成功 / 1 校验失败（MIR 不合法、发射不出）/ 2 参数或 IO 问题。

mod emit;
mod mir;

use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const USAGE: &str = "用法：
  m2c build --mir <file.mir> --out <dir> [--name <proj>]
  m2c emit  --mir <file.mir>
  m2c --selftest";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() || args.iter().any(|a| a == "--help" || a == "-h") {
        println!("{}", USAGE);
        return ExitCode::from(if args.is_empty() { 2 } else { 0 });
    }
    if args.iter().any(|a| a == "--selftest") {
        return selftest();
    }

    let cmd = args[0].as_str();
    let mut mir_path: Option<PathBuf> = None;
    let mut out_dir: Option<PathBuf> = None;
    let mut name = String::from("gen");
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--mir" => {
                i += 1;
                if i >= args.len() {
                    eprintln!("--mir 缺参数");
                    return ExitCode::from(2);
                }
                mir_path = Some(PathBuf::from(&args[i]));
            }
            "--out" => {
                i += 1;
                if i >= args.len() {
                    eprintln!("--out 缺参数");
                    return ExitCode::from(2);
                }
                out_dir = Some(PathBuf::from(&args[i]));
            }
            "--name" => {
                i += 1;
                if i >= args.len() {
                    eprintln!("--name 缺参数");
                    return ExitCode::from(2);
                }
                name = emit::ident(&args[i]);
            }
            other => {
                eprintln!("不认识的参数：{}", other);
                return ExitCode::from(2);
            }
        }
        i += 1;
    }

    let mir_path = match mir_path {
        Some(p) => p,
        None => {
            eprintln!("缺 --mir");
            return ExitCode::from(2);
        }
    };
    let text = match fs::read_to_string(&mir_path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("读不了 {}：{}", mir_path.display(), e);
            return ExitCode::from(2);
        }
    };
    let funcs = match mir::parse(&text) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("MIR 不合法：{}", e);
            return ExitCode::from(1);
        }
    };

    match cmd {
        "emit" => {
            for f in &funcs {
                match emit::emit_func(f) {
                    Ok(code) => println!("{}", code),
                    Err(e) => {
                        eprintln!("发射失败：{}", e);
                        return ExitCode::from(1);
                    }
                }
            }
            ExitCode::SUCCESS
        }
        "build" => {
            let out = match out_dir {
                Some(p) => p,
                None => {
                    eprintln!("缺 --out");
                    return ExitCode::from(2);
                }
            };
            let files = match emit::emit_project(&funcs, &name) {
                Ok(v) => v,
                Err(e) => {
                    eprintln!("发射失败：{}", e);
                    return ExitCode::from(1);
                }
            };
            for (rel, body) in files {
                let p = out.join(Path::new(&rel));
                if let Some(parent) = p.parent() {
                    if let Err(e) = fs::create_dir_all(parent) {
                        eprintln!("建目录失败 {}：{}", parent.display(), e);
                        return ExitCode::from(2);
                    }
                }
                if let Err(e) = fs::write(&p, body) {
                    eprintln!("写文件失败 {}：{}", p.display(), e);
                    return ExitCode::from(2);
                }
                println!("[ok] {}", p.display());
            }
            ExitCode::SUCCESS
        }
        other => {
            eprintln!("不认识的子命令：{}\n{}", other, USAGE);
            ExitCode::from(2)
        }
    }
}

/// 自证：不需要 cargo test 也能在门里跑（门跑的是二进制）。
fn selftest() -> ExitCode {
    let mut good = 0u32;
    let mut bad = 0u32;
    let mut chk = |cond: bool, name: &str| {
        if cond {
            good += 1;
        } else {
            bad += 1;
            println!("  [FAIL] {}", name);
        }
    };

    let src = "version 1\nfunc:f\narg:x:f64\nret:y:f64\nop:OP-ADD:y:x:x\nend\n";
    let parsed = mir::parse(src);
    chk(parsed.is_ok(), "能解析最小 MIR");
    let funcs = parsed.unwrap_or_default();
    chk(funcs.len() == 1 && funcs[0].name == "f", "函数名正确");
    chk(funcs[0].declared() == vec!["x".to_string(), "y".to_string()],
        "作用域 = 参数 + 返回值 + 算子输出（去重）");

    // 不认识的行必须报错（不静默跳过）
    chk(mir::parse("version 1\nfunc:f\n???\nend\n").is_err(), "未知构造报错");
    chk(mir::parse("func:f\nend\n").is_err(), "缺 version 报错");

    // 发射：实现了的算子
    let code = emit::emit_func(&funcs[0]).unwrap_or_default();
    chk(code.contains("mlc_op_add"), "实现了的算子发射成 mlc_op_*");
    chk(code.contains("return st;"), "无 unmapped 时返回 st");

    // 未实现算子：必须明确失败，而不是编一段
    let un = mir::parse("version 1\nfunc:g\narg:x:f64\nret:y:f64\nop:OP-TRANSPOSE:y:x\nend\n")
        .unwrap_or_default();
    let code2 = emit::emit_func(&un[0]).unwrap_or_default();
    chk(code2.contains("MLC_UNIMPLEMENTED"), "未实现算子发 MLC_UNIMPLEMENTED");
    chk(!code2.contains("mlc_op_transpose("), "不会凭空调用不存在的函数");

    // unmapped 语句：要有 TODO 且整体部分实现
    let um = mir::parse(
        "version 1\nfunc:h\nret:y:f64\nunmapped:y = foo(x);\nend\n").unwrap_or_default();
    let code3 = emit::emit_func(&um[0]).unwrap_or_default();
    chk(code3.contains("TODO(unmapped)"), "unmapped 变成 TODO");

    // 作用域外的参数：必须拒绝
    let out_scope = mir::parse("version 1\nfunc:k\nret:y:f64\nop:OP-ADD:y:y:zzz\nend\n")
        .unwrap_or_default();
    let code4 = emit::emit_func(&out_scope[0]).unwrap_or_default();
    chk(code4.contains("TODO(arg)"), "作用域外参数被拒绝");

    // 确定性
    let a = emit::emit_func(&funcs[0]).unwrap_or_default();
    let b = emit::emit_func(&funcs[0]).unwrap_or_default();
    chk(a == b, "同一 MIR 两次发射逐字节一致");

    // 项目骨架
    let proj = emit::emit_project(&funcs, "demo").unwrap_or_default();
    let names: Vec<&str> = proj.iter().map(|(n, _)| n.as_str()).collect();
    chk(names.contains(&"CMakeLists.txt"), "工程产出含 CMakeLists");
    chk(names.contains(&"include/demo.h"), "工程产出含头文件");

    println!(
        "SELFTEST COUNTS {{\"bad\": {}, \"good\": {}}}",
        bad, good
    );
    if bad == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
