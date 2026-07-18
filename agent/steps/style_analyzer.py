"""Step 2: 达人内容风格建模 - Analyze blogger style with flexible field matching."""
from agent.models import StyleProfile, ExpressionStyle, CameraStyle, NarrativePhase
from agent.llm import call_llm_json


SYSTEM_PROMPT = """你是一个专业的小红书博主内容风格分析助手。
从博主内容拆解报告中提取结构化风格特征，返回 JSON。

JSON 输出格式：
{
  "blogger_name": "博主名称",
  "persona": "人设描述",
  "scenes": ["场景1", "场景2"],
  "content_type": "内容类型: 美食制作/产品测评/场景休闲/减脂vlog",
  "time_range": "博主视频时长区间, 如35-45",
  "expression": {"voiceover": false, "subtitle_style": "...", "bgm": "...", "tone": "..."},
  "camera_style": {"angles": ["俯拍", "特写"], "movement": "...", "lighting": "..."},
  "narrative_structure": [{"phase": "开场钩子", "time": "0-6s", "shot": "..."}],
  "product_placement_rules": ["规则1", "规则2"]
}
只返回 JSON。"""


def _get(data: dict, *keys):
    for k in keys:
        if k in data and data[k] is not None:
            v = data[k]
            return v if not isinstance(v, str) or v else ""
    return ""


def _get_list(data: dict, *keys):
    for k in keys:
        if k in data and isinstance(data[k], list):
            return data[k]
    return []


def analyze_style(style_analysis_text: str) -> StyleProfile:
    prompt = f"""请分析以下博主内容拆解，提取结构化风格特征：
{style_analysis_text}
必须提取：blogger_name, persona, scenes, expression, camera_style, narrative_structure, product_placement_rules
**重要：如果博主的表达方式中包含"口播""真人出镜""配音""旁白"等关键词，则 expression.voiceover 应设为 true；如果是"无口播""全程字幕""无人声"等，则设为 false。**"""
    data = call_llm_json(prompt, SYSTEM_PROMPT)
    if not data:
        return StyleProfile(blogger_name="未知博主", persona="", scenes=[],
                            expression=ExpressionStyle(voiceover=False, subtitle_style="", bgm="", tone=""),
                            camera_style=CameraStyle(angles=[], movement="", lighting=""),
                            narrative_structure=[], product_placement_rules=[])
    expr = data.get("expression", {}) or {}
    cam = data.get("camera_style", {}) or {}
    narr = data.get("narrative_structure", []) or []
    # Post-process: override voiceover if source text contains keywords
    raw_lower = style_analysis_text.lower()
    has_voiceover_keyword = ('口播' in raw_lower or '配音' in raw_lower or '旁白' in raw_lower) and '无口播' not in raw_lower
    voiceover_val = expr.get('voiceover', False) or expr.get('has_voiceover', False) or has_voiceover_keyword

    return StyleProfile(
        blogger_name=_get(data, "blogger_name", "name", "blogger", "author"),
        persona=_get(data, "persona", "personality", "character"),
        scenes=_get_list(data, "scenes", "content_scenes", "topics"),
        content_type=_get(data, "content_type", "type") or "美食制作",
        time_range=_get(data, "time_range", "duration_range") or "50-60",
        expression=ExpressionStyle(
            voiceover=voiceover_val,
            subtitle_style=_get(expr, "subtitle_style", "subtitle", "text_style"),
            bgm=_get(expr, "bgm", "music", "bgm_style"),
            tone=_get(expr, "tone", "voice", "style"),
        ),
        camera_style=CameraStyle(
            angles=_get_list(cam, "angles", "camera_angles", "shots"),
            movement=_get(cam, "movement", "camera_movement", "motion"),
            lighting=_get(cam, "lighting", "light", "color_tone"),
        ),
        narrative_structure=[
            NarrativePhase(phase=_get(p, "phase", "stage"), time=_get(p, "time", "duration"), shot=_get(p, "shot", "description"))
            for p in narr if isinstance(p, dict)
        ],
        product_placement_rules=_get_list(data, "product_placement_rules", "placement_rules", "ad_rules"),
    )
