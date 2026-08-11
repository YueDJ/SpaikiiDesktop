const { chromium } = require('playwright');
const path = require('path');

const concepts = [
  'conceptV1-bolt-pure',
  'conceptV2-bolt-ring',
  'conceptV3-bolt-wordmark',
];

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/YDJ/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe'
  });
  const page = await browser.newPage({ viewport: { width: 512, height: 512 } });
  for (const name of concepts) {
    const svgPath = path.resolve(__dirname, `${name}.svg`);
    await page.goto('file:///' + svgPath.replace(/\\/g, '/'));
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.resolve(__dirname, `${name}.png`) });
    console.log(`Rendered ${name}.png`);
  }
  await browser.close();
})();
