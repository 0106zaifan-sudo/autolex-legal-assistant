# P0真实模型集成：准备完成，等待用户安全配置

日期：2026-11-06（北京时间）。分支：`feature/live-ai-acceptance`。
父基线：`feature/case-structure-parse-coverage`的`267de0bef77ca71b3f8ea99014867a021bf66188`。

**当前没有真实付费模型调用。** 本次只完成无密钥代码、两份模拟材料、离线安全测试及验收工具。按用户要求停在安全配置节点，不读取现有Secret内容、不检查API余额、不自动部署或修改main。

后续多服务商适配见[MULTI_PROVIDER.md](MULTI_PROVIDER.md)。本工具现可按`AI_PROVIDER`选择OpenAI或DeepSeek，默认准备模式仍不读取凭据、不调用任一模型。以下原OpenAI基线与135项历史测试保留供溯源；Codespaces的安全Secret补入方式及本轮测试以新说明为准。

## 1. 当前验收状态

| 场景 | 材料 | 真实调用状态 | 服务端模型标识 | token | 内容正确性/人工核验 |
|---|---|---|---|---|---|
| SIM_A | 模拟_接管提示争议.docx | not_run | 未获得 | 未获得，不填0 | 未验收 |
| SIM_B | 模拟_时间缺失与日志核验.docx | not_run | 未获得 | 未获得，不填0 | 未验收 |

真实尝试0次，不存在可声称的真实准确率或真实模型错误案例。机器可读状态见`LIVE_AI_ACCEPTANCE_STATUS.json`。预设核对项是对自建虚构材料的人工预期，不是模型生成结果。

SIM_A重点核对：碰撞11月1日08:30、维修11月2日09:00不能错配；两方对接管提示的相反主张分别保留；日志完整性待核实。

SIM_B重点核对：碰撞没有具体时间，不能借11月4日材料接收日期填补；接收记录只有日期精度，不补午夜；主张、日志核验问题与事实分开。

两份文件均在文件名、正文首行明确标注完全虚构。`acceptance_samples/manifest.json`绑定文件哈希和核对项；验收工具只接受固定SIM_A/SIM_B，哈希改变或路径逃逸立即停止，不接受任意真实上传文件。

## 2. 检查发现与修复

| 检查项 | 基线问题 | 本次实现 |
|---|---|---|
| 官方SDK | responses.parse本地解析失败时难以保留原响应usage；原model字段只是请求名 | 继续使用官方OpenAI SDK和Responses API，改为严格Schema的responses.create，先保留元数据再本地Pydantic/引证校验。离线测试核对Schema与官方SDK.parse产生的Schema一致 |
| 解析覆盖 | 已有覆盖确认、失败关闭和快照绑定 | 保留并检查报告的文件哈希/解析版本匹配；不完整报告须明确确认已读范围，失败/拒绝的文件不能调用 |
| 单实例限流 | 已有次数、冷却和120秒在途租约，但相对数据库路径可能因启动目录不同分成两份 | 复用原SQLite原子事务；相对路径统一解析到项目根，CLI与Streamlit共用；真实批次还要求AI_SINGLE_INSTANCE=true |
| 累计输入 | 原来仅限制单文档24000字符/80块，没有请求级/累计输入账本 | 增加单请求编码预算、全应用日预算、访问主体小时预算；预算包含提示、Schema和请求编码余量，不只数正文；失败仍占次数和输入预算 |
| 旧账本 | 旧记录没有输入量 | 自动迁移，按每旧调用24000字符/256000请求字节保守占用，并标legacy_upper_bound；不把未知历史输入当零，不冒充真实token |
| 超时 | SDK阶段30秒不是总墙钟截止，线程取消不能终止请求 | 默认真实调用使用spawn子进程，默认45秒总截止，最大配置90秒；超时终止/kill并join后才释放租约，关闭自动重试。进程截止行为用独立睡眠进程测试 |
| 记录 | 原结果缺少provider model、usage和校验失败的调用凭据 | 生成call_receipt，记录实际返回模型标识、状态、响应ID、usage、耗时、版本、输入预算及验证状态；结构/引证失败仍保留元数据，无用量时为null |
| 批次安全 | 连续两次会撞30秒冷却，出错可能被当成功 | 批次预检查两次预算与次数，顺序执行并尊重冷却；401/429/取消后不继续第二次，不自动重试，不自动批准语义验收 |
| 测试来源 | mock容易被误当成真实验收 | 注入executor必为offline_test；注入SDK客户端标injected_test_client；真实批次拒收注入测试模式的结果；未运行和未知用量不填假值 |

默认预算：全应用每天20次、同主体滚动小时5次、冷却30秒；日/小时正文字符分别100000/50000；单请求完整编码预算128000字节，日/小时累计512000/256000字节；最大输出4000token。

