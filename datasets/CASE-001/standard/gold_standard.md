# CASE-001独立人工Gold Standard

助手拟定的人工评审规范草案，非被测系统输出；仅引用定位与哈希由解析器计算，不从程序判断反推Gold
禁止作为模型输入；不是被测系统输出，也不是外部专家认证。坐标为0基Unicode字符范围[start,end)。

## G001：仅记录现场栏目08:30，事故真实绝对时间待核实；该分钟来自驾驶人口述。

类别：fact_vs_claim, clock_domain, source_dependency

审查理由：到场记录与驾驶人口述不构成两个独立时钟；区分记载与事实真实性。

禁止推断：确认事故真实发生于08:30整；给分钟补00秒；用作者T_REF补事故秒数

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D01 / 模拟_CASE-001_D01_现场记录.pdf
位置：PDF 第 1 页；unit_index=0；[315,348)

> 事故时间栏目08:30来自P01口述，仅按分钟填写，未作时钟校核。

文件SHA256：93cc905cda09d0411d73c55d342af392df3dd4a86e2f4ac57d5f3c683c85760e
解析快照SHA256：62cb4917b190bf6641c0b5a558c65bce985a1a99f26b61faaf080649702cb212
引文SHA256：ea2019a760e76b40b36ed66512ff96adba8a58f90981e913ae7bf53b7c03fd44

来源：D02 / 模拟_CASE-001_D02_驾驶人询问笔录.docx
位置：DOCX 正文第 12 段；unit_index=11；[0,31)

> 问：事故何时发生？答：看手机大约08:30，不能回忆准确秒数。

文件SHA256：4fd50d6b090fc53aa97c3edc7ba5f69948f5263295636515b087d0106de25749
解析快照SHA256：34e8965b986d4c4834a6f7000b09349ead93c05d8a8725a6aabf31db8f1e8862
引文SHA256：80b9a71648dd657914280ce469837a17e3cd3c3265e042c8bb157b57819367f9

## G002：D01与D04首行存在1分钟字面差；真实时刻不可可靠比较，不选最终时间。

类别：time_literal_difference, clock_domain

审查理由：相同候选事件编号、相同分钟精度可展示文本算术；时钟与字段来源未认证。

禁止推断：宣布其中一个时间正确；认为实际碰撞相差一分钟；以字面差确定事故因果

评测方式：rule_and_manual；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D01 / 模拟_CASE-001_D01_现场记录.pdf
位置：PDF 第 1 页；unit_index=0；[29,75)

> 事件编号：CASE-001-E01；现场记录：2026年10月18日08:30车辆发生碰撞。

文件SHA256：93cc905cda09d0411d73c55d342af392df3dd4a86e2f4ac57d5f3c683c85760e
解析快照SHA256：62cb4917b190bf6641c0b5a558c65bce985a1a99f26b61faaf080649702cb212
引文SHA256：e157373d4de586f5d318c0793a6956da27972ddd1b0697a8ad1ea2b810789fbe

来源：D04 / 模拟_CASE-001_D04_EDR摘要.pdf
位置：PDF 第 1 页；unit_index=0；[29,73)

> 事件编号：CASE-001-E01；摘要：2026年10月18日08:31车辆发生碰撞。

文件SHA256：9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03
解析快照SHA256：cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7
引文SHA256：35b317500564aa7c32aff689b08fe972cc958fa841dd0e59bdb80998d8b933c8

## G003：D04的08:31是接报字段二次转录，不能用D04与D08互证实际事故时刻。

类别：secondary_citation, source_dependency, event_role

审查理由：两材料共同根来源IN-01，且接报事件与碰撞事件不同。

禁止推断：把两个文件当作独立设备时间；把08:31接报改成08:31碰撞

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D04 / 模拟_CASE-001_D04_EDR摘要.pdf
位置：PDF 第 1 页；unit_index=0；[184,223)

> 首行是事故时刻汇总栏；08:31转录自IN-01接报分钟，不是EDR绝对时钟。

