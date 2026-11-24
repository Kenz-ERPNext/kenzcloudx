// Renders kenzcloudx/public/images/og-en.png and og-ar.png (1200x630) from og.html, with the home hero
// heading and tag line taken from kenzcloudx/website/content/{en,ar}.json.
//   cd apps/kenzcloudx/scripts/og && npm i --no-save playwright && npx playwright install chromium && node render.mjs
import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = resolve(here, "../../kenzcloudx");
const browser = await chromium.launch();
for (const lang of ["en", "ar"]) {
	const hero = JSON.parse(readFileSync(`${app}/website/content/${lang}.json`, "utf8")).home.hero;
	const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
	await page.goto(pathToFileURL(`${here}/og.html`).href);
	await page.evaluate(({ lang, hero }) => {
		document.documentElement.lang = lang;
		document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
		const h1 = document.getElementById("h1");
		const add = (text) => text.split("\n").forEach((part, i) => { if (i) h1.append(document.createElement("br")); h1.append(part); });
		add(hero.h1.pre);
		const acc = document.createElement("span");
		acc.className = "acc";
		acc.textContent = hero.h1.acc;
		h1.append(acc);
		add(hero.h1.post);
		document.getElementById("tag").textContent = hero.tag;
	}, { lang, hero });
	await page.evaluate(() => document.fonts.ready);
	await page.screenshot({ path: `${app}/public/images/og-${lang}.png` });
	await page.close();
}
await browser.close();
