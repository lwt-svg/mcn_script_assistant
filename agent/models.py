"""Data models for the MCN Script Agent."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BriefInfo:
    brand_name: str
    product: str
    flavors: List[str]
    core_selling_points: List[str]
    target_audience: str
    usage_scenarios: List[str]
    constraints: List[str]

    def to_prompt_block(self):
        lines = [f"- 品牌: {self.brand_name}", f"- 产品: {self.product}",
                 f"- 口味: {', '.join(self.flavors)}",
                 f"- 核心卖点: {', '.join(self.core_selling_points)}",
                 f"- 目标人群: {self.target_audience}",
                 f"- 使用场景: {', '.join(self.usage_scenarios)}", "--- 约束条件 ---"]
        for c in self.constraints:
            lines.append(f"  - {c}")
        return "\n".join(lines)


@dataclass
class CameraStyle:
    angles: List[str]
    movement: str
    lighting: str


@dataclass
class ExpressionStyle:
    voiceover: bool
    subtitle_style: str
    bgm: str
    tone: str


@dataclass
class NarrativePhase:
    phase: str
    time: str
    shot: str


@dataclass
class StyleProfile:
    blogger_name: str
    persona: str
    scenes: List[str]
    expression: ExpressionStyle
    camera_style: CameraStyle
    narrative_structure: List[NarrativePhase]
    product_placement_rules: List[str]
    content_type: str = "美食制作"
    time_range: str = "50-60"

    def to_prompt_block(self):
        lines = [f"- 博主: {self.blogger_name}", f"- 人设: {self.persona}",
                 f"- 场景: {', '.join(self.scenes)}",
                 f"- 内容类型: {self.content_type}",
                 f"- 时长区间: {self.time_range}秒",
                 f"- 口播: {'无' if not self.expression.voiceover else '有'}",
                 f"- 字幕: {self.expression.subtitle_style}",
                 f"- BGM: {self.expression.bgm}", f"- 调性: {self.expression.tone}",
                 f"- 镜头: {', '.join(self.camera_style.angles)}",
                 f"- 运镜: {self.camera_style.movement}",
                 f"- 光线: {self.camera_style.lighting}", "--- 叙事 ---"]
        for p in self.narrative_structure:
            lines.append(f"  {p.phase} ({p.time}): {p.shot}")
        lines.append("--- 植入规则 ---")
        for r in self.product_placement_rules:
            lines.append(f"  - {r}")
        return "\n".join(lines)


@dataclass
class StoryboardRow:
    phase: str
    time: str
    visual_description: str
    subtitle: str
    product_placement: str
    bgm: str


@dataclass
class Script:
    title: str
    brand: str
    scene: str
    duration: str
    style_reference: str
    storyboard: List[StoryboardRow]
    product_placement_points: List[str]
    compliance_notes: List[str]
    raw_text: str = ""

    def to_markdown(self):
        lines = [f"# {self.title}", "", f"**品牌**: {self.brand}", f"**场景**: {self.scene}",
                 f"**时长**: {self.duration}", f"**风格参考**: {self.style_reference}", "",
                 "---", "", "## 分镜表", "",
                 "| 阶段 | 时间 | 画面描述 | 字幕 | 产品植入 | BGM |",
                 "|------|------|---------|------|---------|-----|"]
        for row in self.storyboard:
            lines.append(f"| {row.phase} | {row.time} | {row.visual_description} | {row.subtitle} | {row.product_placement} | {row.bgm} |")
        lines.extend(["", "---", "", "## 产品植入点", ""])
        for i, p in enumerate(self.product_placement_points, 1):
            lines.append(f"{i}. {p}")
        lines.extend(["", "## 合规风险提醒"])
        for n in self.compliance_notes:
            lines.append(f"- {n}")
        return "\n".join(lines)


@dataclass
class ComplianceCheck:
    rule: str
    status: str
    details: str


@dataclass
class ComplianceReport:
    passed: bool
    checks: List[ComplianceCheck]
    suggestions: List[str]

    def to_markdown(self):
        lines = [f"**整体状态**: {'[PASS] 通过' if self.passed else '[FAIL] 需修改'}", "",
                 "| 检查项 | 状态 | 详情 |", "|--------|------|------|"]
        for c in self.checks:
            icon = "[PASS]" if c.status == "pass" else "[FAIL]"
            lines.append(f"| {c.rule} | {icon} | {c.details} |")
        lines.extend(["", "### 修改建议", ""])
        for s in self.suggestions:
            lines.append(f"- {s}")
        return "\n".join(lines)


@dataclass
class IterationRecord:
    iteration: int
    script: Script
    compliance: ComplianceReport
    fix_summary: str = ""


@dataclass
class AgentResult:
    brief: BriefInfo
    style_profile: StyleProfile
    script: Script
    compliance_report: ComplianceReport
    feishu_url: Optional[str] = None
    iterations: List[IterationRecord] = field(default_factory=list)
    total_iterations: int = 1