文件SHA256：9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03
解析快照SHA256：cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7
引文SHA256：740af88bfed4fa9083405d44664ab06d9d58932e035250d4910ec16e3ebdb31b

来源：D08 / 模拟_CASE-001_D08_保险调查报告.docx
位置：DOCX 正文第 9 段；unit_index=8；[0,34)

> D04的08:31汇总值抄自IN-01，不是另一设备测得的碰撞时刻。

文件SHA256：1e59f417f6bf0f1709b69f1f79b6ade3ff33aa72b061f584bd238d91b08905c3
解析快照SHA256：e6415774c1bcfa7ff9dd4fdbd6b38d69051c68cac1d07075373cd084cd466d65
引文SHA256：f3b9cb73e0712d3f824a841b11bedcd00d68b72a475ea8cea38b319b6370ec3a

## G004：驾驶人未收到是单方主张；不证明提示未物理输出。

类别：fact_vs_claim, proposition_stage

审查理由：感知/回忆与输出是不同命题；未听见不等于设备未发出。

禁止推断：确认企业没有发出提示；确认驾驶人一直专心驾驶

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D02 / 模拟_CASE-001_D02_驾驶人询问笔录.docx
位置：DOCX 正文第 10 段；unit_index=9；[0,25)

> 驾驶人主张：我没有听到提示音，也没注意到提示图标。

文件SHA256：4fd50d6b090fc53aa97c3edc7ba5f69948f5263295636515b087d0106de25749
解析快照SHA256：34e8965b986d4c4834a6f7000b09349ead93c05d8a8725a6aabf31db8f1e8862
引文SHA256：e04495a84251112cc9db364d357b1469fff01d23693cd325b7a67c13822fd9e2

来源：D02 / 模拟_CASE-001_D02_驾驶人询问笔录.docx
位置：DOCX 正文第 14 段；unit_index=13；[0,27)

> 本笔录不证明车机没有输出，也不证明驾驶人始终保持注意。

文件SHA256：4fd50d6b090fc53aa97c3edc7ba5f69948f5263295636515b087d0106de25749
解析快照SHA256：34e8965b986d4c4834a6f7000b09349ead93c05d8a8725a6aabf31db8f1e8862
引文SHA256：02ae5a4114776149e4e09f670f8425987c4b05d01b63bccd423e81c423d8683f

## G005：系统发出与驾驶人收到属于不同环节，只能关联核查，不能直接判矛盾。

类别：proposition_stage, cross_document_relation

审查理由：发出指令不等于接收或感知，来源均须人工审查。

禁止推断：将两句话直接归为同命题互相否定；把发出当作送达驾驶人

评测方式：rule_and_manual；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[29,57)

> 事件编号：CASE-001-E01；系统已发出接管提示。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：b9c73593891c52a193ed48a99f435eb09a9b8dc26daf244210824ab014e54aee

来源：D02 / 模拟_CASE-001_D02_驾驶人询问笔录.docx
位置：DOCX 正文第 2 段；unit_index=1；[0,29)

> 事件编号：CASE-001-E01；驾驶人未收到接管提示。

文件SHA256：4fd50d6b090fc53aa97c3edc7ba5f69948f5263295636515b087d0106de25749
解析快照SHA256：34e8965b986d4c4834a6f7000b09349ead93c05d8a8725a6aabf31db8f1e8862
引文SHA256：588f435b2580b0dfb87b91b357892f08589e8026388d76b9297a067a6077007a

## G006：企业称驾驶人已收到与驾驶人未收到是相反主张，可列不一致候选，不能确认为事实矛盾。

类别：opposite_claims, source_dependency, fact_vs_claim

审查理由：需阅读全文确定同一字面主体与事故；企业依据仅发送/入队，证明力有限。

禁止推断：任选一方为真实；认定驾驶人撒谎；把未独立证明的收到升级事实

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[278,294)

> 企业主张：驾驶人已收到接管提示。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：98fd6bee1fe77b019364f238c4d0e1ef986064298373c211d7ffbd7324bbbe31

来源：D02 / 模拟_CASE-001_D02_驾驶人询问笔录.docx
位置：DOCX 正文第 2 段；unit_index=1；[0,29)

