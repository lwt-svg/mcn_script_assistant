"""MCN Script Agent — LangGraph StateGraph implementation.

Architecture (5-step graph with parallel entry):

                    START
                      │
          ┌───────────┼───────────┐
          ▼           │           ▼
    parse_brief       │    analyze_style
          └───────────┼───────────┘
                      ▼
              generate_script
                      │
                      ▼
              check_compliance
                      │
              ┌───────┴───────┐
              │               │
         [PASS]           [FAIL]
              │               │
              ▼               ▼
        write_output    fix_script
              │               │
              ▼               ▼
            [END]      check_compliance (again)
                          │     │
                     [PASS]  [FAIL & >=max_iter]
                          │     │
                          ▼     ▼
                    write_output (warn)
                          │
                          ▼
                        [END]

Usage:
    from agent.mcn_agent import create_mcn_agent_graph, run_mcn_agent

    result = run_mcn_agent(
        brief="Brand brief...",
        style_analysis="Blogger analysis...",
        scene="夏日早餐",
    )
    print(result.script.title)
"""

from typing import TypedDict, List, Optional, Literal

from langgraph.graph import StateGraph, START, END

from agent.models import (
    BriefInfo, StyleProfile, Script, ComplianceReport,
    AgentResult, IterationRecord,
)
from agent.steps.brief_parser import parse_brief as _parse_brief
from agent.steps.style_analyzer import analyze_style as _analyze_style
from agent.steps.script_generator import generate_script as _generate_script
from agent.steps.risk_checker import check_compliance as _check_compliance
from agent.steps.risk_checker import generate_fix_instructions
from agent.steps.feishu_writer import write_to_feishu as _write_to_feishu
from agent.steps.feishu_writer import save_to_local
from agent.llm import get_global_usage
from agent.config import AGENT_CONFIG


# ── State Definition ─────────────────────────────────────────

class AgentState(TypedDict):
    """Shared state passed through all graph nodes."""
    # Inputs
    brief_text: str
    style_text: str
    scene: str
    max_iterations: int
    write_feishu: bool

    # Step outputs
    brief_info: Optional[BriefInfo]
    style_profile: Optional[StyleProfile]
    script: Optional[Script]
    compliance: Optional[ComplianceReport]

    # Iteration tracking
    iterations: int
    fix_instructions: str
    iteration_records: List[IterationRecord]

    # Final output
    feishu_url: Optional[str]
    errors: List[str]
    verbose: bool


# ── Graph Nodes ──────────────────────────────────────────────

def parse_brief_node(state: AgentState) -> dict:
    """Step 1: 需求结构化解析"""
    _log(state, f"Step 1: 需求结构化解析...")
    try:
        brief_info = _parse_brief(state["brief_text"])
        _log(state, f"  → 品牌: {brief_info.brand_name}, 产品: {brief_info.product}")
        return {"brief_info": brief_info}
    except Exception as e:
        _log(state, f"  [ERROR] Brief解析失败: {e}")
        return {"brief_info": None, "errors": state.get("errors", []) + [f"parse_brief: {e}"]}


def analyze_style_node(state: AgentState) -> dict:
    """Step 2: 达人内容风格建模"""
    _log(state, f"Step 2: 达人内容风格建模...")
    try:
        style_profile = _analyze_style(state["style_text"])
        _log(state, f"  → 博主: {style_profile.blogger_name}, 场景: {len(style_profile.scenes)} 个")
        return {"style_profile": style_profile}
    except Exception as e:
        _log(state, f"  [ERROR] 风格分析失败: {e}")
        return {"style_profile": None, "errors": state.get("errors", []) + [f"analyze_style: {e}"]}


def generate_script_node(state: AgentState) -> dict:
    """Step 3: 商单脚本标准化生成"""
    brief = state["brief_info"]
    style = state["style_profile"]
    scene = state["scene"]

    if not brief or not style:
        _log(state, "  [ERROR] Brief或风格数据缺失，无法生成脚本")
        return {"errors": state.get("errors", []) + ["generate_script: missing brief or style"]}

    _log(state, f"Step 3: 商单脚本标准化生成 (场景: {scene})...")
    try:
        script = _generate_script(brief, style, scene)
        _log(state, f"  → 标题: {script.title}, 分镜数: {len(script.storyboard)}")

        # Track iteration record
        records = list(state.get("iteration_records", []))
        records.append(IterationRecord(
            iteration=state.get("iterations", 0) + 1,
            script=script,
            compliance=state.get("compliance"),
            fix_summary=state.get("fix_instructions", "")[:80],
        ))

        return {"script": script, "iteration_records": records}
    except Exception as e:
        _log(state, f"  [ERROR] 脚本生成失败: {e}")
        return {"errors": state.get("errors", []) + [f"generate_script: {e}"]}


