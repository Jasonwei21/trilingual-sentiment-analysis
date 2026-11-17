/**
 * 便携版 DOM 冒烟测试（jsdom 真实执行 Vue/AntD/marked 全链路）。
 * 运行：node tests/portable_dom_test.mjs   （依赖 jsdom，node_modules 已装）
 */
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { JSDOM } from "jsdom";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(root, "三语情感极性分析-便携版.html"), "utf-8");

let failed = 0;
const check = (name, cond, detail) => {
  if (cond) console.log("ok   " + name);
  else { failed++; console.log("FAIL " + name + (detail ? "  -> " + detail : "")); }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  pretendToBeVisual: true,
  beforeParse(window) {
    window.matchMedia = () => ({
      matches: false, addListener() {}, removeListener() {},
      addEventListener() {}, removeEventListener() {},
    });
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    window.Element.prototype.scrollIntoView = () => {};
    window.getComputedStyle = window.getComputedStyle || (() => ({}));
  },
});
const { window } = dom;
const doc = window.document;

await sleep(1200);

// ---- 1. 分析页挂载 ----
const analysis = doc.getElementById("app-analysis");
check("analysis mounted", analysis && analysis.innerHTML.length > 200);
check("title rendered", (analysis.textContent || "").includes("三语情感极性分析台"));
check("samples rendered", (analysis.textContent || "").includes("中文纯中性评价"));

// ---- 2. 输入触发分析（本地引擎） ----
const ta = analysis.querySelector("textarea");
check("textarea found", !!ta);
if (ta) {
  ta.value = "非常不好";
  ta.dispatchEvent(new window.Event("input", { bubbles: true }));
  await sleep(800);
  const txt = analysis.textContent || "";
  check("analysis result shown", txt.includes("负面") && txt.includes("-100"));
  check("matched table", txt.includes("好"));
}

// ---- 3. 使用指南：目录 + 正文 ----
const manualBtns = Array.from(analysis.querySelectorAll("button"));
const guideBtn = manualBtns.find((b) => (b.textContent || "").includes("使用指南"));
check("guide button exists", !!guideBtn);
if (guideBtn) {
  guideBtn.click();
  await sleep(300);
  check("manual overlay open", doc.getElementById("manualOverlay").hidden === false);
  await sleep(600);
  const mtext = doc.getElementById("app-manual").textContent || "";
  check("manual content", mtext.includes("产品概述") && mtext.includes("参考文献"));
  check("manual toc", mtext.includes("目录"));
  const links = doc.querySelectorAll("#app-manual .toc-list a, #app-manual a");
  check("toc links present", links.length > 10, "links=" + links.length);
  doc.getElementById("closeManual").click();
  check("manual overlay closed", doc.getElementById("manualOverlay").hidden === true);
}

// ---- 4. 词典查看 ----
const lexBtn = manualBtns.find((b) => (b.textContent || "").includes("查看词典明细"));
check("lexicon button exists", !!lexBtn);
if (lexBtn) {
  lexBtn.click();
  await sleep(500);
  check("lexicon overlay open", doc.getElementById("lexiconOverlay").hidden === false);
  const ltext = doc.getElementById("app-lexicon").textContent || "";
  check("lexicon info", ltext.includes("官方名称") && ltext.includes("keenage.com"));
  check("lexicon table", ltext.includes("词条") && (ltext.includes("8754") || /共\s*8754/.test(ltext)));
  doc.getElementById("closeLexicon").click();
  check("lexicon overlay closed", doc.getElementById("lexiconOverlay").hidden === true);
}

console.log(failed === 0 ? "\nDOM SMOKE ALL PASS" : "\n" + failed + " FAILED");
window.close();
process.exit(failed === 0 ? 0 : 1);
