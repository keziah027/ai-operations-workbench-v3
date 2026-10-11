"""人工包装类型与辅助标签；不推断图像内容。"""
from copy import deepcopy
import re
import pandas as pd

DEFAULT_COVERS=['待标注','产品主体','使用场景','人物/角色','拼贴合集','文字信息','其他','知识卡片','截图/对话','人物口播','实拍场景']
BODY_TYPES=['待标注','问题—方法','观点—论据','经历—复盘','步骤清单','其他']

def tags(value):
    return list(dict.fromkeys(part.strip() for part in re.split('[,，、;；]',value or '') if part.strip()))

def setup_packaging(state):
    state.setdefault('packaging',{'cover_types':list(DEFAULT_COVERS)})
    choices=state['packaging']['cover_types']
    for row in state['annotations']:
        cover=row.get('封面类型') or '待标注'
        if cover not in choices: choices.append(cover)
        row['封面类型']=cover
        row.setdefault('封面辅助标签','')
        row.setdefault('辅助标签已复核',False)
        row.setdefault('正文结构（人工）','待标注')
    return state

def change_cover_type(state, action, old='', name='', replacement=''):
    result=setup_packaging(deepcopy(state))
    choices=result['packaging']['cover_types']; name=name.strip()
    if action in ['add','rename'] and (not name or len(name)>40 or name in choices):
        raise ValueError('请输入未使用的1—40字类型名称。')
    if action!='add' and (old not in choices or old=='待标注'): raise ValueError('请选择有效类型，“待标注”不能改名或删除。')
    if action=='add': choices.append(name)
    elif action=='rename':
        choices[choices.index(old)]=name
        for row in result['annotations']:
            if row['封面类型']==old: row['封面类型']=name
    elif action=='delete':
        if any(row['封面类型']==old for row in result['annotations']) and (replacement not in choices or replacement==old):
            raise ValueError('此类型正在使用，请明确选择替代类型或“待标注”。')
        choices.remove(old)
        for row in result['annotations']:
            if row['封面类型']==old: row['封面类型']=replacement
    else: raise ValueError('未知包装操作。')
    result['revision']+=1
    return result

def packaging_tables(frame):
    covers=frame[frame['封面类型'].fillna('待标注').ne('待标注')]['封面类型'].value_counts().rename_axis('主封面类型').reset_index(name='篇数')
    covers['占已标注封面（%）']=covers['篇数']/max(1,covers['篇数'].sum())*100
    reviewed=frame[frame.get('辅助标签已复核',pd.Series(False,index=frame.index)).eq(True)]
    all_tags=list(dict.fromkeys(tag for value in reviewed.get('封面辅助标签',[]) for tag in tags(value)))
    auxiliary=pd.DataFrame([{'辅助标签':tag,'命中篇数':sum(tag in tags(value) for value in reviewed['封面辅助标签']),
                              '已复核篇数':len(reviewed),'占已复核（%）':100*sum(tag in tags(value) for value in reviewed['封面辅助标签'])/len(reviewed)} for tag in all_tags])
    return {'主封面类型分布':covers,'封面辅助标签（可重叠）':auxiliary}
