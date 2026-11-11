# 1.4：稀疏短别名证据选择生产集成

独立 worktree 分支 `feature/v14-short-evidence-aliases`，基线 b864800eda6c991c0e10b8cd6549c2cb93149258。开始时基线干净，745项基线测试全部通过（62.859秒）。先写26项旧代码缺少1.4模块而失败的规格测试，再实现；最终新增42项（39核心/SDK/预算/ZIP，3 Streamlit AppTest）。

最终执行 `PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps python -m unittest discover -s tests -v`：**787项全部通过，67.985秒**。保留原745项断言，仅历史1.3界面夹具显式选1.3；新默认1.4由独立AppTest覆盖。此前中间完整回归784项也通过，之后补3项预算及术语测试并重新运行全套。

专项验证：确定性别名及顺序稳定、单字符替换不落入合法集合、容量拒绝、动态Schema与本地上下文枚举一致、同批次未知/跨案/过期/快照变化/目录篡改拒绝、选中与未知编号诊断分开、主证据约束、重复问题与不同问题保留、合法但无关来源仍待人工审核、EDR标题支持与DSSAD无依据拒绝、四模块一次请求、未授权/未确认解析风险/预算/额度不足阻止调用、失败不导入、显式导入幂等及人工复核保护、混合协议拒绝、ZIP附件有无均恢复审计、重算清单的篡改ZIP原子拒绝。两服务商均通过官方SDK+本地HTTP MockTransport，零自动重试；AppTest覆盖新版入口、重新授权、错误显示、安全回执及禁止自动导入。

`python tools/generate_case_001.py --check` 通过（8份虚构材料、14个标准版文件）。原件、Gold、ai_analysis.py、security.py、ai_providers.py、multidoc_v12.py、multidoc_v13.py 与基线无差异。历史协议验证与CaseBundle/ZIP版本不改；仅扩展新协议分派及安全回执字段。

完整B01 D01—D04：62来源/62别名，DeepSeek预算76394字节、官方SDK本地序列化75370字节，OpenAI预算76414/实际75390，均低于128000；输出上限6000。真实Token未测为null，不以Mock用量估计费用。完整预算可重复生成并有断言。

本轮真实AI调用0次，不读取/修改Secrets，不访问现有配额数据库，不部署、不合并。跨批次别名可能碰撞，依赖完整批次上下文；合法但无关来源和问题语义仍需人工审核。没有取得此前第六次真实回执与原工作包，未执行精确同一性复核，也未用夹具替代。

详见[设计、兼容和下一次人工验收步骤](docs/V14_SHORT_ALIASES.md)、[B01预算](docs/V14_B01_BUDGET.json)、[完整离线日志](docs/v14_offline_tests.txt)。以上是离线验证，不代表真实DeepSeek输出可靠性或法律语义已验收。

以下保留历史报告。

# 1.3：程序拥有证据目录哈希

分支`feature/v2e-program-owned-catalog-hash`，基线`0e65f9501c65d9384b812c56b75aac0b98b44613`，干净基线独立worktree。基线716项通过，64.023秒。

先新增20项缺1.3模块失败的规格测试，最终新增29项（26核心、3 AppTest）。完整`python -m unittest discover -s tests -v`：**745项全部通过，65.706秒**。原716项检查意图保留；仅将`tests/test_v2e_ui.py`历史夹具显式设置1.2，旧断言全部保留，新默认1.3由独立AppTest覆盖。

1.3响应Schema完全没有pending_catalog_sha256字段，不设默认、不补字段、不调用旧1.2验证器修补响应。程序请求前计算目录SHA，响应后重建比对，保存安全回执及审计。模型仍显式选择全部PE来源；未知/跨案/目录变化/版本混用拒绝。旧1.2模块字节不变，缺哈希仍拒绝。四模块仍一次请求，显式导入及ZIP重验保持。

官方SDK+本地HTTP Mock覆盖两服务商，验证缺少模型回传哈希的新响应可通过格式及绑定，不自动写案；篡改目录、哈希、非法编号及重算清单的恶意ZIP恢复均拒绝且原子。AppTest验证新默认、重新授权、成功不自动导入及失败回执。DeepSeek预算94137、SDK本地序列化93113字节；真实Token未测为null。原件、Gold、旧预算及核心安全规则未改。

