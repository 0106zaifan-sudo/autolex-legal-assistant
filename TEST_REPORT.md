# V2.0-B候选事件选择结构性修复最新离线测试

独立分支 `feature/v2b-event-candidate-selection`，基线 `de85fcc236b52f51a33c0c54742a8699c387c9c5`，基线工作区干净，另建worktree。

完整执行 `python -m unittest discover -s tests -v`：**456项全部通过，33.428秒**，原418项不改，新增38项（37项候选/调用/导入测试、1项AppTest网页实际链路）。先新增24项会失败的测试（旧代码缺少候选模块和入口），实现后逐步补齐安全反例。首轮442项通过；扩展审阅历史测试时修正新测试把关系对象误作ID的fixture用法，未改生产历史逻辑；最终456项通过。

覆盖固定四材料准确坐标/文件与快照哈希/原文SHA、唯一候选ID、同文本不同文档/跨案隔离、分号/换行/跨段主张与否定作用域、08:30/08:31分别保留、未知/date/second/多时间、编号选择Schema（含动态enum）、引文与时间覆盖字段拒绝、重复/虚构编号、事实推断约束、原验证链仍执行、失败不写案件、输入预算/部分解析确认/授权/额度/调用一次/零重试、导入重放与篡改审计拒绝、原人工审阅保留和两服务商官方SDK本地HTTP Mock。

完整日志见[本轮日志](docs/v2b_event_candidates_tests.txt)，Schema、兼容策略、操作与风险见[结构性修复说明](docs/V2B_EVENT_CANDIDATES.md)。旧1.0接口保留供兼容，网页新入口使用1.1候选选择，不自动回退。案件Schema2.0单文档/1.2案件、原证据与费用/超时机制不改。

本轮真实API调用0次，不读改Secrets、私有验收或真实案件，不部署、不合并。本次日志中的token值为人工Mock，不是真实调用。离线通过不证明真实服务端兼容或模型选全事件，也无法确定第四次失败的具体标点。

以下保留历史报告。

# V2.0-B时间线引文Prompt补丁最新离线测试

独立分支 `feature/v2b-timeline-quote-fix`，基线 `51d60ee6be8b30661968a3abcef167bd7e838d05`；原工作区干净，独立worktree开发。

完整执行 `python -m unittest discover -s tests -v`：**418项全部通过，28.685秒**；保留原399项，新增19项。先增加离线反例，旧Prompt缺少7项明确指导；实现只替换联合Prompt的时间线指导。新增测试初版误认为跨行文本会在同一source，核对build_sources后分别测试“来源层跨行拒绝”和“绑定层CR/LF拒绝”，未修改生产分句逻辑或原断言。

固定四份虚构材料未变。覆盖分号/句号/问号/感叹号/换行、完整句段、主体否定/主张与时间不截断、原文坐标/文件哈希/独立来源、跨文档借时间、精度、未知状态、失败回执与不写案件、不制造事件及facts.reasoning约束保留。完整日志见[本轮日志](docs/v2b_timeline_quote_tests.txt)，规则、修复范围与残余风险见[补丁说明](docs/V2B_TIMELINE_QUOTE_FIX.md)。

本轮真实API调用0次，不读改Secrets，不部署、不合并。安全回执不含模型原文，不能确定第三次真实失败的具体标点；418项离线通过不代表真实模型时间线完整性已验收。

以下保留历史报告。

# V2.0-B事实 reasoning 协议补丁最新离线测试

独立分支 `feature/v2b-fact-reasoning-fix`，基线 `7fef12a74258fb9adcf97b902a031885bbc63bb4`，基线工作区干净，另建 worktree。

完整执行 `python -m unittest discover -s tests -v`：**399项全部通过，28.170秒**。原387项不修改、新增12项。先在旧代码运行新增测试，出现12个失败断言与2个错误（含subTest计数），复现缺失契约；最小补丁后新增12项和完整套件通过。

