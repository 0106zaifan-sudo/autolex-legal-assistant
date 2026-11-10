# V2.0-E首次真实B01格式失败：排查与安全诊断

独立分支feature/v2e-schema-diagnostics；基线feature/v2e-pending-selection-integration / f4717133631a9ad25074878540d174f39d9bd2be。检查基线工作区干净后建立独立worktree。以下分析只依据用户提供的回执和仓库代码，不读取私有回执/响应、Secrets或运行数据库。

## 已确认的代码问题

用户回执表明已收到completed响应，随后format=failed_or_unavailable、evidence=not_run，format/schema_rejected且section=null。本次不是当前代码路径下的网络/认证失败，也未进入证据绑定。用户报告总Token42762、输出3848；本轮未独立核验计费记录，不能由此重建JSON或推断截断、字段错误及费用。

原schema_diagnostic丢掉了Pydantic错误type，只用loc尝试映射四个业务列表。根JSON解析失败、根类型错误、顶层缺字段和版本Literal不匹配等都可能退化成同一个schema_rejected/section=null。**诊断信息不足是确定的代码缺陷；真实响应的具体错误仍未知。** section=null只表示未映射到facts/timeline/pending_evidence/relations，不能直接当成某个顶层字段出错。

## Schema、Prompt和SDK审查

1. Analysis12要求schema_version=multidoc-analysis/1.2、prompt_version=multidoc/pending-selection-v1，以及case_id、batch_sha256、pending_catalog_sha256和四个结果列表；对象禁止额外字段，列表/字符串有长度、类型、模式等约束。任一不合规都会在证据检查前拒绝。
2. 当前1.2 Prompt的版本与Schema一致，已删旧pending自由text/quote契约，只允许编号和reasoning；facts的reasoning空字符串、timeline事件编号、relations两侧引用等仍有各自限制。没有证据确认本轮存在版本矛盾，不能据缺失原稿随意删字段或加默认值。
3. 官方SDK使用responses.create保留外层元数据和usage，随后取Response.output_text，再由Pydantic model_validate_json校验完整对象。已检查安装版本openai 2.54.0的属性实现：所有message/output_text块以空分隔拼接，无文本时返回空字符串。分块组成一个JSON可以成功；两个完整对象拼接会因尾随内容失败。这是已确认的SDK行为，不是已经定位的本次根因，也不应自动选第一个对象修复。
4. 服务商明确refusal或非completed状态在格式校验前被拒绝；当前回执的format阶段不能被等同为这些状态。文本化拒绝若作为普通output_text出现，仍可能导致JSON错误，但无原稿无法确认。
5. OpenAI请求保留strict；DeepSeek沿用既有适配不发送strict，本地Pydantic仍严格。provider_status=completed只证明服务端完成返回，不证明所有必填字段、Literal、模式及业务约束已通过本地验证。
6. 当前版本可能遇到空文本、Markdown围栏、根数组/嵌套包装、缺少目录哈希、版本字符串不一致、字段类型/长度错误或额外字段等。以上只是可测试的可能性；不能将其中一种人工反例说成真实响应。未获得实际运行Commit/Prompt哈希，仓库审查也不能证明真实环境运行的每个文件都与基线完全相同。

**本轮不修改Schema、Prompt、SDK提取或模型输出。** 不去围栏、不补字段、不纠正版本、不挑选JSON片段、不更换引用，不降低任何验证要求。请求预算、输出限制、超时、认证、额度及零重试保持。

## 安全诊断改进

生产逻辑只改validation_diagnostics.py。保留原stage、rule=schema_rejected、section、item_index、来源和诊断版本；在格式失败时增加独立schema_error_version=schema-errors/v1以及：

| 字段 | 内容与边界 |
| --- | --- |
| schema_error_count | Pydantic报告的完整错误数量 |
| schema_error_type_counts | 固定错误类型白名单的完整计数；未知自定义类型归other_validation_error，不回显其名称 |
| schema_errors | 最多20条，每条只有type、category、path、path_redacted |
| schema_errors_truncated | 是否省略了超出明细上限的错误；总数和类型计数不截断 |

category区分json_parse、missing_field、field_type、version_mismatch、literal_value、extra_field、value_constraint及other_schema_error。schema_version/prompt_version/parser_version的Literal错误可归版本不匹配，不记录实际值或Pydantic expected上下文。

