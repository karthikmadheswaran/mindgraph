const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

const ROOT_DIR = path.resolve(__dirname, "..");
const SCREENSHOT_DIR = path.join(ROOT_DIR, "docs", "screenshots");
const ENV_PATH = path.join(ROOT_DIR, ".env");
const DEFAULT_BASE_URL = "https://rawtxt.in";
const HEADED = process.argv.includes("--headed");
let baseUrl = DEFAULT_BASE_URL;

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) {
    return;
  }

  const content = fs.readFileSync(filePath, "utf8");
  content.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      return;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      return;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    let value = trimmed.slice(separatorIndex + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (key && process.env[key] === undefined) {
      process.env[key] = value;
    }
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function screenshotPath(fileName) {
  return path.join(SCREENSHOT_DIR, fileName);
}

function log(message) {
  console.log(`[screenshots] ${message}`);
}

function logError(label, error) {
  console.error(`[screenshots] ${label} failed: ${error.message}`);
}

async function stabilize() {
  await sleep(1000);
}

async function capture(page, fileName, options = {}) {
  const outputPath = screenshotPath(fileName);
  await page.screenshot({
    path: outputPath,
    fullPage: Boolean(options.fullPage),
  });
  log(`Saved ${outputPath}`);
}

async function waitForAnySelector(page, selectors, options = {}) {
  const timeout = options.timeout || 10000;
  try {
    return await Promise.any(
      selectors.map((selector) =>
        page.waitForSelector(selector, { timeout, visible: true })
      )
    );
  } catch {
    throw new Error(`Timed out waiting for selectors: ${selectors.join(", ")}`);
  }
}

// Wait for a nice-to-have selector without failing the capture if it never
// appears (e.g. the drift card only shows when the account has a pending
// drifting intention). Returns true if it showed, false on timeout.
async function waitForOptionalSelector(page, selector, timeout = 8000) {
  try {
    await page.waitForSelector(selector, { timeout, visible: true });
    return true;
  } catch {
    return false;
  }
}

async function clickButtonByText(page, text) {
  const clicked = await page.evaluate((targetText) => {
    const normalizedTarget = targetText.trim().toLowerCase();
    const buttons = Array.from(document.querySelectorAll("button"));
    const button = buttons.find(
      (item) => item.textContent.trim().toLowerCase() === normalizedTarget
    );

    if (!button) {
      return false;
    }

    button.click();
    return true;
  }, text);

  if (!clicked) {
    throw new Error(`Could not find button with text "${text}"`);
  }
}

async function navigateToView(page, label) {
  log(`Navigating to ${label}`);
  await clickButtonByText(page, label);
  await stabilize();
}

async function captureStep(label, task) {
  log(`Starting ${label}`);
  try {
    await task();
    log(`Finished ${label}`);
  } catch (error) {
    logError(label, error);
  }
}

async function login(page, credentials) {
  if (!credentials.email || !credentials.password) {
    log("SCREENSHOT_EMAIL or SCREENSHOT_PASSWORD missing; authenticated screenshots will be skipped.");
    return false;
  }

  log("Opening auth page");
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/?view=auth`, { waitUntil: "networkidle2" });
  await stabilize();

  await page.waitForSelector('input[type="email"]', { timeout: 15000, visible: true });
  await page.type('input[type="email"]', credentials.email, { delay: 20 });
  await page.type('input[type="password"]', credentials.password, { delay: 20 });
  await Promise.all([
    page.waitForSelector(".app-layout", { timeout: 30000, visible: true }),
    page.click('button[type="submit"]'),
  ]);
  await stabilize();

  log("Logged in");
  return true;
}

async function captureLanding(page) {
  await page.setViewport({ width: 1280, height: 800 });
  await page.goto(baseUrl, { waitUntil: "networkidle2" });
  await stabilize();
  await capture(page, "landing.png", { fullPage: true });
}

// Home — capture-first composer + the "Noticed" drift card. The drift card is
// only present when the account has a pending drifting intention, so we wait
// for it optionally and shoot the view either way.
async function captureHome(page) {
  await page.setViewport({ width: 1280, height: 900 });
  await navigateToView(page, "Home");
  await page.waitForSelector(".write-view", { timeout: 15000, visible: true });
  const hadDrift = await waitForOptionalSelector(page, ".noticed-section");
  if (!hadDrift) {
    log("No 'Noticed' drift card on the account — capturing Home without it.");
  }
  await stabilize();
  await capture(page, "home.png");
}

// Journal — one scrollable life view (On your plate / Patterns / Intentions /
// Entries), no sub-tabs.
async function captureJournal(page) {
  await page.setViewport({ width: 1280, height: 900 });
  await navigateToView(page, "Journal");
  await page.waitForSelector(".journal-view", { timeout: 15000, visible: true });
  // Entries stream in via infinite scroll after mount; wait for a real card so
  // the shot doesn't catch the skeleton loaders (falls through if the account
  // has no entries yet).
  await waitForOptionalSelector(page, ".entry-card", 10000);
  await stabilize();
  await capture(page, "journal.png");
}

async function captureGraph(page) {
  await page.setViewport({ width: 1280, height: 900 });
  await navigateToView(page, "Graph");
  await waitForAnySelector(page, [
    ".knowledge-graph-svg",
    'svg[aria-label="Interactive knowledge graph"]',
  ]);
  await stabilize();
  await capture(page, "graph.png");
}

async function captureAskView(page) {
  await page.setViewport({ width: 1280, height: 900 });
  await navigateToView(page, "Ask");
  await page.waitForSelector(".ask-view", { timeout: 15000, visible: true });
  await stabilize();
  await capture(page, "ask-view.png");
}

async function main() {
  loadDotEnv(ENV_PATH);
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  baseUrl = (process.env.SCREENSHOT_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, "");

  const credentials = {
    email: process.env.SCREENSHOT_EMAIL,
    password: process.env.SCREENSHOT_PASSWORD,
  };

  log(`Launching browser in ${HEADED ? "headed" : "headless"} mode`);
  const browser = await puppeteer.launch({
    headless: !HEADED,
    defaultViewport: null,
  });

  const page = await browser.newPage();
  page.setDefaultTimeout(15000);

  try {
    await captureStep("landing.png", () => captureLanding(page));

    const isLoggedIn = await login(page, credentials).catch((error) => {
      logError("login", error);
      return false;
    });

    if (!isLoggedIn) {
      log("Skipping authenticated captures.");
      return;
    }

    await captureStep("home.png", () => captureHome(page));
    await captureStep("journal.png", () => captureJournal(page));
    await captureStep("graph.png", () => captureGraph(page));
    await captureStep("ask-view.png", () => captureAskView(page));
  } finally {
    await browser.close();
    log("Browser closed");
  }
}

main().catch((error) => {
  logError("script", error);
  process.exitCode = 1;
});
