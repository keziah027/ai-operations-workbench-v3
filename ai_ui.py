"""A single optional sixth tab shared by all existing data-entry paths."""
from copy import deepcopy
import json
import streamlit as st
from ai_client import load_config, AIConfig, AIError, MISSING, ask_ai, request_version
from ai_summary import build_summary
from ai_contract import SECTIONS, render_sections, validate_response, ResponseError
from ai_state import new_workspace,install_result,accept,undo_accept,reopen_chat,append_chat,export_ai
from state_codec import fingerprint
from project_state import account_identity
from note_schema import publication_dates
from deployment import public_mode


def workspace_key(snapshot): return 'ai-workspace-'+fingerprint(account_identity(snapshot))[:20]


def render_ai(snapshot, analysis, key):
    st.write('**AI运营助手 · 草稿需核对后采纳**')
    demo = public_mode()
    st.caption('公开演示：由本地规则生成带证据引用的示例草稿，不是大模型推理；数据不发送到AI服务，API费用为零。' if demo else '本地统计由程序计算。AI只解释本次证据；上传、切换模块、修改标注和打开存档都不会自动调用。')
    try: config=load_config(); config_error=''
    except AIError as exc: config=AIConfig(); config_error=str(exc)
    if config_error: st.error(config_error)
    elif demo: st.info('可体验生成、编辑、采纳、问答示例与报告导出的完整流程。开放式问答能力仅在私有本地模式配置API后启用。')
    elif not config.api_key: st.info(MISSING)
    else: st.caption('已检测到本机密钥配置；尚未验证服务是否可用。')
    allowed=(demo or bool(config.api_key)) and not config_error
    store_key=workspace_key(snapshot)
    account_id=fingerprint(account_identity(snapshot))[:20]
    if store_key not in st.session_state:
        st.session_state[store_key]=new_workspace(account_id)
    workspace=st.session_state[store_key]
    options=workspace.setdefault('options',{})
    dates=publication_dates(analysis['detail']['发布时间']).dropna()
    with st.expander('本次分析范围与内容（演示不发送）' if demo else '本次发送范围与内容',expanded=True):
        st.caption('演示摘要仅在本会话中用于规则输出，不向外部AI服务发送。' if demo else '发送：来源与范围、程序统计、主题与形式、当前身份/领域/确认目标、账号简介、抽样标题和正文片段。不发送原始Excel、登录资料或原始链接。')
        private=st.checkbox('摘要纳入我的定位、人群和诊断补充（演示不发送）' if demo else '同时发送我的定位、人群和诊断补充（内部备注）',value=options.get('private',False),key=f'ai-private-{key}')
        body=st.checkbox('包含已读取的正文片段',value=options.get('body',True),key=f'ai-body-{key}')
        options.update(private=private,body=body)
        date_range=None
        if len(dates):
            filtering=st.checkbox('按首发日期筛选AI样本',value=options.get('filtering',False),key=f'ai-filter-{key}')
            options['filtering']=filtering
            if filtering:
                from datetime import date
                default_dates=tuple(date.fromisoformat(d) for d in options['dates']) if options.get('dates') else (dates.min().date(),dates.max().date())
                chosen=st.date_input('AI样本首发日期范围',value=default_dates,key=f'ai-dates-{key}')
                if not isinstance(chosen,(tuple,list)) or len(chosen)!=2:
                    st.info('请选齐开始与结束日期。'); return {}
                date_range=chosen
                options['dates']=[d.isoformat() for d in chosen]
        try:
            summary=build_summary(snapshot,analysis,max_notes=config.max_notes,body_chars=config.body_chars if body else 0,
                                  max_chars=max(6000,config.max_input_chars-11000),include_private=private,date_range=date_range)
        except (ValueError,TypeError,KeyError):
            st.warning('当前范围无法生成AI摘要，请核对日期范围与数据；本地模块仍可使用。'); return {}
        sample=summary['sampling']
        st.write(f"统计 {summary['total_notes']} 篇；{'分析' if demo else '发送'}文本 {sample['text_sample_count']} 篇，其中正文 {sample['body_count']} 篇。")
        st.caption(f"文本抽样：{'是' if sample['sampled'] else '否'}；文本截断：{'是' if sample['text_truncated'] else '否'}；未纳入统计事实：{sample['omitted_facts']} 条。模式：{config.model}。" + ('演示不产生API费用。' if demo else '费用以API实际账单为准。'))
        if not summary['notes']: st.warning('当前上限下没有可发送的文本样本，只能解释保留的统计事实；可缩小范围后再生成。')
        if len(summary['notes'])<3: st.info('文本样本较少，定位与选题只能作为初步假设；可能无法形成建议。')
        with st.expander('查看演示摘要（编号可用于核对）' if demo else '查看实际发送摘要（编号可用于核对）'):
            st.json(summary,expanded=False)
        st.caption('藏赞比=收藏÷点赞；评赞比=评论÷点赞。缺失或缩略数字不进入精确统计；累计表现不是每日新增。')
    version=request_version(summary,config)
    st.caption('当前数据与配置版本：'+version[:12])
    record=workspace.get('record')
    stale=bool(record and record['version']!=version)
    if stale: st.warning('数据、人工修订或配置已变化：旧AI结果已过期。请点击重新生成；旧结果不会进入当前正式报告。')
    if workspace.get('accepted') and workspace['accepted']['version']!=version:
        st.info('此前采纳的结论属于旧版本，本次导出不包含它。')
    busy_key='ai-busy-'+account_id
    if st.button('重新生成AI分析' if record else '生成AI分析',key=f'ai-generate-{key}',disabled=not allowed or st.session_state.get(busy_key,False)):
        st.session_state[busy_key]=True
        try:
            with st.spinner('正在生成并校验AI草稿，请勿重复点击…'):
                new_record=ask_ai(summary,config)
                install_result(workspace,new_record)
            st.session_state.pop('ai-error-'+account_id,None)
        except AIError as exc: st.session_state['ai-error-'+account_id]=str(exc)
        finally: st.session_state[busy_key]=False
        st.rerun()
    if st.session_state.get('ai-error-'+account_id): st.error(st.session_state['ai-error-'+account_id])
    record=workspace.get('record')
    if record:
        try: validate_response(record['result'],record['summary'])
        except (ResponseError,KeyError,TypeError):
            st.error('保存的AI草稿未通过校验，请重新生成。'); return {}
        st.caption(f"草稿生成：{record['generated_at']} · 模型 {record['model']} · 版本 {record['version'][:12]} · 提示词 {record['prompt_version']}")
        if demo: st.caption('本次由规则生成，没有API请求，用量与费用均为零。')
        elif record.get('usage'): st.caption('本次API返回用量：'+json.dumps(record['usage'],ensure_ascii=False)+'；费用未知。')
        else: st.caption('本次用量未知；未估算费用。')
        if stale:
            with st.expander('查看旧版本草稿（仅供核对）'):
                for section,text in workspace['edited'].items(): st.write(SECTIONS[section][0]); st.text(text)
        else:
            st.caption('下方文字可编辑。点击“保存编辑并采纳”后进入报告；不会改写前五模块的人工定位或标注。')
            with st.form(f'ai-edit-{key}-{workspace["editor_epoch"]}'):
                edited={}
                for section in record['result']:
                    edited[section]=st.text_area(SECTIONS[section][0],value=workspace['edited'].get(section,''),height=220,max_chars=16000,
                                                 key=f'ai-text-{key}-{workspace["editor_epoch"]}-{section}')
                save_draft=st.form_submit_button('保存草稿修改（不采纳）')
                adopt=st.form_submit_button('保存编辑并采纳')
            if save_draft or adopt:
                if adopt: accept(workspace,version,edited)
                else:
                    from ai_summary import safe_text
                    workspace['edited']={k:safe_text(v,16000) for k,v in edited.items()}
                st.rerun()
            left,right=st.columns(2)
            if left.button('恢复本次AI原稿',key=f'ai-reset-{key}'):
                workspace['edited']=render_sections(record['result'],record['summary']); workspace['editor_epoch']+=1; st.rerun()
            if right.button('撤销/恢复上次采纳',key=f'ai-undo-{key}',disabled=not workspace.get('accepted') and not workspace.get('previous_accepted')):
                undo_accept(workspace); st.rerun()
        accepted=workspace.get('accepted')
        if accepted and accepted['version']==version:
            st.success('已有当前版本的采纳结论，正式报告使用下面这份结果。后续草稿修改需再次采纳才生效。')
            with st.expander('查看正式报告采用的AI结论'):
                for section,text in accepted['sections'].items(): st.write(SECTIONS[section][0]); st.text(text)
        with st.expander('查看本份草稿的统计事实与笔记原文'):
            st.dataframe(record['summary']['facts'],hide_index=True,width='stretch')
            st.dataframe(record['summary']['notes'],hide_index=True,width='stretch')
    include=st.checkbox('导出时附上未采纳草稿（独立附录）',value=False,key=f'ai-appendix-{key}',disabled=not record or stale)
    st.divider()
    st.write('**基于当前数据提问**')
    st.caption('演示问答返回固定规则说明与当前统计事实，不理解自由提问。' if demo else '只在点击发送时调用；最多保留当前八轮，发送最近配置轮数的截取文本。AI历史回答不作为新证据。没有支持的统计函数时会说明限制。')
    if not workspace['chat_version']: workspace['chat_version']=version
    chat_stale=workspace['chat_version']!=version
    if chat_stale: st.warning('旧对话基于旧样本或配置。请先重开当前数据对话，再继续提问。')
    if st.button('重开当前数据对话',key=f'ai-chat-reset-{key}'):
        reopen_chat(workspace,version); st.rerun()
    for item in workspace['chat']:
        with st.chat_message('user'): st.text(item['question'])
        with st.chat_message('assistant'): st.text(item['answer'])
    if workspace['archived_chat']:
        with st.expander('上一次对话（历史，不作为当前证据）'):
            for item in workspace['archived_chat']: st.text(item['question']+'\n'+item['answer'])
    with st.form(f'ai-question-{key}',clear_on_submit=False):
        question=st.text_input('向AI提问',max_chars=1500,placeholder='例如：哪类选题值得继续测试？')
        send=st.form_submit_button('发送问题',disabled=not allowed or chat_stale or st.session_state.get(busy_key,False))
    if send:
        st.session_state[busy_key]=True
        try:
            with st.spinner('正在根据当前证据回答…'):
                answer=ask_ai(summary,config,question,workspace['chat'])
                append_chat(workspace,version,question,answer)
            st.session_state.pop('ai-chat-error-'+account_id,None)
        except AIError as exc: st.session_state['ai-chat-error-'+account_id]=str(exc)
        finally: st.session_state[busy_key]=False
        st.rerun()
    if st.session_state.get('ai-chat-error-'+account_id): st.error(st.session_state['ai-chat-error-'+account_id])
    if not demo and workspace['chat'] and workspace['chat'][-1].get('usage'):
        st.caption('最近问答返回用量：'+json.dumps(workspace['chat'][-1]['usage'])+'；费用未知。')
    return export_ai(workspace,version,include and not stale)