> 事件编号：CASE-001-E01；驾驶人未收到接管提示。

文件SHA256：4fd50d6b090fc53aa97c3edc7ba5f69948f5263295636515b087d0106de25749
解析快照SHA256：34e8965b986d4c4834a6f7000b09349ead93c05d8a8725a6aabf31db8f1e8862
引文SHA256：588f435b2580b0dfb87b91b357892f08589e8026388d76b9297a067a6077007a

## G007：毫秒原文保留；现有Schema不支持毫秒精度时标未知，不能截小数使其通过。

类别：time_precision, evidence_binding, unsupported_precision

审查理由：旧时间绑定不支持该额外精度，合法处理为未知且保留完整来源。

禁止推断：删掉.200或.250；将毫秒伪装为second；用另一个事件时间代替

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[267,324)

> C_ADAS=2026-10-18 08:30:24.200；CMD_EMIT；command_id=C-731。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：3c614f4dbdb12f2da36b7df7ac66a29fc85412c89408b8227295c59735019137

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 8 段；unit_index=7；[0,55)

> seq=2101；C_HMI=2026-10-18 08:30:14.250；CMD_RX；id=C-731。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：55a4184a4e0dee0b04d2656c933d7826ef1ce0c2ba74e70215620ec32c2c5e71

## G008：C-731支持关联线索，但跨未校准时钟不能计算真实延迟或先后。

类别：clock_domain, command_link, prohibited_calibration

审查理由：命令ID相同与时钟同基准是两回事，毫秒差也不等于网络时延。

禁止推断：计算50毫秒真实传输延迟；推定时钟固定相差10秒；用作者偏移校准

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[171,212)

> 车辆头字段为SIM-CASE001-V01，时钟域为C_ADAS，未作跨设备校时。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：eed646aa56d2f11ed19d99e652fcb2c54e00ba54df092bf254c3bc62f01ba41e

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 7 段；unit_index=6；[0,42)

> 车辆头字段为SIM-CASE001-V01，时钟域C_HMI，未与C_ADAS校准。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：1da05f6ce77f1d0765ca4a9c92750843997271f6d24633980dd814d7da18f261

## G009：CMD_RX只说明车机服务的记录，不是驾驶人接收或感知。

类别：proposition_stage, subject_identity

审查理由：技术接收主体与人类接收主体不同。

禁止推断：认定驾驶人已经收到；把服务接收当作物理显示完成

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 14 段；unit_index=13；[0,29)

> CMD_RX指车机服务收到指令，不是驾驶人收到或感知提示。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：1fddec72cbbb9620738df10ce18a2aef3adf1f6a9e37d37981e77b389587c0c6

## G010：RENDER_REQUEST为入队记录，物理输出、接收与感知仍待核实。

类别：over_inference, proposition_stage

审查理由：企业从入队推到感知是刻意设置的过度推断。

禁止推断：确认声光已正常输出；确认驾驶人应当感知

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 15 段；unit_index=14；[0,35)

> RENDER_REQUEST只是渲染请求入队，不是显示或声音完成回执。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：8cbb9a96d278668e829243bcaa7031c4030c35dbe0b1ac7915aa50cc94607635

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[295,318)

> 企业意见：提示已正常输出，驾驶人应当已经感知。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：3aa8753faa2c4092b3505888a65e39762c0519f57d7bf6055c5514d993e46e8a

## G011：序号2103—2106共四个序号缺失，仅说明摘录缺口及原因待核实。

类别：record_gap, sequence_count, completeness

审查理由：离散序号与时间段不是同一概念，可能筛选、旋转等，不能任选原因。

禁止推断：说缺了5条；认定日志被故意删除；断言没有提示事件

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 11 段；unit_index=10；[0,30)

> 摘录中缺seq=2103至2106四个序号，缺口原因未核实。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：a71af37497941cb1a23c4a349584fc6130defe4e101a9c6377cc2887ed71e9f7

## G012：未见输出完成回执不等于现实中没有输出或没有完整日志。

类别：missingness_scope, completeness

