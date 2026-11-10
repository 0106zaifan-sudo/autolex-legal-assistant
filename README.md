# 智能网联汽车法律资料整理与检索助手

面向法学及司法鉴定研究生的 AI 法务实习演示项目。第二阶段基线：`feature/ai-case-facts`；P0证据绑定补丁：`feature/fix-evidence-binding`；本轮案件/解析覆盖分支：`feature/case-structure-parse-coverage`。原有 PDF/DOCX 解析、规则提取、检索与 Excel 导出保持离线；新增可选的 OpenAI 官方 SDK 案件事实分析，并支持OpenAI/DeepSeek官方Responses接口切换。AI 需要单独配置 Secrets、登录并确认发送资料，可能产生 API 费用。未配置密钥时禁用 AI，不用模拟结果冒充模型输出。

## 架构与文件

```text
浏览器 / Streamlit（app.py）
  → PDF / DOCX 解析（core.py: read_units）
  → 原文规则提取（core.py: extract）
  → 会话内资料及人工核验日志
  → 全文关键词 / 法院 / 核验状态 / 数据类型筛选
  → Excel 五张表（core.py: export_excel）
  → 可选 AI（ai_analysis.py）→ 官方 Responses API 结构化输出
  → 引文/分类/位置校验 → 四类分析及带来源的 JSON 导出
访问门禁（ai_ui.py / security.py）在所有上传、查看和下载之前运行。
```

- `app.py`：网页入口，导入、筛选、原文比对、逐项人工核验、下载。
- `core.py`：独立业务逻辑；不依赖 Streamlit，可以单独测试。
- `samples/`：6 个明确标识的虚构样本，两个主题各有 PDF/DOCX，另有字段缺失 DOCX、无文字 PDF。
- `make_samples.py`：重建样本。虚构法院、2099 年虚构案号、虚构规则均仅供测试。
- `tests/`：解析、出处、缺失值、核验、检索、导出及 Streamlit 交互测试。
- `TEST_REPORT.md`：实际验证结果与范围。
- `ai_analysis.py`：Pydantic 输出模型、官方 SDK 请求、原文和分类校验。
- `ai_ui.py`：访问验证、AI 面板及离线模拟演示。
- `security.py`：Secrets 配置、密码哈希验证、SQLite 原子额度及并发控制。
- `project_archive.py`：项目下载白名单，排除 Secrets、Git 历史和运行数据库。
- `samples_ai/`、`make_ai_samples.py`：独立的第二阶段虚构事故材料及固定响应，不改变原6份样本。
- `.streamlit/secrets.example.toml`：空凭据配置模板；不是实际密钥文件。
- `PHASE2_ACCEPTANCE.md`：第二阶段逐步验收方法和安全边界。

## 从零启动（推荐 Python 3.12）

先将整个项目文件夹保存到电脑，进入该文件夹。下列命令每行分别执行。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

首次启动默认使用公开模式，无访问配置时会锁定页面。**仅在自己的电脑离线演示**，创建 `.streamlit/secrets.toml`，内容如下：

```toml
APP_MODE = "local"
```

此时原功能与明确标识的离线模拟分析可用，AI 调用保持禁用。不要把 local 模式用于公开部署。配置文件已加入 `.gitignore`。

浏览器打开 **http://localhost:8501**。此地址指运行命令的那台电脑。在云端启动时，需要平台提供的 8501 端口预览/转发入口，不能用自己电脑的 localhost 访问云端。

首次安装依赖需要网络；之后规则功能和固定模拟分析可离线使用。程序关闭 Streamlit 使用统计。只有用户确认并点击 AI 按钮时，所选文档正文及证据绑定所需的文件/解析文本哈希与版本标识才发送到官方 OpenAI API；文件名不发送。安装依赖使用包仓库。请先用模拟资料演示。

运行测试：

```bash
python -m unittest discover -s tests -v
```

上述 `python` 请替换为虚拟环境 Python 路径。重建样本：`python make_samples.py`。

## 三分钟演示顺序

1. 点击“加载模拟测试样本”，确认 6 份资料、全部初始待人工核验。
2. 搜索“消费者 宣传”，应出现辅助驾驶主题的 PDF、DOCX 两份资料。空格分隔的关键词须同时出现，可命中全文。
3. 选择一份资料，在字段候选表中查看争议焦点、法律依据及页码/段落；右侧比对原文。
4. 将一个有原文的候选设为“已人工核验”，填写核验人和“仅核对模拟原文一致性”，保存。其余字段仍待核验，因此整份资料保持待核验。
5. 清空关键词，查看“模拟_信息缺失.docx”没有补写法院或条款；查看“模拟_无文字页.pdf”的提示。
6. 按法院或数据类型筛选，下载 Excel，展示“字段与出处”和“核验日志”。
7. 左侧“下载完整项目 ZIP”可保存代码、样本和文档。

