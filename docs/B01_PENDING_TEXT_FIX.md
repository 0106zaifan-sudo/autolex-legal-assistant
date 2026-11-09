# CASE-001 B01待核实事项字段契约修复

分支：`feature/b01-pending-evidence-text-fix`。从干净的数据分支提交`202594c6ec88b152167e0080deb0a677467d325c`建立独立worktree，未覆盖其他工作区。

## 可确定的失败原因与未知信息

用户提供的真实回执显示服务商已完成、格式通过，随后在`pending_evidence[0]`的`inference/text_not_in_quote`失败。这是内容证据绑定错误，不是网络或Schema格式错误。`check_inference`要求text在至少一条sources.quote中连续出现；每个引用仍须独立通过来源、原文坐标、哈希及原有推断/质量校验。不能把“至少一个引用包含text”误解为其他引用可以不核验。

回执没有模型原始输出，无法确定真实text/quote，也无法分辨改写、拼接、问题误放text或选错引文等具体诱因。以下仅为人工构造的离线反例，不是本次真实响应。原Prompt只说“text仍摘录原文”，对跨文件场景中锚点与核验问题的分工说明不足；本轮没有发现应放宽校验的证据。

## 最小生产改动

仅修改multidoc_ai.py的基础Prompt，两条指令同时进入派生的候选事件Prompt：text直接复制至少一个quote的连续原文，禁止概括、改写、跨文件拼接；多个文档的独立sources应保留，跨文件问题写入以“待核实推断：”开头、问号结束的reasoning。text不必同时存在于每条quote。

没有改动Pydantic/JSON Schema、check_inference、引文/坐标/哈希校验、时间线、分类、导入、SDK、权限或额度。没有后处理重写输出。既有Schema1.1及Prompt版本名称不变，因为这是已有契约澄清；现有prompt_sha256及批次指纹记录实际指令变更。旧批次授权不能复用于新Prompt，需要重新预检并显式授权。

## D01/D04可重复例子

D01原文锚点：`事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。`

D04独立引用：`首行是事故时刻汇总栏；08:31转录自IN-01接报分钟，不是EDR绝对时钟。`

合法text可为上述任意一条的连续原文。两条来源同时保留；合法reasoning为`待核实推断：是否需要分别核对口述与接报卡转录来源，再核查两份材料的时钟基准？`。成功导入保留两个文档的证据坐标和待人工核验状态，不确认事故最终时刻。

把两条引文直接拼接、改写为对比摘要或把核验问题放进text，都会被拒绝。有效text加上伪造的第二条quote仍被拒绝。失败保留安全诊断和模拟Token回执，不污染案件、不重试；测试额度记录仅位于临时测试数据库。

## 测试与预算

先加入12项测试：旧Prompt在两套Prompt共10个指令子断言失败，其余反例已复现原规则。修复后12项通过。完整执行`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps python -m unittest discover -s tests -v`：568项全部通过，56.269秒。原556项测试文件与断言未改。完整日志见[b01_pending_offline_tests.txt](b01_pending_offline_tests.txt)。

B01默认DeepSeek静态预检：4份文档、2015输入字符（原解析正文1940字符）、62来源块、4候选事件；请求字节72094→72462，低于128000。字符数低于16000。解析覆盖确认仍要求D01/D03/D04。此为静态预算，不是Token估算或当前真实账户剩余额度查询，也不授予任何调用权限。

Prompt更新使生成器预算与批次指纹变化，因此仅刷新standard/batches.json、manifest.json、SHA256SUMS及相关预算说明。八份原始材料、Gold Standard、人工规范、生成脚本和数据设计文档均与基线字节一致；未修改旧数据分支。完整新旧预算与Prompt哈希见[B01_PENDING_BUDGET.json](B01_PENDING_BUDGET.json)。manifest.baseline_sha仍表示数据最初设计基线。

## 限制与后续最小验收

全部模型响应由本地Mock注入；本轮真实模型调用0次，不读改Secrets、不部署、不自动重试。离线通过只能证明契约、拒绝边界、导入原子性与预算，没有证明真实DeepSeek遵从新Prompt的稳定性。Prompt本身无法保证合规，原严格校验继续拒绝不合规输出。

后续经人工授权只运行B01一次：重新预检全部所选文档并确认覆盖风险与付费授权，检查pending_evidence.text在至少一个quote中连续存在、两侧独立来源坐标有效、reasoning保留有依据的跨文件问题，确认安全回执中格式/证据状态及Token。若失败按诊断定位，不自动重试；没有原始响应时继续避免猜测具体内容。其他推断、时间线或关系规则仍可能导致拒绝，本补丁不扩大处理范围。
