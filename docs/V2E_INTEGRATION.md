# AutoLEX V2.0-E：1.2证据编号选择生产集成

基线：feature/b01-pending-evidence-selection-prototype / a9bfe12c58e289b11c7bab3b12897896ee8fc66a。独立worktree、feature/v2e-pending-selection-integration分支；基线工作区干净。日期2026-11-10（上海）。本轮没有真实模型请求。

## 协议、目录和调用

新增multidoc-analysis/1.2、multidoc/pending-selection-v1；facts保持事实/主张及空reasoning约束，timeline保持CE候选选择，relations保持两侧独立引文，pending_evidence改为anchor_id、evidence_ids、reasoning。不允许模型填写pending的text、quote、kind、哈希或坐标。新版Prompt删除了继承的旧pending自由text/quote指令，只有一个明确的待核实事项契约；旧Prompt没有变。原型独立响应不是完整生产结果；1.2有自己的完整Schema、Prompt和批次指纹。

pending_catalog.py是生产和离线原型共享的可信目录构建器，版本pending-source-catalog/1。每个PE编号绑定case_id、document_id、MD来源ID、文件SHA256、解析快照SHA256、解析器版本、unit/start/end/location、完整原文、原文SHA256和证据锚点ID。相同文字不同文档或不同位置不合并。先验证原件及快照，再make_span核验原文坐标，不以文件名证明技术概念。

每条候选保留完整物理行，包括主体、否定、分号、多命题和原始换行，不按标点截取“更容易通过”的片段；完整行不保证跨行主体范围独立。超长行被原解析器切块时，1.2明确拒绝整批，安全诊断给出physical_line_split、排除数及来源ID，不默默遗漏。保持原2—4文档、每文档8000字符、总体16000字符/96来源块，以及事件目录64候选限制；目录不截断。

新请求不重复发送完整PE目录的正文及所有元数据，而发送candidate_id/source_id/document_id/quote_sha256紧凑映射；原文与文件/位置/快照信息已经在sources及documents中。服务端完整目录仍在调用前后构建并对比。若把整个目录再次展开会超出B01字节上限，紧凑映射解决重复传输，不删原文、不减少候选、不增加额度。

multidoc_v12.py提供prepare_case、request_for、validate_output及analyze_case；analyze_case分派至既有multidoc_ai.analyze_case的同一次SDK流程，复用Settings认证、明确批次授权、每份PDF解析覆盖确认、QuotaStore真实预留/累计输入预算、冷却、并发、超时、零自动重试和finally释放。没有额外按文件或按模块模型调用，失败不降级1.1。

响应依次经过：完整1.2 Pydantic格式验证→重建当前档案/目录→核对批次和目录哈希→逐项检查PE编号、主证据包含、重复→恢复text与全部sources→内部显式转换到既有绑定验证器（含时间线候选恢复）→facts/时间/术语/引文/关系与输出质量检查。转换只使用模型明确选择的编号，不搜索相似文字，不自动补选标题或修改reasoning。公开结果及调用回执始终标识1.2，raw_output保存原始1.2结构化对象，绝不冒充1.1模型响应。

三层状态独立：format_status=passed、evidence_status=passed、semantic_status=pending_human_review。引用准确不保证问题有依据、证据真实、责任或因果成立。任一关键检查失败整批拒绝，预览和导入相互独立。

## 人工核验与错误边界

标题只识别材料。D04涉及EDR的正文若本身不含EDR，模型须显式选择同文档标题或含EDR正文作为附加证据；程序不会代选。EDR不能授权DSSAD，字段或功能不能从另一文档移植。原unsupported_data_term、时间、推断标识、存在性和法条/案例保护均保持。

同一证据支持不同核查问题时全部保留；相同来源集合的精确相同问题整批拒绝，不静默去重。最多4来源，不能为了容量或过检删除关键证据。主证据必须显式属于选中集合，不自动附加。

合法但不相关的编号、主体误归属、跨文档技术概念转移以及提问中的隐含责任判断，仍可能通过词面校验；必须人工审核。完整物理行只防止程序截断，不证明语义蕴涵。1.2没有自动确认事实或责任，人工确认仅沿用原独立操作。