## 字段与核验原则

| 字段 | MVP 做法 | 需要人工确认的内容 |
|---|---|---|
| 文件名 | 保留上传文件名，并计算内容 SHA256 | 文件来源、命名是否准确 |
| 法院 | 匹配正文中的“……人民法院”候选 | 是否是审理法院，而非引用其他法院 |
| 案号 | 匹配括号年份与“号”结构 | 是否完整、是否属于本案 |
| 争议焦点 | 仅摘录“争议焦点：/争议的焦点：”所在行 | 跨行内容、是否是裁判归纳而非当事人意见 |
| 法律依据 | 摘录书名号名称及紧邻条款 | 可能只是文献或主张，不能认定是法院采用的依据 |
| 原文位置 | PDF 物理页序；DOCX 正文段落或表格行列；字符区间 | PDF 排版提取可能乱序，需对照原文件 |
| 核验状态 | 全部初始“待人工核验” | 用户逐项核验，有记录才可变更 |

规则只做高可解释性的候选提取，可能漏检、误检；例如法院前缀、跨行案号、分隔的条款。不会将规则结果自动升级为已核验，也不会在缺失时生成“看起来合理”的法律信息。多个候选全部保留。摘录是对文档中出现内容的记录，不代表该内容正确。

“已人工核验”是用户填写的判断，程序不确认核验人身份、不联网验证权威来源。核验备注应注明范围：仅比对原文，或另行核查了法院公开信息、法规版本及有效性。模拟样本即使比对一致，仍然是模拟数据，不能变成真实案例。

资料整体状态按“提取有误 > 待人工核验 > 已人工核验”汇总。缺失字段不能设为已核验，需要补充来源；此版不提供直接改写候选，以便保留提取证据。

## 已知范围与限制

- PDF 必须有可提取文本层；无文字页仅提示，不含 OCR。部分扫描页/乱码不能可靠自动识别。加密 PDF 拒绝处理。
- DOCX 读取正文段落、正文表格及嵌套表格，按物理XML单元格检查覆盖；页眉页脚、批注、修订、文本框、域或图片等未支持区域生成报告，不擅自补写。段落号不是 Word 页码。
- 单文件 20 MB；PDF 最多 300 页；DOCX 解压总量最多 80 MB。面向可信的个人演示资料，不是互联网多租户文件服务。
- 数据只在会话内存中。刷新重连可能丢失会话，服务重启必然丢失；及时导出 Excel。Excel 是离线成果，不提供重新导入核验记录的功能。
- Excel 包含总表、字段与出处、原文分片、核验日志、说明。长正文分片保存，字段候选单格受 Excel 32767 字符限制。原始二进制文件不嵌入 Excel，请另存原文件。
- 文件名和正文等导出值会防护 Excel 公式注入。SHA256 只能用于文件一致性检查，不证明文件真实性。
- 未增加案件持久化数据库或独立用户账户；访问控制使用共享访问密码，调用限制使用独立 SQLite 数据库。没有语义搜索、自动法律意见或联网法规更新。AI JSON 单独下载，原有 Excel 格式不变。

## 11 月 10 日前的展示安排（北京时间）

| 日期 | 任务 | 验收 |
|---|---|---|
| 2026-11-06 | 完成 MVP、样本、测试 | 能打开页面、检索、核验和导出 |
| 2026-11-07 | 在自己的电脑安装，按演示顺序走通 | 保存 Excel 和页面截图；记录环境问题 |
| 2026-11-08 | 经许可加入 2–3 份脱敏真实资料，逐项比对 | 写出漏检/误检及法律效力核查范围 |
| 2026-11-09 | 冻结功能，导师演示彩排 | 准备 3 分钟讲解及离线 Excel 备用成果 |
| 2026-11-10 | 留作展示与修复缓冲 | 展示原文可追溯和“不编造”的处理机制 |

展示可先演示原文整理，再展示新增的“关键事实及主张、事故时间线、法律争议焦点、待核实证据”四类分析。没有 API 密钥也能查看明确标注的固定模拟响应；不要将此演示描述为真实模型调用。

## AI 配置与第二阶段验收

