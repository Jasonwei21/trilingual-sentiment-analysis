/**
 * 三语情感极性判定引擎（便携版）。
 *
 * 与 Python 实现（trilingual_sentiment/analyzer.py + webapp/app.py）规则一致：
 * - 语言识别：假名→ja，汉字→zh，拉丁→en
 * - 分词：词表最长匹配（en 空格/正则 + 缩写展开）；ja 含连用形还原（く→い）
 * - 构词拆分：否定前缀/后缀、程度前缀
 * - 否定反转：窗口 2，zh/en 向左、ja 向右，奇偶取反（双重否定复原）
 * - 程度加权：窗口 2 向左，连乘并以 3.0 封顶
 * - 倾向分：I = clip(平均加权分 / 2.0) × 100；|I| ≤ 10 视为中性
 *
 * UMD：浏览器挂载 window.PortEngine，Node 可 require。
 */
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) module.exports = factory();
  else root.PortEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LABEL_POSITIVE = "正面";
  const LABEL_NEGATIVE = "负面";
  const LABEL_NEUTRAL = "中性";
  const LABEL_UNKNOWN = "无法判断";

  const MAX_DEGREE = 3.0;
  const NEG_WINDOW = 2;
  const DEG_WINDOW = 2;
  const SCORE_UNIT = 2.0;
  const NEUTRAL_BAND = 10.0;
  const MAX_VOCAB_MATCH = 8;

  // 语言构词配置（与 analyzer._LANGUAGE_DEFAULTS 一致）
  const LANG_CFG = {
    zh: {
      name: "中文",
      prefixes: ["不", "没", "无", "未", "非", "别", "莫", "勿"],
      suffixes: [],
      negDirection: "left",
    },
    ja: {
      name: "日本語",
      prefixes: [],
      suffixes: ["なかった", "ません", "ない", "なかっ", "ず", "ぬ"],
      negDirection: "right",
    },
    en: {
      name: "English",
      prefixes: [],
      suffixes: ["n't"],
      negDirection: "left",
    },
  };

  const HAN_RE = /[\u3400-\u4dbf\u4e00-\u9fff\uF900-\uFAFF]/g;
  const KANA_RE = /[\u3040-\u30FF]/g;
  const LATIN_RE = /[A-Za-z]/g;
  const CJK_RUN_RE = /[\u3400-\u4dbf\u4e00-\u9fff\uF900-\uFAFF\u3040-\u30FF]+|[A-Za-z]+(?:'[A-Za-z]+)?/g;

  function detectLanguage(text) {
    text = text || "";
    const han = (text.match(HAN_RE) || []).length;
    const kana = (text.match(KANA_RE) || []).length;
    const latin = (text.match(LATIN_RE) || []).length;
    const counts = { han: han, kana: kana, latin: latin };
    const total = han + kana + latin;
    if (total === 0) {
      return { code: "unknown", name: "未知", confidence: 0, counts: counts };
    }
    let code, share;
    if (kana > 0) {
      code = "ja";
      share = (kana + han) / total;
    } else if (han > 0) {
      code = "zh";
      share = han / total;
    } else {
      code = "en";
      share = latin / total;
    }
    return {
      code: code,
      name: LANG_CFG[code].name,
      confidence: Math.round(Math.min(1, Math.max(0, share)) * 1000) / 1000,
      counts: counts,
    };
  }

  function splitSentences(text) {
    return String(text)
      .split(/[。！？!?]+|(?<=\.)\s+|[\n；;]+/)
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
  }

  function buildProfiles(data) {
    const profiles = {};
    for (const code of Object.keys(LANG_CFG)) {
      const d = data[code] || { lexicon: {}, negation: [], degree: {} };
      const lexicon = new Map(Object.entries(d.lexicon || {}));
      const negation = new Set(d.negation || []);
      const degree = new Map(Object.entries(d.degree || {}).map(function (kv) { return [kv[0], Number(kv[1])]; }));
      const vocab = new Set();
      lexicon.forEach(function (_v, k) { vocab.add(k); });
      negation.forEach(function (k) { vocab.add(k); });
      degree.forEach(function (_v, k) { vocab.add(k); });
      const cfg = LANG_CFG[code];
      profiles[code] = {
        code: code,
        name: cfg.name,
        lexicon: lexicon,
        negation: negation,
        degree: degree,
        vocab: vocab,
        prefixes: cfg.prefixes.slice().sort(function (a, b) { return b.length - a.length; }),
        suffixes: cfg.suffixes.slice().sort(function (a, b) { return b.length - a.length; }),
        negDirection: cfg.negDirection,
        degreeKeys: Array.from(degree.keys()).sort(function (a, b) { return b.length - a.length; }),
      };
    }
    return profiles;
  }

  // ---------- 分词 ----------
  function expandStem(lang, stem) {
    const out = [stem];
    if (lang === "ja" && /く$/.test(stem) && stem.length >= 2) {
      out.push(stem.slice(0, -1) + "い");
    }
    return out;
  }

  function enTokenize(text) {
    const t = String(text).toLowerCase().replace(/cannot/g, "can not").replace(/n't/g, " not");
    return t.match(/[a-z]+/g) || [];
  }

  function greedyTokenize(text, profile) {
    const runs = String(text).match(CJK_RUN_RE) || [];
    const tokens = [];
    for (const run of runs) {
      if (/^[A-Za-z]/.test(run)) {
        tokens.push(run.toLowerCase());
        continue;
      }
      let i = 0;
      while (i < run.length) {
        let matched = null;
        let mlen = 0;
        const upper = Math.min(run.length, i + MAX_VOCAB_MATCH);
        for (let j = upper; j > i; j--) {
          const cand = run.slice(i, j);
          const variants = /く$/.test(cand) && cand.length >= 2
            ? [cand, cand.slice(0, -1) + "い"]
            : [cand];
          for (const v of variants) {
            if (profile.vocab.has(v)) {
              matched = v;
              mlen = j - i;
              break;
            }
          }
          if (matched) break;
        }
        if (matched) {
          tokens.push(matched);
          i += mlen;
        } else {
          tokens.push(run[i]);
          i += 1;
        }
      }
    }
    return tokens;
  }

  function tokenize(text, profile) {
    return profile.code === "en" ? enTokenize(text) : greedyTokenize(text, profile);
  }

  // ---------- 词典命中（含构词拆分）----------
  function degreeSplit(profile, token) {
    for (const deg of profile.degreeKeys) {
      if (token.startsWith(deg) && token.length > deg.length) {
        const stem = token.slice(deg.length);
        for (const cand of expandStem(profile.code, stem)) {
          if (profile.lexicon.has(cand)) {
            return { key: cand, degree: deg, weight: profile.degree.get(deg) };
          }
        }
      }
    }
    return null;
  }

  function lookupToken(profile, token) {
    const key = profile.code === "en" ? token.toLowerCase() : token;
    const lex = profile.lexicon;

    function tryStem(stem) {
      for (const cand of expandStem(profile.code, stem)) {
        if (lex.has(cand)) return cand;
      }
      return null;
    }

    if (lex.has(key)) {
      return { key: key, morphNeg: false, negTrigger: null, degree: null, weight: 1.0 };
    }
    // 规则词（否定词/程度词）本身不参与构词拆分，防止「非常→常」这类误拆
    if (profile.negation.has(key) || profile.degree.has(key)) {
      return null;
    }
    // 后缀否定：…ない / …n't
    for (const suf of profile.suffixes) {
      if (key.endsWith(suf) && key.length > suf.length) {
        const hit = tryStem(key.slice(0, key.length - suf.length));
        if (hit) return { key: hit, morphNeg: true, negTrigger: suf, degree: null, weight: 1.0 };
      }
    }
    // 前缀否定：不好；（否定+程度复合：不太好 → 只反转、不加权）
    for (const pre of profile.prefixes) {
      if (key.startsWith(pre) && key.length > pre.length) {
        const stem = key.slice(pre.length);
        const hit = tryStem(stem);
        if (hit) return { key: hit, morphNeg: true, negTrigger: pre, degree: null, weight: 1.0 };
        const degHit = degreeSplit(profile, stem);
        if (degHit) return { key: degHit.key, morphNeg: true, negTrigger: pre, degree: null, weight: 1.0 };
      }
    }
    // 程度前缀：太慢 → 太 + 慢
    const deg2 = degreeSplit(profile, key);
    if (deg2) return { key: deg2.key, morphNeg: false, negTrigger: null, degree: deg2.degree, weight: deg2.weight };
    // 词形还原：良く → 良い
    for (const cand of expandStem(profile.code, key)) {
      if (cand !== key && lex.has(cand)) {
        return { key: cand, morphNeg: false, negTrigger: null, degree: null, weight: 1.0 };
      }
    }
    return null;
  }

  // ---------- 规则窗口 ----------
  function negationScan(profile, tokens, index) {
    const positions = [];
    if (profile.negDirection === "left" || profile.negDirection === "both") {
      for (let j = Math.max(0, index - NEG_WINDOW); j < index; j++) positions.push(j);
    }
    if (profile.negDirection === "right" || profile.negDirection === "both") {
      for (let j = index + 1; j < Math.min(tokens.length, index + 1 + NEG_WINDOW); j++) positions.push(j);
    }
    let trigger = null;
    let count = 0;
    for (const j of positions) {
      if (profile.negation.has(tokens[j])) {
        count += 1;
        trigger = tokens[j];
      }
    }
    const negated = count % 2 === 1;
    return { negated: negated, trigger: negated ? trigger : null };
  }

  function degreeScan(profile, tokens, index) {
    let weight = 1.0;
    let trigger = null;
    for (let j = Math.max(0, index - DEG_WINDOW); j < index; j++) {
      const w = profile.degree.get(tokens[j]);
      if (w !== undefined) {
        weight *= w;
        trigger = tokens[j];
      }
    }
    return { weight: Math.min(weight, MAX_DEGREE), trigger: trigger };
  }

  // ---------- 计分 ----------
  function toIndex(weighted) {
    if (!weighted.length) return null;
    const mean = weighted.reduce(function (a, b) { return a + b; }, 0) / weighted.length;
    const clipped = Math.max(-1, Math.min(1, mean / SCORE_UNIT));
    return Math.round(clipped * 100 * 10) / 10;
  }

  function labelFromIndex(index) {
    if (index === null || index === undefined) return LABEL_UNKNOWN;
    if (index > NEUTRAL_BAND) return LABEL_POSITIVE;
    if (index < -NEUTRAL_BAND) return LABEL_NEGATIVE;
    return LABEL_NEUTRAL;
  }

  function analyzeSentence(profile, text) {
    const tokens = tokenize(text, profile);
    const matched = [];
    for (let i = 0; i < tokens.length; i++) {
      const tok = tokens[i];
      const hit = lookupToken(profile, tok);
      if (!hit) continue;
      const neg = negationScan(profile, tokens, i);
      const deg = degreeScan(profile, tokens, i);
      const negated = hit.morphNeg !== neg.negated; // 异或：双重否定复原
      let degreeWeight = hit.weight * deg.weight;
      if (degreeWeight > MAX_DEGREE) degreeWeight = MAX_DEGREE;
      const base = profile.lexicon.get(hit.key);
      const weighted = base * (negated ? -1 : 1) * degreeWeight;
      const trigger = hit.negTrigger || (negated ? neg.trigger : null);
      matched.push({
        word: hit.key,
        surface: tok,
        base_score: base,
        weighted_score: Math.round(weighted * 1e6) / 1e6,
        negated: negated,
        negation_trigger: trigger,
        degree: hit.degree || deg.trigger,
        degree_weight: Math.round(degreeWeight * 1e6) / 1e6,
        position: i,
      });
    }
    const score = matched.reduce(function (a, m) { return a + m.weighted_score; }, 0);
    const index = toIndex(matched.map(function (m) { return m.weighted_score; }));
    // 分词标注
    const matchedByPos = {};
    for (const m of matched) matchedByPos[m.position] = m;
    const tagged = tokens.map(function (tok, i) {
      const m = matchedByPos[i];
      if (m) return { text: tok, kind: "sentiment", word: m.word, weighted_score: m.weighted_score };
      if (profile.negation.has(tok)) return { text: tok, kind: "negation" };
      if (profile.degree.has(tok)) return { text: tok, kind: "degree" };
      return { text: tok, kind: "plain" };
    });
    return {
      tokens: tagged,
      matched: matched,
      score: Math.round(score * 1e4) / 1e4,
      index: index,
      label: matched.length ? labelFromIndex(index) : LABEL_UNKNOWN,
    };
  }

  function analyzeText(data, text) {
    const profiles = buildProfiles(data);
    text = String(text || "");
    const overall = detectLanguage(text);
    const sentences = [];
    const allWeighted = [];
    let totalScore = 0;
    let matchedCount = 0;

    for (const sent of splitSentences(text)) {
      const guess = detectLanguage(sent);
      if (!profiles[guess.code]) {
        sentences.push({
          text: sent,
          language: guess,
          label: LABEL_UNKNOWN,
          index: null,
          score: 0,
          matched: [],
          tokens: [],
          warnings: ["无法识别该句语言（仅支持中文/日语/英语）"],
        });
        continue;
      }
      const r = analyzeSentence(profiles[guess.code], sent);
      for (const m of r.matched) allWeighted.push(m.weighted_score);
      totalScore += r.score;
      matchedCount += r.matched.length;
      sentences.push({
        text: sent,
        language: guess,
        label: r.label,
        index: r.index,
        score: r.score,
        matched: r.matched,
        tokens: r.tokens,
        warnings: [],
      });
    }

    const index = toIndex(allWeighted);
    return {
      text: text,
      language: overall,
      index: index,
      label: labelFromIndex(index),
      score: Math.round(totalScore * 1e4) / 1e4,
      matched_count: matchedCount,
      sentence_count: sentences.length,
      sentences: sentences,
    };
  }

  return {
    LABEL_POSITIVE: LABEL_POSITIVE,
    LABEL_NEGATIVE: LABEL_NEGATIVE,
    LABEL_NEUTRAL: LABEL_NEUTRAL,
    LABEL_UNKNOWN: LABEL_UNKNOWN,
    detectLanguage: detectLanguage,
    splitSentences: splitSentences,
    tokenize: tokenize,
    analyzeText: analyzeText,
  };
});
