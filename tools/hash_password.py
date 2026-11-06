"""交互读取访问密码，仅输出盐化哈希，不把密码写入文件或命令历史。"""
import getpass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security import hash_password

if __name__ == '__main__':
    first = getpass.getpass('设置访问密码（12–128字符）：')
    second = getpass.getpass('再次输入：')
    if first != second:
        raise SystemExit('两次密码不一致')
    print(hash_password(first))