def check_compliance_node(state: AgentState) -> dict:
    """Step 4: 内容合规风控校验"""
    script = state["script"]
    style = state["style_profile"]

    if not script:
        return {"errors": state.get("errors", []) + ["check_compliance: no script"]}

    _log(state, f"Step 4: 内容合规风控校验...")
    try:
        compliance = _check_compliance(script, style)
        status = "[PASS] 通过" if compliance.passed else "[FAIL] 需修改"
        _log(state, f"  → 检查结果: {status}")

        # 在 node 中生成 fix_instructions（而非在条件路由函数中），
        # 因为路由函数只能返回目标节点名，无法更新 state
        fix_instructions = ""
        if not compliance.passed:
            fix_instructions = generate_fix_instructions(script, compliance)
            _log(state, f"  → 生成修复指令 (第{state.get('iterations', 0) + 1}次迭代)...")

        return {
            "compliance": compliance,
            "iterations": state.get("iterations", 0) + 1,
            "fix_instructions": fix_instructions,
        }
    except Exception as e:
        _log(state, f"  ❌ 合规检查失败: {e}")
        return {"errors": state.get("errors", []) + [f"check_compliance: {e}"]}


def fix_script_node(state: AgentState) -> dict:
    """Step 3b: 修复脚本（合规 FAIL 后调用）"""
    brief = state["brief_info"]
    style = state["style_profile"]
    scene = state["scene"]
    old_script = state["script"]
    fix_instructions = state.get("fix_instructions", "")
    iteration = state.get("iterations", 0)

    _log(state, f"Step 3 (第{iteration}次迭代): 修复脚本...")
    try:
        fixed = _generate_fixed_script_node(brief, style, scene, old_script, fix_instructions)
        if fixed:
            _log(state, f"  → 修复后标题: {fixed.title}")
            return {"script": fixed}
    except Exception as e:
        _log(state, f"  ❌ 脚本修复失败: {e}")
        return {"errors": state.get("errors", []) + [f"fix_script: {e}"]}

    return {}


def write_output_node(state: AgentState) -> dict:
    """Step 5: 自动化文档同步归档"""
    script = state["script"]
    compliance = state["compliance"]
    feishu_url = None

    _log(state, "Step 5: 保存脚本...")

    if script and compliance:
        # Always save locally
        save_to_local(script, compliance)

        # Optionally write to Feishu
        if state.get("write_feishu", True):
            _log(state, "  → 尝试写入飞书文档...")
            feishu_url = _write_to_feishu(script, compliance)
            if feishu_url:
                _log(state, f"  → 飞书文档: {feishu_url}")

    return {"feishu_url": feishu_url}


# ── Conditional edge routing ─────────────────────────────────

def route_after_compliance(state: AgentState) -> Literal["fix_script", "write_output"]:
    """Route based on compliance check result."""
    compliance = state.get("compliance")
    iterations = state.get("iterations", 0)
    max_iter = state.get("max_iterations", AGENT_CONFIG["max_iterations"])

    if not compliance:
        return "write_output"

    if compliance.passed:
        _log(state, f"  → 合规检查通过! (迭代{iterations}次)")
        return "write_output"

    if iterations < max_iter:
        # fix_instructions 已在 check_compliance_node 中生成并写回 state
        return "fix_script"

    _log(state, f"  → ⚠️  已达到最大迭代次数 ({max_iter})，输出当前脚本")
    return "write_output"


# ── Helper functions ─────────────────────────────────────────

def _log(state: AgentState, msg: str):
    """Print log if verbose mode is on."""
    if state.get("verbose", True):
        print(msg)


def _generate_fixed_script_node(
    brief: BriefInfo,
    style_profile: StyleProfile,
    scene: str,
    original_script: Script,
    fix_instructions: str,
) -> Optional[Script]:
    """Regenerate a script with fix instructions applied."""
    from agent.llm import call_llm

    prompt = f"""我需要你修复以下短视频脚本中的合规问题。

## 品牌 Brief
{brief.to_prompt_block()}

## 参考博主风格
{style_profile.to_prompt_block()}

## 拍摄场景
{scene}

## 原始脚本
{original_script.raw_text}

## 需要修复的问题
{fix_instructions}

请根据修复要求重新生成完整的脚本。保持博主风格不变，只修复合规问题。
使用 markdown 表格输出分镜表。"""

    system_prompt = """你是一个专业的小红书脚本修复助手。根据合规审查反馈修改脚本。

规则:
1. 输出必须以  开头作为标题行, 例如 
2. 保持博主风格不变, 只修复合规问题
3. 使用 markdown 表格输出完整分镜表
4. 分镜表之后写 ## 产品植入点 和 ## 合规风险提醒
5. 不要改变叙事结构、风格和产品植入方式"""

    response = call_llm(prompt, system_prompt, temperature=0.2)
    from agent.steps.script_generator import _parse_script
    return _parse_script(response, brief, scene, style_profile)


