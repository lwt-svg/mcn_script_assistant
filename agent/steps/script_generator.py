"""Step 3: 商单脚本标准化生成 - Xiaohongshu-quality scripts with enterprise compliance."""
import re
from typing import List
from agent.models import BriefInfo, StyleProfile, Script, StoryboardRow
from agent.llm import call_llm


SYSTEM_PROMPT = """你是一位资深小红书MCN内容策划，专门为品牌商单撰写达人短视频脚本。

## 核心原则
你的脚本必须像「这个博主本人写的」，同时严格对齐企业品牌合规标准。

### 1. 3秒钩子法则
- 开头0-3秒必须是「最诱人的画面」：拉丝酸奶、挖起的一勺、食材掉落慢动作
- 字幕用博主口吻抓眼球
- 绝对禁止：拍空桌子、慢悠悠开场

### 2. 博主灵魂注入
- 使用博主常用语气词、口头禅、emoji
- 字幕要有「网感」：用"谁懂啊""拿捏住了"等热词
- 走清爽早餐、日常美食、治愈吃法路线

### 3. 时间轴必须连续无断层
- 各分段时间必须首尾相连: 0-5s → 5-12s → 12-25s → 25-40s → 40-52s → 52-60s
- 不允许出现 0-3s 下个直接跳到 6-10s 这种断层
- 最后一段结束时间 = 总时长(50-60s)

### 4. 拍摄指令必须可执行
每个分镜画面描述包含：机位（俯拍/45度侧拍/特写/慢镜头）、具体动作、质感描述

### 5. 产品植入「软但不弱」
- 产品是「场景的解决方案」，非强行推荐
- 卖点展示：仅靠镜头拍瓶身"0蔗糖""高蛋白"字样，字幕不重复卖点
- 产品出镜控制在 3 次：开场拉丝(1次) + 制作使用(1次) + 成品同框(1次)

### 6. 企业合规红线 (严格遵守!)
- 禁止绝对化用语：不能写"天花板""全网第一""最好""最有效""无敌""满分"
- 禁止减脂暗示：不能写"轻盈""控糖""饱腹抗饿""一上午不饿"
- 禁止强引导话术：不能写"赶紧冲""闭眼入""必须囤""链接在主页"
- 卖点仅描述产品属性(0蔗糖、高蛋白)，不绑定身材管理
- 结尾种草温和："日常早餐轻松安排""快试试吧"风格

### 7. 输出规则
- 直接输出脚本内容, 不要以"好的""当然""作为"等对话开头
- 第一行必须是 # 标题
- 不要任何开场白或结束语

### 8. 输出格式
用 markdown 表格输出分镜表，包含：阶段 | 时间 | 画面描述 | 字幕 | 产品植入 | BGM
分镜结束后写 ## 产品植入点 和 ## 合规风险提醒"""


def generate_script(brief: BriefInfo, style_profile: StyleProfile, scene: str) -> Script:
    prompt = _build_prompt(brief, style_profile, scene)
    response = call_llm(prompt, SYSTEM_PROMPT, temperature=0.6)
    return _parse_script(response, brief, scene, style_profile)


