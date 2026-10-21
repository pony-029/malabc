//! `m2c`：MIR → C 的发射器（R434 / Week1）。
//!
//! 用法：
//!   m2c build --mir out.mir --out gen/ --name solver
//!   m2c emit  --mir out.mir            # 打到 stdout，便于对拍
//!   m2c --selftest                     # 门里用，不依赖 cargo test
//!
//! 退出码：0 成功 / 1 校验失败（MIR 不合法、发射不出）/ 2 参数或 IO 问题。

mod emit;
mod mir;
mod project;

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
            let files = match project::emit_project(&funcs, &name) {
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

    let src = "version 2\nfunc:f\narg:x:f64:3\nret:y:f64:3\nop:OP-ADD:y:x:x\nend\n";
    let parsed = mir::parse(src);
    chk(parsed.is_ok(), "能解析带形状的 MIR");
    let funcs = parsed.unwrap_or_default();
    chk(funcs.len() == 1 && funcs[0].name == "f", "函数名正确");
    chk(
        funcs[0].declared() == vec!["x".to_string(), "y".to_string()],
        "作用域 = 参数 + 返回值 + 算子输出（去重）",
    );
    chk(funcs[0].var_shape("x") == Some(vec![3]), "形状被解析出来");

    chk(mir::parse("version 1\nfunc:f\n???\nend\n").is_err(), "未知构造报错");
    chk(mir::parse("func:f\nend\n").is_err(), "缺 version 报错");

    let code = emit::emit_func(&funcs[0]).unwrap_or_default();
    chk(code.contains("mlc_op_add"), "实现了的算子发射成 mlc_op_*");
    chk(code.contains("mlc_array_init(y"), "返回值按形状初始化（指针直传，不取地址）");
    chk(code.contains("return st;"), "无 unmapped 时返回 st");

    // 未实现算子：必须明确失败
    let un = mir::parse("version 2\nfunc:g\narg:x:f64:2\nret:y:f64:2\nop:OP-TRANSPOSE:y:x\nend\n")
        .unwrap_or_default();
    let code2 = emit::emit_func(&un[0]).unwrap_or_default();
    chk(code2.contains("MLC_UNIMPLEMENTED"), "未实现算子发 MLC_UNIMPLEMENTED");
    chk(!code2.contains("mlc_op_transpose("), "不会凭空调用不存在的函数");

    // unmapped
    let um = mir::parse(
        "version 2\nfunc:h\narg:x:f64:2\nret:y:f64:2\nunmapped:y = foo(x);\nend\n",
    )
    .unwrap_or_default();
    let code3 = emit::emit_func(&um[0]).unwrap_or_default();
    chk(code3.contains("TODO(unmapped)"), "unmapped 变成 TODO");

    // 作用域外参数
    let out_scope =
        mir::parse("version 2\nfunc:k\narg:y:f64:2\nret:y:f64:2\nop:OP-ADD:y:y:zzz\nend\n")
            .unwrap_or_default();
    let code4 = emit::emit_func(&out_scope[0]).unwrap_or_default();
    chk(code4.contains("TODO(arg)"), "作用域外参数被拒绝");

    // 立即数下标
    let idx = mir::parse("version 2\nfunc:p\narg:v:f64:3\nret:z:f64:1\nop:OP-INDEX:z:v:3\nend\n")
        .unwrap_or_default();
    let code5 = emit::emit_func(&idx[0]).unwrap_or_default();
    chk(code5.contains("(int64_t)3"), "立即数下标发射成字面量");

    // for 循环
    let lp = mir::parse(
        "version 2\nfunc:q\narg:v:f64:3\nret:s:f64:1\nfor:i:1:3\nop:OP-SUM:s:v\nend\nend\n",
    )
    .unwrap_or_default();
    chk(!lp.is_empty() && lp[0].loops.len() == 1, "for 循环被解析");
    let code6 = emit::emit_func(&lp[0]).unwrap_or_default();
    chk(code6.contains("for (int64_t i = 1; i <= 3; ++i)"), "for 发射成 C 循环");

    // 广播：与 C / Python 同规则
    let bc = mir::parse(
        "version 2\nfunc:b\narg:a:f64:2,3\narg:d:f64:3\nret:y:f64:2,3\nop:OP-ADD:y:a:d\nend\n",
    )
    .unwrap_or_default();
    let code_bc = emit::emit_func(&bc[0]).unwrap_or_default();
    chk(code_bc.contains("mlc_array_init(y, MLC_F64, 2, (int64_t[]){2, 3})"),
        "2x3 + 3 广播成 2x3");
    chk(emit::bcast_shape(&[3, 1], &[1, 4]) == Some(vec![3, 4]), "3x1 与 1x4 广播成 3x4");
    chk(emit::bcast_shape(&[2], &[3]).is_none(), "2 与 3 不可广播（必须拒绝）");

    // 确定性
    let a = emit::emit_func(&funcs[0]).unwrap_or_default();
    let b = emit::emit_func(&funcs[0]).unwrap_or_default();
    chk(a == b, "同一 MIR 两次发射逐字节一致");

    // 工程骨架
    let proj = project::emit_project(&funcs, "demo").unwrap_or_default();
    let names: Vec<&str> = proj.iter().map(|(n, _)| n.as_str()).collect();
    chk(names.contains(&"CMakeLists.txt"), "工程产出含 CMakeLists");
    chk(names.contains(&"include/demo.h"), "工程产出含头文件");
    let main_c = proj
        .iter()
        .find(|(n, _)| n == "src/main.c")
        .map(|(_, b)| b.clone())
        .unwrap_or_default();
    chk(main_c.contains("m2c_f("), "main 真的调用生成函数");

    println!("SELFTEST COUNTS {{\"bad\": {}, \"good\": {}}}", bad, good);
    if bad == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
