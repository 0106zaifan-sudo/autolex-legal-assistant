# V2.0-B 验证失败安全诊断补丁

基线 `a717d63593b303dc0eeee3abebf2c01789dd7a08`；独立分支 `feature/v2b-validation-diagnostics`。原工作区干净，在独立 worktree 开发。

## 能确定的失败原因与不能确定的部分

用户提供的真实回执显示服务商 completed、格式 passed、证据 failed，说明服务调用和顶层结构化解析成功。旧代码将引文定位、单文档投影校验、时间绑定、事实分类、推断和输出质量错误汇总成 output_validation_failed，没有保留具体规则与条目。因此无法仅凭 6090/2337/8427 Token 判断是哪条证据失败，本轮也没有读取那次模型原始输出或私有验收文件。

原有明确的强关系语义拒绝通常会记录 evidence_status=passed、semantic_status=rejected_by_conservative_policy。所述 pending_human_review 更符合在该阶段之前失败，仍不能据此确定具体错误。

对四份公开 samples_multidoc 原始材料的离线核查发现：

- 现场记录和电子摘要事件行都有“事件编号：SIM-V2-001；…”前缀；整行作为 timeline 引文跨越分号，既有时间绑定拒绝为 timeline_multi_sentence。电子摘要还含“原始日志未提供。”第二句，整段引用也跨句；来源块可能保留换行。
- 在同一 source 内采用分号后完整事件句、保留逐字正文和原始坐标，可通过绑定；不能替模型静默剪裁引文。本轮测试验证整行失败、合法事件句成功，没有改样本或验证规则。
- 原文现场08:30与电子摘要08:31分别绑定，各自保留。借用另一段或另一文件时间、错误精度、未知时间附带日期仍拒绝。
- 驾驶人/企业材料正文分别为“驾驶人未收到接管提示”“系统已发出接管提示”，没有显式“主张”前缀。不能据文件名断言这次真实失败一定触发 CLAIM_MARKERS。人工构造带主张前缀的反例仍被拒绝为 claim_or_uncertainty_as_fact。
- 关系/待核实推断需原文支持、正确待核实前缀和问号；无依据引入时间、EDR/DSSAD或断言日志必然存在仍拒绝。发出与收到不是同一命题，强支持/不一致不满足保守规则仍在独立语义阶段拒绝。

这些是已复现的可能路径，不是实际 DeepSeek 输出根因的证明。

## 安全诊断结构与定位

失败回执新增 `validation_diagnostic`（成功回执不新增伪失败项）：

```json
{"version":"multidoc-diagnostic/v1","stage":"document_binding","rule":"timeline_multi_sentence","section":"timeline","item_index":0,"item_index_base":0,"source_ids":["MD_0123456789abcdef01234567"],"trigger_source_id":null,"document_ids":[]}
```

stage 区分 format、batch、reference、document_format、document_binding、inference、output_quality、semantic_policy 及 call 等阶段。section 为 facts/timeline/pending_evidence/relations；index 指模型顶层列表中从0开始的位置，而不是按文件分组后的局部位置。time_source 失败也保留其触发编号。根级或聚合错误没有唯一所属条目时使用 null，不假造索引。

规则包括引文缺失/不唯一、跨案/跨文件、快照/原件/坐标错误、时间跨句/截句/正文不匹配/借用日期/精度/未知状态、重复事件、主张或未核实材料冒充事实、推断依据和格式、问题质量，以及强关系语义不受支持。已知旧异常文本只做固定代码映射，未知异常统一安全 fallback，绝不序列化异常正文。测试检查既有静态校验异常均有映射，未来新增规则应同步补映射。

格式异常只提取白名单 section、整数 index，必要时提取该条来源编号；不保存 Pydantic input/msg/context 或完整 loc。来源编号仅接受本批次编号或固定 MD_ 十六进制格式，异常编号脱敏为 rejected_source_id。文档编号由可信来源清单反查，不输出文件名、位置文本、引文、模型输出、密码、密钥或完整请求。

保留原 Token usage、服务商/模型状态、错误代码、快照、Prompt 哈希及计费回执。调用失败/拒绝/超时/取消也有安全阶段代码；模型调用前的权限、授权、解析、预算失败保持原阻断行为，不伪造服务商回执或 Token 消耗。

## 技术改动与安全边界

- `validation_diagnostics.py`：独立安全映射和格式定位。
- `multidoc_ai.py`：显式规则、全局索引映射；逐项复用原 validator 定位，再运行原整文 validator 和质量处理，保留聚合限制与重复事件拒绝。没有修改 Prompt、Schema、原文哈希算法、时间安全规则或 SDK/QuotaStore。
- `multidoc_ui.py`：在既有当前案件/批次安全回执区域增加 JSON 下载，失败仍无可导入结果。
- 两个新增测试文件：35项核心 Mock/离线规则测试与1项界面回执测试。界面测试恢复 AppTest 修改的 __main__，避免污染后续 multiprocessing spawn 超时测试；未改原断言或生产运行器。
- `project_archive.py`：下载源码包白名单包含新模块、测试和报告。
- README、TEST_REPORT 与测试日志：记录真实执行结果。

CaseStore、案件 Schema、原人工审阅历史和原子导入流程未改。失败仍抛出异常，不返回有效结果，不写入案件。诊断默认只报告第一个错误；同一次输出存在多个错误时，逐项检查可能改变首个报告错误的先后顺序。未知的将来异常可能只有阶段与 fallback，不能保证定位到唯一条目。

## 离线验证与下一次真实验收

先增加失败测试，再实现诊断；完整结果见 `v2b_validation_diagnostics_tests.txt` 和根目录 TEST_REPORT。模型响应全部为本地注入/HTTP mock，真实 API 调用0次。原固定样本、原351项测试及其断言不变。

下一次需人工审查本补丁并明确授权后，在同案选择原四份虚构材料、逐份确认解析风险、对本批次一次授权，只执行一次真实联合分析，不自动重试。展开“最近联合调用安全回执”，下载“联合验证安全回执（不含原文）”。失败时提供 validation_diagnostic、三层验证状态、服务商模型与 Token 用量即可定位首个规则、顶层条目和来源编号；不要分享密钥或真实案件原文。诊断仍不足时再审查经授权的虚构材料输出，不通过反复付费重试猜测。

离线通过不代表真实 DeepSeek 引文及语义验收通过；本补丁不改变模型输出质量，亦不自动修复不可信结果。本轮不付费、不部署、不合并。
