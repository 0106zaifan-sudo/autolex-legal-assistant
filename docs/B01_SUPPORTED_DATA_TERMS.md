# CASE-001 B01第二次失败：技术术语的显式来源支持

本轮基线：`feature/b01-pending-evidence-text-fix` / `fcfa64d92e3277fd035461fd82c851dae264e525`。检查工作区干净后建立独立worktree `/workspace/work/autolex_b01_terms` 与分支 `feature/b01-supported-data-term-fix`，未覆盖用户工作。

## 1. 根因判断的边界

用户提供的真实回执是response_received、format_status=passed、evidence_status=failed，定位inference / pending_evidence[4] / unsupported_data_term。请求已正常返回，不能作为网络或Schema失败处理。

检查check_inference可知：reasoning中出现EDR或DSSAD（大小写不敏感），而该术语不在本条所有引用quote的并集中，就拒绝。该检查发生在本条resolve引文核验及text连续性检查之前，因而此规则不能证明其余引文已有效，更不能证明模型生成了错误事实。当前回执没有原始输出，也没有具体缺失术语；不能确定是EDR、DSSAD还是两者，不能还原此次真实text/quote/reasoning。

可复现的两种情况：有依据的文档类型仅在解析标题/其他正文而未被引用，会被现有窄范围规则拒绝；另一个情况是模型引入了当前引用没有依据的技术概念。D04确实支持前一种可能，但这不是已确认的真实失败详情。上一轮text_not_in_quote未在首条再次触发，不代表长期稳定遵从，也不代表本条text已通过。

## 2. D04实际解析与离线正反例

材料为固定的`模拟_CASE-001_D04_EDR摘要.pdf`。文件SHA256为`9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03`；解析快照SHA256为`cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7`，解析器`core.read_units/v2-coverage`。以下均为第1页、unit_index=0的零基半开字符区间。S编号仅为单文档局部说明，实际请求仍用绑定本案/本文档的MD全局编号。

| 来源 | 原文 | 坐标 |
| --- | --- | --- |
| D04局部S004 | 模拟材料：EDR摘要 | [89,99) |
| D04局部S008 | EDR只提供相对触发锚点t=0的测试摘要，未提供可信绝对日期。 | [224,255) |
| D04局部S015 | 原始二进制数据及提取过程镜像未提供，摘要为二次转写。 | [498,524) |

人工构造的核验问题为`待核实推断：D04的EDR摘要所涉原始二进制数据及提取过程镜像是否需要进一步核查？`，text直接取S015连续原文。

| 构造情况 | 校验结果 | 解释 |
| --- | --- | --- |
| 仅引用S015，reasoning提到EDR | unsupported_data_term | S015不含EDR；未引用的标题不自动成为依据，不能据此认定问题本身虚假 |
| 引用S015并独立引用S004 | 通过证据校验，语义待人工核验 | 标题与正文各有真实坐标和哈希，核查问题及正文保留，不删价值分析 |
| 引用S008，核查相对锚点与绝对时刻关系 | 通过证据校验，语义待人工核验 | 技术术语在实质正文直接出现 |
| 引用EDR标题却提出DSSAD字段问题 | unsupported_data_term | EDR不能授权DSSAD，L2不能被自动等同于DSSAD背景 |
| 将DSSAD写进文件名、伪造DSSAD标题 | 前者unsupported_data_term；后者quote_not_found | 文件名可变，伪造原文不能获得术语支持 |
| 将D04标题配给D01的source_id | quote_not_found | 不能转移引文归属 |
| 合法EDR引文，但reasoning断言“EDR必然存在” | asserted_data_existence | 词面支持不授权存在性断言 |
| 合法术语引文，但text改写摘要 | text_not_in_quote | 上一轮严格连续原文约束仍生效 |
| D01口述分钟与D04相对锚点的核查问题，保留各自来源 | 通过证据校验，语义待人工核验 | 不补最终时间，不把D04字段当成D01记录 |

另用未修改的D05原句`L2场景使用ADAS状态日志，本材料不是DSSAD记录。`验证：可以讨论DSSAD适用边界，不能据此断言DSSAD记录存在。测试响应均人工构造，不是用户此次真实响应，也不是模型能力数据。

## 3. 方案比较与最小修复