覆盖事实/主张空字符串、非空/空白/null/缺字段、原validator仍拒绝、推断/关系字段保留、两服务商官方SDK本地HTTP Mock、格式拒绝定位、Token保留、单次调用与零重试、额度消耗、无后处理修改和失败不写案件。完整日志见[本轮日志](docs/v2b_fact_reasoning_tests.txt)，兼容边界与真实复测建议见[补丁说明](docs/V2B_FACT_REASONING_FIX.md)。

真实模型API调用0次，不读取或修改Secrets，不部署、不合并。格式约束已离线核验，不代表真实服务端兼容或模型输出质量已验收。

以下保留历史报告。

# V2.0-B验证诊断补丁最新离线测试

独立分支 `feature/v2b-validation-diagnostics`，基线 `a717d63593b303dc0eeee3abebf2c01789dd7a08`。原工作区干净，独立 worktree 开发。

完整执行 `python -m unittest discover -s tests -v`：**387项全部通过，27.538秒**。原351项保留，新增36项（35项核心诊断、1项界面）。完整日志见[本轮日志](docs/v2b_validation_diagnostics_tests.txt)，根因边界、映射和下一次验收见[诊断说明](docs/V2B_VALIDATION_DIAGNOSTICS.md)。

首次新增测试验证缺少诊断；第一次完整执行387项时2项原子进程测试受新增AppTest测试遗留的 __main__ 影响失败，修复新增测试的状态清理后完整387项通过。未改原测试断言、超时运行器或生产保护规则。所有模型请求均为注入或本地Mock，真实API调用0次，不读改Secrets、不部署、不合并。

以下保留历史报告。

# V2.0-B最新离线测试

独立分支feature/v2-multidoc-ai，基线360911ff7a。开始前原工作区干净，独立worktree开发。

实际执行完整测试：**351项通过，24.684秒**，原294项功能回归通过，新增57项。原test_*文件和断言未修改；UI隔离helper额外拦截联合模型入口，保护更严格。完整日志见[本轮日志](docs/multidoc_ai_offline_tests.txt)，设计、流程、文件与边界见[联合分析说明](docs/MULTIDOC_AI_V2B.md)。

测试覆盖同文本独立来源、全局编号与冲突、跨案污染、文件ID/哈希/快照、时间/未知状态/精度及发出与收到、非法引用、重叠去重与不同问题保留、原审阅不覆盖、原子导入、费用/授权/规模/解析覆盖、两家官方SDK的本地HTTP mock、超时/401回执、会话同意重置和安全导出。所有模型响应为人工注入或本地mock，不是实际模型结果。

真实API调用0次；不读取/修改Secrets或真实案件，不部署、不合并。原单文档AI、原SDK运行器、权限限流、证据算法与固定材料/gold不变。模型语义及新Prompt完整性仍需后续明确授权的真实验收，本轮到此停止。

以下保留历史报告。

# V2.0-A最新离线验证

294项通过，19.297秒；原267项测试不变，新增27项。详见[多文档说明](docs/MULTIDOC_V2A.md)及[完整日志](docs/multidoc_offline_tests.txt)。真实模型调用0次，不读取Secrets，不部署。

以下保留历史记录。

# 最新：V1.1时间线完整性补丁

2026-11-09（北京时间）；`feature/output-quality-p1-timeline`，基线`e5e0744`。原工作区干净，独立worktree开发。

完整离线回归：**267项通过，17.506秒**；原247项加新增20项。仅一处旧Prompt修订号断言按新版本更新，没有删除断言；其他旧测试与固定材料/gold不变。完整日志见[本轮离线日志](docs/timeline_completeness_offline_tests.txt)，根因、最小修复及局限见[补丁说明](docs/TIMELINE_COMPLETENESS_PATCH.md)。

