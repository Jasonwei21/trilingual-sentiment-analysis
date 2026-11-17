# 🎯 三语情感极性分析台

> **中文 / 日本語 / English** 三语情感极性判定工具 —— 写一段话进来，马上告诉你它是「夸」还是「贬」。

**v1.0.0**

---

## ✨ 功能特性

- 🌐 **自动识别语言** —— 中 / 日 / 英混着写也认得出，逐句分析
- ✂️ **自动分词** —— jieba / fugashi+UniDic / 空格分词，命中词一目了然
- 📊 **-100 ～ +100 倾向分** —— 越接近 +100 越正面，越接近 -100 越负面
- 🔄 **像人一样理解** —— 「不」「没有」自动反转，「非常」「很」算进语气轻重
- 🔍 **结果可溯源** —— 每个词为什么得分、得了多少分，明细全公开
- 📖 **词典可查验** —— 内置词典浏览器，全部词条可搜索、可下载

## 🚀 快速开始

**Windows（免安装）**
```
解压 三语情感极性分析-Windows.zip → 双击 SentimentAnalysis.exe
```
关闭浏览器标签页即自动退出，无需 Python、无需联网。

**macOS（免安装）**
```
在 Mac 上双击 packaging/build_mac.command 打包 → 双击 SentimentAnalysis.app
```

**源码运行**
```bash
pip install -r requirements.txt
python webapp/app.py --open     # 打开 http://127.0.0.1:8765
```

## 📝 一分钟看懂

输入：

```
这个产品非常好用，价格不错，简直完美！
```

输出：

| 指标 | 结果 |
|---|---|
| 倾向分 | **+100**（越接近 +100 越正面） |
| 标签 | 正面 |
| 命中 | 好用 ×2.0、不错、完美 |

更多示例（否定、程度、中英日混排、中性对冲）见 [使用指南](docs/MANUAL.md)。

## 🧠 判定原理（一句话版）

> 词典匹配 + 否定反转（窗口 2）+ 程度加权（上限 3.0）→ 词级加权分取平均 → 归一到 -100～+100

| 语言 | 情感词典 | 词条数 | 分词 |
|---|---|---|---|
| 中文 | 知网 HowNet 情感分析用词语集 | 8754 | jieba |
| 日语 | 単語感情極性対応表（日本語評価極性辞書） | 13575 | fugashi + UniDic-lite |
| 英语 | MPQA Subjectivity Lexicon | 6451 | 空格/正则 |

完整规则、公式、参数、局限性与参考文献 → [docs/MANUAL.md 第二部分](docs/MANUAL.md)（论文方法部分可直接取材）

## 📂 项目结构

```
trilingual_sentiment/   判定引擎（分析器 / 规则 / 词典 / 语言检测）
webapp/                 Web 界面（Vue 3 + Ant Design，离线可用）
dictionaries/           三大词典原始资源（论文溯源）
docs/                   完整使用手册与方法说明
packaging/              Windows / macOS 打包配置
tools/                  词典构建、图标、便携版生成
tests/                  63 项测试（Python + jsdom DOM 冒烟）
```

## 🛠 二次开发

```bash
python -m unittest discover -s tests -v          # 跑测试
python -m PyInstaller --noconfirm --clean packaging/build_exe.spec   # 打 exe
bash packaging/build_mac.command                  # 打 macOS 包
```

- **换词典**：编辑 `trilingual_sentiment/data/*.csv`，或用加载器接入 HowNet / MPQA / 単語感情極性対応表 原始格式
- **调规则**：否定词 `*_negation.txt`、程度词 `*_degree.csv`，窗口与上限在 `SentimentAnalyzer(...)` 配置
- **API**：`POST /api/analyze {"text": "..."}` → 倾向分 / 标签 / 逐句明细；Python API 见 [docs/MANUAL.md](docs/MANUAL.md)

## 👤 作者

硕士在读，平时喜欢 vibe coding 一些小东西。

## 🙏 鸣谢

- 📚 三大情感词典：知网 **HowNet** 情感分析用词语集 · **単語感情極性対応表**（日本語評価極性辞書）· **MPQA Subjectivity Lexicon**
- 🤖 小爱同学（Xiaomi MiMo）
- ⚡ Codex

## 📄 版权与许可

```
Copyright (c) 2026 Jasonwei
```

本项目以 **MIT License** 开源发布，详见 [LICENSE](LICENSE)。词典原始资源版权归原发布方所有，引用请注明各词典版本与出处（见手册第二部分参考文献）。
