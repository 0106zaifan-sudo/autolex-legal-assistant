# V1.1补丁：未知时间事件与完整性诊断

2026-11-09（北京时间）。基线：`feature/output-quality-p1`的`e5e0744`；独立分支：`feature/output-quality-p1-timeline`。开始时基线工作区干净，使用新worktree开发，未覆盖用户工作。

## 原因分析

用户提供的真实现象：SIM_B的碰撞原文在facts中，但timeline只有2026年11月4日的接收事件，`timeline_expected_bindings`失败；也没有碰撞具体时间的待核实问题。本轮只用这些已提供信息及公开固定模拟材料分析，没有读取任何私有验收文件。

1. **Schema和原证据绑定验证的是已输出条目是否合规，不保证模型选取齐全。** timeline允许空列表；原Prompt解释了unknown字段，但没有明确要求重要事件在无日期时仍必须入选。
2. P1新增“去重”和“少写/留空”等约束，模型可能将其扩大理解为facts中已有事件就不必放timeline，或把“时间未知”误作“不能列事件”。这是合理原因假设，不能据此证明模型内部推理。
3. P1后处理对timeline仅排除两种已知完整模拟声明，其余事件原样保留；SIM_B碰撞句不属于声明。离线对照确认：若输入同时包含未知时间碰撞和明确日期接收事件，P1后处理保留两条，排序与锚点完全不变。

代码与复现更支持模型侧漏选，而非P1整理移除碰撞事件。但没有检查真实原始响应，不能对那次调用作绝对归因，也不能声称新Prompt已使真实模型恢复完整输出。

## 最小修复

### Prompt

新增明确要求：

- 对原文独立支持的重要事件逐项检查，时间未知不等于事件不存在；碰撞、维修、接收等事件不能仅因无日期被省略。
- unknown事件继续使用原Schema：`time_state=unknown`、`time_precision=unknown`、`time_text=未知`、`time_source=null`，不推算日期。
- facts负责事实/主张摘录，timeline负责时间组织；同一事件在二者合理复用，不适用facts/pending之间的精确重复整理规则。
- 不机械复制全部facts；文件声明、目录元信息及非事件问题不当作事件。
- 对未记载时间的碰撞等事件，在pending引用本事件原文，提出“碰撞具体时间有无其他材料记载？”一类问题；不声称已有其他材料或时间已知。

`PROMPT_REVISION`更新为`output-quality-p1-timeline/v1`并继续记录具体Prompt SHA256。原Schema 2.0、prompt_version=evidence-binding-v2、P1的`OUTPUT_QUALITY_VERSION=output-quality-p1/v1`均不变。旧版本断言仅更新提示修订的预期值，断言没有删除，其他原测试保持不变。

### 保守诊断，不制造事件

仅靠Prompt不能可靠保证完整性。因此新增`_assess_timeline_completeness`，在原Schema、证据绑定和P1质量处理全部通过后运行。它**只返回诊断，不添加/复制timeline、facts或pending条目，不填时间，不重分类，不自动重试**。

诊断范围刻意有限：仅比较当前已校验facts中含“发生碰撞/追尾/事故、完成维修、收到车辆检查材料/检查材料”等字面正向事件。否定、条件或不确定句不据此认定正向事件；多引用、事实摘录位置不唯一或跨句上下文则标歧义。

匹配必须保持文档SHA256、解析文本SHA256、解析版本、unit位置一致，并由timeline的原event_source范围覆盖facts摘录；相同文字位于另一处或另一个当事人的来源，不算同一事件已经覆盖。相同位置但事实/主张kind不一致也要求人工复核，不自动裁决谁的分类正确。

时间支持只从该摘录所在的同一原文句段检查，不能拿宽引文中下一句的维修日期充当碰撞时间。不能确认唯一受支持日期/时刻时，还检查pending是否有**本事件来源范围内**的时间核查问题；不能用另一接收事件的引用代替。

主要诊断规则：

| 规则 | 含义 |
|---|---|
| `important_fact_event_missing_from_timeline` | 已提取的重要事件未找到同位置时间线覆盖 |
| `timeline_kind_mismatch` | 同位置有事件，但事实/主张归属不同 |
| `unknown_event_time_question_missing` | 时间支持缺失或不明确，且未发现同来源的时间核查问题 |
| `event_context_ambiguous` | 多引用、位置不唯一或跨句，不能安全识别单一事件 |

返回JSON增加`timeline_completeness`，回执增加状态和安全诊断；只含规则、整理后facts下标、source_id、哈希和坐标，不包含原文句子或问题文本；下标对应当前质量视图，不伪称原始模型JSON下标。一般坐标定位facts.text在原unit的范围，歧义项可能定位首条引用范围；这是复核定位信息，不是新建EvidenceSpan，不修改任何既有引用或坐标。