安全回执保留1.2版本、Prompt哈希、文档快照、目录版本/哈希、模型/服务商状态、Token/账单明细、阶段/列表/零基索引/固定错误码，以及被过滤的PE编号。无效编号只允许PE+24位hex或rejected_candidate_id，不回显任意模型字符串。unsupported_data_term继续只报告固定EDR/DSSAD词表。回执不含quote、reasoning、目录正文、请求、Key或密码。

目录/规模失败在发送前阻断，UI展示发送前安全诊断；模型返回后失败仍保留Token用量、format/evidence状态和诊断，不自动导入或重试。本轮没有增加私有原始响应落盘功能，默认也不捕获完整请求或响应；避免在未完成专门安全设计前扩展数据保存面。

## 新旧协议与ZIP兼容

| 项目 | 处理 |
| --- | --- |
| 1.0历史自由时间线/待核实摘录 | 原prepare_case/validate_case_output/import路径保留 |
| 1.1事件候选+自由待核实摘录 | 原prepare_case/validate_candidate_output保留，不重新解释旧结果 |
| 1.2事件候选+PE编号选择 | 独立prepare/完整Schema/校验；导入按明确版本分派 |
| 离线原型pending-evidence-selection/1.0-prototype | 仍独立，不可作为生产分析导入或ZIP分析附件 |
| CaseBundle1.1/1.2、V2C ZIP格式 | 不改变格式或静默升级旧案件；新增明确1.2分析回执校验分派 |

结果包含pending_selection完整目录、版本/哈希、模型原选择及恢复后的独立引用，raw_output为原始1.2结构。安全回执只保存pending_selection_ids（anchor/evidence IDs和reasoning哈希）、目录版本/哈希、完整输出哈希，不包含问题原文。显式导入后，案件inferences和evidence存储问题及原文锚点；案件回执额外记录pending_statement_ids，连接选择编号与已存推断记录。人工审阅及关系历史不覆盖；若同一问题和相同证据已经作为人工推断存在，新增分析关联该记录并保留其原始origin，不改成人工已确认或伪装AI来源。

导出含联合分析附件时，保留完整目录和1.2原输出审计；没有附件时，也能从原件和解析快照重建目录，并核对回执原选择ID、问题哈希及案件推断/证据锚点。ZIP恢复验证目录、事件编号、记录链接、文件/解析SHA、引用和原推断约束。篡改目录、选择、问题哈希、恢复内容或记录链接会拒绝，失败不写入当前会话。同一run_id对应不同输出哈希会拒绝，重复导入同一结果保持幂等。

目录算法/Prompt/Schema将来改变时应注册新版本校验器；本实现对未知或不能重建的1.2档案明确拒绝，不能用新语义静默解释旧结果。没有数字签名，工作包不能证明复核人身份或模型服务商真实性；完整自洽重写的伪造仍超出校验能力。

## B01实际预算与SDK兼容

使用固定D01/D02/D03/D04，不是三文档原型。62来源、62个PE候选、4个事件候选，原正文1940字符，原文加事件候选2015字符。完整预算见[V2E_B01_BUDGET.json](V2E_B01_BUDGET.json)。

| 服务商/模型 | 适配后请求预算（含1024余量） | 官方SDK本地HTTP Mock实际序列化字节 | 输出上限 |
| --- | ---: | ---: | ---: |
| DeepSeek/deepseek-flash | 94403 | 93379 | 6000 |
| OpenAI/gpt-4.1-mini | 94423 | 93399 | 6000 |

未调用服务商，实际输入/输出Token未测得，报告使用null，不按字符数编造Token或费用。Mock用量只验证回执，不是能力或账单数据。目录元数据和动态枚举会增加输入Token；6000输出容量不能保证真实复杂分析一定完整。截断、拒绝或结构不完整继续拒绝并保留调用状态，不自动重试。

官方OpenAI Python SDK本地HTTP Mock覆盖两服务商：Responses序列化、动态PE/CE枚举、完整响应验证、一次请求、max_retries=0；嵌套对象additionalProperties=false且全部字段required。OpenAI保留strict；DeepSeek沿用已有适配，移除不支持的strict/store/truncation并明确reasoning.effort=none，本地验证不依赖服务端strict。离线序列化通过不保证真实服务商当前支持相同Schema/枚举规模或按新Prompt输出。

