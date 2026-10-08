#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ai_cli.py --- matlabc 的「面向各种 AI 模型」CLI 接口层。

设计原则（对齐 matlabc 哲学）：
  * 零第三方依赖：仅用标准库（urllib/json/os/argparse）。
  * 离线优先：无任何 provider / 密钥时，自动降级为「写/打印提示词」（等价于 --ai-prompts 的提升版）。
  * 安全：API 密钥只从环境变量读取，任何输出都做脱敏，绝不落盘日志。

provider 抽象支持：
  * offline   默认；不联网，返回组装好的提示词（供人工粘贴任意离线 AI 工具）。
  * openai    OpenAI 及任何 OpenAI 兼容端点（Ollama / vLLM / 本地 / 以及国产：
              DeepSeek、通义千问 DashScope、智谱 GLM、Kimi、百川、豆包火山、零一、阶跃）。
  * anthropic Anthropic Claude（messages API）。
  * ernie     百度文心一言（OAuth2 client_credentials 换 access_token）。
  * iflytek   讯飞星火（WebSocket 签名鉴权；需可选依赖 websocket-client）。
  通过 PROVIDER_PRESETS / PROVIDER_ALIASES 注册，--provider 可直接用中文别名。

与 matlabc 既有修复闭环（--gen-apply-patch / --gen-tests-risk / --gen-pr）通过
parse_unified_diff() 对接：AI 返回的补丁可被抽取并回流做「可应用 + 无新告警」自证。
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

# ----------------------------------------------------------------------------
# 任务引导语（与 OPERATOR_CATALOG.md §6 元类型解耦：task 决定 prompt 形态）
# ----------------------------------------------------------------------------
TASK_GUIDE = {
    "review": "请作为资深代码审查员，定位问题并给出最小化修复建议（用中文，简洁）。",
    "fix": "请直接给出可应用的修复，使用 ```diff 统一补丁```（unified diff）形式输出。",
    "explain": "请解释下列代码/告警的成因与运行时风险。",
    "tests": "请针对高风险点生成最小 pytest/unittest 测试桩骨架。",
    "refactor": "请针对重复代码/可维护性告警给出重构方案，并附 ```diff 补丁```。",
}

CODE_BLOCK_RE = re.compile(r"```([\w-]*)\n(.*?)```", re.DOTALL)
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{6,}|Bearer\s+[A-Za-z0-9._-]{6,}|api_key[=:]\s*\S+)", re.IGNORECASE)

# ----------------------------------------------------------------------------
# Provider 预设注册表（含国产大模型）
# ----------------------------------------------------------------------------
# cls 取值：
#   "openai"   复用 OpenAICompatProvider（所有 OpenAI 兼容端点：Ollama/DeepSeek/
#               vLLM/通义千问/DashScope/智谱/零一/豆包/百川/Kimi/阶跃 等）
#   "anthropic" Anthropic Claude
#   "ernie"     百度文心一言（client_id/client_secret 换 access_token）
#   "iflytek"   讯飞星火（WebSocket 签名鉴权；需可选依赖 websocket-client）
PROVIDER_PRESETS = {
    # 国际
    "openai":    {"cls": "openai",    "base_url": "https://api.openai.com/v1",
                  "default_model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY",
                  "label": "OpenAI"},
    "anthropic": {"cls": "anthropic", "base_url": "https://api.anthropic.com/v1",
                  "default_model": "claude-3-5-sonnet-latest", "api_key_env": "ANTHROPIC_API_KEY",
                  "label": "Anthropic Claude"},
    # 国产（OpenAI 兼容）
    "deepseek":  {"cls": "openai", "base_url": "https://api.deepseek.com/v1",
                  "default_model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY",
                  "label": "DeepSeek 深度求索"},
    "qwen":      {"cls": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                  "default_model": "qwen-plus", "api_key_env": "DASHSCOPE_API_KEY",
                  "label": "通义千问（阿里 DashScope）"},
    "zhipu":     {"cls": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4",
                  "default_model": "glm-4-plus", "api_key_env": "ZHIPU_API_KEY",
                  "label": "智谱 GLM（清华）"},
    "moonshot":  {"cls": "openai", "base_url": "https://api.moonshot.cn/v1",
                  "default_model": "moonshot-v1-8k", "api_key_env": "MOONSHOT_API_KEY",
                  "label": "Kimi 月之暗面"},
    "baichuan":  {"cls": "openai", "base_url": "https://api.baichuan-ai.com/v1",
                  "default_model": "Baichuan4", "api_key_env": "BAICHUAN_API_KEY",
                  "label": "百川智能"},
    "doubao":    {"cls": "openai", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                  "default_model": "doubao-pro-32k", "api_key_env": "ARK_API_KEY",
                  "label": "豆包（字节火山方舟）"},
    "yi":        {"cls": "openai", "base_url": "https://api.lingyiwanwu.com/v1",
                  "default_model": "yi-large", "api_key_env": "YI_API_KEY",
                  "label": "零一万物 Yi"},
    "stepfun":   {"cls": "openai", "base_url": "https://api.stepfun.com/v1",
                  "default_model": "step-1-flash", "api_key_env": "STEPFUN_API_KEY",
                  "label": "阶跃星辰 StepFun"},
    # 国产（独立鉴权）
    "ernie":     {"cls": "ernie", "base_url": "https://aip.baidubce.com",
                  "default_model": "ernie-4.0-8k", "api_key_env": "ERNIE_API_KEY",
                  "api_secret_env": "ERNIE_SECRET_KEY", "label": "文心一言（百度）"},
    "iflytek":   {"cls": "iflytek", "base_url": "wss://spark-api.xf-yun.com",
                  "default_model": "generalv3.5", "api_key_env": "IFLYTEK_API_KEY",
                  "api_secret_env": "IFLYTEK_API_SECRET", "app_id_env": "IFLYTEK_APP_ID",
                  "label": "讯飞星火"},
}