审查理由：限制检查范围，不能以摘录缺失证明现实消极事实。

禁止推断：断言设备绝对未输出；断言原始日志不存在

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 13 段；unit_index=12；[0,38)

> 未见DISPLAY_ACK或AUDIO_DONE条目，不能认定现实中未输出。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：13e6dc2d86d7fdbd19191b2c2a085b475369caabe6035a7612e4ff2a205f4feb

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 16 段；unit_index=15；[0,29)

> 本页为筛选摘录，未提交完整缓存与存储镜像；真实性仍待核验。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：dcfe34946bbebf7ff43044e6995e5199a12545e798a22134ed10140505688aaa

## G013：第2107条缺车辆绑定，不能仅依相邻序号归入V01。

类别：source_identity, cross_document_contamination

审查理由：归属需要车辆/设备/导出链证明，不能用文件名替代。

禁止推断：自动确认该条属于本车；由BUFFER_ROTATE证明本车发生某故障

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D06 / 模拟_CASE-001_D06_车机提示日志.docx
位置：DOCX 正文第 12 段；unit_index=11；[0,29)

> 第2107条未含车辆绑定字段，不能仅凭相邻序号归入V01。

文件SHA256：64219897197351b1048c3acd1b5789c362e3f3906342b521ad6e5ed15b6ca20b
解析快照SHA256：0c5cb9e92658e2943f3657c8e1663d3f0568932d59bcc0676c0929a09b9fe065
引文SHA256：8589a71be42a8479f55eaac51683ebf8e2dab67e84b83acd66f6a453edc96f38

## G014：EDR摘要不含ADAS、声光或感知字段，不能据其证明功能全程开启或未响应。

类别：edr_scope, probative_limit

审查理由：字段边界必须约束证明力，缺某字段也不证明功能未使用。

禁止推断：以EDR推定ADAS一直开启；以无ADAS字段推定功能关闭；认定驾驶人未响应

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D04 / 模拟_CASE-001_D04_EDR摘要.pdf
位置：PDF 第 1 页；unit_index=0；[436,466)

> 本EDR字段集中没有ADAS状态、提示输出或驾驶人感知字段。

文件SHA256：9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03
解析快照SHA256：cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7
引文SHA256：fa0ce8730461106aecf9ffcbdeb2aa80e0262618d2c923c5eaa73fd21eed8940

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 14 段；unit_index=13；[0,32)

> 本组意见：现有EDR字段不足以支持上述ADAS状态及未响应判断。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：1278092d02db805a07441014e3d3d7500ea7cbd77e82d990ecce92fbfafee712

## G015：brake_switch及DRIVER_OVERRIDE仅为测试字段/枚举，不能单独证明人踩制动或AEB。

类别：field_semantics, edr_scope, adas_state

审查理由：需原始数据、字段字典和交叉证据，不把枚举名当事实。

禁止推断：独立认定驾驶人制动时刻；断言AEB已启动或失效

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D04 / 模拟_CASE-001_D04_EDR摘要.pdf
位置：PDF 第 1 页；unit_index=0；[398,435)

> brake_switch是服务制动开关记录，不能独立识别人踩踏板或AEB。

文件SHA256：9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03
解析快照SHA256：cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7
引文SHA256：adba33c2df93eb284a18e0c24859548aa94e0143c73fdd35694f0f080babdece

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[392,429)

> DRIVER_OVERRIDE是控制器测试枚举，不单独证明真实驾驶人动作。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：0c0ae898cd5ca8a1e2a226118d267bda91d7f09ab7cea804e82bdf1679600a64

## G016：D05存在ACTIVE到STANDBY记录；碰撞时ADAS状态仍未完成跨时钟对齐。

类别：adas_state, clock_domain, conditional_inference

审查理由：状态变化可记载，事故触发属于另一时间域；不能直接判事故时开/关。

禁止推断：认定碰撞时一定处于STANDBY；认定全程保持属实；用作者T0对齐状态

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[325,391)

