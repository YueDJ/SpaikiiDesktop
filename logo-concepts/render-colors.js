const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/YDJ/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe'
  });
  const page = await browser.newPage({ viewport: { width: 768, height: 512 } });
  const svgPath = path.resolve(__dirname, 'conceptV-colors.svg');
  await page.goto('file:///' + svgPath.replace(/\\/g, '/'));
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.resolve(__dirname, 'conceptV-colors.png') });
  console.log('Rendered conceptV-colors.png');
  await browser.close();
})();
