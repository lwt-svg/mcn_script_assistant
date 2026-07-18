"""Step 5: 自动化文档同步归档 - Write script to Feishu document."""
import os, re
from datetime import datetime
from typing import Optional
import requests
from agent.config import FEISHU_CONFIG
from agent.models import Script, ComplianceReport

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def write_to_feishu(script, compliance_report):
    app_id, app_secret = FEISHU_CONFIG["app_id"], FEISHU_CONFIG["app_secret"]
    if not app_id or not app_secret:
        _save_local(script, compliance_report)
        return None
    try:
        token = _get_token(app_id, app_secret)
        doc_id = _create_doc(token, script)
        doc_url = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"\n[FEISHU] 文档已创建: {doc_url}")
        root_id = _get_root_block_id(token, doc_id)
        blocks = _build_clean_blocks(script, compliance_report)
        _write_blocks(token, doc_id, root_id, blocks)
        return doc_url
    except Exception as e:
        print(f"\n[FEISHU] 写入失败: {type(e).__name__}: {e}")
        _save_local(script, compliance_report)
        return None


def _get_token(app_id, app_secret):
    resp = requests.post(f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                         json={"app_id": app_id, "app_secret": app_secret}, timeout=10)
    _check(resp, "获取Token")
    return resp.json()["tenant_access_token"]


def _create_doc(token, script):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{FEISHU_BASE}/docx/v1/documents", headers=headers,
                         json={"title": f"{script.brand}脚本 - {script.scene}"}, timeout=10)
    _check(resp, "创建文档")
    return resp.json()["data"]["document"]["document_id"]


def _get_root_block_id(token, doc_id):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{FEISHU_BASE}/docx/v1/documents/{doc_id}/blocks", headers=headers, timeout=10)
    _check(resp, "获取根块")
    items = resp.json().get("data", {}).get("items", [])
    if not items: raise RuntimeError("文档无根块")
    return items[0]["block_id"]


def _write_blocks(token, doc_id, parent_id, blocks):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{FEISHU_BASE}/docx/v1/documents/{doc_id}/blocks/{parent_id}/children"
    for i in range(0, len(blocks), 40):
        chunk = blocks[i:i + 40]
        resp = requests.post(url, headers=headers, json={"children": chunk}, timeout=30)
        _check(resp, f"写入内容 (chunk {i//40 + 1})")


def _check(resp, ctx):
    if resp.status_code != 200:
        print(f"\n[FEISHU ERROR] {ctx}: HTTP {resp.status_code}\n  Body: {resp.text[:300]}")
        resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        print(f"\n[FEISHU ERROR] {ctx}: code={data['code']}, msg={data.get('msg', '')}")
        raise RuntimeError(f"Feishu API error {data['code']}")


def _clean(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.replace('|', ' ').strip()


def _build_clean_blocks(script, report):
    blocks = []
    blocks.append(_block("heading1", _clean(script.title)))
    blocks.append(_block("text", f"品牌：{script.brand} ｜ 场景：{script.scene} ｜ 时长：{script.duration}"))
    blocks.append(_block("text", f"风格参考：{script.style_reference}"))
    blocks.append(_block("text", f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"))
    blocks.append(_block("divider", ""))
    blocks.append(_block("heading2", "分镜表"))
    for i, row in enumerate(script.storyboard):
        blocks.append(_block("text", f"【{_clean(row.phase)}】（{row.time}）"))
        blocks.append(_block("text", f"  画面：{_clean(row.visual_description)}"))
        if row.subtitle:
            blocks.append(_block("text", f"  字幕：{_clean(row.subtitle)}"))
        blocks.append(_block("text", f"  植入：{_clean(row.product_placement)} ｜ BGM：{_clean(row.bgm)}"))
        if i < len(script.storyboard) - 1:
            blocks.append(_block("text", ""))
    blocks.append(_block("divider", ""))
    blocks.append(_block("heading2", "产品植入点"))
    for i, p in enumerate(script.product_placement_points, 1):
        blocks.append(_block("text", f"{i}. {_clean(p)}"))
    blocks.append(_block("divider", ""))
    blocks.append(_block("heading2", "合规检查报告"))
    blocks.append(_block("text", f"整体状态：{'通过' if report.passed else '需修改'}"))
    for c in report.checks:
        icon = "✅" if c.status == "pass" else "❌"
        blocks.append(_block("text", f"{icon} {c.rule}：{_clean(c.details)[:120]}"))
    if report.suggestions:
        blocks.append(_block("heading2", "修改建议"))
        for s in report.suggestions:
            blocks.append(_block("text", f"  {_clean(s)}"))
    return blocks


def _block(bt, content):
    type_map = {"text": 2, "heading1": 3, "heading2": 4, "divider": 22}
    t = type_map.get(bt, 2)
    if t == 22:
        return {"block_type": 22, "divider": {}}
    key = "heading1" if t == 3 else "heading2" if t == 4 else "text"
    return {"block_type": t, key: {"elements": [{"text_run": {"content": content, "text_element_style": {}}}], "style": {}}}


def _save_local(script, report):
    from agent.config import AGENT_CONFIG
    out = AGENT_CONFIG["output_dir"]
    os.makedirs(out, exist_ok=True)
    fp = os.path.join(out, f"script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    md = script.to_markdown() + "\n\n---\n\n## 合规检查报告\n\n" + report.to_markdown()
    with open(fp, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n[FILE] 脚本已保存到: {fp}")


save_to_local = _save_local