本轮真实模型调用0次，不读改Secrets或现有额度，不部署/重试/合并。Mock结果不能证明真实DeepSeek或法律语义通过。详见[设计与兼容风险](docs/V13_CATALOG_OWNERSHIP.md)、[预算](docs/V13_B01_BUDGET.json)、[完整日志](docs/v13_offline_tests.txt)。

以下保留历史报告。

# V2.0-E首次B01格式失败：安全Schema诊断

分支`feature/v2e-schema-diagnostics`，基线`f4717133631a9ad25074878540d174f39d9bd2be`，干净基线独立worktree。基线686项通过，57.179秒。

先增加28项旧诊断无法满足的HTTP Mock/安全测试（26项缺字段错误、1项失败，1项既有分块行为通过），实施后补2项历史兼容；共新增30项。最终完整`python -m unittest discover -s tests -v`：**716项全部通过，60.120秒**，原686项测试文件与断言不改。依赖通过现有PYTHONPATH指定；openai 2.54.0、pydantic 2.14.3。

覆盖JSON解析/空文本/围栏/根类型、缺字段、版本/字段类型/模式、额外字段、20条明细上限及完整60项统计、上下文路径白名单、未知键/类型/序号脱敏、多文本块拼接边界、旧1.0与文档解析版本。官方SDK全程本地MockTransport；失败仍一次请求、保留模拟Token、evidence=not_run、不写案件。没有实际服务商请求。

生产只改schema_diagnostic及辅助过滤；未改Schema、Prompt、SDK提取、证据、门禁或ZIP。新增字段不含msg/input/ctx/url、字段值或异常原文。不能由旧section=null定位真实字段，人工反例不是此次真实响应。Mock130用量与用户报告42762/3848无同一性。

本轮真实模型调用0次，不读改Secrets、原材料/Gold、现有额度记录，不部署、不自动重试、不合并main。详见[审查与限制](docs/V2E_SCHEMA_DIAGNOSTICS.md)、[完整日志](docs/v2e_schema_diagnostic_tests.txt)。

以下保留历史报告。

# AutoLEX V2.0-E：1.2证据编号选择生产集成

基线`a9bfe12c58e289b11c7bab3b12897896ee8fc66a`，独立worktree分支`feature/v2e-pending-selection-integration`。基线642项完整通过，53.426秒。

先新增20项旧代码缺少1.2模块而失败的规格测试，再实施。最终新增44项（40项完整B01/SDK/安全/预算/ZIP测试，4项AppTest），完整`python -m unittest discover -s tests -v`：**686项全部通过，58.789秒**，原642项的检查意图保留。原测试只调整`tests/test_multidoc_ui.py`夹具，显式选择1.1历史入口，全部旧断言不删；新版默认1.2由新增AppTest实际覆盖。运行使用既有PYTHONPATH依赖目录。

完整四文档B01 D01/D02/D03/D04，在一次请求中保留facts/timeline/relations/pending_evidence。PE目录确定性恢复text及全部选中来源，再走旧校验。覆盖此前三类失败反例、标题术语支持、非法/跨案编号、篡改目录/回执/恢复内容、主体误归属仍待人工审查、重复问题、额度不足、未授权/未确认覆盖、预算超限、长行碎片及目录上限、调用中档案变化、ZIP含/不含分析附件的审计恢复、同run_id内容冲突、重新计算清单后的恶意ZIP拒绝原子性、既有人工推断来源保留和明确导入。

官方SDK+本地HTTP Mock覆盖OpenAI与DeepSeek的Responses请求/动态Schema/响应校验和零重试；不是实际模型效果。SDK Mock实际序列化字节：DeepSeek 93379、OpenAI 93399，含余量预算94403/94423，低于128000。输入字符2015，输出上限6000；真实输入/输出Token未测，JSON报告为null。原始材料、Gold及原数据预算未改。

新1.2批次指纹与旧1.0/1.1独立，历史校验、案件结构和ZIP格式保持；回执只含安全ID/哈希，问题和恢复引文存案件记录，分析附件保留完整选择审计。未知或不合格输出整批拒绝，不自动补选、删项、改写、重试或确认事实。

