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
    let mut expect_path: Option<PathBuf> = None;
    let mut case_args: Vec<(PathBuf, PathBuf)> = Vec::new();
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
            "--case" => {
                i += 1;
                if i >= args.len() {
                    eprintln!("--case 缺参数（形如 fixture.txt=expected.txt）");
                    return ExitCode::from(2);
                }
                match args[i].split_once('=') {
                    Some((fx, ex)) => case_args.push((PathBuf::from(fx),
                                                      PathBuf::from(ex))),
                    None => {
                        eprintln!("--case 需要 夹具=期望 的形式");
                        return ExitCode::from(2);
                    }
                }
            }
            "--expect" => {
                i += 1;
                if i >= args.len() {
                    eprintln!("--expect 缺参数");
                    return ExitCode::from(2);
                }
                expect_path = Some(PathBuf::from(&args[i]));
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
                match emit::emit_func(f, &funcs) {
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
            let cases = build_cases(expect_path.as_ref(), &case_args);
            let files = match project::emit_project(&funcs, &name, &cases) {
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

fn load_expect(path: Option<&PathBuf>) -> std::collections::BTreeMap<String, String> {
    let mut m = std::collections::BTreeMap::new();
    let p = match path {
        Some(p) => p,
        None => return m,
    };
    let text = match fs::read_to_string(p) {
        Ok(t) => t,
        Err(_) => return m,
    };
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((k, v)) = line.split_once(':') {
            m.insert(k.trim().to_string(), v.trim().to_string());
        }
    }
    m
}


/// 解析夹具文件：`x = 10 20 30` → { "x": [10,20,30] }
fn load_fixture(path: &PathBuf) -> std::collections::BTreeMap<String, Vec<f64>> {
    let mut m = std::collections::BTreeMap::new();
    let text = match fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => return m,
    };
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let (name, rest) = match line.split_once('=') {
            Some(x) => x,
            None => continue,
        };
        let vals: Vec<f64> = rest
            .split(|c: char| c.is_whitespace() || c == ',')
            .filter(|t| !t.is_empty())
            .filter_map(|t| t.parse::<f64>().ok())
            .collect();
        if !vals.is_empty() {
            m.insert(name.trim().to_string(), vals);
        }
    }
    m
}

