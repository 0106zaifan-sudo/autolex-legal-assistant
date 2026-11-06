# 首个需修改文件：ai_analysis.py

状态：**补丁规格，尚未修改该业务文件。** 本次没有一次性实现后续模块。

## 1. 为什么先改这里

AI分支已具备官方SDK、Pydantic、原文摘录和调用限制，没必要重新搭建AI入口。当前最直接可复现的错误发生在`validate_analysis`：事件text命中碰撞引文、time_text命中维修引文，二者可以组合通过。

这会把可回溯的片段拼成不正确时间线，影响事故初审的因果分析。先修输出契约和证据绑定，比扩充模型提示词或先接知识库更有收益。生产main的ZIP/门禁阻断问题复用现有AI分支的修复，不重新实现。

## 2. 现有代码定位

基线`5307554`：

- `TimelineItem`，约51–52行：只增加自由字符串time_text，没有时间证据锚点。
- `validate_analysis`，约113–136行：分别对多个quote做`any`检查，缺少事件与时间关联。
- `Analysis`及`analyze_record`，约55–59、144–165行：尚未记录Schema/Prompt版本，不利于以后迁移和评测。

## 3. 第一个补丁的最小范围

1. 为时间线项目引入可判定时间证据字段：标明事件主锚点及时间锚点。首版只接受时间出现在**支撑本事件的同一引文**；如果只能从其他段落推测，保存未知时间和待核实关系，不自动补到事件上。
2. 由程序根据引用重新计算起止偏移，不信任模型自报页码/字符位置。引用必须属于当前文档与当前解析快照，跨案/跨文档未显式关联时拒绝。
3. 对缺失时间使用显式unknown状态，保留原始文本。没有时分不补成已知精确的00:00事件；日期归一化信息需记录精度。相反主张作为两条记录，不能合成一个确定事件。
4. 输出Schema/Prompt版本，安排旧固定响应的显式迁移或兼容适配，不能不改fixture就默默解释成新版数据。
5. 现有SDK官方地址、`store=False`、Secrets、配额、零重试、错误提示、原文摘录限制和待核验默认值保持。

建议契约草图（不是已经提交的Python实现）：

```text
TimelineEvent:
  statement_id
  event_source: EvidenceAnchor
  time_state: explicit | unknown
  time_text: 原文时间或空
  time_source: EvidenceAnchor | null
  time_precision: minute | date | unknown
  verification: pending

EvidenceAnchor:
  document_sha256
  parsed_text_sha256
  parser_version
  unit_id / source_id
  start / end / quote
```

完整案件级`EvidenceAnchor`后续由P0-B抽到`case_schema.py`和`evidence.py`。第一个补丁可以在`ai_analysis.py`内部建立最小兼容契约，不应为一个问题迁移全项目。

## 4. 配套修改文件

“首个文件”指主业务修改入口，落地时仍应同提交包含必要回归测试：

| 文件 | 补丁作用 |
|---|---|
| **ai_analysis.py** | 主修改：事件/时间证据绑定、unknown、精度、Schema版本 |
| tests/test_ai_analysis.py | 将探针A转为应拒绝的回归，并加入下列正反例 |
| samples_ai/mock_analysis.json | 按明确版本迁移固定模拟响应，保持真实/模拟标签 |
| make_ai_samples.py | 与fixture契约同步，保证样本可重建 |
| ai_ui.py（仅必要显示适配） | 清楚显示未知时间、精度和原文引用，不改变其他页面流程 |

## 5. 首个补丁验收清单

- [ ] 现有探针A的碰撞/维修时间错配被拒绝。
- [ ] 同事件、同引文中的完整时间通过并可按字符区间回放。
- [ ] 不在原文中的时间、篡改引文、无效source ID、其他文档引用全部拒绝。
- [ ] 缺失时间显示未知，不生成具体时间或先后因果。
- [ ] 只有日期时显示日期精度，不把它展示为已知午夜。
- [ ] 相同时间的相反主张分别保留，不自动选真。
- [ ] 重复短语无法唯一定位时要求扩大引用/人工选择，不静默选第一个。
- [ ] SDK mock完整路径及原41项回归继续通过；增加了多少测试就按实际输出报告，不预填新数量。
- [ ] 固定离线演示可加载，旧Schema结果要么显式迁移，要么给出兼容提示。
- [ ] 无真实密钥、无模型费用；至少一次真实集成验收留到P0-D安全配置完成后。

本补丁不解决全部语义支持关系、长期存储、法律检索、模型准确率或公开多租户认证。探针B–G在后续工作包跟进；不能修复A就宣称来源溯源已全部正确。
