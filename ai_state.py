"""Plain, project-saveable AI drafts. Local human annotations are never modified."""
from copy import deepcopy
from datetime import datetime, timezone
from ai_contract import render_sections
from ai_summary import safe_text


def new_workspace(account_id):
    return {'account_id':account_id,'record':None,'edited':{},'accepted':None,'previous_accepted':None,
            'chat_version':'','chat':[],'archived_chat':[],'editor_epoch':0}


def install_result(workspace, record):
    workspace['record']=deepcopy(record)
    workspace['edited']=render_sections(record['result'],record['summary'])
    workspace['editor_epoch']+=1


def accept(workspace, version, edited):
    record=workspace.get('record')
    if not record or record['version']!=version: raise ValueError('旧样本草稿不能采纳到当前报告，请重新生成。')
    clean={k:safe_text(v,16000) for k,v in edited.items()}
    workspace['edited']=clean
    workspace['previous_accepted']=deepcopy(workspace.get('accepted'))
    workspace['accepted']={k:deepcopy(record[k]) for k in ['version','summary','model','returned_model','generated_at','prompt_version','contract_version','app_version','usage']}
    workspace['accepted'].update(sections=deepcopy(clean),accepted_at=datetime.now(timezone.utc).isoformat(),status='用户修改并采纳')


def undo_accept(workspace):
    workspace['accepted'],workspace['previous_accepted']=workspace.get('previous_accepted'),workspace.get('accepted')


def reopen_chat(workspace, version):
    workspace['archived_chat']=workspace['chat'][-8:]
    workspace['chat']=[]
    workspace['chat_version']=version


def append_chat(workspace, version, question, record):
    if workspace['chat_version']!=version: raise ValueError('数据版本变化，请先重开对话。')
    workspace['chat'].append({'version':version,'question':safe_text(question,1500),
                             'answer':render_sections(record['result'],record['summary'])['answer'],
                             'generated_at':record['generated_at'],'model':record['model'],'usage':record['usage']})
    workspace['chat']=workspace['chat'][-8:]


def export_ai(workspace, version, include_draft=False):
    result={}
    accepted=workspace.get('accepted')
    if accepted and accepted['version']==version: result['accepted']=deepcopy(accepted)
    record=workspace.get('record')
    if include_draft and record and record['version']==version:
        result['draft']={k:deepcopy(record[k]) for k in ['version','summary','model','returned_model','generated_at','prompt_version','contract_version','app_version','usage']}
        result['draft'].update(sections=deepcopy(workspace['edited']),status='未采纳草稿（独立附录）')
    return result
