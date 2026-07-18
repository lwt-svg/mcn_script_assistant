"""Step 4: 内容合规风控校验 - Two-layer compliance: rules + LLM semantic."""
from typing import List, Tuple
from agent.models import Script, ComplianceReport, ComplianceCheck, StyleProfile
from agent.config import FORBIDDEN_WORDS, CAUTION_WORDS, MIN_DURATION_SECONDS, MAX_DURATION_SECONDS
from agent.llm import call_llm


LLM_CHECK_SYSTEM_PROMPT = """你是一个小红书内容合规审查专家，同时具备企业品牌合规审核经验。
检查短视频脚本是否存在以下问题：

1. 功效承诺：即使没有直接使用违禁词，是否存在暗示减肥、降糖、瘦身等效果的话术
2. 夸大宣传：是否存在"最好""无敌""100%"等绝对化用语或隐性夸大
3. 广告法风险：是否存在医疗暗示、引导购买、诱导点击等违规内容
4. 风格匹配：脚本是否符合所述博主的风格
5. 植入自然度：产品出现是否生硬，是否打断叙事节奏

## 企业合规专项审查
a) 绝对化用语："天花板""全网第一""闭眼入""必须囤"等极限词
b) 隐性减脂暗示："轻盈""控糖""饱腹""不饿"等与身材管理相关的联想
c) 强营销引导："赶紧冲""快去抢""限时"等诱导下单话术
d) 卖点过度重复：同一卖点在字幕中出现超过2次

返回 JSON 格式：{"checks": [...], "suggestions": [...]} 只返回 JSON。"""


def check_compliance(script, style_profile=None):
    checks = []
    rules_pass = True

    c1, d1 = _check_forbidden_words(script)
    checks.append(ComplianceCheck(rule="禁止功效承诺及违禁词", status=c1, details=d1))
    if c1 == "fail": rules_pass = False

    c2, d2 = _check_placement(script)
    checks.append(ComplianceCheck(rule="产品植入自然度", status=c2, details=d2))
    if c2 == "fail": rules_pass = False

    c3, d3 = _check_duration(script, style_profile)
    checks.append(ComplianceCheck(rule="时长合规", status=c3, details=d3))
    if c3 == "fail": rules_pass = False

    if style_profile and not style_profile.expression.voiceover:
        c4, d4 = _check_no_voiceover(script)
        checks.append(ComplianceCheck(rule="口播禁令(博主无口播)", status=c4, details=d4))
        if c4 == "fail": rules_pass = False

    llm_checks, llm_suggestions = _llm_semantic_check(script)
    for lc in llm_checks:
        if not isinstance(lc, dict): continue
        checks.append(ComplianceCheck(rule=f"语义审查-{lc.get('rule', '未知')}",
                      status=lc.get("status", "pass"), details=lc.get("detail", "")))
        if lc.get("status") == "fail": rules_pass = False

    suggestions = _generate_suggestions(checks, llm_suggestions)
    return ComplianceReport(passed=rules_pass and all(c.status == "pass" for c in checks),
                            checks=checks, suggestions=suggestions)


def _check_forbidden_words(script):
    parts = [script.title]
    for row in script.storyboard:
        parts.extend([row.subtitle, row.visual_description])
    parts.extend(script.product_placement_points)
    check_text = " ".join(parts)
    found = [w for w in FORBIDDEN_WORDS if w in check_text]
    return ("fail", f"发现违禁词: {', '.join(found)}") if found else ("pass", "未发现违禁词")


def _check_placement(script):
    if not script.storyboard:
        return "fail", "分镜表为空"
    mentions = sum(1 for row in script.storyboard if "酸奶" in row.visual_description or "产品" in row.product_placement)
    if mentions == 0: return "fail", "脚本中未发现产品植入"
    if mentions > 5: return "fail", f"产品出现过于频繁({mentions}次)"
    return "pass", f"产品出现 {mentions} 次，频次合理"