状态为`needs_review`、`no_gap_detected`或`not_assessed`。**所有状态的`completeness_verified`都为false。** 没发现缺口不等于全文完整；若事件在facts和timeline都被漏掉，该比较不能发现。没有覆盖模式时是not_assessed，不伪称已验证。

UI对needs_review显示固定警告，明确提示事件、时间核查问题或归属可能有缺口。分析仍可作为待人工核验的摘录查看/导入，原人工核验门槛不变；绑定或质量验证通过不等于完整性通过。

## 原验收标准保持不变

SIM_A/SIM_B文件、manifest/gold以及`live_acceptance.automatic_checks`全部未修改。人工构造“facts有碰撞、timeline只有接收”的响应后，新诊断会提示两个缺口，**但仍只有一条时间线，原`timeline_expected_bindings`仍为false**。不是通过补造事件或降低金标准让测试通过。

未知时间事件仍按原排序列在有明确日期的组之后，不表示碰撞在接收之后，也不推断因果。没有改变时间精度、同日排序或未知时间绑定规则。

## 实际离线验证

先增加20项离线回归；旧实现为2个failure、15个error，其余通过，显示原流程没有诊断/Prompt约束/UI提示，而“输入已有两条事件时后处理保留”已经通过。补丁后20项通过。

完整测试：

```text
python -m unittest discover -s tests -v
Ran 267 tests in 17.506s
OK
```

原247项回归通过，新增20项。旧测试只更新一处Prompt修订号预期值（仍明确断言新值）；没有删除失败断言。完整日志见`timeline_completeness_offline_tests.txt`。Python 3.12，现有依赖通过`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps`加载，依赖未变。

覆盖未知/明确日期事件、缺失时间问题、事实与timeline归属不同、相反主张/不同位置不互相替代、宽引文不借下一句日期、部分摘录被完整事件正确覆盖、多引用歧义、否定/条件句、重复事件仍拒绝、借日期仍失败、输入不变、诊断不含原文、P1处理保留事件、SIM_A原时间线/主张以及UI明确警告。

模型路径全部为内存替身或原有HTTP mock，真实模型请求0次。未读取私有验收文件、实际Secrets，未部署、未合并或修改受保护分支。

## 修改文件

| 文件 | 原因 |
|---|---|
| `ai_analysis.py` | 强化未知事件与跨列表职责Prompt，递增Prompt修订，增加只读诊断与回执字段 |
| `ai_ui.py` | 展示完整性待核查警告，不显示原文诊断日志或制造事件 |
| `tests/test_timeline_completeness.py` | 20项新的完全离线回归 |
| `tests/test_output_quality.py` | 仅更新一条Prompt修订号预期值，保留P1质量版本断言 |
| `project_archive.py` | 新测试/说明/日志加入原ZIP白名单，继续排除运行目录与Secrets |
| `README.md`、`TEST_REPORT.md` | 使用边界、实际测试记录 |
| `docs/TIMELINE_COMPLETENESS_PATCH.md`、`docs/timeline_completeness_offline_tests.txt` | 本说明及完整离线日志 |

## 风险与下一次最小真实复测

Prompt只能提高遵循概率；诊断是字面规则与来源位置比较，不是完整事件抽取或法律语义证明。事件若两处同时漏掉、措辞未覆盖、跨句指代复杂或来自多份材料，可能无法发现。时间问题检测主要依据同来源及时间词，不能证明问题足够具体；保留为人工审查提示。否定/条件过滤也是启发式，不代替事实认定。复杂情形可能误报，不能把no_gap_detected作为完整性证书。

用户另行明确授权后，最少单独SIM_B一次：

1. 原自动检查`timeline_expected_bindings`为true，碰撞和2026年11月4日接收两条事件都有对应完整原文。
2. 碰撞保持unknown/unknown/未知/null，不能用接收日期补时间；日期精度的接收事件不补午夜。
3. pending有对应碰撞原文支持的时间核查问题，并保留日志完整性待核实，二者不得互相替代。
4. facts分类、精确去重、元信息处理和审计均保持；查看新Prompt修订与哈希及完整性诊断，必要时人工逐条复核。

若预算允许，再单独SIM_A一次，检查相反主张、事故/维修日期与时间线引用不回归。始终沿用已有受控CLI、认证、配额与零自动重试，不自动重复失败请求。

**267项离线通过只验证补丁的确定性行为，不证明真实DeepSeek已经补齐未知时间事件。后者仍待下一次获授权的真实调用和人工复核。**