Prompt明确未知时间重要事件仍应进入timeline、facts与timeline合理复用不受去重影响，并提对应时间核查问题。新增只读完整性诊断及UI警告，不自动补事件、时间或问题。人工构造漏碰撞响应仍只有接收事件，原timeline_expected_bindings仍失败，证明未降低金标准。

原Schema/证据/时间函数、P1分类去重与元信息审计、人工核验、安全/限流/超时、受控验收工具均保持不变。用户提供的真实失败仅用于构造离线情形，未读取私有验收文件或Secrets，真实API调用0次，不部署或合并。仅Prompt不能可靠保证完整性；新DeepSeek输出是否恢复两条事件仍待真实复测。

以下保留历史报告。

---

# 最新：P1输出质量

2026-11-09（北京时间）；分支`feature/output-quality-p1`，基线`feature/multi-provider-deepseek`的`9ea9fd1`。原工作区开始时干净，在独立worktree开发。用户已告知基线真实DeepSeek验收通过；本轮不读取或复制其私有记录。

完整离线回归：**247项通过，17.219秒**；原223项测试文件和断言未改，新增24项。先用人工构造的固定SIM_A/B反例重现问题，再实施局部修改。完整日志见[本轮离线日志](docs/output_quality_p1_offline_tests.txt)，前后行为与局限见[输出质量说明](docs/OUTPUT_QUALITY_P1.md)。

变化：原证据校验通过后，将facts中的推断移入pending，按类型/原文/问题/完整锚点精确去重；两种完整中性模拟声明归document_metadata，移位/合并原条目留quality_audit。不重写模型问题；已覆盖的重复疑问表达或移动后超过8项上限明确拒绝，保留usage及失败预算，不自动重试。新修订号output-quality-p1/v1与原Schema 2.0/绑定Prompt版本并行，保留历史兼容。

原Schema、CLAIM_MARKERS、来源SHA256/坐标、时间绑定/排序、案件导入防篡改、人工核验、权限、配额、超时和SDK路径不变。正常导入及时间线、无误合并、失败不隐藏均有新增测试。真实API调用0次，不读取/修改Secrets，不部署、不合并main；离线通过不证明新Prompt真实模型效果。

以下保留历史报告。

---

# 最新：单场景验收与UI测试配置隔离

2026-11-06（北京时间）；`feature/multi-provider-deepseek`，基线`64282dc`。

实际执行`python -m unittest discover -s tests -v`：**223项通过，18.167秒**，包含原205项及新增18项。四个原UI测试文件只接入隔离基类/setUp，test_*方法和断言不变；其余原测试文件未改。完整日志见[本轮离线日志](docs/single_scenario_offline_tests.txt)，具体变更见[单场景说明](docs/SINGLE_SCENARIO.md)。

覆盖SIM_A/SIM_B单选、默认双样本、未选报告、费用与认证保护、仅选中样本预留预算、剩余一次额度、原账本不重置/失败不退款、未选样本哈希校验、安全捕获兼容，以及模拟宿主环境/本地Secrets隔离。CLI真实路径测试仅使用内存虚构配置与执行替身，不打开实际Secrets或调用SDK。

真实模型请求0次。不读取或改写实际Secrets，不部署；分类、哈希、时间、模型超时/重试、限流、安全捕获及固定材料/gold与基线一致。测试通过不代表真实验收通过。

以下保留历史记录。

---

# 最新：SIM_B失败定位与可选私有调试

2026-11-06（北京时间）；`feature/multi-provider-deepseek`，基线`5a18ec3`。

完整离线回归：**205项通过，16.359秒**。原有176项测试文件未改，新增29项固定样本调试/安全/回放测试。Python 3.12，工作区已有依赖通过`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps`加载，依赖版本不变。完整日志见[本轮离线日志](docs/sample_debug_offline_tests.txt)。

[SIM_B定位与调试说明](docs/SIM_B_DEBUG.md)及[9项人工离线对照](docs/sim_b_manual_reproduction.json)明确区分整句误分类、客观半句保守拒绝、待核实问题、单方主张及独立客观记录。可用`python tools/replay_sim_b.py`完全离线重现，不读取Secrets或访问模型。

