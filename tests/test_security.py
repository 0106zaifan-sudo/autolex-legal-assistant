import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from security import Settings, SecurityError, QuotaStore, hash_password, valid_password_hash, verify_password

HASH = 'pbkdf2_sha256$200000$' + 'ab'*16 + '$' + 'cd'*32
HASH2 = 'pbkdf2_sha256$200000$' + 'ac'*16 + '$' + 'ce'*32

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite3'
        self.store=QuotaStore(self.path)
        self.settings=Settings(password_hash=HASH,daily_limit=2,hourly_limit=2,cooldown=1)
        self.now=1793923200.0

    def test_secrets_only_and_fail_closed_defaults(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'environment-key-must-not-be-used'}):
            config=Settings.from_secrets({})
        self.assertEqual(config.mode,'public')
        self.assertEqual(config.api_key,'')
        self.assertTrue(config.ai_disabled_reason(None))
        config=Settings.from_secrets({'OPENAI_API_KEY':'test-placeholder','APP_PASSWORD_HASH':HASH,'AI_SINGLE_INSTANCE':True})
        self.assertEqual(config.ai_disabled_reason(config.principal),'')
        self.assertNotIn('test-placeholder',repr(config))
        self.assertNotIn(HASH,repr(config))

    def test_invalid_settings_rejected(self):
        for values in ({'APP_MODE':'unknown'}, {'APP_PASSWORD_HASH':'plaintext'},
                       {'AI_DAILY_LIMIT':0},{'AI_HOURLY_LIMIT':True},{'AI_DAILY_LIMIT':101},
                       {'AI_LIMIT_DB':':memory:'},{'AI_LIMIT_DB':''}):
            with self.subTest(values=values),self.assertRaises(SecurityError):Settings.from_secrets(values)

    def test_hash_password_validation_and_comparison(self):
        encoded=hash_password('simulation-password-long')
        self.assertTrue(valid_password_hash(encoded))
        self.assertTrue(verify_password('simulation-password-long',encoded))
        self.assertFalse(verify_password('wrong',encoded))
        self.assertFalse(verify_password('x','invalid'))
        with self.assertRaises(SecurityError):hash_password('short')

    def test_atomic_parallel_calls_allow_one_inflight(self):
        def reserve(_):
            try:return QuotaStore(self.path).reserve_ai(self.settings,self.settings.principal,now=self.now)
            except SecurityError:return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            leases=list(pool.map(reserve,range(6)))
        self.assertEqual(sum(x is not None for x in leases),1)

    def test_shared_persistent_daily_and_hourly_limits(self):
        a=self.store.reserve_ai(self.settings,self.settings.principal,now=self.now)
        self.store.release(a)
        reopened=QuotaStore(self.path)
        b=reopened.reserve_ai(self.settings,self.settings.principal,now=self.now+2)
        reopened.release(b)
        with self.assertRaises(SecurityError):reopened.reserve_ai(self.settings,self.settings.principal,now=self.now+4)
        # 变更访问密码也不能绕过全应用日额度。
        other=replace(self.settings,password_hash=HASH2)
        with self.assertRaises(SecurityError):reopened.reserve_ai(other,other.principal,now=self.now+4)

    def test_cooldown_and_hourly_expiry(self):
        settings=replace(self.settings,daily_limit=20,hourly_limit=1,cooldown=30)
        lease=self.store.reserve_ai(settings,settings.principal,now=self.now)
        self.store.release(lease)
        for seconds in (1,31,3599):
            with self.subTest(seconds=seconds),self.assertRaises(SecurityError):
                self.store.reserve_ai(settings,settings.principal,now=self.now+seconds)
        self.store.reserve_ai(settings,settings.principal,now=self.now+3601)

    def test_lease_expiration_and_global_login_throttle(self):
        self.store.reserve_ai(self.settings,self.settings.principal,now=self.now)
        with self.assertRaises(SecurityError):self.store.reserve_ai(self.settings,self.settings.principal,now=self.now+119)
        self.store.reserve_ai(self.settings,self.settings.principal,now=self.now+121)
        for _ in range(20):self.store.reserve_login(now=self.now)
        with self.assertRaises(SecurityError):QuotaStore(self.path).reserve_login(now=self.now+1)
        self.store.reserve_login(now=self.now+601)

    def test_storage_failure_and_unauthenticated_fail_closed(self):
        with self.assertRaises(SecurityError):QuotaStore(self.path/'impossible')
        with self.assertRaises(SecurityError):self.store.reserve_ai(self.settings,None,now=self.now)