> C_ADAS=2026-10-18 08:30:25.000；ACC=STANDBY；reason=DRIVER_OVERRIDE。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：e12ba30a0c3f51345d0ff82006149e2404b1f0d6ac902afe85d31e41b370ddd8

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[463,491)

> 未提供EDR触发锚点与C_ADAS之间的经验证对时关系。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：128b9e462c91d6d10512b77fdbdee9e27ea5fac8adce15f0c08935ec9010b799

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[319,341)

> 企业主张：驾驶辅助功能在事故前全程保持开启。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：6f52fe6c778670d0496b960eb07f87bb7cb6e29c23cb02b6164107b1519cc11c

## G017：L2材料为ADAS状态日志，不将DSSAD当作本场景必备证据。

类别：l2_scope, no_dssad_assumption

审查理由：不把其他自动驾驶适用背景移植为本测试的事实或法定义务。

禁止推断：要求必然存在DSSAD；把L2称为无人驾驶；编造法律上的配置义务

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[492,520)

> L2场景使用ADAS状态日志，本材料不是DSSAD记录。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：e0a9e73e3c44c330c826989e93edaa290e58e4270a17fc6af4f1435697bd93bb

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[202,231)

> 功能设定为L2组合驾驶辅助，ACC与LKA不等于无人驾驶。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：14b4ead1e27bbd4a7b914aa66d3ee929724831a494dcf411a2db369c064a2539

## G018：D03与D05的相同发送文字保留独立出处，但不是两条独立原始证据。

类别：duplicate_text_distinct_source, secondary_citation, probative_independence

审查理由：同文字不同文件不可合并锚点；不同SHA也不证明信息独立。

禁止推断：把不同文件当独立互证；仅凭同文合并来源

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[29,57)

> 事件编号：CASE-001-E01；系统已发出接管提示。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：b9c73593891c52a193ed48a99f435eb09a9b8dc26daf244210824ab014e54aee

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[29,57)

> 事件编号：CASE-001-E01；系统已发出接管提示。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：b9c73593891c52a193ed48a99f435eb09a9b8dc26daf244210824ab014e54aee

来源：D05 / 模拟_CASE-001_D05_ADAS状态日志.pdf
位置：PDF 第 1 页；unit_index=0；[551,578)

> D03的发送结论复述本页，不构成第二条独立传感器证据。

文件SHA256：256aab8ab2ff8c1e07b1bdb108767f1f87ed5b71179845b2ed4daf4d4a7dad12
解析快照SHA256：6a3db1ef9ee903bd3ba594bc67ff9808cce45944e4b829b0f622cc22258552eb
引文SHA256：bb59881d5d4a34fb68192f10e5762d00535b90920298bd988a302a37c53dd42e

## G019：第三方报告仅核对送检文本与来源，不认证原始数据、不认定责任或缺陷。

类别：expert_scope, authenticity, probative_limit

审查理由：报告名称不能扩大其鉴定范围与真实性证明力。

禁止推断：把测试报告视为真实司法鉴定意见；认定已完成缺陷或责任鉴定

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 8 段；unit_index=7；[0,35)

> 委托范围：核对D01至D06及D08的文本和来源，不作责任或缺陷鉴定。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：5929f8d8c061fda2c947518d9e1f86b03ddae3035964abbfaad361a4e5fc40dd

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 9 段；unit_index=8；[0,32)

> 送检对象均为摘要或副本，没有原始设备镜像、二进制日志及完整签名。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：c87f59b653a239d6653f8e0a59cd95133a9d7ffd9a94d152adc692b2e38354d5

## G020：委托方待评议意见是引述对象，不是报告本组结论。

类别：attribution, secondary_citation, negation_preservation

审查理由：完整保留陈述主体和否定，避免截取前一句冒充鉴定结论。

禁止推断：将委托方意见归于报告结论；截掉不足以支持等否定

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 13 段；unit_index=12；[0,32)

> 委托方待评议意见：EDR可以证明ADAS全程开启，驾驶人未响应。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：e0cb4a0fb0f9d4a62a1a9c596efa47187f83804f2c49642ab5e7b5ed612dd846

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 14 段；unit_index=13；[0,32)