def _check_duration(script, style_profile=None):
    time_values = []
    for row in script.storyboard:
        for part in row.time.replace("s", "").replace("秒", "").split("-"):
            try: time_values.append(int(part.strip()))
            except ValueError: pass
    if not time_values: return "pass", "无法解析分镜时间"

    # Use dynamic time range from style_profile if available
    min_dur, max_dur = MIN_DURATION_SECONDS, MAX_DURATION_SECONDS
    if style_profile and hasattr(style_profile, "time_range") and style_profile.time_range:
        try:
            parts = style_profile.time_range.replace("秒", "").split("-")
            prs = [int(p.strip()) for p in parts]
            if len(prs) == 2:
                min_dur, max_dur = prs[0], prs[1]
        except: pass

    max_time = max(time_values)
    if max_time < min_dur: return "fail", f"总时长约 {max_time}s，低于最低 {min_dur}s"
    if max_time > max_dur: return "fail", f"总时长约 {max_time}s，超过最大 {max_dur}s"
    return "pass", f"总时长约 {max_time}s"


def _check_no_voiceover(script):
    if not script.raw_text: return "pass", "无法检查口播内容"
    indicators = ["口播:", "口播：", "配音:", "配音：", "旁白:", "OS:", "voiceover", "画外音"]
    found = [ind for ind in indicators if ind.lower() in script.raw_text.lower()]
    return ("fail", f"发现口播指示词: {', '.join(found)}") if found else ("pass", "未发现口播内容")


def _llm_semantic_check(script):
    from agent.config import LLM_CONFIG
    if not LLM_CONFIG.get("api_key"): return [], []
    storyboard_text = "".join(f"|{r.phase}|{r.time}|{r.visual_description}|{r.subtitle}|{r.product_placement}|\n" for r in script.storyboard)
    prompt = f"""审查以下脚本合规性，含企业专项：
标题: {script.title}  品牌: {script.brand}  场景: {script.scene}
分镜: {storyboard_text}
检查：功效暗示、绝对化用语、强引导、减脂暗示、卖点重复"""
    try:
        resp = call_llm(prompt, LLM_CHECK_SYSTEM_PROMPT, temperature=0.1)
        from agent.llm import extract_json
        data = extract_json(resp)
        if data: return data.get("checks", []), data.get("suggestions", [])
    except: pass
    return [], []


def _generate_suggestions(checks, llm_suggestions):
    suggestions = list(llm_suggestions)
    for c in checks:
        if c.status == "fail": suggestions.append(f"【{c.rule}】{c.details[:80]}")
    if not suggestions: suggestions.append("脚本已通过所有合规检查")
    return suggestions


def generate_fix_instructions(script, report):
    failed = [c for c in report.checks if c.status == "fail"]
    if not failed: return ""
    instructions = ["请修复以下问题并重新生成脚本："]

    # 具体分析：哪些分镜有产品出镜
    placement_rows = []
    for i, row in enumerate(script.storyboard):
        if "酸奶" in row.visual_description or "产品" in row.product_placement:
            placement_rows.append(i + 1)

    for f in failed:
        instructions.append(f"- {f.rule}: {f.details}")

    # 植入频次超标 → 给具体删减指令
    if any("产品植入" in c.rule for c in failed):
        if len(placement_rows) > 3:
            keep = placement_rows[:1] + placement_rows[-1:]  # 保留第一个和最后一个
            remove = [r for r in placement_rows if r not in keep]
            instructions.append(f"\n⚠️ 当前有 {len(placement_rows)} 个分镜出现产品出镜，必须删减到 ≤3 处:")
            instructions.append(f"  ✅ 保留第 {keep} 个分镜（开场拉丝 + 成品同框）")
            for r in remove:
                instructions.append(f"  ❌ 删除第 {r} 个分镜中的产品画面（瓶子/logo不出镜，只保留食材操作）")

    found_words = []
    for c in failed:
        if "违禁词" in c.rule:
            for w in FORBIDDEN_WORDS:
                if w in c.details: found_words.append(w)
    if found_words:
        instructions.append("\n必须替换:")
        REPLACEMENTS = {"减肥": "控糖/健康管理", "神器": "好物", "天花板": "很赞", "必买": "推荐"}
        for w in found_words:
            rep = REPLACEMENTS.get(w, "")
            instructions.append(f"  - 【{w}】→ {rep}" if rep else f"  - 删除【{w}】")

    if report.suggestions:
        instructions.append("\n修改建议:")
        for s in report.suggestions: instructions.append(f"  - {s}")
    return "\n".join(instructions)
