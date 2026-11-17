/**
 * 三语情感极性分析台 —— Vue 3 + Ant Design Vue 前端应用
 *
 * 三种页面容器（存在哪个挂哪个）：
 *   #app-analysis  主分析页
 *   #app-lexicon   词典查看（表格 / 搜索 / 分页 / 官方来源）
 *   #app-manual    使用指南（内建 md 阅读器，marked 渲染 + 目录跳转）
 *
 * 双模式：
 *   web 模式     → 数据走 /api/* 与 /files/*
 *   便携版模式    → window.__PORTABLE__ = true，数据走内嵌 PortEngine / DATA / README
 */
(function () {
  "use strict";
  const PORTABLE = window.__PORTABLE__ === true;

  // ============================ 数据适配 ============================
  const Sources = {
    async analyze(text) {
      if (PORTABLE) return PortEngine.analyzeText(DATA, text);
      const r = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "分析失败");
      return d;
    },
    async lexiconEntries(key) {
      if (PORTABLE) {
        const m = {
          zh_sentiment: Object.entries(DATA.zh.lexicon),
          ja_sentiment: Object.entries(DATA.ja.lexicon),
          en_sentiment: Object.entries(DATA.en.lexicon),
          zh_negation: DATA.zh.negation.map((w) => [w]),
          ja_negation: DATA.ja.negation.map((w) => [w]),
          en_negation: DATA.en.negation.map((w) => [w]),
          zh_degree: Object.entries(DATA.zh.degree),
          ja_degree: Object.entries(DATA.ja.degree),
          en_degree: Object.entries(DATA.en.degree),
        };
        return { entries: m[key] || [] };
      }
      const r = await fetch("/api/lexicon/" + key);
      return r.json();
    },
    async manualText() {
      if (PORTABLE) return window.__README_TEXT__ || "";
      const r = await fetch("/files/readme.md");
      return r.text();
    },
  };

  function openPage(name) {
    if (PORTABLE) {
      const ov = document.getElementById(name + "Overlay");
      if (ov) ov.hidden = false;
    } else {
      location.href = "/" + name;
    }
  }
  window.__openPage = openPage;

  // ============================ 心跳续活（web 模式）============================
  // 每个标签页独立 client_id：30 秒心跳续活；关闭标签页时 sendBeacon 通知服务端退出。
  // 页面刷新 / 分析页↔词典页↔使用指南跳转：5 秒宽限期内新页面续活，服务不退出。
  if (!PORTABLE) {
    let cid = sessionStorage.getItem("sa_client_id");
    if (!cid) {
      cid = "c-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      sessionStorage.setItem("sa_client_id", cid);
    }
    const ping = () =>
      fetch("/api/ping", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: cid }),
      }).catch(() => {});
    ping();
    setInterval(ping, 30000);
    window.addEventListener("pagehide", () => {
      // sendBeacon 在页面关闭时仍能送达（普通 fetch 会被浏览器取消）
      const body = JSON.stringify({ id: cid });
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/exit", new Blob([body], { type: "text/plain" }));
      } else {
        fetch("/api/exit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: true,
        }).catch(() => {});
      }
    });
  }

  // ============================ 词典元信息 ============================
  const LEX_META = {
    zh_sentiment: {
      title: "中文情感词典（完整版）",
      name: "知网 HowNet「情感分析用词语集（beta 版）」",
      site: "http://www.keenage.com",
      siteText: "知网 HowNet 官方网站（keenage.com）",
      origin: "GitHub 镜像 buptsaisai/SentimentAnalysisDictionary（官方站点下载不可用时）；原始文件存于 dictionaries/hownet/",
      score: "正面情感词语 +1.5 / 负面情感词语 -1.5 / 正面评价词语 +1.0 / 负面评价词语 -1.0",
    },
    ja_sentiment: {
      title: "日语情感词典（完整版）",
      name: "日本語評価極性辞書（単語感情極性対応表）",
      site: "http://www.cl.ecei.tohoku.ac.jp/index.php/Open_Resources/Japanese_Sentiment_Polarity_Dictionary",
      siteText: "東北大学大学院情報科学研究科 乾・岡﨑研究室 Open Resources",
      origin: "pn.csv.m3.120408.trim（名词语）+ wago.121808.pn（用言），同站直接下载；原始文件存于 dictionaries/",
      score: "p（ポジティブ）→ +1.0，n（ネガティブ）→ -1.0，e（中立）不收录；双向冲突词剔除",
    },
    en_sentiment: {
      title: "英语情感词典（完整版）",
      name: "MPQA Subjectivity Lexicon（Wilson, Wiebe & Hoffmann, 2005）",
      site: "http://mpqa.cs.pitt.edu/lexicons/subj_lexicon/",
      siteText: "MPQA 官方词典发布页（University of Pittsburgh）",
      origin: "subjclueslen1-HLTEMNLP05.tff（GitHub 镜像获取）；原始文件存于 dictionaries/",
      score: "strongsubj ±1.5，weaksubj ±1.0；both / neutral 不收录",
    },
    zh_negation: { title: "中文否定词表", isRule: true, score: "命中后对邻接情感词做极性反转（窗口 2，向左）" },
    ja_negation: { title: "日语否定词表", isRule: true, score: "命中后做极性反转（窗口 2，向右）；含后缀否定拆分（〜ない 等）" },
    en_negation: { title: "英语否定词表", isRule: true, score: "命中后做极性反转（窗口 2，向左）" },
    zh_degree: {
      title: "中文程度词表", isRule: true,
      score: "对情感词分值乘性加权，窗口 2 向左、上限 3.0（极其/最→2.0、超→1.8、很→1.5、较→1.2、稍稍/不足→0.5）",
    },
    ja_degree: { title: "日语程度词表", isRule: true, score: "对情感词分值乘性加权，窗口 2 向左、上限 3.0（非常に→2.0、とても→1.6、少し→0.5 …）" },
    en_degree: { title: "英语程度词表", isRule: true, score: "对情感词分值乘性加权，窗口 2 向左、上限 3.0（extremely→2.0、very→1.5、slightly→0.5 …）" },
  };
  const LEX_FILE = {
    zh_sentiment: "zh_sentiment.csv", ja_sentiment: "ja_sentiment.csv", en_sentiment: "en_sentiment.csv",
    zh_negation: "zh_negation.txt", ja_negation: "ja_negation.txt", en_negation: "en_negation.txt",
    zh_degree: "zh_degree.csv", ja_degree: "ja_degree.csv", en_degree: "en_degree.csv",
  };
  const LEX_ORDER = [
    "zh_sentiment", "ja_sentiment", "en_sentiment",
    "zh_negation", "ja_negation", "en_negation",
    "zh_degree", "ja_degree", "en_degree",
  ];
  const LEX_LABEL = (k) => LEX_META[k].title.replace("（完整版）", "");

  // ============================ 公共样式（Claude 暖色风格） ============================
  // 色板：米色背景 #F0EEE6 / 暖白卡片 / 陶土橙主色 #D97757 / 暖灰文字描边 / 圆角 8px
  const THEME = {
    token: {
      colorPrimary: "#D97757",
      colorLink: "#D97757",
      colorInfo: "#D97757",
      colorError: "#C2503B",
      colorSuccess: "#6E8B5B",
      colorWarning: "#C08A4E",
      colorBgLayout: "#F0EEE6",
      colorBgContainer: "#FAF9F5",
      colorBgElevated: "#FAF9F5",
      colorText: "#57524A",
      colorTextSecondary: "#8A7F6A",
      colorTextTertiary: "#A79C88",
      colorBorder: "#E3DACE",
      colorBorderSecondary: "#EDE6D8",
      borderRadius: 8,
      boxShadow: "0 2px 10px rgba(146,111,79,.10), 0 1px 2px rgba(146,111,79,.06)",
      boxShadowSecondary: "0 2px 8px rgba(146,111,79,.08)",
    },
  };

  const style = document.createElement("style");
  style.textContent = `
    body { background:#F0EEE6; margin:0; }
    .page { max-width:980px; margin:0 auto; padding:28px 20px 64px; position:relative; }
    .page-head { min-height:38px; margin-bottom:30px; padding-right:150px; }
    .app-foot { margin:42px 0 8px; text-align:center; color:#A79C88; font-size:12px; line-height:1.9; }
    .page-head h1 { font-size:25px; margin:0; letter-spacing:.5px; line-height:1.35; color:#3D3529; }
    .page-head .sub { margin:6px 0 22px; color:#8A7F6A; font-size:14px; }
    .manual-btn { position:absolute; top:30px; right:22px; }

    /* ---- AntD 暖色覆盖 ---- */
    .ant-card { background:#FAF9F5 !important; border-color:#E8E0D0 !important; border-radius:8px !important;
      box-shadow:0 2px 10px rgba(146,111,79,.10), 0 1px 2px rgba(146,111,79,.06) !important; }
    .ant-btn { border-radius:8px !important; box-shadow:none !important; font-weight:500; }
    .ant-btn-primary { background:#D97757 !important; border-color:#D97757 !important; }
    .ant-btn-primary:hover, .ant-btn-primary:focus { background:#C86A4D !important; border-color:#C86A4D !important; }
    .ant-btn-default { background:#F6E3D8 !important; color:#B85C3C !important; border-color:#EAC9B4 !important; }
    .ant-btn-default:hover, .ant-btn-default:focus { background:#F0D4C3 !important; color:#A34E31 !important; border-color:#E2B69B !important; }
    .ant-btn-link { color:#B85C3C !important; }
    .ant-tag { border-radius:8px !important; font-weight:500; }
    .ant-tag-red { background:#F2D9CD !important; color:#A34E31 !important; border-color:#E8C0AC !important; }
    .ant-tag-green { background:#DFE7D0 !important; color:#5C7346 !important; border-color:#C7D4AE !important; }
    .ant-tag-orange { background:#EFE0BE !important; color:#8A6830 !important; border-color:#E0CCA0 !important; }
    .ant-tag-blue { background:#E4DDCC !important; color:#6B5D48 !important; border-color:#D3C7AE !important; }
    .ant-tag-default { background:#EFEADD !important; color:#8A7F6A !important; border-color:#E3DBC9 !important; }
    .ant-input, .ant-input-affix-wrapper, .ant-textarea {
      background:#FAF9F5 !important; border-color:#E3DACE !important; border-radius:8px !important; color:#57524A !important; }
    .ant-input:hover, .ant-input-affix-wrapper:hover, .ant-textarea:hover { border-color:#D0BFA6 !important; }
    .ant-input:focus, .ant-input-focused, .ant-input-affix-wrapper:focus-within, .ant-textarea:focus {
      border-color:#D97757 !important; box-shadow:0 0 0 2px rgba(217,119,87,.14) !important; }
    .ant-input::placeholder, .ant-textarea::placeholder { color:#A79C88 !important; }
    .ant-divider { border-color:#E8E0D0 !important; }
    .ant-divider-inner-text { color:#8A7F6A !important; font-size:12.5px; }
    .ant-table { background:#FAF9F5 !important; }
    .ant-table-thead > tr > th { background:#F2EDE1 !important; color:#6B5D48 !important; border-color:#E8E0D0 !important; }
    .ant-table-tbody > tr > td { border-color:#EFE8DA !important; color:#57524A !important; }
    .ant-table-tbody > tr:hover > td { background:#F5F0E4 !important; }
    .ant-pagination .ant-pagination-item-active { border-color:#D97757 !important; }
    .ant-pagination .ant-pagination-item-active a { color:#D97757 !important; }
    .ant-radio-group-solid .ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled) {
      background:#D97757 !important; border-color:#D97757 !important; }
    .ant-radio-button-wrapper { border-color:#E3DACE !important; color:#6B5D48 !important; }
    .ant-radio-button-wrapper:hover { color:#D97757 !important; }
    .ant-statistic-title { color:#8A7F6A !important; }
    .ant-statistic-content { color:#3D3529 !important; }
    .ant-empty-description { color:#A79C88 !important; }
    .ant-list-item-meta-title { color:#3D3529 !important; }
    .ant-list-item-meta-description { color:#8A7F6A !important; }
    .ant-alert { border-radius:8px !important; }
    .ant-alert-error { background:#F7E2D9 !important; border-color:#E8B6A3 !important; }
    .ant-alert-error .ant-alert-message, .ant-alert-error .ant-alert-description { color:#A34E31 !important; }

    /* ---- 极性刻度条 ---- */
    .meter { position:relative; height:18px; margin:18px 0 0; }
    .meter-track { position:absolute; inset:0; border-radius:8px;
      background:linear-gradient(90deg,#6E8B5B 0%,#D9D0BE 50%,#C2503B 100%); }
    .meter-needle { position:absolute; top:-7px; bottom:-7px; width:4px; background:#3D3529;
      border-radius:4px; transform:translateX(-50%); transition:left .45s cubic-bezier(.22,1,.36,1);
      box-shadow:0 0 0 3px rgba(250,249,245,.85); }
    .meter-needle::after { content:""; position:absolute; top:-6px; left:50%; transform:translateX(-50%);
      border-left:6px solid transparent; border-right:6px solid transparent; border-top:7px solid #3D3529; }
    .meter-ticks { display:flex; justify-content:space-between; margin-top:10px; color:#8A7F6A; font-size:12px; }
    .meter-ticks .t-neg { color:#6E8B5B; } .meter-ticks .t-pos { color:#C2503B; }
    .mini-meter { position:relative; height:8px; background:#E8E0D0; border-radius:8px; overflow:hidden; width:120px; }
    .mini-meter > span { position:absolute; top:0; bottom:0; }
    .mini-fill-pos { left:50%; background:#C2503B; } .mini-fill-neg { right:50%; background:#6E8B5B; }
    .big-score { font-size:42px; font-weight:700; line-height:1; font-variant-numeric:tabular-nums; }
    .big-score small { font-size:14px; color:#8A7F6A; font-weight:500; }
    .big-score.pos { color:#C2503B; } .big-score.neg { color:#6E8B5B; } .big-score.neu { color:#A79C88; }
    .score-row { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }

    /* ---- 芯片 / 徽章（暖色） ---- */
    .chip { display:inline-flex; align-items:center; gap:4px; border-radius:8px;
      padding:2px 10px; font-size:12.5px; line-height:1.7; border:1px solid transparent; white-space:nowrap; }
    .chip-pos   { background:#F2D9CD; color:#A34E31; border-color:#E8C0AC; }
    .chip-neg   { background:#DFE7D0; color:#5C7346; border-color:#C7D4AE; }
    .chip-negation { background:#EFE0BE; color:#8A6830; border-color:#E0CCA0; }
    .chip-degree { background:#E4DDCC; color:#6B5D48; border-color:#D3C7AE; }
    .chip-plain { background:#EFEADD; color:#8A7F6A; border-color:#E3DBC9; }
    .chip-lang  { background:#F6E3D8; color:#B85C3C; border-color:#EAC9B4; }
    .badge { display:inline-flex; align-items:center; border-radius:8px; padding:3px 14px;
      font-size:14px; font-weight:700; }
    .badge-pos { background:#C2503B; color:#FBF7F1; }
    .badge-neg { background:#6E8B5B; color:#FBF7F1; }
    .badge-neu { background:#D9D0BE; color:#57524A; }
    .badge-unk { background:#E8E0D0; color:#8A7F6A; }

    /* ---- 使用指南正文 ---- */
    .manual-body { color:#57524A; }
    .manual-body h1 { font-size:22px; margin:.7em 0 .4em; color:#3D3529; }
    .manual-body h2 { font-size:18px; margin:1.3em 0 .5em; padding-bottom:.25em; border-bottom:1px solid #E8E0D0; color:#3D3529; }
    .manual-body h3 { font-size:15.5px; margin:1.1em 0 .4em; color:#4A4237; }
    .manual-body table { border-collapse:collapse; width:100%; font-size:13px; margin:.8em 0; }
    .manual-body th, .manual-body td { border:1px solid #E8E0D0; padding:6px 10px; text-align:left; }
    .manual-body th { background:#F2EDE1; color:#6B5D48; }
    .manual-body code { background:#F0EBDD; border-radius:4px; padding:1px 5px; font-size:12.5px; color:#8A5A3C; }
    .manual-body pre { background:#F0EBDD; border-radius:8px; padding:12px 16px; overflow:auto; font-size:12.5px; }
    .manual-body pre code { background:none; padding:0; color:#57524A; }
    .manual-body blockquote { border-left:3px solid #D97757; background:#F7EDE2; margin:.8em 0; padding:6px 14px; color:#6B5D48; }
    .manual-body a { color:#B85C3C; }

    /* ---- 词典信息卡 ---- */
    .lex-info { background:#F5F0E4; border:1px solid #E8E0D0; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:12.5px; color:#6B5D48; }
    .lex-info .row { margin:2px 0; }
    .lex-info a { color:#B85C3C; }
  `;
  document.head.appendChild(style);

  // ============================ 分析页 ============================
  function mountAnalysis(el) {
    const { createApp, ref, computed } = Vue;
    createApp({
      setup() {
        const text = ref("");
        const result = ref(null);
        const loading = ref(false);
        const error = ref("");
        let timer = null;

        const samples = [
          { label: "中文好评", text: "这个产品非常好用，价格不错，简直完美！" },
          { label: "中文差评", text: "质量太差了，非常糟糕，真的很失望！" },
          { label: "日语好评", text: "この商品はとても素晴らしいです。とても満足しています。" },
          { label: "日语差评", text: "この店はひどくて、とても残念でした。" },
          { label: "英语好评", text: "This product is really great and the service is excellent." },
          { label: "英语差评", text: "The quality is terrible and I am very disappointed." },
          { label: "中文纯中性评价", text: "有满意的地方，也有失望的地方。" },
        ];

        const indexTone = computed(() => {
          const v = result.value && result.value.index;
          if (v === null || v === undefined) return "neu";
          return v > 10 ? "pos" : v < -10 ? "neg" : "neu";
        });
        const needleLeft = computed(() => {
          const v = result.value && result.value.index;
          return v === null || v === undefined ? 50 : Math.max(0, Math.min(100, (v + 100) / 2));
        });
        const labelClass = (label) =>
          label === "正面" ? "pos" : label === "负面" ? "neg" : label === "中性" ? "neu" : "unk";
        const fmt = (v, d = 1) => (v === null || v === undefined ? "—" : (v > 0 ? "+" : "") + Number(v).toFixed(d));

        async function run() {
          const t = text.value.trim();
          if (!t) { result.value = null; error.value = ""; return; }
          loading.value = true;
          error.value = "";
          try {
            result.value = await Sources.analyze(t);
          } catch (e) {
            error.value = e.message || String(e);
          } finally {
            loading.value = false;
          }
        }
        function onInput() {
          clearTimeout(timer);
          timer = setTimeout(run, 350);
        }
        function useSample(s) { text.value = s.text; run(); }
        const allTokens = computed(() =>
          result.value ? result.value.sentences.flatMap((s) => s.tokens || []) : []);
        const matchedRows = computed(() => {
          const rows = [];
          if (!result.value) return rows;
          for (const s of result.value.sentences)
            for (const m of s.matched || [])
              rows.push({ key: rows.length + "-" + m.position, ...m });
          return rows;
        });
        const matchColumns = [
          {
            title: "词条", dataIndex: "word",
            customRender: ({ record }) => {
              const kids = [Vue.h("b", null, record.word)];
              if (record.surface && record.surface !== record.word)
                kids.push(Vue.h("span", { style: { color: "#A79C88", fontSize: "12px" } }, "（" + record.surface + "）"));
              return Vue.h("span", null, kids);
            },
          },
          {
            title: "基础分", width: 90,
            customRender: ({ record }) => Vue.h("span", { style: { fontVariantNumeric: "tabular-nums" } }, record.base_score.toFixed(2)),
          },
          {
            title: "加权后", width: 95,
            customRender: ({ record }) => Vue.h(
              "b",
              { style: { color: record.weighted_score >= 0 ? "#C2503B" : "#6E8B5B", fontVariantNumeric: "tabular-nums" } },
              (record.weighted_score > 0 ? "+" : "") + record.weighted_score.toFixed(2)
            ),
          },
          {
            title: "否定", width: 120,
            customRender: ({ record }) => (record.negated ? "是（" + (record.negation_trigger || "") + "）" : "否"),
          },
          {
            title: "程度", width: 110,
            customRender: ({ record }) => (record.degree ? record.degree + " ×" + record.degree_weight : "—"),
          },
        ];
        return {
          THEME, text, result, loading, error, samples, indexTone, needleLeft, labelClass, fmt,
          run, onInput, useSample, allTokens, matchedRows, matchColumns, PORTABLE,
          openManual: () => openPage("manual"), openLexicon: () => openPage("lexicon"),
        };
      },
      template: `
      <a-config-provider :theme="THEME">
      <div class="page">
        <a-button type="primary" class="manual-btn" @click="openManual">📘 使用指南</a-button>
        <div class="page-head">
          <h1>三语情感极性分析台</h1>
          </div>

        <a-card :bordered="true">
          <a-textarea v-model:value="text" :rows="5" placeholder="在这里输入或粘贴一段话，例如：这个产品非常好用，就是有点贵……" @input="onInput" />
          <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;margin-top:12px">
            <a-space :size="8" wrap>
              <a-button v-for="s in samples" :key="s.label" size="small" @click="useSample(s)">{{ s.label }}</a-button>
            </a-space>
            <span style="color:#8A7F6A;font-size:12.5px">{{ text.length }} 字</span>
          </div>
        </a-card>

        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top:16px" />

        <a-card v-if="result" :bordered="true" style="margin-top:16px">
          <a-space :size="12" wrap>
            <a-tag :color="result.language.code === 'unknown' ? 'default' : 'blue'" style="font-size:13px">
              {{ result.language.name }} · {{ result.language.code === 'unknown' ? '未识别' : result.language.code }}
            </a-tag>
            <span style="color:#8A7F6A;font-size:12.5px">
              置信度 {{ Math.round(result.language.confidence * 100) }}%
              ｜汉字 {{ result.language.counts.han }} · 假名 {{ result.language.counts.kana }} · 拉丁 {{ result.language.counts.latin }}
            </span>
          </a-space>

          <div class="score-row" style="margin-top:18px">
            <div class="big-score" :class="indexTone">
              {{ result.index === null ? '—' : fmt(result.index) }}<small>/100</small>
            </div>
            <a-tag :color="labelClass(result.label) === 'pos' ? 'red' : labelClass(result.label) === 'neg' ? 'green' : labelClass(result.label) === 'neu' ? 'default' : 'default'" style="font-size:14px;font-weight:700">
              {{ result.label }}
            </a-tag>
          </div>
          <div class="meter">
            <div class="meter-track"></div>
            <div class="meter-needle" :style="{ left: needleLeft + '%', opacity: result.index === null ? 0 : 1 }"></div>
          </div>
          <div class="meter-ticks">
            <span class="t-neg">-100 纯负面</span><span>0 中性</span><span class="t-pos">+100 纯正面</span>
          </div>

          <a-row :gutter="16" style="margin-top:16px">
            <a-col :span="8"><a-statistic title="原始加权总分" :value="result.score" :precision="2" :value-style="{ fontSize: '20px' }" /></a-col>
            <a-col :span="8"><a-statistic title="命中情感词" :value="result.matched_count" :value-style="{ fontSize: '20px' }" /></a-col>
            <a-col :span="8"><a-statistic title="句子数" :value="result.sentence_count" :value-style="{ fontSize: '20px' }" /></a-col>
          </a-row>

          <a-divider orientation="left" plain>自动分词</a-divider>
          <a-space :size="[6, 8]" wrap>
            <template v-for="(t, i) in allTokens" :key="i">
              <a-tag v-if="t.kind === 'sentiment'" :color="t.weighted_score >= 0 ? 'red' : 'green'">
                {{ t.text }}<span style="opacity:.8;font-size:11px"> {{ fmt(t.weighted_score, 2) }}</span>
              </a-tag>
              <a-tag v-else-if="t.kind === 'negation'" color="orange">{{ t.text }}</a-tag>
              <a-tag v-else-if="t.kind === 'degree'" color="blue">{{ t.text }}</a-tag>
              <a-tag v-else>{{ t.text }}</a-tag>
            </template>
          </a-space>

          <a-divider orientation="left" plain>匹配到的情感词</a-divider>
          <a-empty v-if="!matchedRows.length" description="没有命中情感词典的词 —— 无法判断极性" />
          <a-table v-else :data-source="matchedRows" :columns="matchColumns" :pagination="false"
                   size="small" :row-key="(r) => r.key" :scroll="{ x: 560 }" />

          <template>
            <a-divider orientation="left" plain>逐句分析</a-divider>
            <a-list size="small" :data-source="result.sentences" :split="true">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta>
                    <template #title>
                      <a-tag color="blue" style="margin-right:8px">{{ item.language.name }}</a-tag>
                      {{ item.text }}
                    </template>
                    <template #description>
                      <a-space :size="12" align="center">
                        <div class="mini-meter">
                          <span v-if="item.index !== null"
                            :class="item.index >= 0 ? 'mini-fill-pos' : 'mini-fill-neg'"
                            :style="{ width: Math.abs(item.index) / 2 + '%' }"></span>
                        </div>
                        <a-tag>{{ item.label }} {{ item.index === null ? '' : fmt(item.index, 0) }}</a-tag>
                      </a-space>
                    </template>
                  </a-list-item-meta>
                </a-list-item>
              </template>
            </a-list>
          </template>

          <a-alert v-for="(w, i) in [].concat(...result.sentences.map(s => s.warnings || []))" :key="'w'+i"
            type="warning" show-icon :message="w" style="margin-top:8px" />
        </a-card>

        <a-empty v-else-if="!loading" description="输入内容后自动分析 ↑" style="margin-top:24px" />

        <a-card :bordered="true" style="margin-top:16px">
          <p style="margin:0 0 14px;font-size:14.5px;line-height:1.9">
            <b>这是个什么工具？</b>它帮你判断一段文字「是夸还是贬」。把评论、评价或感受贴进来，
            它会自动认出你说的是中文、日语还是英语，把句子里带感情色彩的词一个个挑出来，最后算出一个整体分数——
            越接近 +100 说明越正面，越接近 -100 说明越负面，0 就是好坏参半。<br>
            句子里出现「不」「没有」这样的否定词，它会像人一样把意思反过来理解；出现「非常」「很」这样的词，
            会把语气的轻重也算进去。每个词为什么得分、得了多少分，下面的明细里都写得清清楚楚。
          </p>
          <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap">
            <a-button type="primary" size="large" @click="openLexicon">📖 查看词典明细</a-button>
            <div style="color:#8A7F6A;font-size:12.5px;line-height:1.9">
              <b style="color:#3D3529">本工具使用的词典：</b>
              中文 · 知网 HowNet 情感分析用词语集<br>
              日语 · 単語感情極性対応表（日本語評価極性辞書）　｜　英语 · MPQA Subjectivity Lexicon
            </div>
          </div>
        </a-card>
        <div class="app-foot">
          Copyright &copy; 2026 Jasonwei &nbsp;·&nbsp; MIT License &nbsp;·&nbsp; v1.0.0<br>
          本项目以 MIT License 开源发布，完整条款见 LICENSE 文件
        </div>
      </div>
      </a-config-provider>`,
    }).use(antd).mount(el);
  }

  // ============================ 词典查看 ============================
  function mountLexicon(el) {
    const { createApp, ref, computed, onMounted } = Vue;
    createApp({
      setup() {
        const active = ref("zh_sentiment");
        const entries = ref([]);
        const search = ref("");
        const loading = ref(false);
        const meta = computed(() => LEX_META[active.value]);
        const filtered = computed(() => {
          const f = search.value.trim().toLowerCase();
          return f ? entries.value.filter((e) => e[0].toLowerCase().includes(f)) : entries.value;
        });
        const columns = computed(() => {
          const hasScore = entries.value.length && entries.value[0].length > 1;
          const cols = [
            {
              title: "序号", width: 70,
              customRender: ({ index }) => index + 1,
            },
            {
              title: "词条", dataIndex: 0,
              customRender: ({ record }) => {
                const v = record.length > 1 ? Number(record[1]) : 0;
                const color = v > 0 ? "#C2503B" : v < 0 ? "#6E8B5B" : undefined;
                return Vue.h("span", { style: color ? { color, fontWeight: 600 } : {} }, record[0]);
              },
            },
          ];
          if (hasScore)
            cols.push({
              title: "分值", width: 110, dataIndex: 1,
              customRender: ({ record }) => {
                const v = Number(record[1]);
                const color = v > 0 ? "#C2503B" : v < 0 ? "#6E8B5B" : "#8A7F6A";
                return Vue.h("span", { style: { color, fontWeight: 600, fontVariantNumeric: "tabular-nums" } }, (v > 0 ? "+" : "") + v);
              },
            });
          return cols;
        });
        async function load(key) {
          active.value = key;
          loading.value = true;
          search.value = "";
          try {
            const d = await Sources.lexiconEntries(key);
            entries.value = d.entries;
          } finally {
            loading.value = false;
          }
        }
        onMounted(() => load("zh_sentiment"));
        return {
          THEME, active, entries, search, loading, meta, filtered, columns, load,
          LEX_ORDER, LEX_LABEL, LEX_FILE,
          goBack: () => { if (PORTABLE) { document.getElementById("lexiconOverlay").hidden = true; } else location.href = "/"; },
        };
      },
      template: `
      <a-config-provider :theme="THEME">
      <div class="page">
        <a-button class="manual-btn" @click="goBack">← 返回分析页面</a-button>
        <div class="page-head">
          <h1>词典文件查看</h1>
          <p class="sub">本工具实际使用的全部词条（完整版，300 条/页，可搜索、可翻页）；情感词典标注官方名称与官网。</p>
        </div>
        <a-card>
          <a-radio-group v-model:value="active" button-style="solid" size="small" @change="load(active)" style="margin-bottom:12px">
            <a-radio-button v-for="k in LEX_ORDER" :key="k" :value="k" style="font-size:12px">{{ LEX_LABEL(k) }}</a-radio-button>
          </a-radio-group>

          <div class="lex-info" v-if="meta">
            <template v-if="!meta.isRule">
              <div class="row"><b>官方名称：</b>{{ meta.name }}</div>
              <div class="row"><b>官方网站：</b><a :href="meta.site" target="_blank" rel="noopener">{{ meta.siteText }}</a>（{{ meta.site }}）</div>
              <div class="row"><b>获取与转换：</b>{{ meta.origin }}</div>
              <div class="row"><b>分值约定：</b>{{ meta.score }}</div>
            </template>
            <div v-else class="row"><b>规则说明：</b>{{ meta.score }}</div>
          </div>

          <a-space style="margin-bottom:12px" wrap>
            <a-input v-model:value="search" placeholder="搜索词条…（实时过滤）" allow-clear style="min-width:240px" />
            <a-button v-if="!PORTABLE" :href="'/files/lexicon/' + LEX_FILE[active]" download>⬇ 下载本文件</a-button>
          </a-space>

          <a-table
            :data-source="filtered" :columns="columns" :loading="loading" size="small"
            :row-key="(r, i) => String(i)"
            :pagination="{ pageSize: 300, showSizeChanger: false, size: 'small',
                           showTotal: (t) => '共 ' + t + ' 条 · 每页 300 条' }"
            :scroll="{ y: 520 }" />
        </a-card>
        <div class="app-foot">
          Copyright &copy; 2026 Jasonwei &nbsp;·&nbsp; MIT License &nbsp;·&nbsp; v1.0.0<br>
          本项目以 MIT License 开源发布，完整条款见 LICENSE 文件
        </div>
      </div>
      </a-config-provider>`,
    }).use(antd).mount(el);
  }

  // ============================ 使用指南（md 阅读器 + 目录） ============================
  function mountManual(el) {
    const { createApp, ref, onMounted, nextTick } = Vue;
    createApp({
      setup() {
        const html = ref("");
        const toc = ref([]);
        const container = ref(null);
        onMounted(async () => {
          let text = await Sources.manualText();
          // 去掉文内目录小节（右侧已有可跳转目录）
          text = text.replace(/## \u76ee\u5f55[\s\S]*?(?=\n## )/, "");
          html.value = window.marked ? marked.parse(text) : "<pre>" + text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])) + "</pre>";
          await nextTick();
          const root = container.value;
          if (!root) return;
          const heads = Array.from(root.querySelectorAll("h2, h3"));
          toc.value = heads.map((h, i) => {
            h.id = "sec-" + i;
            return { id: "sec-" + i, text: h.textContent, level: h.tagName === "H2" ? 1 : 2 };
          });
        });
        return {
          THEME, html, toc, container,
          goBack: () => { if (PORTABLE) { document.getElementById("manualOverlay").hidden = true; } else location.href = "/"; },
          jump: (id) => {
            const t = document.getElementById(id);
            if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
          },
          PORTABLE,
        };
      },
      template: `
      <a-config-provider :theme="THEME">
      <div class="page">
        <a-button class="manual-btn" @click="goBack">← 返回分析页面</a-button>
        <div class="page-head">
          <h1>使用指南</h1>
        </div>
        <a-row :gutter="20">
          <a-col :span="18">
            <a-card>
              <div class="manual-body" ref="container" v-html="html"></div>
            </a-card>
          </a-col>
          <a-col :span="6">
            <a-card size="small" style="position:sticky;top:16px">
              <template #title>目录</template>
              <div v-if="!toc.length" style="color:#A79C88;font-size:12.5px">加载中…</div>
              <div v-else class="toc-list" style="max-height:70vh;overflow:auto">
                <div v-for="t in toc" :key="t.id"
                  :style="{ marginLeft: t.level === 2 ? '16px' : '0', margin: '4px 0 4px ' + (t.level === 2 ? '16px' : '0') }">
                  <a @click="jump(t.id)" style="cursor:pointer;font-size:12.5px"
                     :style="{ fontWeight: t.level === 1 ? 600 : 400 }">{{ t.text }}</a>
                </div>
              </div>
            </a-card>
          </a-col>
        </a-row>
        <div class="app-foot">
          Copyright &copy; 2026 Jasonwei &nbsp;·&nbsp; MIT License &nbsp;·&nbsp; v1.0.0<br>
          本项目以 MIT License 开源发布，完整条款见 LICENSE 文件
        </div>
      </div>
      </a-config-provider>`,
    }).use(antd).mount(el);
  }

  // ============================ 挂载 ============================
  const mountPoints = [
    ["app-analysis", mountAnalysis],
    ["app-lexicon", mountLexicon],
    ["app-manual", mountManual],
  ];
  for (const [id, fn] of mountPoints) {
    const node = document.getElementById(id);
    if (node) fn(node);
  }
})();