完整步骤见 [PHASE2_ACCEPTANCE.md](PHASE2_ACCEPTANCE.md)。最小公开配置需要 `APP_MODE="public"`、`APP_PASSWORD_HASH`，没有密码哈希会锁定全部资料功能；AI另外需要选定服务商的密钥、`AI_SINGLE_INSTANCE=true`和可写的SQLite存储。`AI_PROVIDER`支持`openai`或`deepseek`，分别读取`OPENAI_API_KEY`或`DEEPSEEK_API_KEY`；新模板推荐DeepSeek，旧配置缺省保持OpenAI。普通环境只从Streamlit Secrets读取；Codespaces可安全补入所选服务商同名Secret，不提供网页密钥输入框。详见[多服务商配置与Codespaces步骤](docs/MULTI_PROVIDER.md)。

生成访问密码哈希：`python tools/hash_password.py`，在自己的终端交互输入密码；只把生成的哈希写入 Secrets，不提交密码、哈希或实际 Secrets 文件。官方 SDK 使用固定官方 API 地址、SDK阶段30秒及默认45秒进程总截止、关闭自动重试、输入24000字符/80块及输出4000 token上限。OpenAI保留`store=False`和原有严格Schema；DeepSeek使用官方无状态Responses协议及文档列明的JSON Schema参数，不发送不支持的store/truncation。协议配置不等于服务商零保留承诺。OpenAI默认`gpt-4.1-mini`，DeepSeek默认`deepseek-flash`；实际可用性和费用取决于API账户，未进行真实调用。

## P0-A 证据绑定补丁（Schema 2.0）

时间线事件现在必须使用唯一、完整的原文句段；时间锚点必须位于同一事件引文中，不能借用维修日期或其他段落。未知/无法支持的时间显示“未知”，不会生成具体日期。返回数据区分date/minute/second/unknown精度，日期不补00:00；同日含仅日期记录时不声称日内顺序。

文件和解析文本快照绑定、Schema/Prompt/解析契约版本随JSON导出。模拟响应已明确迁移到2.0，旧响应不自动复用，需重新分析。现有界面和原资料整理流程未修改。完整验收、测试结果和局限见 [证据绑定补丁说明](docs/EVIDENCE_BINDING_PATCH.md)。

## P0：案件结构与解析覆盖

新增案件工作区，支持显式归档文档、原文摘录、基本信息候选、当事人主张、材料记载、人工确认、时间线及待核实事项。没有密钥也可加入明确标注的离线模拟案件，不发起模型调用。

原件仅保存在会话内存，可按案件下载；案件JSON保留哈希、原文位置及复核记录，不内嵌原始文件字节。PDF逐页、DOCX逐段及单元格生成解析报告；PDF视觉表格始终标明完整性未核验。未覆盖范围不能当作没有证据。解析版本升级至`core.read_units/v2-coverage`，旧记录需重新读取。

完整流程、113项实际测试及剩余限制见 [案件结构与解析覆盖说明](docs/CASE_STRUCTURE_COVERAGE.md)。当前不提供案件JSON恢复导入、OCR、真实材料真实性核验或公开多租户能力。

## P0真实模型验收准备（尚未真实调用）

分支`feature/live-ai-acceptance`基于案件结构分支。新增累计输入预算、默认真实调用进程总截止、服务端模型/usage及失败校验的调用记录，并准备两份固定模拟事故材料。

`python tools/run_live_acceptance.py`默认仅准备，不读Secrets、不调用模型。当前真实尝试0次，模型返回和token均未获得。安全配置、本人终端认证和显式费用确认后才能运行两份真实验收；详见 [真实验收准备与安全配置步骤](docs/LIVE_AI_ACCEPTANCE.md)。不要在聊天发送密钥或密码，不把mock当真实效果。

## 多模型API服务商（当前优先DeepSeek）

开发分支`feature/multi-provider-deepseek`继承`feature/live-ai-acceptance`。服务商配置不改变案件结构、引文核验、解析覆盖确认和单实例共享限流；不同服务商不共用密钥、不自动切换。调用回执新增provider、端点及缓存/推理token对账记录，未知费用不填零。

[完整配置、官方兼容性核对、Codespaces及SIM_A/SIM_B验收步骤](docs/MULTI_PROVIDER.md)。本轮仅完成离线工程验证，未执行真实付费调用，也未部署公开网页。最新测试结果见[TEST_REPORT.md](TEST_REPORT.md)。

## 固定SIM_B失败定位（完全离线）