字节预算是UTF8请求编码量加余量的保守预留，不是服务商token数，不是金额。实际token只从服务商响应的usage记录；价格和费用未核实就不报金额。总截止针对模型工作进程并包含启动，终止清理可能额外耗时约2秒；不包含文件解析或报告写入。duration_ms包含工作进程和本地验证，不是纯服务商网络延迟。停止本地进程不保证服务端取消或不计费，超时/中断后的用量可能未知，禁止自动重试。

数据库只对同一持久文件的单实例有效，single_instance是部署者确认，不是程序能证明的事实。不同副本/磁盘须外部统一限流；服务商项目预算/告警是否硬限制须以服务商实际能力为准。未增加累计上传内存预算、解析进程隔离或公网多租户能力。

## 3. 无密钥阶段已实际执行

```text
python -m unittest discover -s tests -v
Ran 135 tests in 13.250s
OK
```

包含父基线113项原测试和新增22项；原113项所在9个测试文件未修改。新增覆盖累计预算、旧表迁移、失败不退预算、真实返回标识及usage提取、结构/引用失败元数据、官方Schema一致、进程硬截止/清理、模拟材料哈希、批次预算、mock不能冒充live、无费用开关不调用、prepare不读Secrets、不交互认证不继续及取消不执行第二份。

这是离线工程验证，不是模型效果验证。测试中的token数字和mock模型标识只用于断言字段处理，绝不写入真实验收状态。完整日志见`live_acceptance_offline_tests.txt`。没有进行浏览器视觉验收。

还实际执行了：

```bash
python tools/run_live_acceptance.py
```

该默认模式只校验两份模拟材料并生成准备报告，不读取Secrets、不询问密码、不访问OpenAI。输出目录为`.autolex_runtime/acceptance/preparation/`，已被Git忽略。仓库中的状态JSON是该准备状态的可审阅副本。

## 4. 现在需要用户完成安全配置

请不要在聊天里发送API密钥、访问密码、完整Secrets文件或包含它们的截图。

推荐在自己的电脑、自己的交互式终端完成；如果当前云环境提供仅本人可见的安全文件编辑入口，也可配置同一文件并在本人终端运行。单独在其他已部署站点设置Secrets不会自动配置此工作区。当前不需要公开部署。

### 4.1 取得并安装本分支

```bash
git switch feature/live-ai-acceptance
python -m pip install -r requirements.txt
```

使用Python3.12虚拟环境，进入项目根目录。已有独立副本也可先fetch再切换本分支。Windows虚拟环境命令见README。

### 4.2 准备访问密码哈希

```bash
python tools/hash_password.py
```

在自己的终端输入12–128字符访问密码，程序只输出带随机盐的PBKDF2哈希。保留密码供真实验收时本人交互输入；不要把密码发给助手。

### 4.3 安全创建Streamlit Secrets

复制`.streamlit/secrets.example.toml`为`.streamlit/secrets.toml`，**在自己的安全编辑器中**填写：

- `OPENAI_API_KEY`：你的OpenAI API项目专用密钥；API项目需要可用模型及额度。ChatGPT订阅不代表API额度。
- `APP_PASSWORD_HASH`：上一步输出的哈希，不是明文密码。
- `OPENAI_MODEL`：自己项目可用的模型标识；默认gpt-4.1-mini只是请求默认值，本轮未验证其对你的账户是否可用。
- 保留`APP_MODE="public"`、`AI_SINGLE_INSTANCE=true`；这不会发布站点，只保留访问门槛。
- `AI_LIMIT_DB`使用可写、持久的同一路径；默认相对路径统一到本项目根。不要删除/另建数据库绕过限额。
- 保留新模板中的预算及超时默认值，第一批只执行两份模拟材料。

Linux/macOS执行：

```bash
chmod 600 .streamlit/secrets.toml
git check-ignore -v .streamlit/secrets.toml
```

Windows通过文件安全属性限制为本人可读写；脚本的POSIX权限检查不替代Windows ACL。不要把密钥放到命令行参数、环境变量回退、Python代码或GitHub；不执行git add -f。标准Secrets文件及运行输出已加入.gitignore，源码下载仍使用白名单。

### 4.4 配置完成后才运行真实验收

**以下命令可能产生API费用；本次没有替你运行。** 请在自己的交互式终端执行：

```bash
python tools/run_live_acceptance.py --run-live --confirm-paid-calls
```

程序会在终端无回显询问访问密码，验证后只处理两份固定模拟材料。非交互管道拒绝认证；不要用聊天提供密码。总计最多两次尝试，默认间隔30秒，失败也占次数/输入预算。没有两个预算余额时整批在请求前停止。

