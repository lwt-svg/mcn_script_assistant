"""LLM abstraction layer with retry, token tracking, and demo fallback."""

import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from agent.config import LLM_CONFIG


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, prompt: int, completion: int):
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.calls += 1

    def __str__(self):
        if self.calls == 0:
            return "No LLM calls made"
        return (f"LLM calls: {self.calls} | "
                f"Tokens: {self.total_tokens} total "
                f"({self.prompt_tokens} prompt + {self.completion_tokens} completion)")

    def estimate_cost(self, model: str = ""):
        model = model or LLM_CONFIG.get("model", "gpt-4o")
        pricing = {"gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60),
                    "deepseek-chat": (0.27, 1.10), "deepseek-reasoner": (0.55, 2.19)}
        p, c = pricing.get(model, (2.50, 10.00))
        return (self.prompt_tokens / 1_000_000 * p + self.completion_tokens / 1_000_000 * c)


_global_usage = TokenUsage()


def get_global_usage():
    return _global_usage


def reset_global_usage():
    global _global_usage
    _global_usage = TokenUsage()


def call_llm(prompt, system_prompt="", temperature=None, response_format=None, max_retries=None):
    api_key = LLM_CONFIG["api_key"]
    if not api_key:
        return _demo_fallback(prompt, system_prompt)
    if api_key.startswith("sk-your-") or "your-api-key" in api_key.lower():
        return _demo_fallback(prompt, system_prompt)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": LLM_CONFIG["model"],
        "messages": messages,
        "temperature": temperature if temperature is not None else LLM_CONFIG["temperature"],
    }
    if response_format:
        payload["response_format"] = response_format

    retries = max_retries if max_retries is not None else LLM_CONFIG["max_retries"]
    timeout = LLM_CONFIG["request_timeout"]
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(f"{LLM_CONFIG['api_base']}/chat/completions",
                                  headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage")
            if usage:
                _global_usage.add(prompt=usage.get("prompt_tokens", 0) or 0,
                                   completion=usage.get("completion_tokens", 0) or 0)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            break

    raise RuntimeError(f"LLM call failed after {retries} retries. Last: {last_error}")


def call_llm_json(prompt, system_prompt="", temperature=None, max_retries=None):
    api_key = LLM_CONFIG["api_key"]
    use_json_mode = bool(api_key) and "openai" in LLM_CONFIG["api_base"].lower()

    if use_json_mode:
        sp = (system_prompt + "\n\n你必须输出 JSON 格式。") if system_prompt else "你必须输出 JSON 格式。"
        text = call_llm(prompt, sp, temperature, {"type": "json_object"}, max_retries)
        result = _try_parse_json(text)
        if result is not None:
            return result

    text = call_llm(prompt + "\n\n请只输出 JSON 格式，不要包含其他内容。", system_prompt, temperature, None, max_retries)
    return extract_json(text)


def extract_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r'(\{[\s\S]*\})', text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _try_parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


# ── Demo fallback ────────────────────────────────────────────

def _demo_fallback(prompt, system_prompt=""):
    sp = system_prompt.lower()

    if any(kw in sp for kw in ["脚本生成", "短视频脚本", "分镜"]):
        return _DEMO_SCRIPT
    if any(kw in sp for kw in ["合规审查", "合规检查"]):
        return json.dumps({"checks": [
            {"rule": "功效承诺检查", "status": "pass", "detail": "未发现违规"},
            {"rule": "夸大用语检查", "status": "pass", "detail": "无夸大用语"},
            {"rule": "植入自然度", "status": "pass", "detail": "植入频次合理"},
        ], "suggestions": ["脚本已通过所有合规检查"]}, ensure_ascii=False)
    if "brief 解析" in sp or ("提取" in sp and ("品牌" in sp or "brief" in sp)):
        return json.dumps(_DEMO_BRIEF, ensure_ascii=False)
    if any(kw in sp for kw in ["博主", "内容风格", "风格分析", "风格特征"]):
        return json.dumps(_DEMO_STYLE, ensure_ascii=False)

    return _DEMO_SCRIPT


_DEMO_BRIEF = {
    "brand_name": "轻醒", "product": "0蔗糖高蛋白希腊酸奶",
    "flavors": ["原味", "蓝莓", "黄桃"],
    "core_selling_points": ["高蛋白(≥8g/杯)", "0蔗糖", "饱腹感", "低负担"],
    "target_audience": "22-35岁城市女性，关注健身、控糖、轻食和上班族效率生活",
    "usage_scenarios": ["早餐", "运动后", "下午茶"],
    "constraints": ["不能承诺减肥、降糖等功效", "避免夸大效果", "脚本需适合真实达人拍摄", "内容自然种草，不要硬广"],
}

_DEMO_STYLE = {
    "blogger_name": "豆豆子",
    "persona": "松弛感居家美食爱好者，真实自用分享型美食创作者",
    "scenes": ["居家厨房", "早餐", "brunch", "下午茶"],
    "expression": {"voiceover": False, "subtitle_style": "分段弹出短字幕", "bgm": "轻柔舒缓纯音乐", "tone": "安静松弛"},
    "camera_style": {"angles": ["俯拍", "45度侧拍", "特写"], "movement": "慢推拉", "lighting": "柔和自然光"},
    "narrative_structure": [
        {"phase": "开场钩子", "time": "0-6s", "shot": "俯拍操作台，展示食材"},
        {"phase": "食材展示", "time": "6-15s", "shot": "食材特写，产品瓶身"},
        {"phase": "制作流程", "time": "15-40s", "shot": "手部操作，俯拍侧拍交替"},
        {"phase": "成品摆盘", "time": "40-52s", "shot": "成品特写，产品同框"},
        {"phase": "结尾收尾", "time": "52-60s", "shot": "成品定格"},
    ],
    "product_placement_rules": ["产品作为食材自然出现", "卖点通过字幕输出", "禁止功效承诺"],
}

_DEMO_SCRIPT = """# 谁懂啊！早起5分钟的快乐被这个酸奶碗拿捏住了

**品牌**: 轻醒 0蔗糖高蛋白希腊酸奶
**场景**: 夏日早餐
**时长**: 58s
**风格参考**: @豆豆子

## 分镜表
| 阶段 | 时间 | 画面描述 | 字幕 | 产品植入 | BGM |
|------|------|---------|------|---------|-----|
| 开场钩子 | 0-4s | 特写：勺子挖起一勺酸奶碗，浓稠拉丝慢动作，阳光洒在勺子上 | 谁懂啊！早起5分钟的快乐 | 酸奶瓶在画面右下角 | 轻快钢琴曲 |
| 食材展示 | 4-12s | 侧拍：依次摆放酸奶、蓝莓、坚果。镜头扫过瓶身0蔗糖高蛋白字样 | 早八人减脂期早餐灵感 / 还得是这款0蔗糖高蛋白酸奶 | 瓶身正面特写 | 同上 |
| 制作流程 | 12-38s | 俯拍：倒酸奶入碗(展示浓稠挂壁)，慢动作撒蓝莓和坚果 | 铺一层醇厚酸奶打底 / 新鲜蓝莓+香脆坚果 / 一口下去超满足 | 倒酸奶时瓶身出镜 | BGM+食材音效 |
| 成品摆盘 | 38-50s | 45度斜拍：完整酸奶碗，勺子舀起拉丝。产品和成品同框 | 每杯高蛋白>=8g / 清爽不腻 解馋无负担 | 产品和成品同框 | BGM继续 |
| 结尾收尾 | 50-58s | 特写：勺子轻轻搅拌，镜头后退成全景，酸奶瓶在窗边 | 简单干净 好好吃早餐 / 快去试试吧～ | 酸奶瓶在画面中心 | BGM渐弱 |

## 产品植入点
1. 开场4s内产品一角出镜
2. 食材展示段拿起酸奶瓶展示
3. 制作流程段倒酸奶出镜
4. 成品摆盘段产品和成品同框

## 合规风险提醒
- 无功效承诺用语 ✅
- 无夸大措辞 ✅
- 产品植入自然 ✅
- 时长58s符合50-70s ✅
- 全程无口播 ✅
"""