本轮真实模型调用0次，不读改Secrets，不接触现有额度数据库；额度测试只用临时SQLite。不部署、不合并、不修改main或旧验收分支。引用绑定通过不证明法律语义正确，真实DeepSeek兼容性、输出完整性和网页人工语义验收仍未完成。

详见[技术与兼容说明/人工验收流程](docs/V2E_INTEGRATION.md)、[预算](docs/V2E_B01_BUDGET.json)、[完整日志](docs/v2e_offline_tests.txt)。

以下保留历史报告。

# CASE-001待核实事项编号选择：独立离线原型

分支`feature/b01-pending-evidence-selection-prototype`，基线`6998b6f968ee839a17a3df4d978dc3891e99080c`，独立worktree开发，基线工作区干净。

基线591项通过，50.535秒。先新增44项缺模块失败测试，再实施原型并补充7项，总新增51项；最终完整`python -m unittest discover -s tests -v`：**642项全部通过，54.087秒**。原591项测试文件、断言与生产代码均未改。实际运行使用既有PYTHONPATH依赖目录。

模型编号选择由人工夹具构造，不是DeepSeek响应。原型恢复全部明确选中来源、主引文及锚点，再走旧证据/术语/推断验证；未知编号、跨案/篡改、超限、漏主证据及任一失败整批拒绝，CaseStore不被修改。合法但错误主体/过度推断可通过字面绑定，专门测试标记此局限，语义仍待人工核验，原型禁止生产导入。

47项来源候选、1511原文字符、47901字节离线包；不是实际SDK请求/Token或成本指标。8份原件、Gold、数据预算与生成脚本均保持字节一致。工作包旧兼容不改，原型不能混入已验证analysis附件。

本轮真实模型调用0次，不读取Secrets或现有配额记录；原型不访问QuotaStore，完整回归的既有额度测试仅使用临时测试数据库。无自动重试/部署/合并。见[架构评估与结论](docs/PENDING_SELECTION_PROTOTYPE.md)、[完全虚构演示](docs/PENDING_SELECTION_DEMO.json)、[完整日志](docs/pending_selection_offline_tests.txt)。

以下保留历史报告。

# CASE-001 B01技术术语来源修复：最新离线测试

分支`feature/b01-supported-data-term-fix`，基线`fcfa64d92e3277fd035461fd82c851dae264e525`，独立worktree开发。

基线568项通过，55.044秒；新增23项后完整`python -m unittest discover -s tests -v`：**591项全部通过，55.731秒**。原568项测试文件与断言未改。先写规格及反例，旧Prompt的12个指令子断言失败、3项诊断字段测试缺字段，其余引用范围反例已复现。依赖使用既有PYTHONPATH，不读取Secrets。

改动只涉及联合Prompt和固定术语错误诊断；保留unsupported_data_term、text/quote/坐标/哈希/时间/分类及全部安全门禁。D04正文加同文档真实标题引用可保留合法核验问题；无依据DSSAD、伪造标题/跨文档配错source_id仍拒绝；导入只保留待核验推断。新增测试明确暴露词面支持不等于跨文件语义归属验证，不能宣称自动解决概念转移。

B01静态字节73371/128000，输入2015/16000。只刷新预算元数据和指纹；原件与Gold不变。真实模型调用0次，没有自动重试、部署或合并；Mock Token数字不是实际服务商费用。详见[分析与方案](docs/B01_SUPPORTED_DATA_TERMS.md)、[日志](docs/b01_data_term_offline_tests.txt)、[预算](docs/B01_DATA_TERM_BUDGET.json)。

以下保留历史报告。

# CASE-001 B01待核实事项契约修复离线测试

独立分支`feature/b01-pending-evidence-text-fix`，基线`202594c6ec88b152167e0080deb0a677467d325c`。

新增12项，原556项测试文件及断言不改；完整执行`python -m unittest discover -s tests -v`：**568项全部通过，56.269秒**。运行依赖通过PYTHONPATH指定现有离线依赖目录。新增测试先于生产修改，旧Prompt的10个指令子断言失败；反例已能复现text_not_in_quote，正例保留多来源核验问题。Token数字113等仅为Mock，不是真实服务商用量。

