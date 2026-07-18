"""Configuration for the MCN Script Agent.

Loads from .env file (via python-dotenv) or environment variables.
"""

import os
from pathlib import Path

# ── Auto-load .env from project root ──────────────────────────
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_env_path, override=False)
    except ImportError:
        pass

# ── Helper: detect placeholder / fake API keys ────────────────
def _is_placeholder(val: str) -> bool:
    if not val:
        return True
    val_lower = val.lower().strip()
    placeholders = ["sk-your-", "your-", "sk-placeholder", "xxxx", "todo", "replace"]
    for p in placeholders:
        if p in val_lower:
            return True
    return False

# ── LLM Configuration ─────────────────────────────────────────
_raw_api_key = os.getenv("LLM_API_KEY", "")
LLM_CONFIG = {
    "api_key": "" if _is_placeholder(_raw_api_key) else _raw_api_key,
    "api_base": os.getenv("LLM_API_BASE", "https://api.openai.com/v1"),
    "model": os.getenv("LLM_MODEL", "gpt-4o"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
    "max_retries": int(os.getenv("LLM_MAX_RETRIES", "3")),
    "request_timeout": int(os.getenv("LLM_TIMEOUT", "120")),
}

# ── Feishu Configuration ──────────────────────────────────────
FEISHU_CONFIG = {
    "app_id": os.getenv("FEISHU_APP_ID", ""),
    "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
    "base_url": "https://open.feishu.cn/open-apis",
}

# ── Compliance rules ──────────────────────────────────────────
FORBIDDEN_WORDS = [
    "减肥", "瘦身", "掉秤", "燃脂",
    "减脂神效", "狂瘦", "暴瘦", "极速瘦身",
    "神器", "必买", "全网第一", "最好", "最有效",
    "医疗效果", "替代药物",
    "永久瘦", "全身瘦", "局部瘦",
    "躺着瘦", "不运动也能瘦",
    "天花板", "闭眼入", "必须囤",
]

CAUTION_WORDS = [
    "治愈", "特效", "低卡", "随便吃",
    "轻盈", "饱腹", "控糖", "清爽", "赶紧", "囤货",
]

MIN_DURATION_SECONDS = 50
MAX_DURATION_SECONDS = 70

AGENT_CONFIG = {
    "max_iterations": int(os.getenv("AGENT_MAX_ITERATIONS", "5")),
    "num_candidates": int(os.getenv("AGENT_NUM_CANDIDATES", "1")),
    "output_dir": os.getenv("AGENT_OUTPUT_DIR", str(Path(__file__).resolve().parent.parent / "output")),
}