def _build_prompt(brief, style, scene):
    is_voiceover = style.expression.voiceover
    if not is_voiceover:
        voiceover_rule = """绝对不能出现口播人声，全程只靠字幕传递信息。字幕使用短句，控制在2行以内。"""
    else:
        voiceover_rule = """全程真人口播。每个分镜必须写出口播文案（博主实际说的话），字幕即口播内容。
口播要求：
- 语言口语化、接地气，像博主本人真实说话
- 每段口播3-5句话，自然流畅
- 字幕直接写博主说的原话
- 不要用书面语或营销话术"""
        # 如果是测评博主，加额外的测评口播指引
        if getattr(style, "content_type", "") == "产品测评":
            voiceover_rule += """
测评口播风格：
- 开头直接抛出测评问题（'今天来测一下xx'）
- 中间讲真实口感、配料参数（'我们先看配料表'）
- 结尾客观总结优缺点（'综合来看这款更适合xx'）
- 语速快、不废话、像朋友真实吐槽"""
    time_range = getattr(style, "time_range", "50-60") or "50-60"
    try:
        parts = time_range.replace("秒", "").split("-")
        min_t, max_t = int(parts[0]), int(parts[1])
    except:
        min_t, max_t = 50, 60
    content_type = getattr(style, "content_type", "美食制作") or "美食制作"
    
    if content_type == "产品测评":
        structure = f"""## 分镜结构（测评向）
1. 开场实测钩子 (0-5s) - 产品直拍
2. 产品核验 (5-15s) - 配料表/参数特写
3. 质地/口感实测 (15-30s) - 原相机实拍
4. 亮点总结 (30-45s) - 突出优势
5. 收尾 ({45}-{max_t}s) - 客观总结"""
    elif content_type == "场景休闲":
        structure = f"""## 分镜结构（休闲向）
1. 场景钩子 (0-5s) - 工位/居家氛围
2. 产品陈列 (5-15s) - 自然入镜
3. 简易搭配 (15-35s) - 极简操作
4. 成品展示 (35-50s) - 治愈氛围
5. 收尾 ({50}-{max_t}s) - 情绪总结"""
    else:
        m3 = max(30, min_t*3//5)
        m4 = max(45, min_t*4//5)
        structure = f"""## 分镜结构（制作向）
1. 开场钩子 (0-{max(3, min_t//10)}s)
2. 食材展示 ({max(3, min_t//10)}-{max(10, min_t//5)}s)
3. 分步制作 ({max(10, min_t//5)}-{m3}s)
4. 成品摆盘 ({m3}-{m4}s)
5. 结尾 ({m4}-{max_t}s)"""

    return f"""请为以下品牌和博主生成 {min_t}-{max_t} 秒短视频脚本。
    
## 品牌信息
{brief.to_prompt_block()}

## 博主风格
{style.to_prompt_block()}

## 拍摄场景
{scene}

{structure}

## 质量要求
- 开头抓眼球
- {voiceover_rule}
- 字幕带emoji
- 各分段时间连续无断层
- 禁止绝对化用语（天花板/满分/全网第一）
- 禁止减脂暗示（轻盈/控糖/饱腹）
- 禁止强引导（赶紧冲/闭眼入）
- 产品出镜不超3次
- 结尾温和种草
- 总时长控制在{min_t}-{max_t}s, 最后一段结束时间={max_t}s"""


def _parse_script(response, brief, scene, style):
    title = _extract_title(response)
    storyboard = _extract_storyboard(response)
    placement_points = _extract_section(response, "产品植入点")
    compliance_notes = _extract_compliance_notes(response)

    section_headers = {"分镜表", "产品植入点", "合规风险提醒", "品牌信息", "脚本信息", "品牌 Brief"}
    if not title or title == "未命名脚本" or title in section_headers or title.startswith("##"):
        title = f"{scene}｜{brief.brand_name}酸奶"

    return Script(title=title, brand=brief.brand_name, scene=scene,
                  duration=_estimate_duration(storyboard),
                  style_reference=f"参考 @{style.blogger_name}",
                  storyboard=storyboard, product_placement_points=placement_points,
                  compliance_notes=compliance_notes, raw_text=response)


def _extract_title(text):
    lines = text.split("\n")
    section_headers = {"分镜表", "产品植入点", "合规风险提醒", "品牌 Brief", "品牌信息", "脚本信息", "脚本", "品牌"}

    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            cleaned = s.lstrip("#").strip()
            if "|" in cleaned or cleaned in section_headers:
                continue
            if 2 < len(cleaned) < 60:
                return cleaned

    import re
    for line in lines:
        s = line.strip()
        m = re.search(r'[「《](.+?)[」》]', s)
        if m:
            c = m.group(1)
            if len(c) > 3 and "|" not in c:
                return c

    for line in lines[:15]:
        s = line.strip()
        if not s or s.startswith("|") or s in section_headers:
            continue
        if len(s) > 3 and len(s) < 80:
            return s

    for line in lines[:8]:
        s = line.strip()
        if "｜" in s or "拿捏" in s or "谁懂" in s:
            return s
    return "未命名脚本"


def _extract_storyboard(text):
    rows = []
    in_table = False
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("| 阶段") or ("阶段" in s and "时间" in s and s.startswith("|")):
            in_table = True
            continue
        if in_table and re.match(r'^\|[\s\-:]+\|', s):
            continue
        if in_table and s.startswith("|"):
            cells = [c.strip() for c in s.split("|")[1:-1]]
            if len(cells) >= 6:
                rows.append(StoryboardRow(phase=cells[0], time=cells[1],
                    visual_description=cells[2], subtitle=cells[3],
                    product_placement=cells[4], bgm=cells[5]))
        elif in_table and not s.startswith("|"):
            in_table = False
    return rows


def _extract_section(text, section_name):
    items, inside = [], False
    for line in text.split("\n"):
        s = line.strip()
        if section_name in s and s.startswith("##"):
            inside = True
            continue
        if inside:
            if s.startswith("##") and section_name not in s:
                break
            if s.startswith(("1.", "2.", "3.", "4.", "-", "*")) and len(s) > 2:
                items.append(s.lstrip("1234567890.-* ").strip())
    return items


def _extract_compliance_notes(text):
    notes, inside = [], False
    for line in text.split("\n"):
        s = line.strip()
        if "合规风险" in s and s.startswith("##"):
            inside = True
            continue
        if inside:
            if s.startswith("##") and "合规风险" not in s:
                break
            if s.startswith(("-", "✅", "❌", "*")):
                note = s.lstrip("-✅❌* ").strip()
                if note:
                    notes.append(note)
            elif s and not s.startswith("|"):
                notes.append(s)
    return notes


def _estimate_duration(storyboard):
    if not storyboard:
        return "60s"
    max_time = 0
    for row in storyboard:
        for part in row.time.replace("s", "").split("-"):
            try:
                t = int(part.strip())
                if t > max_time:
                    max_time = t
            except ValueError:
                pass
    return f"{max_time}s" if max_time > 0 else "60s"