生产代码仅澄清Prompt。没有放宽或重写text、quote、来源及坐标；失败案件不被导入，没有自动重试。B01静态请求字节72462/128000，输入字符2015/16000，原件与Gold未变。完整[修复说明](docs/B01_PENDING_TEXT_FIX.md)、[测试日志](docs/b01_pending_offline_tests.txt)、[新旧预算](docs/B01_PENDING_BUDGET.json)。

本轮真实模型调用0次，不读取或修改Secrets，不部署。离线通过不等于真实DeepSeek验收通过。

以下保留历史报告。

# AutoLEX V2.0-D证据冲突审查最新离线测试

独立分支 `feature/v2d-evidence-conflict-review`，基线 `1df304f49b226cf1549a9d1e31280a660c3b7c26`。检查基线工作区干净后独立worktree开发。

基线复跑：505项通过，49.224秒。最终执行 `python -m unittest discover -s tests -v`：**542项全部通过，58.507秒**。新增37项（31项核心规则，6项AppTest），原505项测试文件及断言不修改。

先写19项旧代码无法通过的规格测试，再实现只读解释层与工作台。新增规则测试只用四份固定虚构材料及人工反例，不产生模型请求；原套件中的模型调用路径为本地Mock，不能作为真实模型效果或准确率。本轮真实模型调用0次。

覆盖1分钟字面差/实际时刻不可比、缺日期/精度/多时间/时区/覆盖条件、四环节区分、相反命题与复杂否定/引语、主体前后限定防截断、非法引文/坐标/哈希/跨案/副本、日志声明范围与否定防误判、只读无事实确认、多次审阅历史链、V2.0-C ZIP往返视图一致，以及实际AppTest筛选/选择/原文值/提交/查看历史/主界面/清空草稿。

两份固定PDF的partial仅含通用表格覆盖未验证警告；文本页read且锚点通过时允许纯字面算术，仍保留警告及实际时刻不可比标识。其他覆盖问题会阻断计算/强命题/缺口解释，旧解析器和确认机制不变。代码块修剪尾部换行的问题改用只读文本框解决，完整引文值仍逐字核验。

详见[开发说明](docs/CONFLICT_REVIEW_V2D.md)和[完整日志](docs/v2d_conflict_review_tests.txt)。本轮未读改Secrets、不使用真实案件、不部署、不合并。AppTest通过不等于真实浏览器排版或法律/司法鉴定人工语义验收通过。

以下保留历史报告。

# AutoLEX V2.0-C案件工作包最新离线测试

基线 `a1920b55c59262685bd8b8705c3bf53daa0afa1e` / `feature/v2b-event-candidate-selection`；检查工作区干净后另建worktree和分支 `feature/v2c-case-workspace-roundtrip`。

基线完整复跑：456项通过，35.781秒。最终完整执行 `python -m unittest discover -s tests -v`：**505项全部通过，47.595秒**。新增49项（44项工作包核心、5项AppTest），原456项测试文件及断言不修改。

先新增30项失败规格测试（旧基线缺工作包模块），再实现并扩展。第一次完整505项测试有1项原登录UI测试失败：新增上传控件使初始控件数量从1变4。已采用显式打开导入工具后才创建控件的方式修复，原断言保留；最终完整套件通过。其他新增测试中的关系fixture与DataFrame显示方式修正详见开发说明，没有放宽既有证据或语义规则。

覆盖四固定虚构材料保存→新会话→导入→重新校验→恢复显示→再次保存，原件/坐标/时间/关系/人工复核/回执与可选联合分析；缺文件、坏哈希、伪造引文、跨案引用、审阅链、来源/解析版本、历史候选编号/清单、AI原建议及推断重验；ZIP路径/加密/重复/链接/前后缀/限额、DOCX内部ZIP/DTD、重复/并发导入和失败原子性；受限旧JSON恢复、无缓存、无授权/配额/模型恢复、清空资料缓存。测试中的模型响应全部为本地Mock，Token数字不是本轮真实调用。

完整日志见[本轮日志](docs/v2c_workspace_tests.txt)，格式、界面、迁移边界与风险见[开发说明](docs/WORKSPACE_V2C.md)。真实模型调用0次，不读取或修改Secrets、不接触真实案件或私有验收文件、不部署、不合并main。工作包没有签名或加密，不能认证复核人身份或识别完全重写但内部自洽的伪造历史；恢复不等于重新确认真实性。

以下保留历史报告。

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
