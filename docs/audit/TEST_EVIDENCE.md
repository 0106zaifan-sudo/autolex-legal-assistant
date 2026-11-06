# 本次审查的执行证据

审查基线和范围见 CODE_REVIEW.md。测试确实重新运行，以下不是沿用先前报告的耗时。

## 执行命令

```bash
# main 工作树
cd /workspace/work/autolex_upload
PYTHONPATH=/workspace/work/python_deps python -m unittest discover -s tests -v
# 结果：14 tests / 1.166s / OK

# 审查工作树，业务代码与 AI 基线5307554相同
cd /workspace/work/autolex_review
PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps python -m unittest discover -s tests -v
# 结果：41 tests / 4.594s / OK

# 纯模拟、校验器级探针
PYTHONPATH=/workspace/work/phase2_deps:/workspace/work/python_deps python docs/audit/probes.py
# 7个场景；无真实模型调用
```

正常安装项目依赖到虚拟环境后，可去掉上述工作目录专用的PYTHONPATH。保存的原始日志使用执行环境日志时区；本文审查日期和计划采用北京时间。

两个基线不是同一工作树，41项包含原14项，不应相加当作独立覆盖。日志中无ScriptRunContext的警告来自Streamlit AppTest环境；损坏PDF的警告来自异常输入测试，最终运行结果为OK。

## 依赖版本

- streamlit: 1.67.0
- pandas: 3.1.1
- pypdf: 6.10.0
- python-docx: 1.2.0
- openpyxl: 3.1.5
- reportlab: 4.4.9
- openai: 2.54.0
- pydantic: 2.14.3

## 证据文件SHA256

- `main_test_run.txt`: `0f827db3eaf9086003c4ffeb55ed2557d5581cc6d2a61506bc4be3141b2f21a8`
- `ai_test_run.txt`: `c4eaf6654114b1ef7e708ebdf9e55a6e38a0f6fd411783137a65259ec93f5458`
- `probe_results.json`: `57bf5f3a423456ae695d9024593244b36445700470fbbbc7a6e8d15dbd966fff`
- `probes.py`: `ae7dc7be602f5d2435a8722a23beeb920e5d422a444b29e0fed5675778c689cb`

## 没有做的验证

没有实际付费API调用、生产站点访问、生产Secrets读取、模型余额查询、法律条款核实、真实案件输入或依赖漏洞扫描。没有模型语义准确率、检索Recall或费用测量结果。实施方案中的阈值和日期均是计划。
