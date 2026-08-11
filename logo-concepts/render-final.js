const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const sizes = [512, 180, 32, 16];

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/YDJ/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe'
  });
  const svgContent = fs.readFileSync(path.resolve(__dirname, 'sparkii-logo-final.svg'), 'utf-8');
  const html = `<!DOCTYPE html><html><head><style>*{margin:0;padding:0}html,body{width:100%;height:100%;overflow:hidden;background:transparent}svg{display:block;width:100%;height:100%}</style></head><body>${svgContent}</body></html>`;
  const tmp = path.resolve(__dirname, '_r.html');
  fs.writeFileSync(tmp, html);

  for (const size of sizes) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await page.goto('file:///' + tmp.replace(/\\/g, '/'));
    await page.waitForTimeout(300);
    const outPath = path.resolve(__dirname, 'sparkii-logo-' + size + '.png');
    await page.screenshot({ path: outPath, omitBackground: true });
    console.log('sparkii-logo-' + size + '.png (' + fs.statSync(outPath).size + ' bytes)');
    await page.close();
  }
  fs.unlinkSync(tmp);
  await browser.close();
})();