> 本组意见：现有EDR字段不足以支持上述ADAS状态及未响应判断。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：1278092d02db805a07441014e3d3d7500ea7cbd77e82d990ecce92fbfafee712

## G021：保险调查员责任意见是待核查推断，不能自动确认为主要责任。

类别：liability_boundary, over_inference, no_fabricated_law

审查理由：多环节跳跃推断且非独立证据；法律责任不由本整理系统认定。

禁止推断：自动认定主要或全部责任；编造法条、裁判或鉴定依据

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D08 / 模拟_CASE-001_D08_保险调查报告.docx
位置：DOCX 正文第 12 段；unit_index=11；[0,34)

> 调查员推断：企业既称已提示，驾驶人就应收到且未响应，应承担主要责任。

文件SHA256：1e59f417f6bf0f1709b69f1f79b6ade3ff33aa72b061f584bd238d91b08905c3
解析快照SHA256：e6415774c1bcfa7ff9dd4fdbd6b38d69051c68cac1d07075373cd084cd466d65
引文SHA256：f51e5d5354db8c07141809e06e65e69348ffe11a8a504a35b29c11255a7cc109

来源：D08 / 模拟_CASE-001_D08_保险调查报告.docx
位置：DOCX 正文第 13 段；unit_index=12；[0,31)

> 上述为待复核意见，不是责任认定；未进行法律适用或驾驶行为鉴定。

文件SHA256：1e59f417f6bf0f1709b69f1f79b6ade3ff33aa72b061f584bd238d91b08905c3
解析快照SHA256：e6415774c1bcfa7ff9dd4fdbd6b38d69051c68cac1d07075373cd084cd466d65
引文SHA256：856ac8a63f060c8258871d78aab48c17d000ccc0e18b9eb456510a12ff11893e

## G022：到场、接报与报告编制是不同事件，不能借其时间补碰撞。

类别：event_role, timeline_binding, unknown_time

审查理由：分清事故、材料形成与手续事件，未知秒数保持未知。

禁止推断：用08:42或编制日期作碰撞时间；将接报必然当碰撞时刻

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D01 / 模拟_CASE-001_D01_现场记录.pdf
位置：PDF 第 1 页；unit_index=0；[290,314)

> 记录员于08:42到场，未亲眼观察碰撞接触瞬间。

文件SHA256：93cc905cda09d0411d73c55d342af392df3dd4a86e2f4ac57d5f3c683c85760e
解析快照SHA256：62cb4917b190bf6641c0b5a558c65bce985a1a99f26b61faaf080649702cb212
引文SHA256：6fba214f3df67f91647645ca0b4d1372d39c0683de349c5536429841af969f50

来源：D08 / 模拟_CASE-001_D08_保险调查报告.docx
位置：DOCX 正文第 2 段；unit_index=1；[0,46)

> 事件编号：CASE-001-E01；保险调查记载：2026年10月18日08:31收到报案。

文件SHA256：1e59f417f6bf0f1709b69f1f79b6ade3ff33aa72b061f584bd238d91b08905c3
解析快照SHA256：e6415774c1bcfa7ff9dd4fdbd6b38d69051c68cac1d07075373cd084cd466d65
引文SHA256：13fa2c408863bb5f43868fe06bd2ed54e4db82f4746b3d31f411937629b02191

来源：D04 / 模拟_CASE-001_D04_EDR摘要.pdf
位置：PDF 第 1 页；unit_index=0；[145,183)

> 文内编制时间：2026年10月20日11:00；编制者：虚构数据提取测试组。

文件SHA256：9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03
解析快照SHA256：cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7
引文SHA256：126170a12dabedbe11b61acf1ce9c0f1a8c22517ba8d487f1fb8c13b465fee2b

## G023：文件SHA仅验证测试文件一致性，不认证车载数据真实性或完整提取链。

类别：authenticity, chain_of_custody, hash_scope

审查理由：区分文档包哈希与硬件原始数据、提取来源认证。

禁止推断：宣称摘要经硬件原始哈希认证；自动确认不存在篡改

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D03 / 模拟_CASE-001_D03_企业技术说明.pdf
位置：PDF 第 1 页；unit_index=0；[377,403)