可复核：`python tools/prepare_v2e_b01.py --output /tmp/AutoLEX_V2E_B01_budget.json`。此工具固定使用本地MockTransport，不读取Secrets、不打开QuotaStore、没有真实调用选项。预算报告不是调用授权，也不查询实际剩余额度。累计字节预算继续生效，不能据单次小于128KB假定多次调用可用。

## 人工网页验收流程（无真实调用）

1. 在独立分支安装既有requirements，运行Streamlit。完成既有登录；本轮自动测试通过内存虚构配置运行，没有要求读取或配置真实Secrets。
2. 新建虚构案件，归档CASE-001 B01四份材料，选择“1.2 · 证据编号选择”；核对四份文件及SHA。未明确授权或未逐份确认PDF覆盖风险时按钮必须禁用。
3. 用测试客户端注入固定1.2返回（AppTest已覆盖），检查四模块预览、主原文逐字恢复、D04标题支持、两侧来源，核对安全回执没有原文；此时案件尚无新增候选。
4. 明确点击“将当前批次候选明确导入本案”；查看来源、待核验状态、人工审阅历史，再下载工作包，清空会话并导入，检查审计信息一致。
5. 注入未知PE/篡改目录/非法术语，检查错误、阶段、索引、过滤编号、Token保留、授权被消耗、导入禁用及无部分写入。切换1.1或更换文档必须重置授权，不自动重试。
6. 真实网页排版、长引文可读性、浏览器文件上传/下载和法律研究人员的语义复核仍须人工执行；AppTest不是浏览器人工验收或真实模型验收。

## 下一次真实DeepSeek验收（等待人工审查）

先审查本提交、离线测试及预算，不在本轮继续付费。获单独授权后仅运行一次完整四文档B01，重新核对实际剩余额度、脱敏/解析确认及最终SDK预算；记录实际模型版本、输入/输出/推理Token、服务商状态、格式/证据/语义三层结果。重点核查三次旧失败对应的D01+D04、D04标题及D01+D03问题：来源是否完整、主证据是否恰当、reasoning是否有价值且归属正确。遇新失败按安全诊断处理，不猜测未保存的原文，不自动重试。

## 测试记录

基线642项通过（53.426秒）；先新增20项缺模块失败测试，最终新增44项（40核心及4 AppTest）。完整686项全部通过，58.789秒，见根TEST_REPORT及[完整日志](v2e_offline_tests.txt)。原测试仅显式配置UI历史夹具为1.1，保留所有旧断言，新默认1.2另有实际AppTest。本轮真实模型调用0次，没有读取或修改Secrets、现有额度数据库、CASE-001原件或Gold，没有部署、合并或修改main及既有验收分支。

## 修改文件

- 新增`multidoc_v12.py`：完整1.2请求、恢复、校验、回执绑定与历史审计重放。
- 新增`pending_catalog.py`，调整`prototypes/pending_evidence_selection.py`：生产与原型共用目录及选择类型，不依赖离线原型执行生产逻辑。
- 修改`multidoc_ai.py`：复用一次调用门禁、1.2版本分派、原子导入及输出哈希/记录链接；旧1.0/1.1校验逻辑保留。
- 修改`multidoc_ui.py`：默认1.2、明确历史入口、预检诊断及手动导入。
- 修改`workspace_bundle.py`：1.2安全字段白名单、目录/选择/推断重验、分析附件兼容；ZIP格式不变。
- 新增`tests/test_v2e_integration.py`、`tests/test_v2e_ui.py`；调整`tests/test_multidoc_ui.py`历史夹具，原断言保留。
- 新增`tools/prepare_v2e_b01.py`、`docs/V2E_B01_BUDGET.json`：固定虚构四文档预算与SDK本地序列化复核，无真实调用开关。
- 修改`project_archive.py`下载白名单；更新`README.md`、`TEST_REPORT.md`；新增本技术文档与`docs/v2e_offline_tests.txt`。