| 方案 | 安全与改动影响 | 决定 |
| --- | --- | --- |
| 删除unsupported_data_term或仅靠Prompt约束 | 放行无来源术语，降低保护 | 拒绝 |
| 隐式扫描整批正文/文件名放行 | 其他文档可为当前问题借词，来源不透明；文件名不证明内容 | 拒绝 |
| 新增文档元信息引用类型、逐文档技术概念范围Schema | 需要设计可信元信息锚点、逐命题归属、兼容迁移；不宜作为此次最小修复 | 暂缓 |
| 显式引用同文档解析标题并保留正文 | 复用现有sources、坐标、SHA和人工核验；不降低任何验证要求 | 采用 |

生产修改仅multidoc_ai.py：增加Prompt指令，要求EDR/DSSAD由本条引文直接支持；文件名/未引用标题不算；必要时将同文档真实标题作为独立引用，同时保留实质正文。标题只标识材料，不证明功能、存在性或真实性。跨文件核查须区分各文档对象，不能移植术语、字段或功能。relations仍限定其left/right实际引文支持，不凭未引用其他材料借词。

同一术语拒绝条件保持等价，仅在原错误上增加安全的可选诊断字段`unsupported_terms`（只来自固定EDR/DSSAD词表）和`term_support_scope=explicit_quotes_only`。rule、stage、section、索引和来源编号照旧；不序列化模型原文、任意术语、异常正文、Key或请求。诊断来源ID表示该条声称的引用，不表示引文已核验通过。

没有自动补引文、删除术语、重写问题或提升事实。Schema 1.0/1.1、单文档Schema2.0、引文位置/哈希、时间线、分类、关系、人工复核、费用和原子导入均保持。Prompt版本名不变，现有prompt_sha256与批次指纹记录实际变更；旧批次授权不能复用。

## 4. 实际执行结果

基线568项全部通过，55.044秒。先新增23项测试：旧Prompt的12个指令子断言失败，3项新诊断字段测试报缺字段；既有词面正反例已能复现。修改后23项通过；完整执行`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps python -m unittest discover -s tests -v`：**591项全部通过，55.731秒**，原568项测试文件及断言未改。完整日志见[b01_data_term_offline_tests.txt](b01_data_term_offline_tests.txt)。Mock用量127等仅用于验证回执保留，并非真实Token消耗。

B01默认DeepSeek请求字节72462→73371（上限128000）；输入字符2015/16000、4文档、62来源块、4候选保持。D01/D03/D04覆盖风险仍须确认。全部5批预算及指纹见[B01_DATA_TERM_BUDGET.json](B01_DATA_TERM_BUDGET.json)。Prompt变化影响生成元数据，仅刷新batches.json、manifest.json、SHA256SUMS以及预算说明；8原件、Gold JSON/Markdown及人工规范、生成脚本字节不变。manifest.baseline_sha仍是最初数据设计基线。

本轮真实模型调用0次，不读取/修改Secrets、私有验收资料或现有配额数据库；QuotaStore测试只用临时数据库。没有自动重试、部署、合并或修改main/已验收分支。

## 5. 剩余限制及下一次验收

EDR/DSSAD校验是引用集合上的词面必要条件，不是完整语义蕴涵或技术功能校验。测试明确记录：给D01问题附上D04标题后，词面校验可能通过，仍可能错误把EDR属性归给D01；结果仅语义待人工核验，不自动导入或确认事实。本补丁用可追溯引用和Prompt降低风险，**没有保证自动识别所有跨文件概念转移**。可靠自动判定需要以后独立设计逐命题/逐文档范围的协议与反例，不能靠简单的术语名单扩充。

此外，unsupported_reasoning_time同样只认本条引文中的字面时间，未引用的标题日期或合理格式变换可能被保守拒绝；时间集合有来源也不等于每个命题时间归属正确。EDR/DSSAD按子串匹配，不区分否定、适用边界或同名缩写；EDR词出现也不证明其中有ADAS字段。其他术语、复杂存在性句式及语义归属没有完整自动验证。以上不在本轮放宽或扩展。

现有每条sources最多4条，关系只有两侧引用；如果标题引用无法安全加入，不得删除必要证据或偷偷借用元信息。应选用已有且确实支持问题的正文，或交人工补充审查；未来如需更大引用结构应另行变更协议。标题无法解析时也不能用文件名替代。

离线通过不等于真实DeepSeek稳定选择合法引文。下一次仅在人工授权后单独运行B01一次：重新检查所选文档/预算/覆盖风险及授权；核对EDR等术语的具体引用、D04标题与实质正文、各文档对象区分、text连续原文、reasoning核查问题及安全回执。若仍unsupported_data_term，查看新增固定术语与scope以及原有来源编号；没有原始输出时仍不得猜测。失败不导入、不自动重试。
