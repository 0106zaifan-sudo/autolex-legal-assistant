"""默认仅准备。真实调用须显式开关、Secrets文件及交互密码，最多两份固定模拟材料。"""
import argparse
import getpass
from pathlib import Path
import os
import sys
import tomllib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_acceptance import preparation_report,write_report,run_suite,AcceptanceError,ROOT
from security import Settings,QuotaStore,SecurityError,verify_password
from ai_providers import codespaces_values


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-live',action='store_true')
    parser.add_argument('--confirm-paid-calls',action='store_true')
    parser.add_argument('--debug-rejected-samples',action='store_true',
                        help='显式允许固定模拟材料的绑定失败输出保存至私有本地目录，默认关闭')
    args=parser.parse_args(argv)
    output=ROOT/'.autolex_runtime'/'acceptance'
    if not args.run_live:
        if args.debug_rejected_samples:raise AcceptanceError('调试开关仅用于显式真实验收；离线定位请用tools/replay_sim_b.py，不读取Secrets')
        if args.confirm_paid_calls:raise AcceptanceError('缺少--run-live，未调用模型')
        path=write_report(preparation_report(),output/'preparation')
        print('仅准备：真实调用0次，等待安全配置。报告：'+str(path))
        return 0
    if not args.confirm_paid_calls:raise AcceptanceError('真实调用还需--confirm-paid-calls显式允许费用')
    if not sys.stdin.isatty():
        raise AcceptanceError('真实验收必须在用户自己的交互式终端认证；不从聊天或管道读取访问密码')
    path=ROOT/'.streamlit'/'secrets.toml'
    if not path.is_file() or path.is_symlink():raise AcceptanceError('请先在本机安全配置标准Streamlit Secrets文件；不要在聊天发送密钥')
    if os.name=='posix' and path.stat().st_mode & 0o077:
        raise AcceptanceError('Secrets权限过宽，请先chmod 600 .streamlit/secrets.toml')
    with path.open('rb') as handle:values=tomllib.load(handle)
    try:settings=Settings.from_secrets(codespaces_values(values,os.environ))
    except ValueError as exc:raise AcceptanceError(str(exc)) from None
    # 固定相对路径以免从其他工作目录运行时意外创建第二份计数库。
    from dataclasses import replace
    db=Path(settings.db_path)
    if not db.is_absolute():settings=replace(settings,db_path=str(ROOT/db))
    quota=QuotaStore(settings.db_path)
    quota.reserve_login()
    password=getpass.getpass('输入访问密码以执行两份模拟材料真实验收（不会显示或保存）：')
    if not verify_password(password,settings.password_hash):raise AcceptanceError('访问认证未通过，未调用模型')
    del password
    print(f'服务商：{settings.provider_spec.label}；请求模型：{settings.model}。仅处理两份固定模拟材料；失败也占次数/输入预算，不自动重试。冷却期默认30秒。',flush=True)
    options={'confirm_paid':True}
    if args.debug_rejected_samples:options['debug_rejected_samples']=True
    report,directory=run_suite(settings,quota,settings.principal,output,**options)
    print('报告已写入：'+str(directory))
    print('真实尝试次数：'+str(report['actual_live_attempts'])+'；人工语义复核仍待完成。')
    return 0 if all(case['call_status']=='response_validated' for case in report['cases']) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except (AcceptanceError,SecurityError) as exc:
        print('验收已停止：'+str(exc),file=sys.stderr)
        raise SystemExit(2)
    except (FileNotFoundError,tomllib.TOMLDecodeError):
        print('安全配置文件缺失或格式错误；未显示文件内容。',file=sys.stderr)
        raise SystemExit(2)
    except (EOFError,KeyboardInterrupt):
        print('用户已中止认证或测试；查看已保存报告，勿假定未收到响应就没有计费。',file=sys.stderr)
        raise SystemExit(2)