仅完善Prompt并新增默认关闭、固定样本限制的私有原始结构化输出捕获/回放；分类validator、CLAIM_MARKERS、Schema 2.0、哈希/source、时间绑定、访问控制及限流实现与基线相同。原SIM材料和manifest/gold未改。测试覆盖私有权限、符号链接/路径逃逸、仿冒样本、原文范围、凭据样式及JSON转义、大小/数量限制、失败不导入案件、默认不保存、Schema失败/有效分析不保存、回放不输出原文。

本轮真实模型调用0次，不读取/修改/重新配置实际Secrets，不部署、不执行付费验收。用户提供的既有DeepSeek失败不被离线结果替代；仍缺当次text/quote，不能宣称已证明模型具体错误或真实验收通过。

以下保留历史记录。

---

# 最新：事实/主张分类范围及安全诊断补丁

2026-11-06（北京时间）；`feature/multi-provider-deepseek`，基线`62782c4`。

实际执行`python -m unittest discover -s tests -v`：**176项通过，16.032秒**；原161项测试文件未改，新增15项分类回归。完整日志见[本轮离线日志](docs/fact_classification_offline_tests.txt)，原因、具体修改与残余风险见[分类修复说明](docs/FACT_CLASSIFICATION_PATCH.md)。

保留完整CLAIM_MARKERS词表；检查已核验引文所在原文句及前置归属，排除后续独立句污染，继续拒绝截掉主张/核实前缀、跨块及后置承接限定等情况。新增分类失败的section、0基条目索引、source_id、触发词及规则诊断，不记录原文。Schema 2.0、哈希/source生成、时间绑定及权限/限流实现保持不变。

本轮真实API调用0次，不加载实际Secrets，不运行付费验收，不部署。用户报告的真实SIM_B失败没有被本轮离线结果替代；现有信息不足以确定具体触发项，不能宣称真实复测通过。SIM_B的日志完整性仍必须保守标为待核实。

以下保留历史报告。

---

# 多服务商适配：最新离线测试记录

2026-11-06；分支`feature/multi-provider-deepseek`，基线`feature/live-ai-acceptance`的`c9621de`。

实际执行`python -m unittest discover -s tests -v`：**161项通过，15.226秒**。包含原135项原样保留的回归及新增26项DeepSeek/服务商测试。依赖通过`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps`加载，Python 3.12、官方openai 2.54.0，requirements版本未变。完整日志见[本轮离线日志](docs/multi_provider_offline_tests.txt)。

新增覆盖：独立服务商凭据、默认值/非法配置、Codespaces安全Secret补入、SDK真实序列化的DeepSeek Responses请求及Schema、usage缓存/推理明细、金额未知、输出校验与事件时间绑定失败、HTTP400/401/402/429/500、网络超时及连接错误、子进程截止参数、共享输入/次数预算、解析覆盖与许可门禁、两份固定SIM材料的SDK离线通路、余额不足中止第二份以及界面服务商切换许可复位。

本轮发现SDK会补入`cache_write_tokens=null`，现过滤SDK产生的空usage字段，保留服务商非空明细；不把空值当实测。最终运行全部通过，没有修改原测试断言。源码与Secrets模板检查未发现API密钥模式，未纳入Secrets、SQLite、缓存或真实案件文件；新增测试复用既有明确模拟材料。`git diff --check`通过。

**真实付费请求0次。** SDK请求使用`httpx.MockTransport`，记录`injected_test_client`；SIM批次为`offline_test`，不能当作真实模型验收。两份真实场景仍为not_run，实测返回模型/token/费用未获得，准确率未测。未做公开部署、浏览器视觉或真实API兼容性验收。配置及官方文档核对见[多服务商说明](docs/MULTI_PROVIDER.md)。

以下保留历史记录，不代表最新测试数量。

---

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