字段路径按上下文白名单构造：仅允许已知根字段、业务条目字段、引用字段及正确位置的数组序号；不能只做全局字符串白名单。未知字段名可能本身就是原文或凭据，统一替换为<redacted>并停止后缀；已知quote出现在未知根位置也不照抄。路径最多8段，序号只允许0—1000，超界序号同样脱敏；原item_index也限制在该范围，防止从另一字段旁路回显。

路径里的reasoning/quote等只是公开Schema字段名，**没有任何字段值**。不序列化Pydantic msg/input/ctx/url、原始异常文本、未知原始loc、自定义错误名称、模型正文、请求、API Key或密码。errors()只在内存读取用于筛选，绝不将原字典直接放入回执或普通日志。

下例为人工Mock的“缺目录哈希”，不是本次真实失败：

```json
{
  "stage": "format",
  "rule": "schema_rejected",
  "section": null,
  "schema_error_version": "schema-errors/v1",
  "schema_error_count": 1,
  "schema_errors": [
    {"type": "missing", "category": "missing_field", "path": ["pending_catalog_sha256"], "path_redacted": false}
  ],
  "schema_errors_truncated": false,
  "schema_error_type_counts": {"missing": 1}
}
```

默认不保存模型原稿或请求，不新增私有捕获功能。既有UI的安全回执JSON及下载会展示这些可选字段，无须改变页面逻辑或回执成功路径。旧规则代码和multidoc-diagnostic/v1保留，新增明细有自己的版本；成功案件、原协议和ZIP格式不变。

## 离线反例及结果

先加入28项测试：旧代码缺明细，26项报缺字段错误、1项失败，1项分块成功测试本就通过；再改诊断并补2项旧协议/解析器版本兼容测试，最终新增30项。测试使用完整虚构B01和本地HTTP Mock，直接跑官方SDK→output_text→Pydantic→安全回执，而不是只拼诊断字典。

覆盖非法/空JSON、围栏、根数组/null、缺case_id/目录哈希、Schema/Prompt不匹配、根列表/anchor/ID元素类型、哈希模式、非版本Literal、旧pending text多余字段、任意根/嵌套键脱敏、已知词在错误位置、多个错误/60项错误截断、多个完整JSON拒绝、分块单JSON成功、自定义错误类型与msg/ctx脱敏、路径后缀停止、巨大序号、1.0历史及解析器版本。HTTP Mock格式失败均仍保留服务商状态与模拟usage、证据not_run；实际SDK请求一次，max_retries=0，案件不写入。

基线686项完整通过，57.179秒。新增30项通过，1.689秒。最终执行`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps python -m unittest discover -s tests -v`：**716项全部通过，60.120秒**。原686项测试文件及断言未修改。测试环境openai 2.54.0、pydantic 2.14.3。[完整日志](v2e_schema_diagnostic_tests.txt)。Mock usage130等是人工值，不是此次42762/3848的复现或真实费用。

本轮真实模型调用0次，不读改Secrets、原件、Gold、现有额度数据库、旧协议或旧ZIP文件；不部署、不重试、不合并main。完整回归中的额度测试仅操作临时测试SQLite。

## 下一次真实调用前仍不能验证的内容

- 本次实际JSON、真实错误type/loc/数量、输出文本块结构、是否缺字段/版本错/多对象等，无法凭现有回执恢复。
- 真实模型是否遵从相同动态Schema、原文选择及问题语义，无法由HTTP Mock证明。
- SDK实际Token分布、成本和输出容量是否足够，不能由3848或42762单独推断；更不能声称此次失败已修复或真实验收通过。

历史失败回执没有原始ValidationError，不能补齐新明细。即使未来得到json_invalid类别，脱敏摘要仍不包含非法字符、消息正文或具体包装，不能仅凭该类型区分空文本、围栏和多对象等情形。

本次是可观测性补丁，不改善或自动修复不合规输出本身。下一步先人工审查本提交；任何未来调用需另行授权，重新核对实际运行Commit、Prompt哈希、完整B01、解析确认和当前额度，只请求一次。若再次失败，安全回执会明确给出JSON解析、缺字段、版本、类型或约束类别及已知路径；未知字段名继续脱敏，不因此放宽规则或索取密钥，不自动重试。

修改文件：validation_diagnostics.py；新增tests/test_v2e_schema_diagnostics.py、本说明与测试日志；更新README、TEST_REPORT及项目下载白名单。multidoc_v12.py、multidoc_ai.py、model_runtime.py、SDK适配、所有Schema/Prompt和工作包代码保持字节不变。
