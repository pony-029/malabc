# YALMIP 实测报告（真实开源库）

> 语料：git clone --depth 1 https://github.com/yalmip/YALMIP
> 生成时间：2026-10-18

## 一、规模

| 指标 | 读数 |
| --- | --- |
| 文件 | **1665** |
| 函数 | **2763** |
| 行数 | **109524** |
| 脚本 | **3** |
| 函数文件 | **1662** |
| 类文件 | **0** |
| **调用边** | **20225** |
| └ 跨文件边 | 17369 |
| **函数缺描述** | **1676** |
| **重复代码** | **765** |
| JSON 体积 | 27.1 MB |

## 二、可核对的三类诊断

### 2.1 函数缺描述（前 10 条）

打开对应文件的那一行，函数头确实没有注释块：

| 文件 | 行 | 函数 |
| --- | --- | --- |
| extras/compileinterfacedata.m | 1 | compileinterfacedata |
| modules/global/bmibnb_branch_and_bound.m | 717 | pull |
| modules/global/bmibnb_branch_and_bound.m | 739 | prune |
| modules/global/bnb_branch_and_bound.m | 725 | integersplit |
| modules/global/bnb_branch_and_bound.m | 751 | semisplit |
| modules/global/bnb_branch_and_bound.m | 783 | num2str2 |
| modules/global/bmibnb_branch_and_bound.m | 771 | savetonode |
| modules/global/bmibnb_branch_and_bound.m | 799 | addlpcuts |
| solvers/callmpcvx.m | 485 | push |
| solvers/callmpcvx.m | 492 | pull |

### 2.2 重复代码（前 5 条）

- 相似度 **1.00** —— 函数体结构与 extras/sdpsettings.m/setup_bilevel_options 高度重复（相似度 1.00）
- 相似度 **1.00** —— 函数体结构与 extras/sdpsettings.m/setup_bmibnb_options 高度重复（相似度 1.00）
- 相似度 **1.00** —— 函数体结构与 extras/sdpsettings.m/setup_bmibnb_options 高度重复（相似度 1.00）
- 相似度 **1.00** —— 函数体结构与 extras/sdpsettings.m/setup_kkt_options 高度重复（相似度 1.00）
- 相似度 **1.00** —— 函数体结构与 extras/sdpsettings.m/setup_moment_options 高度重复（相似度 1.00）

### 2.3 跨文件调用（前 8 条）

| 调用者 | 被调用 |
| --- | --- |
| @sdpvar/abs.m:abs | @sdpvar/isreal.m:isreal |
| @sdpvar/abs.m:abs | extras/yalmip.m:yalmip |
| @sdpvar/abs.m:abs | @sdpvar/getbase.m:getbase |
| @sdpvar/abs.m:abs | @sdpvar/fix.m:fix |
| @sdpvar/abs.m:abs | @sdpvar/ismember.m:ismember |
| @sdpvar/abs.m:abs | @sdpvar/getvariables.m:getvariables |
| @sdpvar/abs.m:abs | @sdpvar/size.m:size |
| @sdpvar/abs.m:abs | @sdpvar/norm.m:norm |

## 三、复现

`powershell
git clone --depth 1 https://github.com/yalmip/YALMIP C:\temp\yalmip
cd E:\matlabc\malabc
python matlabc.py C:\temp\yalmip --json C:\temp\yalmip.json --json-compact
`

**产物在 C:\temp\yalmip.json（27.1 MB，不进仓库）**；本报告只摘录前若干条。

## 四、边界

- 本次未跑 --browse（1665 文件会生成 1600+ 页面，当时探针占 CPU）
- 耗时读数受探针干扰（62,704 个 C 文件在并发分析）
