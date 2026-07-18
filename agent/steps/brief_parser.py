"""Step 1: 需求结构化解析 - Parse brand brief with flexible field matching."""
from agent.models import BriefInfo
from agent.llm import call_llm_json


SYSTEM_PROMPT = """你是一个专业的 MCN 品牌 Brief 解析助手。
从品牌 Brief 文本中提取结构化信息，返回 JSON。

JSON 字段说明：
- brand_name: 品牌名称
- product: 产品名称
- flavors: 产品口味列表（数组）
- core_selling_points: 核心卖点列表（数组）
- target_audience: 目标人群描述
- usage_scenarios: 使用场景列表（数组）
- constraints: 品牌约束/注意事项列表（数组）

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


def parse_brief(brief_text: str) -> BriefInfo:
    prompt = f"""请解析以下品牌 Brief 文本，提取结构化信息：
{brief_text}
必须提取的字段：
1. brand_name - 品牌名称
2. product - 产品名称
3. flavors - 产品口味（数组）
4. core_selling_points - 核心卖点（数组）
5. target_audience - 目标人群描述
6. usage_scenarios - 使用场景（数组）
7. constraints - 约束条件（数组）"""
    data = call_llm_json(prompt, SYSTEM_PROMPT)
    if data:
        return BriefInfo(
            brand_name=_get(data, "brand_name", "brand", "brandName"),
            product=_get(data, "product", "product_name", "productName"),
            flavors=_get_list(data, "flavors", "flavor", "tastes"),
            core_selling_points=_get_list(data, "core_selling_points", "selling_points", "coreSellingPoints"),
            target_audience=_get(data, "target_audience", "target_audience_desc", "audience", "targetAudience"),
            usage_scenarios=_get_list(data, "usage_scenarios", "scenarios", "use_scenarios", "usageScenarios"),
            constraints=_get_list(data, "constraints", "rules", "notes"),
        )
    return BriefInfo(brand_name="未知品牌", product="未知产品", flavors=[], core_selling_points=[],
                      target_audience="", usage_scenarios=[], constraints=[])
