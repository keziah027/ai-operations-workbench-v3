"""把当前已采纳的选题文字转为可回填的选题池，不请求 AI、不改变输出契约。"""
import hashlib
import re
import pandas as pd

IDEA_FIELDS = ['标题草稿','建议形式','所属主题或新方向','核心思路','观察指标']
IDEA_COLUMNS = ['序号','选题编号',*IDEA_FIELDS,'采纳选题原文']


def adopted_idea_pool(bundle):
    accepted = bundle.get('accepted') or {}
    text = (accepted.get('sections') or {}).get('ideas', '')
    if not isinstance(text,str) or not text.strip() or text.strip()=='当前数据不足，暂无法判断。':
        return pd.DataFrame(columns=IDEA_COLUMNS)
    # 当前应用保存的是用户编辑并采纳后的段落，不能导出已被修改的旧模型草稿。
    cards = [s.strip() for s in re.split(r'(?m)^【\d+】\s*$',text) if s.strip()]
    labels = [*IDEA_FIELDS,'测试理由与复用方式','证据','原文摘录']
    pattern = r'(?m)^(?:'+'|'.join(re.escape(f) for f in labels)+r')[:：]'
    rows=[]
    for position,card in enumerate(cards,1):
        row={field:'' for field in IDEA_FIELDS}
        markers=list(re.finditer(pattern,card))
        for i,match in enumerate(markers):
            field=match.group(0)[:-1]
            if field in row:
                end=markers[i+1].start() if i+1<len(markers) else len(card)
                value=card[match.end():end].strip()
                row[field] = (row[field]+'\n'+value).strip() if row[field] else value
        if not any(row.values()):
            row['核心思路']=card  # 自由编辑的文字完整保留，不伪造缺失的结构字段。
        identity='|'.join([str(accepted.get('summary',{}).get('account_id','')),str(accepted.get('version','')),
                           str(accepted.get('accepted_at','')),str(position),card])
        row.update(序号=position,选题编号='XT-'+hashlib.sha256(identity.encode()).hexdigest()[:12],采纳选题原文=card)
        rows.append(row)
    return pd.DataFrame(rows,columns=IDEA_COLUMNS)
