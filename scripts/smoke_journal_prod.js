// Rendered-Journal prod spot-check (Journal v2 single-page life view).
//   node scripts/smoke_journal_prod.js
// Asserts, on the signed-in test account:
//   * sections render in order: On your plate → Patterns → Intentions → Entries
//     (only the non-empty ones — order is checked over whichever are present)
//   * no tab bar
//   * no drift-card framing anywhere in Journal (no .po-card outside Patterns'
//     revealed gift cards, no "Drifting" pill text)
//   * the Filter control toggles the chip row
//   * the overflow expander (when present) advertises counts that match what
//     expanding actually reveals
//   * infinite scroll appends a second page (skipped when <= one page of data)
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

const ROOT = path.resolve(__dirname, "..");
const BASE_URL = (process.env.SMOKE_BASE_URL || "https://rawtxt.in").replace(/\/$/, "");

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) return;
  const content = fs.readFileSync(filePath, "utf8").replace(/^﻿/, "");
  content.split(/\r?\n/).forEach((line) => {
    const t = line.trim();
    if (!t || t.startsWith("#")) return;
    const i = t.indexOf("=");
    if (i === -1) return;
    const k = t.slice(0, i).trim();
    const v = t.slice(i + 1).trim().replace(/^["']|["']$/g, "");
    if (k && process.env[k] === undefined) process.env[k] = v;
  });
}

let failures = 0;
function check(label, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${label}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
}
function note(label, detail) {
  console.log(`NOTE ${label}${detail ? ` — ${detail}` : ""}`);
}

(async () => {
  loadDotEnv(path.join(ROOT, ".env"));
  const browser = await puppeteer.launch({
    headless: true,
    defaultViewport: { width: 1280, height: 900 },
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(30000);

  try {
    await page.goto(`${BASE_URL}/?view=auth`, { waitUntil: "networkidle2" });
    await page.waitForSelector('input[type="email"]', { visible: true });
    await page.type('input[type="email"]', process.env.SCREENSHOT_EMAIL);
    await page.type('input[type="password"]', process.env.SCREENSHOT_PASSWORD);
    await Promise.all([
      page.waitForSelector(".app-layout", { visible: true }),
      page.click('button[type="submit"]'),
    ]);

    await page.goto(`${BASE_URL}/#journal`, { waitUntil: "networkidle2" });
    await page.waitForSelector(".journal-view", { visible: true });
    await new Promise((r) => setTimeout(r, 5000));

    const s = await page.evaluate(() => {
      const jv = document.querySelector(".journal-view");
      const headers = Array.from(jv.querySelectorAll("h2")).map((h) =>
        h.textContent.trim()
      );
      const patterns = jv.querySelector(".journal-patterns");
      const poCardsOutsidePatterns = Array.from(jv.querySelectorAll(".po-card")).filter(
        (el) => !(patterns && patterns.contains(el))
      ).length;
      const expander = jv.querySelector(".plate-expander");
      return {
        headers,
        hasTabs: Boolean(jv.querySelector(".journal-tabs")),
        // The framing artifact is the drift PILL, not the word: user data may
        // legitimately contain "Drifting" (e.g. an entry titled that way).
        driftPills: jv.querySelectorAll(".po-pill").length,
        poCardsOutsidePatterns,
        expanderText: expander ? expander.textContent.trim() : null,
        entryCards: jv.querySelectorAll(".entry-card").length,
        totalCountText: (jv.querySelector(".journal-entries .count") || {}).textContent || "",
        hasSentinel: Boolean(jv.querySelector(".entries-sentinel")),
        filterRowVisible: Boolean(jv.querySelector(".entries-filter-row")),
      };
    });

    // Section order over whichever sections are present.
    const expected = ["On your plate", "Patterns", "Intentions", "Entries"];
    const present = expected
      .map((name) => s.headers.findIndex((h) => h.startsWith(name)))
      .filter((i) => i !== -1);
    check(
      "sections in order",
      present.length > 0 && [...present].sort((a, b) => a - b).join() === present.join(),
      `headers=${JSON.stringify(s.headers)}`
    );
    check("no tab bar", !s.hasTabs);
    check("no drift-pill framing in Journal", s.driftPills === 0, `pills=${s.driftPills}`);
    check(
      "no drift po-cards outside Patterns",
      s.poCardsOutsidePatterns === 0,
      `found=${s.poCardsOutsidePatterns}`
    );
    check("infinite-scroll sentinel present", s.hasSentinel);
    check("filter chips collapsed by default", !s.filterRowVisible);

    // Filter control toggles the chip row.
    const filterBtn = await page.$(".entries-filter-toggle");
    if (filterBtn) {
      await filterBtn.click();
      await new Promise((r) => setTimeout(r, 400));
      const open = await page.$(".entries-filter-row");
      check("Filter control opens the chip row", Boolean(open));
      await filterBtn.click();
      await new Promise((r) => setTimeout(r, 400));
      const closed = await page.$(".entries-filter-row");
      check("Filter control closes the chip row", !closed);
    } else {
      note("Filter control", "Entries section empty on this account — skipped");
    }

    // Expander counts match what expanding reveals.
    if (s.expanderText) {
      const beforeRows = await page.evaluate(
        () => document.querySelectorAll(".journal-plate .dl-wrap, .journal-plate .proj-wrap").length
      );
      await page.click(".plate-expander");
      await new Promise((r) => setTimeout(r, 400));
      const afterRows = await page.evaluate(
        () => document.querySelectorAll(".journal-plate .dl-wrap, .journal-plate .proj-wrap").length
      );
      const advertised = (s.expanderText.match(/\d+/g) || []).reduce(
        (a, n) => a + Number(n),
        0
      );
      check(
        "expander reveals the advertised rows",
        afterRows - beforeRows === advertised,
        `'${s.expanderText}' advertised=${advertised} revealed=${afterRows - beforeRows}`
      );
    } else {
      note("overflow expander", "nothing beyond the plate on this account — skipped");
    }

    // Infinite scroll (needs more than one page of entries).
    const totalMatch = /(\d+)\s+total/.exec(s.totalCountText);
    const total = totalMatch ? Number(totalMatch[1]) : null;
    if (total && total > s.entryCards) {
      await page.evaluate(() => {
        document.querySelector(".entries-sentinel").scrollIntoView();
      });
      await new Promise((r) => setTimeout(r, 4000));
      const afterCards = await page.evaluate(
        () => document.querySelectorAll(".journal-view .entry-card").length
      );
      check(
        "infinite scroll appended the next page",
        afterCards > s.entryCards,
        `${s.entryCards} -> ${afterCards} of ${total}`
      );
    } else {
      note(
        "infinite scroll",
        `only ${s.entryCards} entr${s.entryCards === 1 ? "y" : "ies"} (total=${total}) — nothing to append, skipped`
      );
    }
  } finally {
    await browser.close();
  }

  if (failures > 0) {
    console.error(`${failures} Journal spot-check(s) FAILED`);
    process.exit(1);
  }
  console.log("Rendered-Journal spot-check: all checks passed");
})().catch((e) => {
  console.error("SPOT-CHECK CRASHED:", e.message);
  process.exit(1);
});
