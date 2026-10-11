"""Strict response structure and evidence checks; model prose never supplies statistics."""
import json
import re

CONTRACT_VERSION='v3-contract-1'
SECTIONS={
    'profile':('账号识别与定位',1, ['身份','主领域','次领域','核心方向','表达风格','内容价值','人群假设','定位草稿','证据强度','不确定信息']),
    'insights':('关键数据洞察',5,['观察','可能含义','其他解释与限制','待验证问题']),
    'issues':('运营问题诊断',4,['问题或假设','影响范围','优先级与理由','待核对内容']),
    'strategies':('下一阶段策略',5,['做什么','为什么','怎么做','实验安排（建议）','复盘指标','实施条件与限制']),
    'ideas':('测试选题建议',5,['标题草稿','建议形式','所属主题或新方向','核心思路','测试理由与复用方式','观察指标']),
    'answer':('运营问答',1,['数据事实','解释假设','行动建议','能力限制']),
}


class ResponseError(ValueError): pass


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def schema(chat=False):
    string={'type':'string','maxLength':1000}
    reference=obj({'fact_id':{'type':'string'},'value':{'type':'number'},'unit':{'type':'string'}})
    quote=obj({'note_id':{'type':'string'},'field':{'type':'string','enum':['title','body']},'quote':{'type':'string','minLength':1,'maxLength':300}})
    result={}
    for name,(_,limit,fields) in SECTIONS.items():
        if (name=='answer')!=chat: continue
        card=obj({'text':obj({field:string for field in fields}),
                  'fact_ids':{'type':'array','items':{'type':'string'},'maxItems':8},
                  'note_ids':{'type':'array','items':{'type':'string'},'maxItems':8},
                  'numbers':{'type':'array','items':reference,'maxItems':8},
                  'quotes':{'type':'array','items':quote,'maxItems':4}})
        result[name]={'type':'array','items':card,'maxItems':limit}
    return obj(result)


def validate_shape(value, spec):
    kind=spec['type']
    if kind=='object':
        if not isinstance(value,dict) or set(value)!=set(spec['required']): raise ResponseError('响应缺少字段或包含未知字段。')
        for k,v in value.items(): validate_shape(v,spec['properties'][k])
    elif kind=='array':
        if not isinstance(value,list) or len(value)>spec.get('maxItems',100): raise ResponseError('响应数量超出限制。')
        for item in value: validate_shape(item,spec['items'])
    elif kind=='string':
        if not isinstance(value,str) or not spec.get('minLength',0)<=len(value)<=spec.get('maxLength',1000): raise ResponseError('响应文字格式不正确。')
        if 'enum' in spec and value not in spec['enum']: raise ResponseError('响应选项无效。')
    elif kind=='number':
        if isinstance(value,bool) or not isinstance(value,(int,float)): raise ResponseError('响应数字格式不正确。')


def validate_response(value, summary, chat=False):
    if isinstance(value,str):
        if len(value)>120000: raise ResponseError('响应过长。')
        try: value=json.loads(value)
        except (ValueError,TypeError): raise ResponseError('响应不是有效的结构化内容。') from None
    validate_shape(value,schema(chat))
    facts={f['id']:f for f in summary['facts']}; notes={n['id']:n for n in summary['notes']}
    if summary.get('bio'): notes[summary['bio_id']]={'title':'账号简介','body':summary['bio']}
    for section,cards in value.items():
        for card in cards:
            if not set(card['fact_ids'])<=facts.keys() or not set(card['note_ids'])<=notes.keys():
                raise ResponseError('引用了本次未发送的事实或笔记。')
            for number in card['numbers']:
                source=facts.get(number['fact_id'])
                if not source or number['fact_id'] not in card['fact_ids'] or number['value']!=source['value'] or number['unit']!=source['unit']:
                    raise ResponseError('引用数字或单位与程序计算不一致。')
            for quote in card['quotes']:
                note=notes.get(quote['note_id'])
                if not note or quote['note_id'] not in card['note_ids'] or quote['quote'] not in note[quote['field']]:
                    raise ResponseError('证据摘录不在所引用笔记的已发送片段中。')
            for field,content in card['text'].items():
                tokens=re.findall(r'\{\{(F[a-f0-9]+)\}\}',content)
                if any(token not in card['fact_ids'] for token in tokens): raise ResponseError('文字中的数字占位引用无效。')
                if re.search(r'\}\}\s*(?:%|％|万|千|百|倍|元|人|次|篇|百分点)|百分之\s*\{\{',content):
                    raise ResponseError('事实占位符已包含原始单位，不能自行修改单位。')
                remainder=re.sub(r'\{\{F[a-f0-9]+\}\}','',content)
                # All observed numeric quantities must be rendered from facts. Experimental schedules
                # and proposed titles are the only numeric prose exceptions; explicitly suggestions.
                if field not in ['实验安排（建议）','标题草稿']:
                    if re.search(r'\d|[零一二三四五六七八九十百千万两]+\s*(?:%|％|篇|次|人|倍|万|元|成|天|周|个月)',remainder):
                        raise ResponseError('统计数字必须通过事实编号呈现，不能由模型直接写入结论。')
                if '收藏率' in content or '评论率' in content: raise ResponseError('应使用藏赞比、评赞比，并保留正确分母。')
            if not card['fact_ids'] and not card['note_ids'] and not any('不足' in s or '无法判断' in s for s in card['text'].values()):
                raise ResponseError('结论缺少可复核证据或数据不足说明。')
            if section=='insights' and not card['fact_ids'] and not any('不足' in s or '无法判断' in s for s in card['text'].values()):
                raise ResponseError('数据洞察缺少统计事实引用。')
    if not any(value.values()): raise ResponseError('响应没有可用内容。')
    return value


def render_sections(result, summary):
    facts={f['id']:f for f in summary['facts']}
    def replace(match):
        f=facts[match.group(1)]
        return f"{f['value']} {f['unit']}〔{f['id']}〕"
    rendered={}
    for section,cards in result.items():
        lines=[]
        for i,card in enumerate(cards,1):
            lines.append(f'【{i}】')
            for field,content in card['text'].items():
                lines.append(field+'：'+re.sub(r'\{\{(F[a-f0-9]+)\}\}',replace,content))
            lines.append('证据：'+'、'.join(card['fact_ids']+card['note_ids']))
            for item in card['quotes']: lines.append('原文摘录：'+item['quote']+'〔'+item['note_id']+'〕')
        rendered[section]='\n\n'.join(lines) or '当前数据不足，暂无法判断。'
    return rendered
