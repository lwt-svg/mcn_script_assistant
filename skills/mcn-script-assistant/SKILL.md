# MCN 脚本生成助手 Skill

## 元信息
- **名称**: mcn-script-assistant
- **版本**: 1.0.0
- **描述**: 根据品牌 Brief + 小红书博主风格，自动生成合规可拍摄的短视频脚本，并写入飞书文档
- **依赖**: Python 3.10+, LangGraph, DeepSeek/OpenAI API, 飞书开放 API
- **触发词**: "生成脚本"、"写脚本"、"MCN"、"商单"、"小红书脚本"

---

## 一、适用场景与触发条件

### 适用场景
- 小红书短视频商单脚本生成
- 复刻三类博主风格：美食制作 / 产品测评 / 场景休闲
- 软种草、自然植入、合规优先

### 不适用场景
- 口播硬广、直播带货脚本
- 功效型医疗/保健品
- 非食品类且强功效宣称产品

### 触发条件
当用户提出以下请求时，调用此 Skill：
- 帮我生成一个小红书短视频脚本
- 给品牌 X 写一个商单脚本
- 参考博主 Y 的风格，生成一条产品脚本
- 用户提供了品牌 Brief 或提到了 MCN 脚本生成

当用户提出以下请求时，你应该调用此 Skill：
- "帮我生成一个小红书短视频脚本"
- "给品牌 X 写一个商单脚本"
- "参考博主 Y 的风格，生成一条产品脚本"
- 用户提供了品牌 Brief 或提到了 MCN 脚本生成

---

## 二、输入材料与准备工作

### 2.1 读取数据
1. 打开 `final_report.md`，找到 **A1 部分**（10 位博主列表）和 **A3 部分**（选定博主的完整风格拆解）
2. 确认用户是否传了 `--brief` / `--style` / `--scene` 参数

### 2.2 调用入口
```bash
python run_agent.py --scene "夏日早餐" [--brief "品牌信息"] [--style "博主风格"]
```

### 2.3 各个步骤的文件依赖

| 步骤 | 调用文件 | 作用 |
|------|---------|------|
| Step 1 | `agent/steps/brief_parser.py` → `call_llm_json()` | 从 Brief 文本提取结构化 JSON |
| Step 2 | `agent/steps/style_analyzer.py` → `call_llm_json()` | 从 A3 文本提取博主风格 JSON |
| Step 3 | `agent/steps/script_generator.py` → `call_llm()` | 根据风格模板生成脚本 markdown |
| Step 4 | `agent/steps/risk_checker.py` → 规则 + LLM 双层检查 | 合规校验 + 迭代修复（最多 5 次） |
| Step 5 | `agent/steps/feishu_writer.py` → 飞书 API | 写入飞书 + 本地存档 |

---

## 三、执行步骤（工作流程）

### Step 1: 品牌 Brief 解析
- **操作**: 调用 `brief_parser.parse_brief(brief_text)`
- **输入**: 品牌 Brief 文本（品牌名、产品、口味、卖点、人群、约束）
- **输出**: `BriefInfo` 结构化对象
- **文件**: `agent/steps/brief_parser.py`

### Step 2: 博主风格建模
- **操作**: 调用 `style_analyzer.analyze_style(style_text)`
- **输入**: A3 风格拆解文本（人设、场景、镜头、叙事、时长区间、内容类型）
- **输出**: `StyleProfile` 结构化对象（含 `content_type` 和 `time_range`）
- **文件**: `agent/steps/style_analyzer.py`

### Step 3: 脚本生成
- **操作**: 调用 `script_generator.generate_script(brief, style, scene)`
- **动态分镜模板选择**:

| content_type | 分镜结构 | 时长 |
|-------------|---------|------|
| 美食制作 | 钩子→食材→制作→成品→结尾 | 50-60s |
| 产品测评 | 实测钩子→产品核验→口感实测→对比总结→收尾 | 35-45s |
| 场景休闲 | 氛围钩子→产品陈列→简易搭配→成品展示→情绪收尾 | 40-65s |