# 中文 / 常见别名 → 规范名（CLI --provider 可直接用别名）
PROVIDER_ALIASES = {
    "通义千问": "qwen", "阿里": "qwen", "dashscope": "qwen",
    "文心": "ernie", "文心一言": "ernie", "百度": "ernie",
    "智谱": "zhipu", "glm": "zhipu", "chatglm": "zhipu",
    "kimi": "moonshot", "月之暗面": "moonshot",
    "豆包": "doubao", "火山": "doubao", "火山方舟": "doubao", "字节": "doubao",
    "百川": "baichuan",
    "零一": "yi", "零一万物": "yi", "lingyi": "yi",
    "阶跃": "stepfun", "step": "stepfun", "stepfun": "stepfun",
    "深度求索": "deepseek",
    "讯飞": "iflytek", "星火": "iflytek", "iflytek": "iflytek",
}


def _normalize_provider(name):
    """把别名/中文名归一为 PROVIDER_PRESETS 的规范键；无效返回原值（交由解析器降级）。

    大小写不敏感（ASCII 部分 lower）；预设键全小写，故亦对 "Qwen"/"Kimi" 归一。
    """
    if not name:
        return name
    s = name.strip()
    if s in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[s]
    low = s.lower()
    if low in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[low]
    if s in PROVIDER_PRESETS:
        return s
    if low in PROVIDER_PRESETS:
        return low
    return s


def redact(text):
    """脱敏：遮蔽 API 密钥 / Bearer / api_key= 值，防止泄露到 stderr/stdout/报告。"""
    if not text:
        return text
    return SECRET_RE.sub(lambda m: m.group(0)[:4] + "****", text)


def parse_code_blocks(text):
    """从模型自由文本中抽取全部 ```lang ... ``` 代码块，返回 [(lang, code), ...]。"""
    return [(lang.strip(), code.strip("\n")) for lang, code in CODE_BLOCK_RE.findall(text or "")]


def _looks_like_diff(block):
    return any(l.startswith(("--- ", "+++ ", "@@")) for l in block.splitlines())


def parse_unified_diff(text):
    """抽取模型输出中的 unified diff 片段（取最长一段），供 git apply / 自证引擎消费。

    识别：以 diff --git / --- / +++ / @@ / +/-/空格 开头的连续行（排除 ``` 围栏），
    且必须含 --- / +++ / @@ 才认定为有效 diff。返回字符串；无可识别 diff 返回空串。"""
    best = ""
    cur = []
    for line in (text or "").splitlines():
        if line.startswith("```"):
            # 围栏：先结算已攒块
            if cur and _looks_like_diff("\n".join(cur)) and len("\n".join(cur)) > len(best):
                best = "\n".join(cur)
            cur = []
            continue
        if line.startswith(("diff --git", "--- ", "+++ ", "@@", "-", "+", " ")):
            cur.append(line)
        else:
            if cur and _looks_like_diff("\n".join(cur)) and len("\n".join(cur)) > len(best):
                best = "\n".join(cur)
            cur = []
    if cur and _looks_like_diff("\n".join(cur)) and len("\n".join(cur)) > len(best):
        best = "\n".join(cur)
    return best


