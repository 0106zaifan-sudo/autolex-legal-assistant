# SIM_B真实失败定位与固定模拟样本调试

日期：2026-11-06（北京时间）。基线：`5a18ec3`；工作分支：`feature/multi-provider-deepseek`。

## 已知真实结果与不能推定的内容

用户提供的既有真实验收：deepseek-flash、provider_status=completed、Schema通过，证据绑定在`facts[5] / S006 / 尚未核实`失败。该信息将问题定位到**分类防护**，不是服务商连接、JSON Schema或事故日期解析错误。

S006固定模拟原文为：“模拟资料目录：仅列出检查摘要，原始车载日志是否完整尚未核实。”

当前信息说明该条被`kind=事实`承载，触发同句核实限定检查；但尚无当次`text`和`quote`，不能断定模型是将整句/日志完整性误作事实，还是仅摘录客观目录半句被保守拒绝。Schema本身没有“已确认事实”枚举；`kind=事实`也不代表系统已人工确认，不能把列表名facts当作真实性认定。

## 原因分析与本轮最小改动

原Prompt已经区分事实、主张、推断，但`facts`同时承载事实与主张，而“资料记载”容易使模型把任何原文记载都放为kind=事实。S006前半是材料目录记载，后半是日志完整性未核实，模型可能按source顺序逐项抽取或保留原文后统一标事实。**这些是待原始响应验证的解释，不是对当次模型思路的证明。**

本轮只完善Prompt：

- facts是列表名，其中驾驶人/企业陈述仍必须kind=主张。
- “是否完整尚未核实”不代表已经完整，也不代表已经缺失。
- 同一句的混合目录信息不截成半句规避限定，完整引文进入pending_evidence，kind=推断，reasoning只提待核实问题。
- 没有单方说话人的核实事项不强行标成当事人主张。

`CLAIM_MARKERS`、`_fact_classification_diagnostic()`、`validate_analysis()`、Schema 2.0、哈希、source坐标与时间线函数均未改变。没有为了通过S006而放宽校验。保留Prompt版本字段契约，新增回执/调试文件的`prompt_sha256`记录具体提示文本变化。

## 完全离线的9项人工对照

以下引文全部来自原有固定虚构SIM_B；人工输出不代表真实DeepSeek输出。用于复现facts[5]的前5条也由程序人工构造，不声称与用户那次响应相同。完整逐项结果见[人工离线复现JSON](sim_b_manual_reproduction.json)。

| 人工情况 | text/quote与分类 | 当前校验结果 | 解释 |
|---|---|---|---|
| S006整句进入facts[5] | text和quote均为S006全文；kind=事实 | Schema通过，绑定拒绝，index=5、S006、尚未核实 | 可精确复现用户诊断；包含未核实完整性的整句不能升格事实 |
| 客观半句，保留完整quote | text=“仅列出检查摘要”；quote=S006全文；kind=事实 | 绑定拒绝 | 合理客观摘录候选被同句保守规则挡住，不能与“日志完整已确认”的模型错误混为一谈 |
| 客观半句，缩短quote | text=quote=“仅列出检查摘要”；kind=事实 | 绑定拒绝 | validator回到完整原文句，不能靠截quote移除限定 |
| 日志完整性待核实 | text=quote=S006全文；kind=推断；reasoning=“待核实推断：原始车载日志是否完整？” | 通过，仍待人工核验 | 不断言日志完整或缺失；这是当前规则可接受的保守表达 |
| 驾驶人主张升级事实 | “模拟驾驶人主张：碰撞发生前系统未发出接管提示。”；kind=事实 | 拒绝，S004、主张 | 正确保护单方陈述边界 |
| 企业主张升级事实 | “模拟企业主张：提示是否发出仍需核对原始日志。”；kind=事实 | 拒绝，S005、主张 | 企业提出的核实立场也不能直接认定客观事实 |
| 驾驶人主张保留 | 同S004全文；kind=主张，置于facts列表 | 通过，仍待人工核验 | 列表名称不改变kind |
| 企业主张保留 | 同S005全文；kind=主张，置于facts列表 | 通过，仍待人工核验 | 不擅自取舍 |
| 独立接收记载 | “模拟接收记录：2026年11月4日，测试方收到车辆检查材料。”；kind=事实 | 通过，仍待人工核验 | 正向对照；接收日期仍不得挪作碰撞时间 |

可在本人终端运行以下**离线**命令，不读取Secrets、不触发API、不要求访问密码：

```bash
python tools/replay_sim_b.py
```

默认只生成终端对照报告，不保存原始输出。若明确希望把人工反例也保存到私有目录：

```bash
python tools/replay_sim_b.py --save-rejected-samples
```

该命令是manual_offline，真实调用0次、准确率null；只保存绑定失败的反例，成功或Schema失败不保存。

## 可选私有调试捕获

`analyze_record(..., debug_rejected_samples=False)`默认关闭；普通Streamlit上传界面没有启用入口，也不读取新的Secrets设置。

日后用户另行允许真实付费验收时，在既有受控验收命令上**显式追加**`--debug-rejected-samples`。仍必须同时满足原工具的`--run-live`、`--confirm-paid-calls`、本人终端认证、访问控制、单实例配额、累计输入预算及超时限制。单独调试开关会停止，不读取Secrets。本轮没有执行任何真实验收命令。新捕获功能不能追溯恢复此前未保存的原始响应，只对以后明确启用的调用生效。

捕获规则：

