const puppeteer = require('puppeteer-core');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });
  const page = await browser.newPage();
  await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
  await page.waitForSelector('button', { timeout: 5000 });
  
  // 1. Open Workspace modal by clicking INVESTIGATE on incident
  const buttons = await page.$$('button');
  for (const b of buttons) {
    const text = await page.evaluate(el => el.textContent, b);
    if (text && text.includes('INVESTIGATE')) {
      await b.click();
      break;
    }
  }
  await new Promise(r => setTimeout(r, 1000));

  // 2. Open File Manager Floating Window directly
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const fBtn = btns.find(b => b.textContent.trim().includes('File Manager'));
    if (fBtn) fBtn.click();
  });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: 'screenshots/visual_4_floating_filemanager.png' });
  console.log('Captured visual_4_floating_filemanager.png');

  await browser.close();
  console.log('Finished successfully!');
})();