def load_analysis(path):
    """读取分析输入：JSON 则尝试复用 matlabc 的提示词组装；否则按纯文本。"""
    if path and os.path.isfile(path):
        with io.open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            obj = json.loads(raw)
        except ValueError:
            return raw  # 纯文本/Markdown 提示词
        # 复用 matlabc._build_ai_prompts（若存在且不破坏离线）
        try:
            import matlabc as ma  # 延迟导入，保持 ai_cli 可独立运行
            if hasattr(ma, "_build_ai_prompts"):
                model = _obj_to_model(obj)
                out = ma._build_ai_prompts(model)
                if isinstance(out, (tuple, list)):
                    out = "\n".join(str(x) for x in out)
                return out
        except Exception:
            pass
        return json.dumps(obj, indent=2, ensure_ascii=False)
    return path or ""


def _obj_to_model(obj):
    """把 JSON 快照尽量还原成 matlabc 的 analysis model 形状（容错）。"""
    if isinstance(obj, dict) and "root" in obj:
        return obj
    # 直接把 dict 当作 model（_build_ai_prompts 只读部分字段，缺则降级）
    return obj


def build_messages(analysis_text, task, task_cfg=None):
    """组装 (system, user) 消息。task 来自 TASK_GUIDE；task_cfg 来自配置 tasks.<task>。

    task_cfg 可覆盖：
      system       完整系统提示（给定则直接使用，不再拼接内置引导）；
      user_suffix  追加到分析输入后的任务说明。
    未覆盖时回退内置 TASK_GUIDE 引导，保证离线可用。
    """
    task_cfg = task_cfg or {}
    builtin_guide = TASK_GUIDE.get(task, TASK_GUIDE["review"])
    custom_system = task_cfg.get("system")
    if custom_system:
        system = custom_system
    else:
        system = ("你是代码分析助手，服务于 matlabc 静态分析工具。"
                  "只依据给定事实作答，不臆测缺失信息。\n" + builtin_guide)
    suffix = task_cfg.get("user_suffix") or ""
    user = analysis_text or ""
    if suffix:
        user = (user + "\n\n" + suffix) if user else suffix
    if not custom_system:
        user = (user + "\n\n任务：" + builtin_guide) if user else builtin_guide
    return system, user


# ----------------------------------------------------------------------------
# Provider 抽象
# ----------------------------------------------------------------------------
class AIProvider(ABC):
    name = "abstract"

    @abstractmethod
    def complete(self, messages, model=None, max_tokens=1024, temperature=0.2, stream=False):
        """返回模型文本响应（str）。"""
        raise NotImplementedError


class OfflinePromptProvider(AIProvider):
    """无网络降级：返回组装好的提示词，由调用方打印/写文件。"""
    name = "offline"

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.2, stream=False):
        sys_prompt = messages[0]["content"] if messages else ""
        user_prompt = messages[-1]["content"] if messages else ""
        return ("# matlabc AI 提示词（offline 模式，请粘贴到任意离线 AI 工具）\n\n"
                "## 系统设定\n" + sys_prompt + "\n\n## 分析输入\n" + user_prompt)


