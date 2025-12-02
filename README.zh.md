# NexDR (Nex Deep Research)

<div align="center">

**NexDR** 是一个基于 [Nex-N1](https://huggingface.co/nex-agi/DeepSeek-V3.1-Nex-N1) 能动性模型和 [NexAU](https://github.com/nex-agi/nexau) 智能体框架构建的深度研究智能体。可自主完成任务拆解、并行调研、分析汇总，生成结构化研究报告或可视化演示幻灯片。

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

[English](README.md) | 简体中文

</div>

---

## 🏆 领先性能

在 [DeepResearch Bench](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard) 榜单评测中，NexDR 的综合性能**优于 OpenAI Deep Research**，在信息准确性、报告结构化程度及多模态可视化能力上均展现出领先优势。

![基准测试结果](figs/benchmark.png)

---

## 📦 安装

### 前置要求

- Python 3.12 或更高版本
- pip 或 uv 包管理器

### 使用 uv 安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/nex-agi/NexDR.git
cd NexDR

# 使用 uv 安装
uv sync
```

### 使用 pip 安装

```bash
# 克隆仓库
git clone https://github.com/nex-agi/NexDR.git
cd NexDR

# 安装依赖
pip install -e .
```

### 环境配置

在项目根目录创建 `.env` 文件，添加您的 API 密钥：

```bash
# 大语言模型功能（必需）
LLM_API_KEY=your_openai_api_key_here
LLM_BASE_URL=your_openai_base_url_here
LLM_MODEL=model_name_you_used

# 网络搜索与 Serper 抓取（必需）
SERPER_API_KEY=your_serper_api_key_here

# 网页解析（至少选择一种解析器）
JINA_API_KEY=your_jina_api_key_here
DOC_READER_PROVIDERS=jina,serper

# Langfuse 追踪（可选）
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 🚀 快速开始

### 基础用法

运行研究任务并生成 Markdown 报告：

```bash
python quick_start.py \
  --query "量子计算的最新发展是什么？" \
  --report_format markdown \
  --output_dir workspaces/my_research
```

生成 HTML 演示文稿：

```bash
python quick_start.py \
  --query "分析人工智能对医疗健康的影响" \
  --report_format html \
  --output_dir workspaces/healthcare_research
```

### 命令行参数

- `--query`: 您的研究问题（必需）
- `--report_format`: 输出格式 - `markdown` 或 `html`（默认：`markdown`）
- `--output_dir`: 保存结果的目录（默认：`workspaces/workspace_时间戳`）

### 输出结构

运行研究任务后，工作空间将包含：

```
workspaces/my_research/
├── logs_时间戳.log              # 详细执行日志
├── markdown_report.md           # 研究报告（如果是 markdown 格式）
├── citations.json               # 引用参考文献（如果是 markdown 格式）
├── html_report.html            # HTML 演示文稿（如果是 html 格式）
└── final_state.json            # 执行元数据和统计信息
```

---

## 📸 演示案例：幻灯片智能生成

<div align="center">

### 研究问题

> **"请深度调研分析《黑神话 悟空》的成功，包括研发、发布、评价等全方面，并制作一份幻灯片报告讲解。"**

### 生成的 HTML 幻灯片

<table>
  <tr>
    <td width="50%"><img src="figs/demo_1.png" alt="幻灯片 1" /></td>
    <td width="50%"><img src="figs/demo_2.png" alt="幻灯片 2" /></td>
  </tr>
  <tr>
    <td width="50%"><img src="figs/demo_3.png" alt="幻灯片 3" /></td>
    <td width="50%"><img src="figs/demo_4.png" alt="幻灯片 4" /></td>
  </tr>
  <tr>
    <td width="50%"><img src="figs/demo_5.png" alt="幻灯片 5" /></td>
    <td width="50%"><img src="figs/demo_6.png" alt="幻灯片 6" /></td>
  </tr>
  <tr>
    <td width="50%"><img src="figs/demo_7.png" alt="幻灯片 7" /></td>
    <td width="50%"><img src="figs/demo_8.png" alt="幻灯片 8" /></td>
  </tr>
  <tr>
    <td width="50%"><img src="figs/demo_9.png" alt="幻灯片 9" /></td>
    <td width="50%"><img src="figs/demo_10.png" alt="幻灯片 10" /></td>
  </tr>
  <tr>
    <td width="50%"><img src="figs/demo_11.png" alt="幻灯片 11" /></td>
    <td width="50%"><img src="figs/demo_12.png" alt="幻灯片 12" /></td>
  </tr>
  <tr>
    <td colspan="2"><img src="figs/demo_13.png" alt="幻灯片 13" /></td>
  </tr>
</table>

</div>

---

<div align="center">

**⭐ 如果您觉得 NexDR 有用，请在 GitHub 上给我们一个 Star！⭐**

</div>
