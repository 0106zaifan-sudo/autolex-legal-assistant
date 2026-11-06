# 单场景验收与UI测试隔离

2026-11-06（北京时间）；分支`feature/multi-provider-deepseek`，基线`64282dc`。

## 使用方式

`tools/run_live_acceptance.py`新增`--scenario SIM_A`和`--scenario SIM_B`，只接受这两个固定ID。不指定时保留两份材料的原行为。

安全的离线准备示例：

```bash
python tools/run_live_acceptance.py --scenario SIM_B
```

该模式仅核对固定模拟文件并生成准备报告，不读取Secrets、不询问访问密码、不调用API。报告仍包含SIM_A与SIM_B两行，顶层`selected_scenarios=["SIM_B"]`；SIM_A为`selected=false, call_status=not_run, not_run_reason=not_selected`，模型/token未知，自动检查未执行。Markdown同时明确写出“未选择，未运行”。SIM_B准备阶段也是not_run，直到另行执行真实验收。

日后用户另行明确授权真实调用时，在既有受控验收命令追加`--scenario SIM_B`即可选择一份，也可同时追加`--debug-rejected-samples`启用已有私有失败捕获。所有原有`--run-live`、`--confirm-paid-calls`、本人交互认证、配置与额度要求继续生效；选择场景本身不允许费用。**本轮没有执行真实验收或付费请求。**

## 最小行为变化

- 继续完整验证清单中的两份固定文件及哈希、模拟标识、解析覆盖；只把选中的记录交给模型执行循环。未选文件若损坏仍会使固定验收集校验失败，不因单选忽略材料完整性。
- 预检查调用数按选中记录数计算，字符/请求字节预算仅对选中材料调用`prepare_request`。剩余一次额度且预算够时可运行单样本，双样本仍被阻止。
- 使用原SQLite路径和全部已有调用记录，不清空、不迁移、不换库；真正执行时仍按原原子预留机制计次/占预算，失败不返还。访问认证、并发租约、冷却期（含原60秒批次等待上限）、超时与SDK零自动重试不变。
- 报告始终保留两个场景，按scenario_id关联行，避免选SIM_B却把结果写到SIM_A。未选场景没有分析文件、模型标识、token或自动核对结果。
- 批次阶段和CLI退出码只看选中的场景；SIM_B正常完成时不因SIM_A未选而返回失败。`acceptance_status`仍为not_approved，语义审核仍待人工完成，退出0不代表整个P0已验收。
- 调试开关只显式传给选中场景；捕获规则、目录权限、原文防护及失败不导入案件的行为均不变。

## UI测试污染问题及处理

已核对固定依赖Streamlit 1.67.0的AppTest源码：只有`at.secrets`非空才替换全局`st.secrets`。空值测试可能沿用本地/全局配置；应用的Codespaces补入机制还会读取当前环境中的所选服务商Secret。因此仅不设置测试key不能可靠模拟“没有key”。

新增`tests/ui_isolation.py`，只在测试层执行：

1. 创建新的纯内存空Secrets对象，避免空AppTest退回本地配置；拦截磁盘Secrets解析，测试结束断言未调用。
2. 用显式模拟环境（默认空字典）调用真实`codespaces_values`辅助函数，不检查或修改宿主环境变量的值；需要测Codespaces分支时必须传入明确的虚构环境。
3. 拦截模型运行入口并断言UI测试未调用，避免误接通真实模型。

四个已有UI测试文件接入共享隔离基类，`test_*`断言未改变；只有测试继承和setUp接入变化。生产`ai_ui.load_settings`、Codespaces凭据补入逻辑、配置文件和Secrets模板均未修改，也没有读取、创建或改写实际Secrets。该测试适配使用当前锁定Streamlit版本的私有内存字段，升级Streamlit后需要重新核对AppTest行为。

新增测试用**虚构的宿主Codespaces密钥及不可读取的全局Secrets对象**验证UI无密钥场景，不读取真实环境值。还验证明确传入的虚构Codespaces环境仍能走原服务商补入函数。

## 实际离线验证

```text
python -m unittest discover -s tests -v
Ran 223 tests in 18.167s
OK
```

Python 3.12，使用工作区已有隔离依赖，通过`PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps`加载；依赖版本未修改。原205项用例继续通过，新增18项单场景/费用/调试/UI隔离测试。完整日志见`single_scenario_offline_tests.txt`。

新增测试覆盖默认双样本、SIM_A/SIM_B单选、未选报告及文件、非法ID、未授权费用/非交互/错误密码阻止执行、真实CLI参数转交（只使用内存虚构配置和替身）、单样本剩余额度/预算、保留原账本且失败占用预算、未选样本哈希异常仍阻止、SIM_B私有失败捕获及UI配置隔离。所有SDK执行均为HTTP mock或内存替身，实际模型调用0次。

静态核对原模型调用、Schema/分类/证据/时间校验、安全捕获、权限/限流实现与基线一致；SIM_A/SIM_B文件及manifest/gold未修改。UI原断言保持不变。

## 修改文件

| 文件 | 内容 |
|---|---|
| `tools/run_live_acceptance.py` | 场景参数、提示语、选择传递及退出码 |
| `live_acceptance.py` | 单选、按实际数量预检查、完整报告与执行过滤 |
| `tests/test_single_scenario.py` | 新增18项离线验证 |
| `tests/ui_isolation.py` | 共享测试配置隔离 |
| `tests/test_app.py`、`tests/test_ai_ui.py`、`tests/test_case_ui.py`、`tests/test_providers.py` | 接入UI隔离，保留原断言 |
| `project_archive.py` | 将新增测试和说明纳入下载白名单，继续排除Secrets/运行数据 |
| `README.md`、`TEST_REPORT.md`、`docs/LIVE_AI_ACCEPTANCE.md` | 使用说明与实际测试记录 |
| `docs/SINGLE_SCENARIO.md`、`docs/single_scenario_offline_tests.txt` | 本说明与完整日志 |

本次没有真实模型验收结果。未来另行授权后，应核对指定SIM_B时实际仅一条SDK尝试、SIM_A明确未运行、原账本继续累计，以及绑定失败仍受原私有捕获/人工核验边界约束。不需要为本功能更改Secrets。