1. 必须通过Schema且绑定失败。失败仍抛`output_validation_failed`，不返回有效result、不导入案件，也不自动重试。
2. 文件名/模拟标签不足以放行；固定SIM_A/SIM_B的**内置文件哈希**、本地原始文件字节、文件名、解析版本及全部unit文本均需一致。还核对输出context，text/quote必须来自固定正文。修改manifest不能绕过白名单。
3. 仅写`.autolex_runtime/rejected_sample_debug/<随机32位ID>.json`。既有`.gitignore`已忽略整个运行目录；没有修改.gitignore或Secrets。ZIP继续只使用白名单，不包含调试文件。
4. POSIX目录700、文件600，owner为当前用户；dir_fd、O_NOFOLLOW、O_EXCL拒绝符号链接重定向与覆盖。不能保证该权限的平台失败关闭，不降级为公开保存。
5. 不传入SDK响应头、请求认证、访问密码或完整Settings。捕获检查凭据样式及当前内存配置中的key/hash是否出现在输出中，同时检查JSON解码后的字符串，防止unicode转义绕过；遇到敏感内容拒绝保存。不会为调试另行读取密钥或密码。固定模拟输入是主要边界，匹配规则不是任意真实案件的通用隐私过滤器。
6. 单输出上限512000字节、封装上限1024000字节、目录最多100个条目；达到上限返回storage_limit_reached，不删除历史文件。限额是本地资源防护，不是计费额度或并发配额替代。

文件为专用debug envelope，标记`purpose=rejected_debug_not_valid_analysis`、fixture_id、execution_mode、Schema通过/绑定失败、prompt_sha256。`raw_output`保留返回的原始JSON字符串（不重新序列化内部原文）；它**不是有效案件分析文件**。回执只增加debug_capture.status和随机artifact_id等固定元数据，不增加原文或本地完整路径。没有新增公开日志打印。

可能的状态包括disabled、saved、refused_non_fixture、refused_context、refused_non_fixture_text、refused_schema、refused_valid_analysis、refused_sensitive_output、storage_limit_reached、capture_failed等。捕获拒绝或磁盘故障不会把分析失败改成成功。

## 私有失败文件的离线回放

使用回执中的32位artifact_id，在本人终端运行：

```bash
python tools/replay_sim_b.py --artifact-id <32位ID>
```

仅从固定私有目录读取，不接受任意文件路径；拒绝符号链接、宽权限、硬链接、非普通文件及非当前用户文件；非阻塞打开避免误读命名管道时挂起。通过对应固定SIM_A或SIM_B回放validator，只打印校验状态和安全诊断，**不打印保存的raw_output或引文**。`actual_live_attempts`仍为0；origin_execution_mode只是来源标签，不是本轮模型调用证明。请在私有编辑器中查看原始输出，不把调试目录或截图上传仓库。文件由本人按需清理；代码不自动删除历史失败证据。

## 修改文件清单

| 文件 | 修改内容 |
|---|---|
| `ai_analysis.py` | 改善Prompt、记录prompt_sha256、绑定失败时可选捕获；不修改validator |
| `sample_debug.py` | 固定样本身份校验、私有安全捕获与读取 |
| `sim_b_debug.py` | 9项人工反例及本地validator回放 |
| `tools/replay_sim_b.py` | 不读Secrets的离线CLI |
| `live_acceptance.py` | 显式传递调试选项，默认保持关闭 |
| `tools/run_live_acceptance.py` | 可选CLI调试开关，保留原认证与付费确认 |
| `tests/test_sample_debug.py` | 29项新增离线测试 |
| `project_archive.py` | 新代码/测试/说明纳入白名单，排除运行数据 |
| `README.md` | 离线调试入口说明 |
| `TEST_REPORT.md` | 本轮实际测试记录，保留历史报告 |
| `docs/LIVE_AI_ACCEPTANCE.md` | 后续受控验收的可选捕获说明 |
| `docs/SIM_B_DEBUG.md` | 原因、对应关系、操作、局限及复测清单 |
| `docs/sim_b_manual_reproduction.json` | 明确人工离线来源的9项实际validator结果 |
| `docs/sample_debug_offline_tests.txt` | 完整离线测试日志 |

## 本轮测试及后续方案

完整离线测试：**205项通过，16.359秒**，原有176项测试文件未修改，新增29项。详见[完整日志](sample_debug_offline_tests.txt)。静态核对原分类/时间/哈希函数、原材料、manifest/gold及权限/配额实现与5a18ec3一致。没有调用真实模型API，没有读取/修改/重新配置实际Secrets，没有部署或改动受保护分支。

下一次真实测试仅在用户另行明确授权后执行，应检查：

- SIM_B原始facts[5]具体text、quote、kind；区分整句误分类与客观半句保守拒绝。
- 新Prompt是否将S006日志完整性保留在pending_evidence，完整引文及待核实问题正确，不宣称日志已完整或已缺失。
- S004/S005仍分别是主张，不能升格事实；S002碰撞时间仍未知，S003接收日期未借用。
- SIM_A相反主张及事故/维修时间绑定无回归。
- 若再次绑定失败且显式启用调试，核对私有文件确实保存、权限正确、回执只含ID，失败未进入案件。

已有证据表明客观半句可能被保守挡住，但同句限定的语义范围需要人工确认与更多对照，当前不新增逗号拆分白名单或放宽规则。建议先检查真实原始条目与新Prompt效果；若以后明确批准“目录半句可独立为事实”的业务规则，再另开有正反例保护的局部校验修改。仍无通用语义真实性验证，关键词及跨段归属的原有限制继续存在。

本轮结果只证明离线工程行为，不是DeepSeek真实验收通过，也不提供模型准确率。