class _HTTPProvider(AIProvider):
    """基于 urllib 的 HTTP provider 基类（零依赖）。"""

    def __init__(self, timeout=60.0):
        self.timeout = timeout

    def _post(self, url, headers, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            raise RuntimeError("AI 请求失败 HTTP %s: %s" % (e.code, redact(detail)))
        except urllib.error.URLError as e:
            raise RuntimeError("AI 请求失败（网络/端点不可达）：%s" % redact(str(e.reason)))


class OpenAICompatProvider(_HTTPProvider):
    """OpenAI 及兼容端点（Ollama / DeepSeek / vLLM 等）。"""
    name = "openai"

    def __init__(self, api_key, base_url="https://api.openai.com/v1", model=None, timeout=60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = model or "gpt-4o-mini"
        self.timeout = timeout

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.2, stream=False):
        headers = {"Authorization": "Bearer %s" % self.api_key,
                   "Content-Type": "application/json"}
        body = {"model": model or self.default_model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature, "stream": stream}
        raw = self._post(self.base_url + "/chat/completions", headers, body)
        try:
            obj = json.loads(raw)
            return obj["choices"][0]["message"]["content"]
        except (ValueError, KeyError) as e:
            raise RuntimeError("OpenAI 响应解析失败：%s | %s" % (e, redact(raw[:200])))


class AnthropicProvider(_HTTPProvider):
    """Anthropic Claude（messages API，system 单独传）。"""
    name = "anthropic"

    def __init__(self, api_key, base_url="https://api.anthropic.com/v1", model=None, timeout=60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = model or "claude-3-5-sonnet-latest"
        self.timeout = timeout

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.2, stream=False):
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        conv = [m for m in messages if m.get("role") != "system"]
        body = {"model": model or self.default_model, "max_tokens": max_tokens,
                "temperature": temperature, "system": system, "messages": conv}
        raw = self._post(self.base_url + "/messages", headers, body)
        try:
            obj = json.loads(raw)
            blocks = obj.get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (ValueError, KeyError) as e:
            raise RuntimeError("Anthropic 响应解析失败：%s | %s" % (e, redact(raw[:200])))


class ErnieProvider(_HTTPProvider):
    """百度文心一言：先用 client_id/client_secret 换 access_token，再走 chat 接口。

    鉴权：POST /oauth/2.0/token?grant_type=client_credentials&client_id=&client_secret=
    对话：POST /rpc/2.0/ai_custom/v1/wenxinworkshop/chat/<model>?access_token=
    （零依赖；token 仅内存缓存，不落盘。）
    """
    name = "ernie"

    def __init__(self, api_key, api_secret, base_url="https://aip.baidubce.com",
                 default_model="ernie-4.0-8k", timeout=60.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._token = None

    def _get_token(self):
        if self._token:
            return self._token
        url = (self.base_url + "/oauth/2.0/token?grant_type=client_credentials"
               "&client_id=%s&client_secret=%s" % (self.api_key, self.api_secret))
        raw = self._post(url, {"Content-Type": "application/json"}, {})
        try:
            obj = json.loads(raw)
        except ValueError as e:
            raise RuntimeError("ERNIE 令牌响应解析失败：%s | %s" % (e, redact(raw[:200])))
        tok = obj.get("access_token")
        if not tok:
            raise RuntimeError("ERNIE 换取 access_token 失败：%s" % redact(raw[:200]))
        self._token = tok
        return tok

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.2, stream=False):
        token = self._get_token()
        sys_text = ""
        conv = []
        for m in messages:
            if m.get("role") == "system":
                sys_text = m["content"]
            else:
                conv.append({"role": m["role"], "content": m["content"]})
        body = {"messages": conv, "temperature": temperature,
                "max_output_tokens": min(int(max_tokens), 2048)}
        if sys_text:
            body["system"] = sys_text
        chat_model = model or self.default_model
        url = (self.base_url + "/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/%s?access_token=%s"
               % (chat_model, token))
        raw = self._post(url, {"Content-Type": "application/json"}, body)
        try:
            obj = json.loads(raw)
            if obj.get("error_code"):
                raise RuntimeError("ERNIE 调用失败：%s %s" % (
                    obj.get("error_code"), redact(str(obj.get("error_msg", "")))))
            return obj["result"]
        except (ValueError, KeyError) as e:
            raise RuntimeError("ERNIE 响应解析失败：%s | %s" % (e, redact(raw[:200])))


class IflytekProvider(AIProvider):
    """讯飞星火：WebSocket 签名鉴权（需可选依赖 websocket-client，离线优先下缺依赖自动降级）。

    签名算法（RFC 7231 date + HMAC-SHA256 + Base64），路径随模型版本变化：
      general->/v1.1/chat  generalv2->/v2.1/chat  generalv3->/v3.1/chat
      generalv3.5->/v3.5/chat  generalv4->/v4.0/chat
    """
    name = "iflytek"

    _PATH_BY_MODEL = {
        "general": "/v1.1/chat", "generalv2": "/v2.1/chat", "generalv3": "/v3.1/chat",
        "generalv3.5": "/v3.5/chat", "generalv4": "/v4.0/chat",
    }

    def __init__(self, api_key, api_secret, app_id,
                 base_url="wss://spark-api.xf-yun.com",
                 default_model="generalv3.5", timeout=60.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self.app_id = app_id
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout

    def _ws_url(self):
        import datetime
        import hmac
        import hashlib
        import base64
        import urllib.parse
        model = self.default_model
        path = self._PATH_BY_MODEL.get(model, "/v3.5/chat")
        try:  # 时区感知写法：3.12+ 无废弃告警，且 3.6 已支持 timezone
            date = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        except (AttributeError, ValueError):
            date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        sig_origin = ("host: spark-api.xf-yun.com\ndate: %s\nGET %s HTTP/1.1"
                      % (date, path))
        sig_sha = hmac.new(self.api_secret.encode("utf-8"),
                           sig_origin.encode("utf-8"),
                           hashlib.sha256).digest()
        sig_b64 = base64.b64encode(sig_sha).decode("utf-8")
        auth = base64.b64encode(
            ("api_key=\"%s\", algorithm=\"hmac-sha256\", headers=\"host date request-line\", "
             "signature=\"%s\"" % (self.api_key, sig_b64)).encode("utf-8")).decode("utf-8")
        return (self.base_url + "%s?authorization=%s&date=%s&host=spark-api.xf-yun.com"
                % (path, urllib.parse.quote(auth), urllib.parse.quote(date)))

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.2, stream=False):
        try:
            import websocket  # 可选依赖
        except ImportError:
            raise RuntimeError("iflytek 需可选依赖 websocket-client：pip install websocket-client")
        domain = model or self.default_model
        ws_url = self._ws_url()
        payload = {
            "header": {"app_id": self.app_id, "uid": "matlabc"},
            "parameter": {"chat": {"domain": domain, "temperature": temperature,
                                   "max_tokens": int(max_tokens)}},
            "payload": {"message": {"text": [
                {"role": m["role"], "content": m["content"]} for m in messages]}},
        }
        ws = websocket.create_connection(ws_url, timeout=self.timeout)
        try:
            ws.send(json.dumps(payload))
            parts = []
            while True:
                raw = ws.recv()
                if not raw:
                    break
                obj = json.loads(raw)
                hdr = obj.get("header", {})
                if hdr.get("code") != 0:
                    raise RuntimeError("iflytek 调用失败：%s %s"
                                       % (hdr.get("code"), redact(str(hdr.get("message", "")))))
                text = obj.get("payload", {}).get("choices", {}).get("text", [])
                for t in text:
                    parts.append(t.get("content", ""))
                if obj.get("payload", {}).get("choices", {}).get("status") == 2:
                    break
            return "".join(parts)
        finally:
            try:
                ws.close()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# 配置 / 解析
# ----------------------------------------------------------------------------
def load_config(config_path):
    """从 analyzer_config.json 读取 ai: 段；缺省返回 {}。"""
    if not config_path or not os.path.isfile(config_path):
        return {}
    try:
        with io.open(config_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg.get("ai", {}) if isinstance(cfg, dict) else {}
    except (ValueError, OSError):
        return {}


def load_ai_config(main_config_path, ai_config_path=None):
    """合并两类配置，返回「AI 流程」配置字典（顶层即 ai schema）：

      * main_config_path：analyzer_config.json，取其 ai: 段；
      * ai_config_path：独立的 AI 配置文件，顶层直接是 ai schema（不必嵌套 ai:）。
    两者都缺时返回 {}。CLI 显式参数仍优先于本合并结果（见 main）。
    """
    merged = {}
    if main_config_path and os.path.isfile(main_config_path):
        try:
            with io.open(main_config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if isinstance(cfg, dict) and isinstance(cfg.get("ai"), dict):
                merged.update(cfg["ai"])
        except (ValueError, OSError):
            pass
    if ai_config_path and os.path.isfile(ai_config_path):
        try:
            with io.open(ai_config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if isinstance(cfg, dict):
                merged.update(cfg)
        except (ValueError, OSError):
            pass
    return merged


def resolve_provider(name, ai_cfg, env=None):
    """按优先级（CLI/env/配置 > 离线降级）构建单一 provider 实例。

    支持配置 schema：
      ai_cfg.providers.<name> = { cls?, api_key_env, api_key, base_url, model,
                                  api_secret_env, api_secret, app_id_env, app_id,
                                  request_timeout }
      name 可为 PROVIDER_PRESETS 的规范键或其别名（PROVIDER_ALIASES，含中文）。
    返回 (provider, effective_name, warn)。key 缺失时降级 offline 并在 warn 注明。
    """
    env = env or os.environ
    name = _normalize_provider(name)
    if name == "offline":
        return OfflinePromptProvider(), "offline", ""
    preset = PROVIDER_PRESETS.get(name)
    block = (ai_cfg.get("providers") or {}).get(name) or {}
    if preset is None and not block:
        return OfflinePromptProvider(), "offline", "未知 provider=%s，降级为 offline。" % name
    meta = preset or {}
    api_key_env = block.get("api_key_env") or meta.get("api_key_env") or ("%s_API_KEY" % name.upper())
    base_url = block.get("base_url") or meta.get("base_url")
    default_model = block.get("model") or meta.get("default_model")
    timeout = block.get("request_timeout") or ai_cfg.get("request_timeout") or 60.0
    cls = block.get("cls") or meta.get("cls") or "openai"

    if cls == "openai":
        key = (env.get(api_key_env) or block.get("api_key")
               or env.get("%s_API_KEY" % name.upper()))
        if not key:
            return OfflinePromptProvider(), "offline", "未配置 %s，降级为 offline 提示词。" % api_key_env
        eff_base = base_url or ai_cfg.get("openai_base_url")
        return OpenAICompatProvider(key, eff_base, default_model, timeout), name, ""
    if cls == "anthropic":
        key = env.get(api_key_env) or block.get("api_key") or env.get("ANTHROPIC_API_KEY")
        if not key:
            return OfflinePromptProvider(), "offline", "未配置 %s，降级为 offline 提示词。" % api_key_env
        return AnthropicProvider(key, base_url, default_model, timeout), name, ""
    if cls == "ernie":
        key = env.get(api_key_env) or block.get("api_key")
        secret = (env.get(meta.get("api_secret_env") or "ERNIE_SECRET_KEY")
                  or block.get("api_secret"))
        if not (key and secret):
            return OfflinePromptProvider(), "offline", "未配置 %s / %s，降级为 offline。" % (
                api_key_env, meta.get("api_secret_env") or "ERNIE_SECRET_KEY")
        return ErnieProvider(key, secret, base_url, default_model, timeout), name, ""
    if cls == "iflytek":
        key = env.get(api_key_env) or block.get("api_key")
        secret = (env.get(meta.get("api_secret_env") or "IFLYTEK_API_SECRET")
                  or block.get("api_secret"))
        app_id = (env.get(meta.get("app_id_env") or "IFLYTEK_APP_ID")
                  or block.get("app_id"))
        if not (key and secret and app_id):
            return OfflinePromptProvider(), "offline", "未配置 %s / %s / %s，降级为 offline。" % (
                api_key_env, meta.get("api_secret_env") or "IFLYTEK_API_SECRET",
                meta.get("app_id_env") or "IFLYTEK_APP_ID")
        return IflytekProvider(key, secret, app_id, base_url, default_model, timeout), name, ""
    # 未知 cls → 离线
    return OfflinePromptProvider(), "offline", "未知 provider cls=%s，降级为 offline。" % cls


def resolve_provider_auto(preferred, ai_cfg, env=None):
    """按 fallback 链解析有效 provider：preferred 缺密钥时依次尝试 fallback，最终回退 offline。

    返回 (provider, effective_name, warn)；warn 记录最后一条降级原因（便于向用户提示）。
    """
    env = env or os.environ
    candidates = []
    if preferred and preferred != "offline":
        candidates.append(preferred)
    for p in (ai_cfg.get("fallback") or []):
        if p != preferred and p != "offline" and p not in candidates:
            candidates.append(p)
    last_warn = ""
    for name in candidates:
        prov, eff, warn = resolve_provider(name, ai_cfg, env)
        if eff != "offline":
            return prov, eff, ""
        last_warn = warn  # 记录降级原因（offline 末位不进入候选，避免覆盖）
    return OfflinePromptProvider(), "offline", last_warn


def task_params(task, ai_cfg):
    """从配置 tasks.<task> 取出该任务的模型/令牌/温度/提示词覆盖；缺省返回空字典。"""
    block = (ai_cfg.get("tasks") or {}).get(task) or {}
    return {
        "model": block.get("model"),
        "max_tokens": block.get("max_tokens"),
        "temperature": block.get("temperature"),
        "system": block.get("system"),
        "user_suffix": block.get("user_suffix"),
    }


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="ai_cli", description="matlabc 的 AI 模型 CLI 接口层（零依赖/离线优先/JSON 配置驱动）。")
    p.add_argument("--provider", default=None,
                   choices=(["offline"] + list(PROVIDER_PRESETS.keys())
                            + list(PROVIDER_ALIASES.keys())),
                   help="AI 供应商（含国产：deepseek/qwen/ernie/zhipu/moonshot/baichuan/doubao/yi/stepfun/iflytek；"
                        "可用中文别名如 通义千问/文心一言；缺省：MA_AI_PROVIDER → 配置 default_provider → offline）")
    p.add_argument("--model", default=None, help="模型名（覆盖配置/默认）")
    p.add_argument("--prompt-file", default=None, help="分析输入：analysis.json 或提示词 .md/.txt")
    p.add_argument("--task", default=None, choices=list(TASK_GUIDE.keys()),
                   help="任务类型（缺省：配置 default_task → review）")
    p.add_argument("--base-url", default=None, help="OpenAI 兼容端点（覆盖配置）")
    p.add_argument("--max-tokens", type=int, default=None, help="最大生成 tokens（覆盖配置/默认）")
    p.add_argument("--temperature", type=float, default=None, help="采样温度（覆盖配置/默认）")
    p.add_argument("--stream", action="store_true", help="（保留）流式开关")
    p.add_argument("--output", default=None, help="将响应/提示词写入文件")
    p.add_argument("--config", default=None, help="analyzer_config.json 路径（取其 ai: 段）")
    p.add_argument("--ai-config", default=None,
                   help="独立的 AI 配置文件（顶层即 ai schema，不必嵌套 ai:；与 --config 的 ai: 段合并）")
    p.add_argument("--list-providers", action="store_true", help="列出支持的 provider 并退出")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.list_providers:
        print("支持的 provider（国内大模型均通过 OpenAI 兼容或独立适配；--provider 亦可用中文别名）：")
        for n, meta in PROVIDER_PRESETS.items():
            print("  - %-10s %-22s %s" % (n, meta.get("label", ""), meta.get("base_url", "")))
        print("  - offline   （默认/离线，返回可粘贴提示词）")
        return 0
    ai_cfg = load_ai_config(args.config, args.ai_config)
    # CLI 显式 base-url 覆盖配置
    if args.base_url:
        ai_cfg = dict(ai_cfg, openai_base_url=args.base_url)
    # 解析有效 provider（CLI > env > 配置 default_provider > offline；缺密钥按 fallback 链）
    provider_default = os.environ.get("MA_AI_PROVIDER") or ai_cfg.get("default_provider") or "offline"
    preferred = args.provider or provider_default
    provider, eff_name, warn = resolve_provider_auto(preferred, ai_cfg)
    if warn:
        sys.stderr.write("[ai_cli] %s\n" % warn)
    # 解析任务（CLI > 配置 default_task > review）
    eff_task = args.task or ai_cfg.get("default_task") or "review"
    if eff_task not in TASK_GUIDE:
        eff_task = "review"
    tp = task_params(eff_task, ai_cfg)
    analysis = load_analysis(args.prompt_file)
    system, user = build_messages(analysis, eff_task, tp)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    # 令牌/温度：CLI > 任务配置 > 内置默认
    model = args.model or tp.get("model")
    max_tokens = args.max_tokens if args.max_tokens is not None else (tp.get("max_tokens") or 1024)
    temperature = args.temperature if args.temperature is not None else (
        tp.get("temperature") if tp.get("temperature") is not None else 0.2)
    try:
        resp = provider.complete(messages, model=model,
                                 max_tokens=max_tokens, temperature=temperature,
                                 stream=args.stream)
    except RuntimeError as e:
        sys.stderr.write("[ai_cli] 调用失败：%s\n" % e)
        return 1
    if args.output:
        with io.open(args.output, "w", encoding="utf-8") as fh:
            fh.write(resp)
        sys.stderr.write("[ai_cli] 已写入 %s（provider=%s, task=%s）\n"
                        % (args.output, eff_name, eff_task))
    else:
        print(resp)
    # 若含 unified diff，提示可回流修复闭环
    if eff_name != "offline":
        diff = parse_unified_diff(resp)
        if diff:
            sys.stderr.write("[ai_cli] 检测到 unified diff，可用 matlabc --gen-apply-patch 回流自证。\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
