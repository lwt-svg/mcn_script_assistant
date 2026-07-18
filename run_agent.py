"""MCN Script Agent - 运行入口。"""

import argparse, sys, os
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.mcn_agent import run_mcn_agent
from agent.llm import get_global_usage


DEFAULT_BRIEF = """品牌：轻食酸奶「轻醒」
产品：0蔗糖高蛋白希腊酸奶
口味：原味、蓝莓、黄桃
核心卖点：高蛋白(≥8g/杯)、饱腹感、低负担
目标人群：22-35岁城市女性，关注健身、控糖、轻食和上班族效率生活
使用场景：早餐、运动后、下午茶
投放平台：小红书短视频
约束条件：
- 不能承诺减肥、降糖等功效
- 避免夸大效果
- 不能使用"狂瘦""掉秤神器"等违禁词
- 脚本需要适合真实达人拍摄
- 内容自然种草，不要硬广"""

DEFAULT_STYLE = """博主：豆豆子
粉丝量级：18.2w
内容方向：精致一人食brunch｜氛围感酸奶碗教程｜居家简餐｜居家下午茶美食短视频

人设：松弛感居家美食爱好者，并非高强度自律减脂博主。主打慢悠悠在家制作简单精致的一人食，传递治愈的居家生活情绪，属于真实自用分享型美食创作者，无焦虑式身材说教。

内容场景：场景高度集中于居家厨房：周末宅家早餐、居家brunch、午后简易下午茶、5-10分钟快手轻食简餐。几乎无外出探店内容，全部为居家操作台实拍。

表达方式：
- 全程无口播、无人声配音，仅搭配舒缓轻音乐BGM叙事
- 依靠分段弹出的短字幕传递文案信息，字幕克制简短，不做大段营销说教
- 镜头以俯拍、食材特写、慢节奏轻微推拉运镜为主，依靠画面氛围感传递情绪，极大弱化广告痕迹

叙事结构（单条视频标准时长：50-60s）：
1. 开场钩子【0-6s】：俯拍干净操作台，平铺展示本次全部食材
2. 食材展示+产品引入【6-15s】：依次给到食材特写，给到酸奶瓶身特写
3. 分步制作流程【15-40s】：手部操作特写，交替切换俯拍、45°侧拍
4. 成品摆盘强化【40-52s】：45°斜拍完整成品特写，酸奶瓶与成品同框入镜
5. 结尾定格收尾【52-60s】：成品画面静态定格2-3秒

镜头范式：
- 光线：柔和居家自然光，画面干净通透，低饱和治愈色调
- 机位：操作台俯拍、45°斜侧拍、手部操作特写、成品特写
- 运镜：极慢轻微推拉，无快速晃动，全程舒缓安静
- 音频：轻柔治愈纯音乐BGM，全程禁止添加任何口播人声

产品植入规则：
- 产品作为场景化食材自然出现，不做强行推荐
- 卖点依靠字幕输出，画面只展示制作流程
- 禁止使用功效承诺话术
- 禁用"狂瘦""掉秤神器"等夸大话术
- 植入位置：食材展示段(6-15s) + 成品摆盘段(40-52s)"""

STYLE_PRESETS = {
    "豆豆子": DEFAULT_STYLE,
    "三无测评": """博主：三无测评(15.3w粉)
内容方向：无滤镜食品真实测评
人设：理性客观、真实不恰饭的平民测评博主
表达方式：全程真人快速口播，字幕只标核心参数
镜头：固定平视桌面机位，无滤镜
时长区间：35-45
内容类型：产品测评
叙事结构：实测钩子0-5s→产品核验5-12s→质地实测12-28s→横向对比28-38s→理性收尾38-45s
产品植入：多品横向测评对比，出镜2-3次，无强引导""",
}

SCENE_CATALOG = {
    "夏日早餐": "夏日清爽早餐场景，以酸奶碗搭配水果、格兰诺拉",
    "办公室下午茶": "工位轻松下午茶场景，以酸奶搭配坚果、水果",
    "周末brunch": "周末宅家brunch场景，以酸奶搭配吐司、沙拉",
    "运动后加餐": "健身运动后快速补充场景，以酸奶搭配蛋白棒、水果",
    "夏日解馋加餐": "午后解馋清爽场景，以酸奶搭配冰镇水果",
}


def main():
    parser = argparse.ArgumentParser(description="MCN 脚本生成助手 — 5步 Agent 工作流")
    parser.add_argument("--scene", type=str, default="夏日早餐", help="拍摄场景")
    parser.add_argument("--brief", type=str, default=None, help="品牌 Brief（可选）")
    parser.add_argument("--style", type=str, default=None, help="博主风格拆解（可选）")
    parser.add_argument("--max-iter", type=int, default=None, help="合规检查最大迭代次数")
    parser.add_argument("--no-feishu", action="store_true", help="禁用飞书文档写入")
    parser.add_argument("--quiet", action="store_true", help="安静模式")
    parser.add_argument("--list-scenes", action="store_true", help="列出可用场景")
    args = parser.parse_args()

    if args.list_scenes:
        print("可用的拍摄场景：\n")
        for name, desc in SCENE_CATALOG.items():
            print(f"  {name:14}  {desc}")
        return

    verbose = not args.quiet
    if args.scene not in SCENE_CATALOG:
        print(f"[WARN] 场景 \"{args.scene}\" 不在预置场景中，将使用自定义场景")

    # Resolve style: if name matches a preset, use the full description
    style_text = args.style
    if style_text and style_text in STYLE_PRESETS:
        style_text = STYLE_PRESETS[style_text]

    result = run_mcn_agent(
        brief=args.brief or DEFAULT_BRIEF,
        style_analysis=style_text or DEFAULT_STYLE,
        scene=args.scene,
        max_iterations=args.max_iter,
        write_to_feishu_doc=not args.no_feishu,
        verbose=verbose,
    )

    if not args.quiet:
        _print_summary(result)


def _print_summary(result):
    print("\n" + "=" * 60)
    print("[OUTPUT] 最终交付物")
    print("=" * 60)
    if not result.script:
        print("\n[ERROR] 脚本生成失败")
        return
    print(f"\n[TITLE] 脚本标题: {result.script.title}")
    print(f"[BRAND] 品牌: {result.script.brand}  [SCENE] 场景: {result.script.scene}")
    print(f"[TIME]  时长: {result.script.duration}  [STYLE] 风格参考: {result.script.style_reference}")
    if result.script.storyboard:
        print(f"\n[STORYBOARD] 分镜表 ({len(result.script.storyboard)} 段):")
        for row in result.script.storyboard:
            vis = row.visual_description[:30]
            sub = row.subtitle[:20]
            print(f"  {row.phase:10} {row.time:6} | {vis:32} | {sub:22}")
    if result.compliance_report:
        status_icon = "[PASS]" if result.compliance_report.passed else "[FAIL]"
        print(f"\n[CHECK] 合规检查: {status_icon}")
    if result.feishu_url:
        print(f"\n[FEISHU] 飞书文档: {result.feishu_url}")
    usage = get_global_usage()
    if usage.calls > 0:
        print(f"\n[TOKEN] Token 消耗: {usage}")
        print(f"[COST]  预估费用: ${usage.estimate_cost():.4f}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
