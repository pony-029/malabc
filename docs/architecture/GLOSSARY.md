# 架构图中英术语表

> 英文版 candidate 的节点 label 必须命中这里的规范译法。
> `check_architecture_docs.py` 的 AD9 会逐节点核对：中文 label 里出现某个术语，
> 英文 label 必须包含对应英文（任一可接受写法）。
>
> 机器块在文件末尾；人读表与机器块保持一致。新增术语时两处同改。

| 中文 | 英文（任一可接受） | 说明 |
| --- | --- | --- |
| 入口 | entry / entries | CLI 入口、其它入口 |
| 前端 | frontend | MATLAB / C / Python / JS frontend |
| 渲染 | render | 渲染与输出 |
| 输出 | output | 输出层、三态输出 |
| 门禁 | gates | 门禁 / CI |
| 闭环 | fix loop | 修复闭环 |
| 移植 | port | MATLAB→C port、port ledger |
| 二进制 | binary / binaries | 二进制分析 |
| 缓存 | cache | 解析缓存 |
| 配置 | config | 参数 + 配置 |
| 模型 | model | 实体模型 |
| 统一图 | unified graph | 模型 / 统一图 |
| 实体 | entity / entities | 实体模型、实体 |
| 事实 | facts | 事实层 |
| 调用 | call | 调用图、跳转/调用关系 |
| 影响面 | impact | 分析引擎 |
| 依赖 | dependencies | 依赖图 |
| 污点 | taint | 污点流 |
| 维度 | dimension | 维度引擎 |
| 检查 | checks / check | 静态检查 |
| 源码 | source | 数据流输入 |
| 输入 | input | 数据流输入 |
| 回退 | revert | 失败必回退 |
| 基线 | baseline | 基线分析 |
| 补丁 | patch | patch / test skeleton |
| 退出码 | exit code | CI 退出码 |
| 扩展 | extension | VS Code 扩展 |
| 客户端 | client | LSP 客户端 |
| 服务端 | server | LSP 服务端 |
| 算子 | operator | 算子目录、C operator impl |
| 适配器 | adapters / adapter | 双侧适配器 |
| 契约 | contract | C ABI 契约 |
| 保真 | fidelity | 保真执行器 |
| 约束 | constraints / constraint | 双侧约束 |
| 参考 | reference | MATLAB 参考实现 |
| 供应商 | provider | AI 供应商 |
| 报告 | report | --html 报告 |
| 站点 | site | --browse 站点 |

<!-- GLOSSARY v1
{
  "入口": ["entry", "entries"],
  "前端": ["frontend"],
  "渲染": ["render"],
  "输出": ["output"],
  "门禁": ["gates"],
  "闭环": ["fix loop"],
  "移植": ["port"],
  "二进制": ["binary", "binaries"],
  "缓存": ["cache"],
  "配置": ["config"],
  "模型": ["model"],
  "统一图": ["unified graph"],
  "实体": ["entity", "entities"],
  "事实": ["facts"],
  "调用": ["call"],
  "影响面": ["impact"],
  "依赖": ["dependencies"],
  "污点": ["taint"],
  "维度": ["dimension"],
  "检查": ["checks", "check"],
  "源码": ["source"],
  "输入": ["input"],
  "回退": ["revert"],
  "基线": ["baseline"],
  "补丁": ["patch"],
  "退出码": ["exit code"],
  "扩展": ["extension"],
  "客户端": ["client"],
  "服务端": ["server"],
  "算子": ["operator"],
  "适配器": ["adapters", "adapter"],
  "契约": ["contract"],
  "保真": ["fidelity"],
  "约束": ["constraints", "constraint"],
  "参考": ["reference"],
  "供应商": ["provider"],
  "报告": ["report"],
  "站点": ["site"]
}
-->