- **约束**: 各分段时间连续无断层，产品出镜 ≤3 次
- **文件**: `agent/steps/script_generator.py`

### Step 4: 合规检查 + 迭代修复
- **检查项**:
  1. 违禁词规则匹配（FORBIDDEN_WORDS 列表）
  2. 植入频次 ≤3 次
  3. 时长在博主专属区间内
  4. LLM 语义检查（隐性功效暗示、绝对化用语、强引导）
- **失败处理**: 自动生成修复指令（具体到第几个分镜删产品）→ 重新生成 → 再检查
- **终止条件**: 最多 5 次迭代
- **文件**: `agent/steps/risk_checker.py`

### Step 5: 飞书写入 + 本地存档
- **操作**: 调用 `feishu_writer.write_to_feishu(script, report)`
- **流程**: 创建文档 → 获取根块 ID → 分块写入纯文本内容
- **降级**: API 失败时自动保存本地 `output/` 目录
- **文件**: `agent/steps/feishu_writer.py`

---

## 四、风险检查清单与合规规则

### 风险检查清单（输出前逐条过）
- 无减肥/降糖/减脂/饱腹等功效暗示
- 无绝对化用语、极限词、强引导话术
- 产品植入不超3次，自然不生硬
- 时长匹配博主专属区间
- 时间轴连续无断层
- 完全匹配选定博主风格
- 脚本可直接拍摄
- 飞书文档写入成功

### 企业合规红线（不可违反）

### 硬封禁（一票否决）
```
减肥、瘦身、掉秤、燃脂、减脂神效、狂瘦、暴瘦
神器、必买、全网第一、最好、最有效、天花板
医疗效果、替代药物、闭眼入、必须囤
```

### 语义警告（LLM 判断语境）
```
治愈、特效、低卡、随便吃、轻盈、饱腹、控糖、赶紧、囤货
```

### 红线
- ❌ 产品出镜超过 3 次
- ❌ 分段时间断层（0-3s 跳到 6-10s）
- ❌ 结尾强引导（"赶紧冲""闭眼入"）
- ❌ 字幕重复卖点（0蔗糖/高蛋白出现超过 2 次）

---

## 五、输出格式

### 脚本格式
```markdown
# 标题｜副标题

**品牌**: xxx
**场景**: xxx
**时长**: xx s
**风格参考**: @博主

## 分镜表
| 阶段 | 时间 | 画面描述 | 字幕 | 产品植入 | BGM |

## 产品植入点
1. ...
2. ...

## 合规风险提醒
- ✅ ...
```

### 合规报告
```json
{
  "passed": true/false,
  "checks": [{"rule": "...", "status": "pass/fail", "details": "..."}],
  "suggestions": ["..."]
}
```

---

## 六、运行示例

### 基础运行
bash
python run_agent.py --scene 夏日早餐


### 测评博主
bash
python run_agent.py --scene 无糖酸奶横评 --style 三无测评


### 关闭飞书
bash
python run_agent.py --scene 运动后加餐 --no-feishu


## 七、失败处理

| 失败场景 | 处理方式 |
|---------|---------|
| 迭代 5 次仍不合规 | 输出失败报告 + 最后一版脚本 |
| 输入缺失关键信息 | 提示缺失信息，终止执行 |
| 飞书 API 调用失败 | 本地保存，返回提示 |
| LLM API 调用失败 | 自动重试 3 次（指数退避） |

---

## 七、扩展方式

### 添加新博主
在 `final_report.md` 的 A3 部分添加风格拆解，包含：
```markdown
## A3-N 博主：XXX
- 人设：...
- 内容类型：产品测评
- 时长区间：35-45s
- 叙事结构：5段式
- 表达方式：有/无口播
- 产品植入规则：...
```

### 添加新违禁词
在 `agent/config.py` 的 `FORBIDDEN_WORDS` 或 `CAUTION_WORDS` 列表中添加。

### 支持新内容类型
在 `script_generator.py` 的 `_build_prompt()` 中添加新的分镜模板。
