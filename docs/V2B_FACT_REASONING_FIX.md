# V2.0-B facts.reasoning 输出协议补丁

基线：`feature/v2b-validation-diagnostics`，`7fef12a74258fb9adcf97b902a031885bbc63bb4`。独立分支：`feature/v2b-fact-reasoning-fix`。开始前基线工作区干净，另建 worktree，没有覆盖用户修改。

## 根因与最小修改

第二次真实调用的安全诊断已经定位 facts[0] 的 non_inference_reasoning_forbidden。原 ai_analysis.validate_analysis 对事实和主张均执行 `elif item.reasoning: raise AIError(...)`，该规则合理且保持原样。

联合 Prompt 原来只对推断说明 reasoning 的格式，未明确非推断必须为空。FactItem 继承 Item.reasoning 的普通字符串（最大600字符），因此不合规的说明可以先通过联合格式校验，再在单文档证据验证时失败。这是生成协议与既有本地约束表达不一致，本轮不判断模型具体写了什么内容，不读取旧私有运行文件。

生产逻辑仅修改 multidoc_ai.py 三行：

1. Prompt 明确 facts 中 kind=事实或kind=主张时，reasoning 必须为严格空字符串 `""`，不允许缺省、空白、null、解释或推断；核查问题放 pending_evidence，独立引用。
2. FactItem 覆盖 reasoning，保持必填 `str`，设置 `max_length=0`，生成 JSON Schema `type=string, maxLength=0, enum=[""]` 并附字段说明。无默认值，无转换/裁剪/删除逻辑。

空字符串通过；任何非空内容（包括空格和换行）、null、非字符串及缺字段失败。没有自动删除 reasoning 再宣称成功。

## 诊断与兼容性

同类不合规输出现在提前在 format 阶段被拒绝：rule=schema_rejected，section=facts，item_index 为实际索引，保留必要来源编号。format_status=failed_or_unavailable，evidence_status=not_run；服务商 completed 和实际返回 usage 仍保留。这是失败阶段前移，不是降低证据要求。原 document_binding/non_inference_reasoning_forbidden 和全部安全映射仍存在，离线测试直接验证原 validator 仍拒绝事实/主张的非空说明。

没有更改 ai_analysis.py、时间线/推断/关系字段、证据算法、CaseStore、权限、额度、超时、SDK运行器、安全诊断模块或原人工复核历史。现有正常事实/主张输出本就必须 reasoning 为空，结构版本 multidoc-analysis/1.0、prompt_version=multidoc/v1 保持兼容；本次属于把已有禁止条件前置到生成契约，并非新增案件字段。已有回执的 prompt_sha256 记录实际 Prompt 差异，batch_sha256 随 Prompt 哈希变化，旧批次授权不会复用。

JSON Schema 的 enum、maxLength 是现有接口已采用的关键字，没有引入 const、条件组合或自定义 Schema 关键字。保持现有 DeepSeek Responses 适配：不发送 strict/store/truncation，顶层 reasoning.effort=none 不变。该顶层服务商参数与 facts[i].reasoning 是不同字段。OpenAI strict=true 保持原样。

12项新增离线测试使用官方 OpenAI Python SDK 和 httpx.MockTransport 验证两家服务商的发送格式、正常响应、违规响应、单次请求、零重试参数、额度消耗、usage、安全诊断与失败不写案件；没有网络模型请求。Mock 能证明本地 Schema、SDK序列化和适配兼容，不能证明 DeepSeek/OpenAI 服务端接受或服从约束。真实服务端兼容与输出质量仍需下一次明确授权的调用确认。

## 行为与风险

| 项目 | 修改前 | 修改后 |
| --- | --- | --- |
| facts.reasoning 空字符串 | 通过格式，继续证据验证 | 相同 |
| facts.reasoning 非空字符串 | 格式通过，后续原规则拒绝 | 格式立即拒绝，不修剪 |
| 缺省/null/非字符串 | 本地拒绝 | 继续拒绝，必填无默认值 |
| pending_evidence/relations.reasoning | 原格式与证据规则 | 相同，保留核查问题 |
| timeline与原文引用 | 原绑定规则 | 相同 |

其他字段的 Schema 和验证代码未变。但任何 Prompt 改动都可能影响模型对 facts/pending_evidence 的选取、措辞、顺序及Token用量；不能保证真实模型其他字段输出逐字不变。更严格约束也可能使服务商直接拒绝 Schema，或模型仍不遵守并导致格式失败，本轮不会自动回退为宽松 Schema或重试。此前已有非空 reasoning 的无效结果仍不能导入；不修改已有历史。

## 文件与验证

- multidoc_ai.py：一条Prompt约束和FactItem字段收紧。
- tests/test_fact_reasoning_contract.py：12项新增测试，复用虚构 fixture，不继承/重复计数原测试。
- project_archive.py：补丁测试和文档加入源码导出白名单。
- README.md、TEST_REPORT.md、本说明和 v2b_fact_reasoning_tests.txt：使用边界及真实离线日志。

先新增测试，在旧代码上复现契约缺失，再实施补丁；完整测试数字见 TEST_REPORT 和同目录日志。原387项测试及断言不变。真实API调用0次，不读改Secrets、不部署、不合并。

人工代码审查后，下一次最小真实验收仍使用原四份虚构材料，一次明确授权请求，检查 Schema 是否接受、所有 facts.reasoning 是否为空、facts/pending_evidence 分类与原文对应，以及原时间线/跨文件候选有无遗漏。失败时下载安全诊断回执，不自动重试。本轮离线通过不是新的真实验收通过。
