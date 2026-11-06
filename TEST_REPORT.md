# 最新：P0真实模型验收准备阶段（无密钥）

2026-11-06（北京时间），分支`feature/live-ai-acceptance`，父提交`267de0b`。

**135项离线测试通过，13.250秒**，包含原113项及新增22项。原113项测试文件未修改。子进程总截止、累计预算、官方SDK严格Schema及元数据处理、模拟材料和准备/认证边界均做离线验证。没有真实模型调用；测试中的mock模型标识和token数字不是实际模型验收结果。

真实状态：两份模拟材料均not_run，provider model/token未知，准确率未测。见`docs/LIVE_AI_ACCEPTANCE_STATUS.json`、`docs/LIVE_AI_ACCEPTANCE.md`及完整日志`docs/live_acceptance_offline_tests.txt`。

以下保留历史报告，不代表当前最新测试数量或真实AI验收已通过。

---

# 最新：案件结构化与文档解析覆盖测试

2026-11-06（北京时间）；分支`feature/case-structure-parse-coverage`；父提交`68f097a`。

**113项测试通过，9.505秒。** 包含原68项未改动回归及新增45项（解析17、案件存储23、案件页面5）。未调用真实付费API，未执行生产部署。详细说明见`docs/CASE_STRUCTURE_COVERAGE.md`，完整日志见`docs/case_structure_coverage_test_run.txt`。

以下保留旧阶段历史报告，数量/耗时不代表本次运行。

---

# 最新：P0-A 证据绑定补丁测试

日期：2026-11-06（北京时间）；分支：`feature/fix-evidence-binding`，基于AI分支`5307554`。

实际执行 `python -m unittest discover -s tests -v`：**68项通过，5.875秒**。包含原41项回归及27项新增绑定测试。原有测试按Schema 2.0更新固定响应和空分析构造，保留原检查意图。全部使用内存模拟资料、官方SDK的HTTP mock及Streamlit AppTest；无真实付费模型调用。

详细范围和未解决问题见 `docs/EVIDENCE_BINDING_PATCH.md`，完整本次日志见 `docs/evidence_binding_test_run.txt`。以下为保留的第二阶段历史测试记录，不代表本次最新数量。

---

# AutoLex 第二阶段实际测试报告

测试日期：2026-11-06（北京时间）。环境：Linux，Python 3.12。
开发基线：`647b0225a77a2ddaa6c42e17ab821568dc3609be`；开发分支：`feature/ai-case-facts`。

## 实际执行结果

```text
python -m unittest discover -s tests -v
Ran 41 tests in 4.868s
OK
```

测试执行时依赖隔离安装在工作目录，通过 `PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps` 加载，与 requirements 中版本一致。所有模型请求由 HTTP mock 拦截，不访问 OpenAI 网络、不使用真实 API 密钥或付费额度。

| 测试文件 | 数量 | 覆盖范围 |
|---|---:|---|
| test_core.py | 13 | 原有 PDF/DOCX、表格、原文位置、缺失值、关键词/筛选、核验、Excel、长正文及异常文件 |
| test_app.py | 1 | 原有页面导入模拟资料、去重、检索、人工核验、清空和导出生成回归 |
| test_ai_analysis.py | 11 | 官方 SDK 真正序列化/解析；严格 JSON schema、store=False、4000输出token、超时/零重试、引证、时间排序、来源偏移、拒绝/非法JSON、错误提示、失败计次及伪造输出拒绝 |
| test_ai_ui.py | 6 | 默认公开模式锁定、错误/正确密码、退出清空、密码轮换、缺少密钥禁用、固定离线演示、同意发送、切换文档复位、成功/异常页面路径、配置错误 |
| test_security.py | 8 | 仅从 Secrets 读取密钥、默认关闭、配置边界、哈希、并发原子租约、跨存储实例配额、全局日额度、小时额度、冷却期、登录限流、存储异常 |
| test_archive.py | 2 | ZIP 排除 Secrets、环境变量文件、Git、运行数据库、缓存、未知案件和外部符号链接 |
| 合计 | 41 | 全部通过 |

Streamlit 测试使用官方 AppTest，不是浏览器视觉验收。SDK 测试使用真实 `OpenAI` 客户端配合 `httpx.MockTransport`，而非只模拟业务函数；页面层集成另用业务函数 mock 验证成功/异常交互。

## 直接依赖

原6项版本保持不变，新增：

- openai 2.54.0（官方 Python SDK）
- pydantic 2.14.3

未新增实际 Secrets 文件、真实 API 密钥或案件材料。原 `core.py`、原6份测试样本和 Excel 格式保持不变。

## 关键观察与限制

- 无 Secrets 时默认按公开模式锁定整个应用，防止未认证访问上传/资料/下载。离线演示需显式 local 配置，或者配置访问密码后登录。
- API 引证校验可以拒绝不存在来源、非原文摘录、位置歧义、补写事实及非引文时间；它不能证明原文真实、分类完全正确或推断成立。
- 对包含主张标记的块拒绝事实分类是保守规则，可能误拒；仅能返回待核验分析，不做责任认定。
- 同库6线程竞争测试只允许1个在途请求，重新打开数据库仍执行同一额度；失败调用不返还额度。
- 公共调用限流只支持共享同一持久 SQLite 文件的单实例部署。没有跨多副本限流；平台重建临时磁盘会重置额度。部署前应遵守验收文档的持久化/网关要求。
- 下载 ZIP 已改为文件白名单。原遍历方式可能收集部署目录下的 Secrets，因此此项是本次接入密钥前的必要修复。
- 尚未执行真实模型调用、真实材料语义效果评测、浏览器视觉验收、多人正式生产压测或公开部署。

第一阶段记录：此前14项测试通过（13项 core + 1项 app），本次全部保留并回归，仅给原页面测试显式设置本地模式以适配新增门禁。

具体操作见 `PHASE2_ACCEPTANCE.md`。本报告不表示新功能已经上线。