`python tools/replay_sim_b.py`生成9项人工构造对照，不读取Secrets、不访问模型。可选私有调试仅面向哈希固定的SIM_A/SIM_B，默认关闭，失败输出不作为有效案件结果。操作和下一次真实复测清单见[SIM_B调试说明](docs/SIM_B_DEBUG.md)；本轮不修改分类规则，也未执行付费验收。

## 单场景验收准备

`python tools/run_live_acceptance.py --scenario SIM_B`只做SIM_B的离线准备，不读取Secrets、不调用API；可改为SIM_A，不传参数保留双样本选择。报告始终列出两份场景并明确未选场景未运行。真实调用仍需原显式费用确认与本人认证；[完整说明、预算与UI测试隔离](docs/SINGLE_SCENARIO.md)。本轮仅完成离线测试。

## P1输出质量（独立开发分支）

`feature/output-quality-p1`基于`9ea9fd1`，先完整核验原文证据，再将误放facts的推断移到待核实列表，仅精确重复合并，已知模拟声明保留为文件元信息。分析JSON含quality_audit，保留处理前条目与来源。重复病句或待核实项超原容量上限明确拒绝，不自动改写或重试。

Schema 2.0兼容不变，新增独立prompt_revision/output_quality_version及原Prompt哈希追踪；原始validator与历史JSON回放保持兼容。24项新测试加原223项全部离线通过，本轮未进行真实模型复测。具体前后对照、文件清单和最小真实复测建议见[P1说明](docs/OUTPUT_QUALITY_P1.md)。

## V1.1未知时间事件补丁

独立分支`feature/output-quality-p1-timeline`强化Prompt：原文支持的重要事件即使无日期也应列timeline，facts与timeline的合理复用不属于重复。新增只读的timeline_completeness诊断和UI警告，提示重要事件/时间核查问题可能遗漏，不自动补事件或日期；no_gap_detected也不是完整性证明。原金标准、证据绑定及P1质量规则未改。

本轮267项离线测试通过，未调用真实API。根因、完整修改清单及下一次最小复测见[时间线补丁说明](docs/TIMELINE_COMPLETENESS_PATCH.md)。

## V2.0-A多文档证据关系

同案归档多份文件、保存引用后，可离线发现关系候选、并排核对、追加人工审阅并导出1.1案件JSON。候选和人工关系判断均不确认真实性或责任。操作、样本、兼容策略与风险见[多文档说明](docs/MULTIDOC_V2A.md)。

## V2.0-B AI多文档综合分析

独立分支feature/v2-multidoc-ai：同案选择2—4份材料，逐份确认解析风险，并另行授权一次联合请求。来源使用批次全局ID，结果整批验证后预览，明确点击才原子导入。关系和时间差异均待人工核验；导入后案件版本1.2保留原建议、回执及既有审阅。单文档Schema和V2.0-A流程保持兼容。

351项离线测试通过，本轮没有真实API或部署。[详细流程、数据结构、限制及建议验收方案](docs/MULTIDOC_AI_V2B.md)。

## V2.0-B验证失败安全诊断

独立分支 `feature/v2b-validation-diagnostics` 在失败安全回执增加 validation_diagnostic，记录规则、阶段、顶层条目索引与脱敏来源编号，同时保留Token用量。当前批次回执可下载JSON；失败内容仍不能导入案件，不改变原证据约束或案件结构。新增36项测试，完整387项离线通过，没有真实API调用。[诊断边界、模拟材料复现及下一次验收](docs/V2B_VALIDATION_DIAGNOSTICS.md)。

## V2.0-B事实 reasoning 协议修复

facts 中事实/主张的 reasoning 必须为必填空字符串，Prompt与JSON Schema同步表达原有规则；违规输出提前拒绝，不自动清空。原证据、安全诊断、时间线和跨文件校验不变。完整399项离线测试通过（新增12项），未调用真实模型。[契约兼容、影响范围与复测说明](docs/V2B_FACT_REASONING_FIX.md)。

## V2.0-B时间线引文指导修复

联合Prompt明确独立完整句段、内部标点/换行边界及主体/否定/时间保留要求；不能安全拆分时保守保留有来源信息与待核查问题，不自动制造事件。原validator与facts空reasoning契约不变。完整418项离线测试通过（新增19项），无真实API调用。[规则复核、固定样本反例和真实复测边界](docs/V2B_TIMELINE_QUOTE_FIX.md)。

## V2.0-B候选事件选择（结构性修复）

