/**
 * 便携版引擎对拍用例（Node 运行）。
 * 断言值与 tests/test_sentiment.py、tests/test_webapi.py 保持一致。
 * 词典为完整版（HowNet / 単語感情極性対応表 / MPQA）：
 *   zh 好=+1.5 差=-1.0 爱=+1.5 恨=-1.5；ja 良い=+1.0 嬉しい=+1.0；en good=+1.0 bad=-1.5
 */
const path = require("path");
const E = require(path.join(__dirname, "..", "portable", "engine.js"));
const DATA = require(path.join(__dirname, "..", "portable", "data.json"));

let failed = 0;
function check(name, cond, detail) {
  if (cond) {
    console.log("ok   " + name);
  } else {
    failed += 1;
    console.log("FAIL " + name + (detail ? "  -> " + detail : ""));
  }
}
const near = (a, b, eps = 1e-6) => Math.abs(a - b) < eps;

// ---- 基础极性 ----
let r = E.analyzeText(DATA, "好");
check("zh positive", r.label === "正面" && r.index === 75 && r.matched_count === 1, JSON.stringify(r.index));

r = E.analyzeText(DATA, "讨厌");
check("zh negative", r.label === "负面" && r.index < 0);

r = E.analyzeText(DATA, "嬉しい");
check("ja positive", r.label === "正面" && r.index > 0);

r = E.analyzeText(DATA, "good");
check("en positive", r.label === "正面" && r.index === 50);

// ---- 否定 ----
r = E.analyzeText(DATA, "不好");
check("zh negation prefix", r.label === "负面" && near(r.index, -75) && r.sentences[0].matched[0].word === "好"
  && r.sentences[0].matched[0].negated === true, JSON.stringify(r.sentences[0].matched));

r = E.analyzeText(DATA, "not good");
check("en not good", r.label === "负面" && r.sentences[0].matched[0].negation_trigger === "not");

r = E.analyzeText(DATA, "not bad");
check("en double negation", r.label === "正面" && near(r.index, 75), "index=" + r.index);

r = E.analyzeText(DATA, "isn't good");
check("en contraction", r.label === "负面" && r.sentences[0].matched[0].negated === true);

r = E.analyzeText(DATA, "良くない");
check("ja yokunai", r.label === "负面" && near(r.index, -50) && near(r.score, -1.0), JSON.stringify(r.index));

r = E.analyzeText(DATA, "嬉しくない");
check("ja suffix negation", r.label === "负面" && r.sentences[0].matched[0].negated === true);

// ---- 程度 ----
r = E.analyzeText(DATA, "非常好");
check("zh degree", near(r.score, 3.0) && r.sentences[0].matched[0].degree === "非常", JSON.stringify(r.sentences[0].matched));

r = E.analyzeText(DATA, "非常不好");
check("zh degree+negation", r.label === "负面" && near(r.index, -100) && near(r.score, -3.0), "index=" + r.index + " score=" + r.score);

r = E.analyzeText(DATA, "稍微好");
check("zh dampen", near(r.score, 0.75));

r = E.analyzeText(DATA, "very good");
check("en degree", near(r.score, 1.5));

r = E.analyzeText(DATA, "not very good");
check("en degree+negation", r.label === "负面" && near(r.score, -1.5), "score=" + r.score);

r = E.analyzeText(DATA, "とても嬉しい");
check("ja degree", near(r.score, 1.6), "score=" + r.score);

r = E.analyzeText(DATA, "太差");
check("zh degree compound", r.label === "负面" && near(r.score, -1.8) && r.sentences[0].matched[0].degree === "太",
  JSON.stringify(r.sentences[0].matched));

r = E.analyzeText(DATA, "不太好");
check("zh neg+degree compound", r.label === "负面" && near(r.score, -1.5), "score=" + r.score);

// ---- 标签/边界 ----
r = E.analyzeText(DATA, "爱，恨");
check("zh neutral", r.label === "中性" && near(r.index, 0), JSON.stringify(r.sentences[0].matched));

r = E.analyzeText(DATA, "玻璃幕墙");
check("zh no match", r.label === "无法判断" && r.index === null);

r = E.analyzeText(DATA, "안녕하세요");
check("unknown script", r.language.code === "unknown" && r.label === "无法判断");

r = E.analyzeText(DATA, "");
check("empty text", r.label === "无法判断" && r.sentence_count === 0);

// ---- 多语言混排（与 Python webapi 对拍）----
r = E.analyzeText(DATA, "这个产品非常好用！物流差，包装也糟糕。The price is not bad, but quality is terrible.");
const s = r.sentences.map((x) => [x.language.code, x.label, x.index]);
check("mixed sentences", r.sentence_count === 3 && s[0][0] === "zh" && s[0][1] === "正面" && near(s[0][2], 100)
  && s[1][1] === "负面" && near(s[1][2], -50) && s[2][0] === "en" && s[2][1] === "中性" && near(s[2][2], 0),
  JSON.stringify(s));

console.log(failed === 0 ? "\nALL PASS" : "\n" + failed + " FAILED");
process.exit(failed === 0 ? 0 : 1);