# ── Graph Builder ────────────────────────────────────────────

def create_mcn_agent_graph() -> StateGraph:
    """Build and compile the MCN Agent LangGraph."""
    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("parse_brief", parse_brief_node)
    builder.add_node("analyze_style", analyze_style_node)
    builder.add_node("generate_script", generate_script_node)
    builder.add_node("check_compliance", check_compliance_node)
    builder.add_node("fix_script", fix_script_node)
    builder.add_node("write_output", write_output_node)

    # Edges: START → parallel brief + style
    builder.add_edge(START, "parse_brief")
    builder.add_edge(START, "analyze_style")

    # Edges: brief/style → script generation
    builder.add_edge("parse_brief", "generate_script")
    builder.add_edge("analyze_style", "generate_script")

    # Edge: script → compliance check
    builder.add_edge("generate_script", "check_compliance")

    # Conditional: compliance → fix OR output
    builder.add_conditional_edges(
        "check_compliance",
        route_after_compliance,
        {
            "fix_script": "fix_script",
            "write_output": "write_output",
        },
    )

    # Edge: fix → re-check compliance
    builder.add_edge("fix_script", "check_compliance")

    # Edge: output → end
    builder.add_edge("write_output", END)

    return builder.compile()


# ── Convenience Runner ───────────────────────────────────────

COMPILED_GRAPH = None


def get_graph() -> StateGraph:
    """Get or create the compiled graph (singleton)."""
    global COMPILED_GRAPH
    if COMPILED_GRAPH is None:
        COMPILED_GRAPH = create_mcn_agent_graph()
    return COMPILED_GRAPH


def run_mcn_agent(
    brief: str,
    style_analysis: str,
    scene: str,
    max_iterations: int = None,
    write_to_feishu_doc: bool = True,
    verbose: bool = True,
) -> AgentResult:
    """Run the full MCN Agent workflow via LangGraph.

    Args:
        brief: Brand brief text.
        style_analysis: Reference blogger content style analysis.
        scene: Scene theme for the script.
        max_iterations: Max auto-fix iterations (default from config).
        write_to_feishu_doc: Whether to write result to Feishu.
        verbose: Whether to print progress.

    Returns:
        AgentResult with all outputs.
    """
    graph = get_graph()

    initial_state: AgentState = {
        "brief_text": brief,
        "style_text": style_analysis,
        "scene": scene,
        "max_iterations": max_iterations or AGENT_CONFIG["max_iterations"],
        "write_feishu": write_to_feishu_doc,
        "brief_info": None,
        "style_profile": None,
        "script": None,
        "compliance": None,
        "iterations": 0,
        "fix_instructions": "",
        "iteration_records": [],
        "feishu_url": None,
        "errors": [],
        "verbose": verbose,
    }

    final_state = graph.invoke(initial_state)

    # Build AgentResult
    usage = get_global_usage()
    script = final_state.get("script")
    compliance = final_state.get("compliance")
    records = final_state.get("iteration_records", [])

    if verbose:
        print("\n" + "=" * 55)
        print("✅ Agent 工作流完成!")
        print(f"  品牌: {final_state.get('brief_info', {}).brand_name if final_state.get('brief_info') else 'N/A'}")
        print(f"  博主: {final_state.get('style_profile', {}).blogger_name if final_state.get('style_profile') else 'N/A'}")
        print(f"  场景: {scene}")
        print(f"  脚本: {script.title if script else 'N/A'}")
        print(f"  合规: {'✅ 通过' if compliance and compliance.passed else '❌ 需修改'}")
        print(f"  迭代: {len(records)} 次")
        print(f"  {usage}")
        if usage.calls > 0:
            print(f"  预估费用: ${usage.estimate_cost():.4f}")
        if final_state.get("feishu_url"):
            print(f"  飞书: {final_state['feishu_url']}")
        if final_state.get("errors"):
            print(f"  错误: {final_state['errors']}")
        print("=" * 55)

    return AgentResult(
        brief=final_state.get("brief_info"),
        style_profile=final_state.get("style_profile"),
        script=script,
        compliance_report=compliance,
        feishu_url=final_state.get("feishu_url"),
        iterations=records,
        total_iterations=len(records),
    )