缺少密钥、密码错误、解析或哈希异常、预算不足、CLI费用确认缺失时不会发起模型请求。401/429/用户取消后第二份保持not_run。预检查是某一时刻余额快照，真正每次调用仍有SQLite原子检查，其他会话可能使第二次被阻止。

### 4.5 保管并复核输出

输出在`.autolex_runtime/acceptance/<run-id>/`，不提交Git：

- `report.json`、`report.md`：实际执行类型、每份状态、模型标识、token、错误及程序检查。
- `SIM_A_analysis.json`、`SIM_B_analysis.json`：仅在结构和引证验证通过时保存。失败不会伪造分析文件。

访问密码/密钥不在报告里。`provider_model`是服务端实际返回标识；若服务端只返回别名，不能擅自推断固定快照版本。兼容字段model仍是请求标识，以call_receipt的requested_model/provider_model区分。

actual_live_attempts记录默认真实路径的尝试，不等于服务商一定收到请求；网络故障/进程超时会标unknown，用量为null。没有响应不等于不计费。

程序只做预设短语、时间绑定、来源回放和待核实项的检查，标literal_fixture_checks_not_accuracy；不是法律语义准确率。即使程序检查全过，仍保持not_approved并等待人核对：

1. 关键事实是否保留原意、是否遗漏关键条件。
2. 主张是否分别归属、冲突是否保留、是否被误当事实。
3. 碰撞/维修/接收日期是否正确，未知是否仍未知、日期精度是否被保留。
4. 每条引用是否支持对应内容，位置是否正确；推断是否带入材料没有的假设。
5. 待核实项是否真的是需核实的问题，没有编造法条、案例、责任或金额。

当前没有自动批准人工语义审查的命令。保留人工复核人、时间、通过/不通过和具体错误记录；在尚无真实输出时不预填。可提供不含Secret的验收报告和模拟分析文件继续复核，不能提供Secrets。

## 5. 修改文件

- `security.py`：原限流扩展输入预算、迁移和一致数据库路径；访问哈希验证复用。
- `model_runtime.py`（新增）：官方SDK响应元数据与可终止子进程。
- `ai_analysis.py`：完整请求预算、默认有界调用、调用记录及错误保留；保留原Schema/引证校验。
- `ai_ui.py`、`app.py`：最近调用记录查看/下载与清理，不重做原流程。
- `live_acceptance.py`、`tools/run_live_acceptance.py`（新增）：默认准备、受控两份验收、交互认证、费用开关与报告。
- `make_acceptance_samples.py`、`acceptance_samples/`（新增）：模拟材料及预设核对清单。
- `tests/test_live_acceptance.py`（新增）：22项离线测试。
- `.streamlit/secrets.example.toml`、`project_archive.py`、README、TEST_REPORT、本说明及状态/日志：安全模板、下载白名单和验收证据。

未改动文档解析、案件结构、已确认事实规则、原113项测试或依赖版本。未上传实际密钥、运行账本或真实材料。

## 6. 尚未验收及已知边界

真实模型能否成功、其返回标识/usage、关键事实是否正确、两份材料的语义效果均未验证；会在安全配置后如实记录成功或失败。严格输出可能被模型拒绝或截断，不能为凑两次成功而自动重试。

spawn进程启动/终止只完成本机离线行为测试，尚未在用户最终部署平台做真实网络验收；平台若禁止子进程则失败关闭，不能退回无限线程。子进程截止不保证远端取消或费用归零。测试注入客户端路径不提供同等硬截止保证，不可用于真实验收。

保留原解析/OCR/语义支持、单实例及会话内存边界。该准备分支不是生产安全或法律结论正确的证明，也不代表整个P0已验收。

离线日志SHA256：`cae31fbadde049291f1b5267d91fcc4cbbbfb7c3275be8f58cc7b3928e145ab8`。

## 固定模拟材料的可选失败捕获

新增默认关闭的`--debug-rejected-samples`，仅在用户另行明确运行受控真实验收时追加；它不替代费用确认或认证。普通上传界面不提供该入口，不需要新增或改动Secrets。仅固定SIM_A/SIM_B的Schema通过而绑定失败输出可进入被忽略的私有目录，失败继续拒绝。原始输出保存、权限、拒绝条件和完全离线回放见[SIM_B定位与调试](SIM_B_DEBUG.md)。本轮未执行真实验收。

## 单场景选择

`--scenario SIM_A`或`--scenario SIM_B`可限定本批次；不指定仍选两份。没有`--run-live`时只是离线准备，绝不因场景选择允许付费。真实模式仍需原显式付费确认和认证，可与`--debug-rejected-samples`并用；只对选中材料核算预算，保留原共享账本。报告同时列出未选场景为not_run/not_selected。详情见[单场景说明](SINGLE_SCENARIO.md)。