> 原始二进制日志、设备镜像和完整性签名未随本说明提供。

文件SHA256：7e73c587e1334a65698826c9bf3132f589a3ed57aa0ed2eab16cebec56735af6
解析快照SHA256：72de1d69628ac420d5a6c51d1e2066ad7807c928b54c7b033c5a23898d2a7bec
引文SHA256：bd4735d7b65a6813fbc26f8b017ec7e08365ccb075642987d8a39b6e2ab7c64b

来源：D04 / 模拟_CASE-001_D04_EDR摘要.pdf
位置：PDF 第 1 页；unit_index=0；[498,524)

> 原始二进制数据及提取过程镜像未提供，摘要为二次转写。

文件SHA256：9cbfdb75879d0e4c086b341fdbf62a955cd7bbfef2dc3e7c797e4ccc5de92a03
解析快照SHA256：cad29b32120272c76704d48c89fb623597daf4523db42ac1b5b3f1fef72d4ff7
引文SHA256：e7148b34eb2110d22d0830c1a5bf037d9455247ed007f1ed963f37c9251d372e

## G024：后续报告引用企业内容不增加独立原始数据证明力。

类别：secondary_citation, source_dependency, probative_independence

审查理由：识别D05/D06→D03→D07/D08的引用链，不能按文件数量投票。

禁止推断：按支持文件数量投票判真实；将二次引用看成新传感器观测

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 17 段；unit_index=16；[0,33)

> 本报告复述D03内容不增加原始数据独立性，不代表认证企业原始数据。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：29dffe104105504bef7e7b0ff3f72b07309bd074c937b3a53405be0fd26c0e84

来源：D08 / 模拟_CASE-001_D08_保险调查报告.docx
位置：DOCX 正文第 11 段；unit_index=10；[0,32)

> 本报告参考D02和D03，未获得道路连续视频或完整车载原始数据。

文件SHA256：1e59f417f6bf0f1709b69f1f79b6ade3ff33aa72b061f584bd238d91b08905c3
解析快照SHA256：e6415774c1bcfa7ff9dd4fdbd6b38d69051c68cac1d07075373cd084cd466d65
引文SHA256：60f63ef1f792a4148a1366a02a28035e5d1483a166832917850e9e2dbafba94f

## G025：可以提出原始镜像、字段字典、时钟关系及各提示环节的核查问题，但不假定它们已存在。

类别：pending_evidence, missingness_scope

审查理由：仅生成有材料依据的待核查问题，缺项不补事实。

禁止推断：虚构未提供的设备镜像或鉴定结论；自动加入没有来源的EDR/DSSAD资料

评测方式：manual_semantic；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 16 段；unit_index=15；[0,32)

> 事故绝对时刻、碰撞时ADAS状态、提示输出及驾驶人感知仍待核实。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：47516cc72aa6000432c6d50354e572d34501bb9041f7dda1353bdf4975cfab3e

## G026：八份材料必须分批；Gold/作者设计不得作为模型输入。

类别：batch_limits, evaluation_hygiene

审查理由：数据与答案隔离，联合请求遵守2—4文件及预算，不执行付费调用。

禁止推断：一次发送八份；把作者偏移或答案文件送入模型；以离线通过宣称真实模型能力

评测方式：offline_preflight；自动检查仅限明确列出的有限规则，不代表语义验收。

来源：D07 / 模拟_CASE-001_D07_第三方技术鉴定报告.docx
位置：DOCX 正文第 7 段；unit_index=6；[0,33)

> 本文件是模拟技术鉴定测试报告，不是真实司法鉴定意见，无资质或印章。

文件SHA256：b22cafe0f2d40e2124e67effdef89832899f05f6f9356dff7417c9771f571f28
解析快照SHA256：948eae880505abe1fc51387fbfe1b58f1ad700fbb67a23e98ca0c2866f9dac75
引文SHA256：05d28d361b0f5abdc8b6ebe14d5ff989de76f6510a63de319ae591706893eda2