网页新请求采用 `multidoc-analysis/1.1`：调用前从原文构建带坐标/哈希的候选句段，模型只返回候选ID与事实/主张类型。程序恢复原文与时间，再完整运行原证据验证，失败不导入、不自动重试或回退自由引文。原facts空reasoning、时间差异、人工审阅和额度控制保留。编程新调用入口为 `analyze_case_candidates`；旧1.0入口仅保留兼容。完整456项离线通过（新增38项），无真实调用。保守候选可能漏事件，仍须人工核查。[设计、Schema、兼容与风险报告](docs/V2B_EVENT_CANDIDATES.md)。

## V2.0-C案件工作包与工作区恢复

在案件工作区展开“下载案件工作包”，可明确选择附带当前可用的已验证联合分析JSON，点击生成后下载含manifest、案件JSON及PDF/DOCX原件的ZIP。没有缓存就不附带；恢复的历史附件也可再次显式选择保存。

空会话也可打开“案件工作包导入工具”，上传ZIP、勾选确认后点击导入。系统限制大小/路径/压缩比，重解析全部原件并核验哈希、坐标、事实/主张/时间线、关系与审阅引用，全部通过才原子加入会话。同case_id拒绝覆盖，失败不污染旧案件，不恢复AI授权或配额，不自动调用模型。原JSON＋全部原件另有受限1.1/1.2恢复入口，未知版本或快照不匹配拒绝。

原“结构化JSON”仍不包含原件。工作包未加密、未签名，含原件和人工历史，请离线妥善保管；导入历史不等于身份认证或重新真实性确认。完整505项离线测试通过（新增49项），无真实模型调用。[格式、操作、限制与完整测试说明](docs/WORKSPACE_V2C.md)。

## V2.0-D证据冲突审查工作台

在案件工作区保存不同材料引用并发现关系后，打开“证据冲突审查工作台”，可筛选时间记载、提示命题、信息缺口和最新人工状态，并排核对完整引文/上下文、位置与哈希。原候选、当前只读规则解释、人工结论分开显示；修改/驳回/再次审阅只追加原RelationReview历史，不确认事实或责任。

08:30与08:31可显示1分钟字面差，但时区/时钟未认证，实际时间比较保持不可用。发出、输出、接收、感知分开；复杂归属、否定、引语或不满足条件的时间回待核实。CaseBundle和工作包版本不变，恢复后同版本视图可重算，筛选草稿不持久化。完整542项离线通过（新增37项），无真实模型调用；真实浏览器和人工语义仍待验收。[规则、操作、边界及测试说明](docs/CONFLICT_REVIEW_V2D.md)。

CASE-001 B01待核实事项字段契约、离线回归及预算复核见[修复说明](docs/B01_PENDING_TEXT_FIX.md)。真实DeepSeek效果仍需另行人工授权验收。

CASE-001 B01技术术语来源范围、显式标题引用及语义限制见[调查与最小修复](docs/B01_SUPPORTED_DATA_TERMS.md)。词面校验通过不等于技术推断成立。

独立离线研究：待核实事项支持“人工/模型显式选择证据编号→程序恢复原文→原校验器重验”的[原型与架构评估](docs/PENDING_SELECTION_PROTOTYPE.md)。可运行`python tools/run_pending_selection_prototype.py --output /tmp/AutoLEX_pending_selection_demo.json`查看固定虚构演示；不调用模型、不读取Secrets、不导入案件，尚未接入网页或付费验收。

V2.0-E已集成`multidoc-analysis/1.2`：联合分析默认选择1.2，保留1.1历史入口；待核实事项由模型明确选择PE编号，程序恢复原文并严格核验，四个分析模块仍为一次请求。预览不会自动导入，所有结果待人工核验；1.0/1.1历史及案件ZIP继续按版本校验。[技术、兼容及人工网页验收说明](docs/V2E_INTEGRATION.md)；[离线预算报告](docs/V2E_B01_BUDGET.json)。可运行`python tools/prepare_v2e_b01.py --output /tmp/AutoLEX_V2E_B01_budget.json`复核完整B01，工具只用本地HTTP Mock，无真实模型或Secrets访问。本轮686项离线测试通过，真实DeepSeek1.2验收仍待另行人工授权。

V2.0-E格式失败新增安全Schema诊断：错误类型、白名单字段路径、总数及截断标记；不记录模型内容、不自动修复。详见[排查报告与诊断字段](docs/V2E_SCHEMA_DIAGNOSTICS.md)。本轮716项离线通过，不能据此认定首次真实格式失败已定位或解决。
