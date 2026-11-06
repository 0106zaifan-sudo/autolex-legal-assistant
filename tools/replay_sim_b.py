"""完全离线的固定SIM_B反例/私有artifact回放；无模型请求入口。"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sim_b_debug import manual_report, replay_artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--save-rejected-samples',action='store_true',help='显式保存人工构造的固定模拟失败输出')
    group.add_argument('--artifact-id',help='固定私有调试目录中的32位ID，不接受文件路径')
    args = parser.parse_args(argv)
    try:
        report = replay_artifact(args.artifact_id) if args.artifact_id else manual_report(save_rejected_samples=args.save_rejected_samples)
    except (ValueError,OSError):
        print('离线回放已停止：样本或私有artifact无效；未显示文件内容。',file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
