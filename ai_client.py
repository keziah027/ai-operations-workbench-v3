"""Optional official SDK adapter. No request on import/configuration; no secret logging."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tomllib
from ai_contract import schema, validate_response, ResponseError, CONTRACT_VERSION
from ai_summary import safe_text
from prompts.analysis_prompts import SYSTEM_PROMPT, ANALYZE_PROMPT, CHAT_PROMPT, PROMPT_VERSION
from state_codec import fingerprint
from deployment import public_mode

MISSING='当前未配置大模型 API，AI 功能暂不可用，本地数据分析仍可正常使用。'


class AIError(Exception):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)


@dataclass
class AIConfig:
    api_key: str = field(default='',repr=False)
    model: str = 'gpt-4.1-mini'
    timeout: int = 60
    max_notes: int = 24
    body_chars: int = 500
    max_input_chars: int = 60000
    max_output_tokens: int = 6500
    history_turns: int = 4

    def public(self):
        return {k:v for k,v in asdict(self).items() if k!='api_key'}


def load_config(path=None, environ=None):
    if public_mode():
        return AIConfig(model='规则演示（非大模型）')
    env=os.environ if environ is None else environ
    path=Path(path) if path else Path(__file__).parent/'.streamlit'/'secrets.toml'
    try: data=tomllib.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    except (OSError,ValueError): raise AIError('config','AI 配置文件无法读取，请检查 secrets.toml 格式。本地分析仍可使用。') from None
    def get(name, default): return data.get(name,env.get(name,default))
    key=str(get('OPENAI_API_KEY','')).strip()
    if key.lower() in ['your-api-key','填入你的apikey','replace-me']: key=''
    model=str(get('OPENAI_MODEL','gpt-4.1-mini')).strip()
    if not model or len(model)>120: raise AIError('config','请填写有效的 OPENAI_MODEL。')
    limits={
        'timeout':('OPENAI_TIMEOUT',60,10,180), 'max_notes':('AI_MAX_NOTES',24,3,60),
        'body_chars':('AI_BODY_CHARS',500,0,1500), 'max_input_chars':('AI_MAX_INPUT_CHARS',60000,12000,180000),
        'max_output_tokens':('OPENAI_MAX_OUTPUT_TOKENS',6500,1000,16000), 'history_turns':('AI_HISTORY_TURNS',4,0,8)}
    values={}
    for field_name,(name,default,low,high) in limits.items():
        try: value=int(get(name,default))
        except (TypeError,ValueError): raise AIError('config',f'{name} 需要填写整数。') from None
        if not low<=value<=high: raise AIError('config',f'{name} 超出允许范围：{low}—{high}。')
        values[field_name]=value
    return AIConfig(api_key=key,model=model,**values)


def request_version(summary,config):
    return fingerprint([summary,config.public(),PROMPT_VERSION,CONTRACT_VERSION])


def ask_ai(summary, config, question=None, history=None, client_factory=None):
    if public_mode():
        from demo_ai import demo_response
        return demo_response(summary, config, question)
    if not config.api_key: raise AIError('missing',MISSING)
    chat=question is not None
    payload={'summary':summary}
    if chat:
        if not question.strip(): raise AIError('input','请先填写问题。')
        if len(question)>1500: raise AIError('input','问题请控制在1500字以内。')
        payload['question']=safe_text(question,1500)
        payload['history_untrusted']=[{'question':safe_text(h['question'],500),'answer':safe_text(h['answer'],1400)}
                                     for h in (history or [])[-config.history_turns:]] if config.history_turns else []
    serialized=json.dumps(payload,ensure_ascii=False)
    if len(serialized)+len(SYSTEM_PROMPT)>config.max_input_chars:
        raise AIError('input','摘要与对话超过输入上限，请重开对话、减少正文片段或缩小日期范围。未发送请求。')
    try:
        import openai
    except ImportError: raise AIError('sdk','尚未安装 AI 依赖，请重新运行 install.cmd。本地分析仍可使用。') from None
    try:
        # Disable SDK automatic retries: one click, at most one attempt; user can retry explicitly.
        factory=client_factory or openai.OpenAI
        with factory(api_key=config.api_key,base_url='https://api.openai.com/v1',timeout=config.timeout,max_retries=0) as client:
            response=client.responses.create(model=config.model,store=False,
                instructions=SYSTEM_PROMPT+'\n'+(CHAT_PROMPT if chat else ANALYZE_PROMPT),
                input=[{'role':'user','content':serialized}],
                text={'format':{'type':'json_schema','name':'operations_answer' if chat else 'operations_analysis',
                                'strict':True,'schema':schema(chat)}},max_output_tokens=config.max_output_tokens)
        if response.status!='completed': raise AIError('incomplete','模型未完成输出或输出达到上限，上一份结果已保留；可主动重试。')
        result=validate_response(response.output_text,summary,chat)
        usage=getattr(response,'usage',None)
        return {'result':result,'summary':summary,'version':request_version(summary,config),
                'model':config.model,'returned_model':str(getattr(response,'model',config.model)),
                'generated_at':datetime.now(timezone.utc).isoformat(),'prompt_version':PROMPT_VERSION,
                'contract_version':CONTRACT_VERSION,'app_version':'V3',
                'usage':{k:getattr(usage,k,None) for k in ['input_tokens','output_tokens','total_tokens']} if usage else None}
    except AIError: raise
    except ResponseError as exc: raise AIError('structure',str(exc)+' 该响应未采用，上一份有效结果已保留。') from None
    except openai.AuthenticationError: raise AIError('auth','API 认证失败，请在本机检查密钥。') from None
    except openai.PermissionDeniedError: raise AIError('permission','当前 API 项目没有访问权限，请核对项目与模型权限。') from None
    except openai.RateLimitError as exc:
        code=getattr(exc,'code','')
        if code in ['insufficient_quota','billing_hard_limit_reached']:
            raise AIError('quota','API 额度不足，请核对 API 项目的余额或用量上限。') from None
        raise AIError('rate_limit','请求受到限流，请稍后主动重试。') from None
    except openai.APITimeoutError: raise AIError('timeout','请求超时，未自动重试；上一份有效结果已保留。') from None
    except openai.APIConnectionError: raise AIError('network','无法连接 API，请检查网络；本地功能仍可使用。') from None
    except openai.APIStatusError as exc:
        if exc.status_code==402: raise AIError('quota','API 额度或付款状态异常，请核对 API 项目。') from None
        raise AIError('service','API 暂未接受请求，请检查模型与结构化输出支持，或稍后主动重试。') from None
    except Exception: raise AIError('unexpected','AI 调用未完成，上一份有效结果已保留。请检查依赖与配置后重试。') from None
