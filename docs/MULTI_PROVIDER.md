# 多服务商适配与离线验收

基线：`feature/live-ai-acceptance` 的 `c9621de`；开发分支：`feature/multi-provider-deepseek`。不修改main、不部署、不执行真实付费调用。

## 架构与官方兼容性核对

`ai_providers.py`集中固定官方端点、模型默认值、请求适配及token记账。`Settings.api_key`仅保存当前服务商的密钥（repr隐藏），不保存或发送另一服务商的凭据。SDK、进程截止、配额、解析覆盖确认、案件结构、Schema 2.0及引文/事件时间绑定仍复用原实现。

核对日期：2026-11-06。依据DeepSeek[官方Responses指南](https://api-docs.deepseek.com/guides/responses_api/)、[接口参考](https://api-docs.deepseek.com/api/create-response/)及[定价说明](https://api-docs.deepseek.com/quick_start/pricing/)。这是文档兼容性核对，尚无账户实际响应验证。

| 项目 | OpenAI | DeepSeek |
|---|---|---|
| 配置 | `AI_PROVIDER="openai"`；旧配置缺省保持openai | 新模板推荐`AI_PROVIDER="deepseek"` |
| 固定base_url | `https://api.openai.com/v1` | `https://api.deepseek.com` |
| SDK/协议 | 官方openai 2.54.0，`client.responses.create` | 同一官方SDK，`client.responses.create`，POST `/responses` |
| 默认请求模型 | `OPENAI_MODEL="gpt-4.1-mini"` | `DEEPSEEK_MODEL="deepseek-flash"` |
| 凭据 | `OPENAI_API_KEY` | `DEEPSEEK_API_KEY` |
| 结构化请求 | `text.format`含`type=json_schema,name,strict=true,schema` | 官方列出`type=json_schema,name,schema`；不发送未列出的strict |
| 参数差异 | 原有`store=false,truncation=disabled`保留 | 不发送不支持的store/truncation；文档说明接口无状态、超窗400 |
| 思考模式 | 原有行为不变 | `reasoning.effort="none"`显式关闭默认思考，控制4000输出token预算 |
| 返回处理 | 读取status/model/id、SDK的output_text和usage | 文档为兼容Responses结构；同样处理，不按Chat Completions的choices或prompt_tokens解析 |
| 用量明细 | input/output/total及可用明细 | input/output/total、input_tokens_details.cached_tokens、output_tokens_details.reasoning_tokens |

DeepSeek没有使用Chat Completions的`response_format`，也没有将`json_object`当作JSON Schema。没有自动降级为自由文本、另一模型或另一服务商。服务端声称符合Schema也必须通过本地Pydantic和原文引证验证；失败不保存分析，usage仍保留。官方未列出的strict不能当作已验证支持；具体Schema子集、模型账户权限、返回版本及实际时延需要日后真实验收。

完整请求字节预算在服务商适配后计算。固定端点不读取OPENAI_BASE_URL或自定义代理URL配置。公开访问门禁、跨会话SQLite原子限流、单实例确认、累计输入预算、SDK零重试/30秒超时、默认45秒可终止进程均保留。切换服务商不改变同一SQLite额度，不能借此重置预算。界面确认写明所选服务商；切换模型、服务商或资料会重置发送许可和最近结果。401/402/429及取消后停止批次，不继续第二份。

`token_usage`保留SDK反序列化后的非空usage字段，包括服务商额外字段；不把SDK自动添加的null当作实测。`billing`记录缓存命中/未命中和推理token；缓存是输入子集，推理是输出子集，不能再次加到total。无usage时为null，不能当作零。金额和币种均为null，status=`not_reconciled`；本项目不猜动态费率、缓存折扣、峰谷时段或实际账单。超时不保证服务商未计费。输入预算是预留字符/字节量，不是实际token或货币金额。

## Codespaces安全配置（不在聊天中提供密钥）

1. 在GitHub仓库 **Settings → Secrets and variables → Codespaces → New repository secret** 新建`DEEPSEEK_API_KEY`，值只在GitHub的Secret输入框填写。也可在个人Settings的Codespaces Secrets创建并只授权本仓库。不要使用普通Actions Secret或仓库变量代替。
2. 在自己的Codespace切换到本分支。新建Secret后停止并重新启动该Codespace，使Secret作为环境变量注入。不要运行`env`、`printenv`或`echo`来显示密钥。
3. 在Codespaces终端安装依赖并创建本地配置：

```bash
python -m pip install -r requirements.txt
umask 077
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
chmod 600 .streamlit/secrets.toml
python tools/hash_password.py
```

`hash_password.py`交互读取访问密码，只输出哈希。在Codespaces编辑器打开`.streamlit/secrets.toml`，只填写生成的`APP_PASSWORD_HASH`，保留模板的`AI_PROVIDER="deepseek"`、`DEEPSEEK_MODEL="deepseek-flash"`、`AI_SINGLE_INSTANCE=true`和预算。`DEEPSEEK_API_KEY`保持空字符串即可。实际密码不写文件、不发聊天。不要把完整Secrets文件、哈希或终端截图提交仓库。

4. 仅当平台`CODESPACES="true"`时，应用和真实验收CLI从环境补入**所选服务商同名密钥**；显式非空Streamlit Secret优先。普通本地/部署环境仍只从Streamlit Secrets读取。直接调用`Settings.from_secrets`本身不读取环境。无选中服务商密钥时禁用AI，不借用另一密钥。
5. 可先运行不联网的准备检查和离线测试：

```bash
python tools/run_live_acceptance.py
python -m unittest discover -s tests -v
streamlit run app.py
```

在Codespaces Ports打开8501预览，端口Visibility保持**Private**。网页启动和离线演示不调用模型；点击真实分析才可能计费。本轮没有运行模型分析或公开部署。

普通环境可在本人私有编辑器中将选定密钥填入Streamlit Secrets；不要把密钥放在shell命令参数中。切换OpenAI时设置`AI_PROVIDER="openai"`及同名`OPENAI_API_KEY`，无需更改代码。不要更换数据库路径来绕过现有调用预算。

## 日后的真实SIM_A/SIM_B验收（本轮未执行）

工具继续限定原清单哈希绑定的两份模拟DOCX，不需要修改样本或测试gold。配置完成、本人明确愿意支付费用时，才在自己的交互式终端运行：

```bash
python tools/run_live_acceptance.py --run-live --confirm-paid-calls
```

CLI读取相同安全配置并验证访问密码，按DeepSeek执行两份材料，保留原覆盖检查、冷却和共享配额；报告记录provider/base_url、请求模型、服务商返回模型、调用状态、SDK版本、usage、billing及本地核验结果。分析JSON仍可回放文件哈希、引文及原文偏移。输出位于忽略的`.autolex_runtime/acceptance/`，不要把真实材料混入样本。

注入HTTP或executor的测试始终标为`injected_test_client`或`offline_test`、真实尝试0次。真实批次拒绝测试模式或服务商不匹配的回执。金标准字面检查不是准确率；语义正确性仍需人工逐项审查。未运行真实模型前，不填真实模型版本、token、准确率或验收通过。

## 本轮测试与剩余边界

实际测试记录见[TEST_REPORT](../TEST_REPORT.md)及`multi_provider_offline_tests.txt`。新增`tests/test_providers.py`覆盖服务商选择/独立凭据、Codespaces补入、官方SDK的DeepSeek请求/响应、Schema/证据失败、401/402/429/网络异常、超时通路、token明细与未知费用、共用预算、SIM_A/B离线全链路和界面许可重置。

未执行真实付费调用；两份材料的真实状态仍为not_run；无法证明账户可用、服务端完整Schema支持或法律分析准确率。仍无OCR、知识库扩展、多实例配额或生产部署验收。这里的billing是待对账记录，不是计价引擎。固定默认模型可能随官方别名更新，应以日后响应model和服务商账单核验；不能把文档上的模型快照当作实测版本。
