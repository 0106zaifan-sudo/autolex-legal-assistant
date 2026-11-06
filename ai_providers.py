"""固定官方端点的服务商适配；不接受任意URL，不跨服务商回退凭据。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    base_url: str
    key_name: str
    model_name: str
    default_model: str


PROVIDERS = {
    'openai': Provider('openai', 'OpenAI', 'https://api.openai.com/v1',
                       'OPENAI_API_KEY', 'OPENAI_MODEL', 'gpt-4.1-mini'),
    'deepseek': Provider('deepseek', 'DeepSeek', 'https://api.deepseek.com',
                         'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'deepseek-flash'),
}


def get_provider(name):
    if name not in PROVIDERS:
        raise ValueError('AI_PROVIDER 必须为 openai 或 deepseek')
    return PROVIDERS[name]


def adapt_request(request, provider):
    """DeepSeek官方Responses文档核对于2026-11-06；本地校验不依赖服务端strict。"""
    get_provider(provider)
    if provider == 'deepseek':
        request.pop('store', None)  # 官方无状态接口；此参数不支持
        request.pop('truncation', None)  # 超窗返回400，本地预算仍生效
        request['text']['format'].pop('strict', None)  # 官方此格式未列出strict
        request['reasoning'] = {'effort': 'none'}  # 明确关闭默认思考，避免占用输出预算
    return request


def codespaces_values(values, environment):
    """仅在Codespaces导入所选服务商的环境Secret；普通环境不自动回退。"""
    values = dict(values)
    provider = get_provider(str(values.get('AI_PROVIDER', 'openai')))
    if environment.get('CODESPACES') == 'true' and not values.get(provider.key_name):
        values[provider.key_name] = environment.get(provider.key_name, '')
    return values


def billing_record(usage):
    """token不是账单。保留缓存/推理明细，不猜费率、折扣或超时账单。"""
    usage = usage if isinstance(usage, dict) else {}
    def count(value):
        return value if type(value) is int and value >= 0 else None
    def detail(name, key):
        value = usage.get(name)
        return count(value.get(key)) if isinstance(value, dict) else None
    cached = detail('input_tokens_details', 'cached_tokens')
    input_tokens = count(usage.get('input_tokens'))
    uncached = input_tokens - cached if input_tokens is not None and cached is not None and cached <= input_tokens else None
    return {'input_tokens': input_tokens, 'cached_input_tokens': cached,
            'uncached_input_tokens': uncached, 'output_tokens': count(usage.get('output_tokens')),
            'reasoning_tokens': detail('output_tokens_details', 'reasoning_tokens'),
            'total_tokens': count(usage.get('total_tokens')),
            'amount': None, 'currency': None, 'status': 'not_reconciled',
            'note': '仅记录服务商返回的token；金额需核对服务商账单，未收到响应也可能计费。'}
