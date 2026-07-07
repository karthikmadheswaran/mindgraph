// Rendered-Home prod smoke (Task A follow-up to the drift-pick verifier):
// endpoint-level checks alone missed two page-level regressions (Noticed card
// flood; reported root->Ask). This signs in as the screenshot test account,
// visits the root, and asserts what a user actually SEES.
//
//   node scripts/smoke_home_prod.js            (uses .env SCREENSHOT_* creds)
//
// PASS criteria:
//   * root (no hash) lands on Home: #home, .write-view visible, Ask hidden
//   * Noticed stays curated: <= MAX_INSIGHTS reflection cards,
//     <= MAX_INSIGHTS + 1 po-cards total (one drift pick + capped insights)
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

const ROOT = path.resolve(__dirname, "..");
const BASE_URL = (process.env.SMOKE_BASE_URL || "https://rawtxt.in").replace(/\/$/, "");
const MAX_INSIGHTS = 3; // keep in sync with HOME_MAX_INSIGHTS in Home.js

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

(async () => {
  loadDotEnv(path.join(ROOT, ".env"));
  const email = process.env.SCREENSHOT_EMAIL;
  const password = process.env.SCREENSHOT_PASSWORD;
  if (!email || !password) {
    console.error("SCREENSHOT_EMAIL / SCREENSHOT_PASSWORD missing in .env");
    process.exit(2);
  }

  const browser = await puppeteer.launch({
    headless: true,
    defaultViewport: { width: 1280, height: 900 },
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(30000);

  try {
    // Sign in
    await page.goto(`${BASE_URL}/?view=auth`, { waitUntil: "networkidle2" });
    await page.waitForSelector('input[type="email"]', { visible: true });
    await page.type('input[type="email"]', email);
    await page.type('input[type="password"]', password);
    await Promise.all([
      page.waitForSelector(".app-layout", { visible: true }),
      page.click('button[type="submit"]'),
    ]);

    // The real user path: hit the bare root with an existing session.
    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 5000)); // let Noticed/Recent fetches land

    const s = await page.evaluate(() => {
      const visible = (sel) => {
        const el = document.querySelector(sel);
        return Boolean(el && el.offsetParent !== null);
      };
      return {
        hash: window.location.hash,
        homeVisible: visible(".write-view"),
        askVisible: visible(".ask-view"),
        activeNav: (document.querySelector(".sidebar-nav-item.active") || {}).textContent || "?",
        insightCards: document.querySelectorAll(
          ".noticed-section .reflection-slot, .noticed-section .reflection-card-wrapped"
        ).length,
        noticedPoCards: document.querySelectorAll(".noticed-section .po-card").length,
      };
    });

    check("root lands on #home", s.hash === "#home", `hash=${s.hash}`);
    check("Home view visible", s.homeVisible);
    check("Ask view hidden", !s.askVisible);
    check("active nav is Home", s.activeNav === "Home", `nav=${s.activeNav}`);
    check(
      `Noticed insights capped at ${MAX_INSIGHTS}`,
      s.insightCards <= MAX_INSIGHTS,
      `rendered=${s.insightCards}`
    );
    check(
      `Noticed total cards <= ${MAX_INSIGHTS + 1} (drift pick + insights)`,
      s.noticedPoCards <= MAX_INSIGHTS + 1,
      `rendered=${s.noticedPoCards}`
    );
  } finally {
    await browser.close();
  }

  if (failures > 0) {
    console.error(`${failures} smoke check(s) FAILED`);
    process.exit(1);
  }
  console.log("Rendered-Home smoke: all checks passed");
})().catch((e) => {
  console.error("SMOKE CRASHED:", e.message);
  process.exit(1);
});
