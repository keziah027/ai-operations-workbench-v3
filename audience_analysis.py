"""人群与需求候选：只描述明确文本，保留来源、否定与自述边界。"""
import re
import pandas as pd
from note_identity import evidence_id,digest
from dynamic_topics import OTHER
from note_schema import content_text

COLUMNS=['假设ID','假设类别','自动假设','最终假设','证据来源','原文依据','命中笔记数','有效文本样本数',
         '例证笔记标识/链接','待验证问题','状态','关键词依据','潜在人群（待验证）']
PEOPLE=r'刚入职的新人|职场新人|应届生|新手妈妈|新手|初学者|独居者|上班族|设计师|自由职业者|学生|宝妈|新人'

def extract_evidence(value):
    result=[]
    for fragment in re.split(r'[。！？!？\n；;]',content_text(value)):
        if not fragment.strip(): continue
        for match in re.finditer(r'(?:帮助|面向|适合|写给|推荐给|献给|给|致|如果你是|为)\s*('+PEOPLE+')',fragment):
            prefix=fragment[max(0,match.start()-8):match.start()]
            if re.search(r'不|并非|不是|别',prefix): continue
            if re.search(r'学生时代|当年|那时|曾经',fragment[:match.end()]): continue
            result.append(('明确面向人群',match[1],fragment.strip()[:200]))
        for match in re.finditer(r'(?:如何|怎样|怎么|解决|避免|摆脱|改善|学会)([^，,。！？!?；;]{2,28})',fragment):
            if re.search(r'不(?:要|必|用)?$',fragment[max(0,match.start()-4):match.start()]): continue
            result.append(('问题/需求候选',match.group(0).strip(),fragment.strip()[:200]))
        for match in re.finditer(r'通勤(?:途中)?|下班后|睡前|独居(?:时)?|在办公室|在家|面试时|周末|上班时|到店时',fragment):
            if re.search(r'不是|并非|不在',fragment[max(0,match.start()-5):match.start()]): continue
            result.append(('使用/生活场景',match.group(0),fragment.strip()[:200]))
    return list(dict.fromkeys(result))

def audience_candidates(frame,bio):
    unique={}
    for index,note in enumerate(frame.to_dict('records')):
        identity=evidence_id(note,index)
        old=unique.get(identity)
        if old is None or len(str(note.get('正文','')))>len(str(old.get('正文',''))): unique[identity]=note
    documents={identity:content_text(note.get('标题'))+'\n'+content_text(note.get('正文')) for identity,note in unique.items()}
    available=sum(bool(value.strip()) for value in documents.values())
    groups={}
    def add(category,phrase,proof,source,identity=None,link=''):
        key=(category,phrase)
        group=groups.setdefault(key,{'proof':[],'source':set(),'notes':set(),'examples':[]})
        if proof not in group['proof']: group['proof'].append(proof)
        group['source'].add(source)
        if identity:
            group['notes'].add(identity)
            entry=identity+((' '+link) if link else '')
            if entry not in group['examples']: group['examples'].append(entry)
    for category,phrase,proof in extract_evidence(bio): add(category,phrase,proof,'简介（账号自述面向，未验证）')
    for identity,value in documents.items():
        for category,phrase,proof in extract_evidence(value):
            add(category,phrase,proof,'笔记',identity,str(unique[identity].get('笔记链接') or ''))
    for identity,note in unique.items():
        pillar=note.get('主支柱','')
        if pillar and pillar not in [OTHER,'其他','待判定']:
            add('主题兴趣线索',f'关注「{pillar}」的内容需求',f'来自当前内容支柱：{pillar}；弱线索，并非粉丝画像','笔记最终分类',identity,str(note.get('笔记链接') or ''))
    rows=[]
    for (category,phrase),group in groups.items():
        question='哪些实际读者有这个需求？可用评论、访谈或后台受众资料核对，不能据内容推断真实粉丝画像。'
        rows.append({'假设ID':'aud-'+digest(category+'|'+phrase),'假设类别':category,'自动假设':phrase,'最终假设':phrase,
                     '证据来源':'、'.join(sorted(group['source'])),'原文依据':'；'.join(group['proof'][:5]),
                     '命中笔记数':len(group['notes']),'有效文本样本数':available,'例证笔记标识/链接':'；'.join(group['examples'][:5]),
                     '待验证问题':question,'状态':'候选待验证','关键词依据':'；'.join(group['proof'][:5]),'潜在人群（待验证）':phrase})
    return pd.DataFrame(rows,columns=COLUMNS)

def final_audience(automatic,overrides):
    rows=[]
    seen=set()
    for record in automatic.to_dict('records'):
        identity=record['假设ID']; seen.add(identity)
        record.update(overrides.get(identity,{}))
        record['潜在人群（待验证）']=record['最终假设']
        rows.append(record)
    for identity,manual in overrides.items():
        if identity not in seen and manual.get('证据来源')=='人工填写':
            rows.append({**dict.fromkeys(COLUMNS,''),**manual,'假设ID':identity,'命中笔记数':0,
                         '有效文本样本数':0,'潜在人群（待验证）':manual.get('最终假设','')})
    return pd.DataFrame(rows,columns=COLUMNS)