fn build_cases(expect: Option<&PathBuf>,
               pairs: &[(PathBuf, PathBuf)]) -> Vec<project::Case> {
    let mut out: Vec<project::Case> = Vec::new();
    if let Some(p) = expect {
        out.push(project::Case {
            name: "default".to_string(),
            args: std::collections::BTreeMap::new(),
            expect: load_expect(Some(p)),
        });
    }
    for (fx, ex) in pairs {
        out.push(project::Case {
            name: fx
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| "case".to_string()),
            args: load_fixture(fx),
            expect: load_expect(Some(ex)),
        });
    }
    out
}

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

    let code = emit::emit_func(&funcs[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code.contains("mlc_op_add"), "实现了的算子发射成 mlc_op_*");
    chk(code.contains("mlc_array_init(y"), "返回值按形状初始化（指针直传，不取地址）");
    chk(code.contains("return st;"), "无 unmapped 时返回 st");

    // 未实现算子：必须明确失败
    // 用**真正未知**的算子：OP-TRANSPOSE 现在已实现，拿它当反例会失效
    let un = mir::parse("version 2\nfunc:g\narg:x:f64:2\nret:y:f64:2\nop:OP-NOSUCH:y:x\nend\n")
        .unwrap_or_default();
    let code2 = emit::emit_func(&un[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code2.contains("MLC_UNIMPLEMENTED"), "未实现算子发 MLC_UNIMPLEMENTED");
    chk(!code2.contains("mlc_op_nosuch("), "不会凭空调用不存在的函数");

    // 转置已实现：2x3 -> 3x2
    let tr = mir::parse(
        "version 3\nfunc:tr\narg:x:f64:2,3\nret:t:f64:3,2\nop:OP-TRANSPOSE:t:x\nend\n",
    )
    .unwrap_or_default();
    let code_tr = emit::emit_func(&tr[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code_tr.contains("mlc_array_init(t, MLC_F64, 2, (int64_t[]){3, 2})"),
        "转置输出形状是 [n, m]");
    chk(code_tr.contains("mlc_op_transpose(&x, t)"), "转置发射正确");

    // unmapped
    let um = mir::parse(
        "version 2\nfunc:h\narg:x:f64:2\nret:y:f64:2\nunmapped:y = foo(x);\nend\n",
    )
    .unwrap_or_default();
    let code3 = emit::emit_func(&um[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code3.contains("TODO(unmapped)"), "unmapped 变成 TODO");

    // 作用域外参数
    let out_scope =
        mir::parse("version 2\nfunc:k\narg:y:f64:2\nret:y:f64:2\nop:OP-ADD:y:y:zzz\nend\n")
            .unwrap_or_default();
    let code4 = emit::emit_func(&out_scope[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code4.contains("TODO(arg)"), "作用域外参数被拒绝");

    // 立即数下标
    let idx = mir::parse("version 2\nfunc:p\narg:v:f64:3\nret:z:f64:1\nop:OP-INDEX:z:v:3\nend\n")
        .unwrap_or_default();
    let code5 = emit::emit_func(&idx[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code5.contains("(int64_t)3"), "立即数下标发射成字面量");

    // for 循环
    let lp = mir::parse(
        "version 2\nfunc:q\narg:v:f64:3\nret:s:f64:1\nfor:i:1:3\nop:OP-SUM:s:v\nend\nend\n",
    )
    .unwrap_or_default();
    let has_for = lp
        .first()
        .map(|f| f.body.iter().any(|s| matches!(s, mir::Stmt::For { .. })))
        .unwrap_or(false);
    chk(has_for, "for 循环被解析成语句");
    let code6 = emit::emit_func(&lp[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code6.contains("for (int64_t i = 1; i <= 3; ++i)"), "for 发射成 C 循环");

    // while + 嵌套 if（分支里再套分支）
    let nest = mir::parse(
        "version 3\nfunc:n\narg:v:f64:3\narg:i:i64\nret:r:f64:1\n\
         while:i:lt:3\nif:i:gt:1\nop:OP-INDEX:r:v:i\nelse\nop:OP-SUM:r:v\n\
         end\nop:OP-ADD:r:r:r\nend\nend\n",
    )
    .unwrap_or_default();
    let code7 = emit::emit_func(&nest[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code7.contains("while (i < 3)"), "while 发射成 C 循环");
    chk(code7.contains("if (i > 1)") && code7.contains("} else {"),
        "嵌套 if/else 发射正确");

    // 广播：与 C / Python 同规则
    let bc = mir::parse(
        "version 2\nfunc:b\narg:a:f64:2,3\narg:d:f64:3\nret:y:f64:2,3\nop:OP-ADD:y:a:d\nend\n",
    )
    .unwrap_or_default();
    let code_bc = emit::emit_func(&bc[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code_bc.contains("mlc_array_init(y, MLC_F64, 2, (int64_t[]){2, 3})"),
        "2x3 + 3 广播成 2x3");
    chk(emit::bcast_shape(&[3, 1], &[1, 4]) == Some(vec![3, 4]), "3x1 与 1x4 广播成 3x4");
    chk(emit::bcast_shape(&[2], &[3]).is_none(), "2 与 3 不可广播（必须拒绝）");
    chk(emit::bcast_shape(&[2, 1, 3], &[1, 4, 1]) == Some(vec![2, 4, 3]),
        "3D：2x1x3 与 1x4x1 广播成 2x4x3");

    // 调用签名校验：正例放行、参数个数/类型不符必须明确失败
    let two = mir::parse(
        "version 3\nfunc:inner\narg:x:f64:3\nret:y:f64:1\nop:OP-SUM:y:x\nend\n\
         func:ok\narg:v:f64:3\nret:r:f64:1\ncall:r:inner:v\nend\n\
         func:badarity\narg:v:f64:3\nret:r:f64:1\ncall:r:inner:v:v\nend\n\
         func:baddtype\narg:v:f64:3\narg:i:i64\nret:r:f64:1\ncall:r:inner:i\nend\n",
    )
    .unwrap_or_default();
    if two.len() == 4 {
        let ok_code = emit::emit_func(&two[1], &two).unwrap_or_default();
        chk(ok_code.contains("m2c_inner(v, r)"), "签名正确的调用被放行");
        let arity = emit::emit_func(&two[2], &two).unwrap_or_default();
        chk(arity.contains("参数个数不符"), "参数个数不符被拒绝");
        let dtype = emit::emit_func(&two[3], &two).unwrap_or_default();
        chk(dtype.contains("参数类型不符"), "参数类型不符被拒绝");
    } else {
        chk(false, "调用校验的样本没解析出 4 个函数");
    }

    // 矩阵乘：形状是 [a.m, b.n]，且不能用广播规则
    let mm = mir::parse(
        "version 3\nfunc:mm\narg:A:f64:2,3\narg:B:f64:3,2\nret:C:f64:2,2\n\
         op:OP-MATMUL:C:A:B\nend\n",
    )
    .unwrap_or_default();
    let code_mm = emit::emit_func(&mm[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code_mm.contains("mlc_array_init(C, MLC_F64, 2, (int64_t[]){2, 2})"),
        "matmul 输出形状是 [a.m, b.n]");
    chk(code_mm.contains("mlc_op_matmul(&A, &B, C)"), "matmul 发射正确");

    // 内维不匹配必须拒绝（不猜截断）
    let bad_mm = mir::parse(
        "version 3\nfunc:bad\narg:A:f64:2,3\narg:B:f64:2,2\nret:C:f64:2,2\n\
         op:OP-MATMUL:C:A:B\nend\n",
    )
    .unwrap_or_default();
    let code_bad = emit::emit_func(&bad_mm[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(code_bad.contains("TODO"), "内维不匹配的 matmul 被拒绝");

    // 确定性
    let a = emit::emit_func(&funcs[0], &[] as &[mir::Func]).unwrap_or_default();
    let b = emit::emit_func(&funcs[0], &[] as &[mir::Func]).unwrap_or_default();
    chk(a == b, "同一 MIR 两次发射逐字节一致");

    // 工程骨架
    let proj = project::emit_project(&funcs, "demo", &[]).unwrap_or_default();
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
