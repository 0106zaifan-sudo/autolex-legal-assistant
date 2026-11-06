"""复用官方SDK；默认路径在可终止子进程中执行，密钥只走内存。"""
from __future__ import annotations
import json
import logging
import multiprocessing
import time
from ai_providers import get_provider
from openai import (OpenAI, AuthenticationError, RateLimitError, APITimeoutError,
                    APIConnectionError, APIStatusError)

MAX_RESULT_BYTES=512000


class ModelRuntimeError(ValueError):
    def __init__(self, code, metadata=None):
        self.code=code
        self.metadata=metadata or {}
        super().__init__(code)


def call_sdk(api_key, request, client_factory=OpenAI, *, provider='openai'):
    spec=get_provider(provider)
    try:
        with client_factory(api_key=api_key,base_url=spec.base_url,timeout=30.0,max_retries=0) as client:
            # create保留响应元数据，再在父进程做Schema/引证验证；解析失败也不丢usage。
            response=client.responses.create(**request)
        usage=response.usage.model_dump(mode='json',exclude_none=True) if response.usage else None
        refused=any(getattr(content,'type',None)=='refusal' for output in response.output
                    for content in getattr(output,'content',[]))
        return {'provider_status':response.status,'provider_model':response.model,
                'provider_response_id':response.id,'token_usage':usage,
                'output_text':response.output_text,'refused':refused,
                'call_status':'response_received'}
    except AuthenticationError:
        return {'error_code':'authentication_failed','http_status':401,'call_status':'http_error'}
    except RateLimitError:
        return {'error_code':'rate_limited','http_status':429,'call_status':'http_error'}
    except APITimeoutError:
        return {'error_code':'network_timeout','call_status':'transport_error'}
    except APIConnectionError:
        return {'error_code':'connection_failed','call_status':'transport_error'}
    except APIStatusError as exc:
        return {'error_code':'provider_error','http_status':exc.status_code,'call_status':'http_error'}
    except Exception:
        return {'error_code':'sdk_error','call_status':'unknown'}


def _sdk_worker(connection, api_key, request, provider='openai'):
    try:
        for logger in ('openai','httpx','httpcore'):
            logging.getLogger(logger).setLevel(logging.WARNING)
        result=call_sdk(api_key,request,provider=provider)
        encoded=json.dumps(result,ensure_ascii=False).encode()
        if len(encoded)>MAX_RESULT_BYTES:
            result.pop('output_text',None)
            result['error_code']='response_too_large'
            encoded=json.dumps(result,ensure_ascii=False).encode()
        connection.send_bytes(encoded)
    except Exception:
        # 不传异常文本、请求头、API密钥或调试回溯。
        try:connection.send_bytes(b'{"error_code":"worker_failed","call_status":"unknown"}')
        except Exception:pass
    finally:
        connection.close()


def run_process(target,args,timeout):
    context=multiprocessing.get_context('spawn')
    parent,child=context.Pipe(duplex=False)
    process=context.Process(target=target,args=(child,*args),daemon=True)
    deadline=time.monotonic()+timeout
    try:
        process.start()
        child.close()
        remaining=max(0,deadline-time.monotonic())
        if not parent.poll(remaining):
            raise ModelRuntimeError('deadline_exceeded',{'call_status':'unknown','token_usage':None})
        result=json.loads(parent.recv_bytes(MAX_RESULT_BYTES).decode())
        if not isinstance(result,dict):
            raise ValueError('invalid_worker_result')
        return result
    except ModelRuntimeError:
        raise
    except Exception:
        raise ModelRuntimeError('worker_failed',{'call_status':'unknown','token_usage':None}) from None
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill();process.join(timeout=1)
        parent.close();child.close()


def invoke(api_key,request,timeout,client_factory=None,*,provider='openai'):
    get_provider(provider)
    if client_factory is not None:
        # 仅给现有离线HTTP mock注入测试使用，不作为真实调用的截止保证。
        return call_sdk(api_key,request,client_factory,provider=provider)
    return run_process(_sdk_worker,(api_key,request,provider),timeout)
