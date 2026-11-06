"""Secrets 配置、访问控制和 SQLite 原子额度。此模块不读取环境 API 密钥。"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import hashlib
import hmac
import secrets
import sqlite3
import time


class SecurityError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    password_hash: str = field(default='', repr=False)
    mode: str = 'public'
    model: str = 'gpt-4.1-mini'
    daily_limit: int = 20
    hourly_limit: int = 5
    cooldown: int = 30
    single_instance: bool = False
    db_path: str = '.autolex_runtime/limits.sqlite3'

    @classmethod
    def from_secrets(cls, values):
        mode = str(values.get('APP_MODE', 'public'))
        if mode not in ('public', 'local'):
            raise SecurityError('APP_MODE 必须为 public 或 local')
        def bounded(name, default, upper):
            value = values.get(name, default)
            if isinstance(value, bool) or not str(value).isdigit() or not 1 <= int(value) <= upper:
                raise SecurityError(f'{name} 配置无效')
            return int(value)
        settings = cls(api_key=str(values.get('OPENAI_API_KEY', '')).strip(),
                       password_hash=str(values.get('APP_PASSWORD_HASH', '')).strip(), mode=mode,
                       model=str(values.get('OPENAI_MODEL', 'gpt-4.1-mini')),
                       daily_limit=bounded('AI_DAILY_LIMIT', 20, 100),
                       hourly_limit=bounded('AI_HOURLY_LIMIT', 5, 20),
                       cooldown=bounded('AI_COOLDOWN_SECONDS', 30, 3600),
                       single_instance=values.get('AI_SINGLE_INSTANCE', False) is True,
                       db_path=str(values.get('AI_LIMIT_DB', '.autolex_runtime/limits.sqlite3')))
        if not settings.db_path.strip() or settings.db_path == ':memory:':
            raise SecurityError('调用限制必须使用磁盘 SQLite 数据库')
        if settings.password_hash and not valid_password_hash(settings.password_hash):
            raise SecurityError('APP_PASSWORD_HASH 格式无效，请使用 tools/hash_password.py 生成')
        if not settings.model or len(settings.model) > 100:
            raise SecurityError('OPENAI_MODEL 配置无效')
        return settings

    @property
    def principal(self):
        return hashlib.sha256(self.password_hash.encode()).hexdigest() if self.password_hash else None

    def ai_disabled_reason(self, principal):
        if not self.api_key:
            return '未在 Streamlit Secrets 配置 OPENAI_API_KEY，AI 功能已禁用。'
        if not self.principal or principal != self.principal:
            return 'AI 调用需要配置访问密码并登录。'
        if self.mode == 'public' and not self.single_instance:
            return '公开模式请确认单实例部署，并在 Secrets 设置 AI_SINGLE_INSTANCE=true。多实例需外部统一限流。'
        return ''


def valid_password_hash(encoded):
    try:
        algorithm, count, salt, digest = encoded.split('$')
        return (algorithm == 'pbkdf2_sha256' and 200000 <= int(count) <= 1000000
                and len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 32)
    except (ValueError, TypeError):
        return False


def hash_password(password):
    if not 12 <= len(password) <= 128:
        raise SecurityError('访问密码长度应为 12–128 字符')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000).hex()
    return f'pbkdf2_sha256$600000${salt.hex()}${digest}'


def verify_password(password, encoded):
    if not valid_password_hash(encoded) or not 1 <= len(password) <= 128:
        return False
    _, count, salt, expected = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(count)).hex()
    return hmac.compare_digest(actual, expected)


class QuotaStore:
    """同一磁盘文件上跨会话/线程/进程限流；不保存正文、凭据或姓名。"""
    def __init__(self, path):
        self.path = str(path)
        try:
            parent = Path(path).parent
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS events (kind TEXT, principal TEXT, ts REAL, lease TEXT, active_until REAL)')
                db.execute('CREATE INDEX IF NOT EXISTS events_ts ON events(kind, ts)')
            Path(path).chmod(0o600)
        except (OSError, sqlite3.Error):
            raise SecurityError('限流存储不可用，已禁止调用。') from None

    def connect(self):
        return sqlite3.connect(self.path, timeout=5, isolation_level=None)

    def reserve_login(self, now=None):
        now = time.time() if now is None else now
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM events WHERE ts<?', (now - 172800,))
                count = db.execute("SELECT count(*) FROM events WHERE kind='login' AND ts>?", (now - 600,)).fetchone()[0]
                if count >= 20:
                    raise SecurityError('登录尝试过多，请稍后再试。')
                db.execute('INSERT INTO events VALUES (?,?,?,?,?)', ('login', '', now, '', 0))
                db.execute('COMMIT')
        except sqlite3.Error:
            raise SecurityError('限流存储不可用，已禁止登录。') from None

    def reserve_ai(self, settings, principal, now=None):
        if principal != settings.principal or not principal:
            raise SecurityError('未通过访问认证。')
        now = time.time() if now is None else now
        day = datetime.fromtimestamp(now, ZoneInfo('Asia/Shanghai')).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        lease = secrets.token_hex(16)
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM events WHERE ts<?', (now - 172800,))
                active = db.execute("SELECT count(*) FROM events WHERE kind='ai' AND active_until>?", (now,)).fetchone()[0]
                daily = db.execute("SELECT count(*) FROM events WHERE kind='ai' AND ts>=?", (day,)).fetchone()[0]
                hourly = db.execute("SELECT count(*) FROM events WHERE kind='ai' AND principal=? AND ts>?", (principal, now - 3600)).fetchone()[0]
                last = db.execute("SELECT max(ts) FROM events WHERE kind='ai' AND principal=?", (principal,)).fetchone()[0]
                if active:
                    raise SecurityError('已有分析请求正在处理，请稍后再试。')
                if daily >= settings.daily_limit or hourly >= settings.hourly_limit:
                    raise SecurityError('调用额度已用尽，请稍后再试。')
                if last is not None and now - last < settings.cooldown:
                    raise SecurityError('调用过于频繁，请稍后再试。')
                db.execute('INSERT INTO events VALUES (?,?,?,?,?)', ('ai', principal, now, lease, now + 120))
                db.execute('COMMIT')
        except sqlite3.Error:
            raise SecurityError('限流存储不可用，已禁止调用。') from None
        return lease

    def release(self, lease):
        try:
            with self.connect() as db:
                db.execute('UPDATE events SET active_until=0 WHERE lease=?', (lease,))
        except sqlite3.Error:
            # 租约120秒后自动失效，失败不会返还调用额度。
            pass
