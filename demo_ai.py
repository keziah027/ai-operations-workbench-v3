"""Offline, evidence-linked templates; deliberately not presented as model inference."""
from datetime import datetime, timezone
from ai_contract import SECTIONS, validate_response, CONTRACT_VERSION

NOTICE = '【规则演示，非大模型生成】'


def demo_response(summary, config, question=None):
    from ai_client import AIError, request_version
    if question is not None and (not question.strip() or len(question) > 1500):
        raise AIError('input', '请填写问题，并控制在1500字以内。')
    result = {}
    facts = summary.get('facts', [])
    references = [f['id'] for f in facts[:3]]
    # Fact labels may contain digits. Use a neutral label while keeping exact fact IDs.
    evidence = '；'.join('当前统计事实：{{' + f['id'] + '}}' for f in facts[:3])
    for name, (_, _, fields) in SECTIONS.items():
        if (name == 'answer') != (question is not None):
            continue
        values = {field: NOTICE + '当前证据不足，请结合原文和实际运营目标复核。' for field in fields}
        if name == 'profile':
            values['身份'] = NOTICE + '沿用账号画像模块的人工确认结果；不自动替你确认身份。'
            values['核心方向'] = NOTICE + '依据已导入标题、正文和主题结构整理内容方向。'
            values['不确定信息'] = NOTICE + '无法判断真实粉丝画像、商业转化或因果关系。'
        elif name == 'insights':
            values['观察'] = NOTICE + (evidence or '数据不足，无法判断。')
            values['其他解释与限制'] = NOTICE + '累计互动受发布时间与曝光影响；相关性不代表因果。'
            values['待验证问题'] = NOTICE + '可对比同主题、同形式、相近发布时间的内容，核对样本是否足够。'
        elif name == 'issues':
            values['问题或假设'] = NOTICE + '优先核对缺失与缩略指标，避免把未确认数据当成精确值。'
            values['待核对内容'] = NOTICE + '在数据完整度和样本范围表中逐项确认。'
        elif name == 'strategies':
            values['做什么'] = NOTICE + '选择有足够样本的主题，制定可比较的内容实验。'
            values['怎么做'] = NOTICE + '保持主题与发布条件相近，分别测试标题表达与内容形式。'
            values['实验安排（建议）'] = NOTICE + '建议先小批量测试，积累可比样本后复盘。'
            values['复盘指标'] = NOTICE + '结合点赞、收藏、评论及样本范围判断，不承诺增长结果。'
        elif name == 'ideas':
            values['标题草稿'] = NOTICE + '从入门问题到实践步骤：一个可复用的内容框架'
            values['核心思路'] = NOTICE + '从已导入内容中选择读者常见问题，补充过程、证据与适用边界。'
            values['建议形式'] = NOTICE + '选择账号已有且样本充足的内容形式。'
        else:
            values['数据事实'] = NOTICE + (evidence or '数据不足，无法判断。')
            values['行动建议'] = NOTICE + '请使用主题比较、排行榜和数据完整度模块核对问题。'
            values['能力限制'] = NOTICE + '公开模式提供固定规则说明，不理解开放式问题，不调用付费服务。'
        note_ids = []
        if name == 'ideas':
            # 摘要仅提供已发送笔记的部分精确事实；不声称覆盖全账号排行榜。
            fact_values = {f.get('label', ''): f['value'] for f in facts}
            eligible = [(n, fact_values.get('笔记'+n['id']+'：点赞')) for n in summary.get('notes', [])]
            eligible = [(n, value) for n, value in eligible if isinstance(value, (int, float)) and value >= 0]
            eligible.sort(key=lambda item: item[1], reverse=True)
            note_ids = [n['id'] for n, _ in eligible[:2]]
            if note_ids:
                values['测试理由与复用方式'] = NOTICE + '参考本次已发送样本中精确点赞较高的笔记，人工核对标题表达与切入角度；未读取全文时不推断正文结构，也不代表全账号排行。'
        result[name] = [{'text': values, 'fact_ids': references, 'note_ids': note_ids, 'numbers': [], 'quotes': []}]
    validate_response(result, summary, question is not None)
    return {'result': result, 'summary': summary, 'version': request_version(summary, config),
            'model': '规则演示（非大模型）', 'returned_model': 'offline-rule-demo',
            'generated_at': datetime.now(timezone.utc).isoformat(), 'prompt_version': 'offline-demo-v1',
            'contract_version': CONTRACT_VERSION, 'app_version': 'V3-public',
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}}
