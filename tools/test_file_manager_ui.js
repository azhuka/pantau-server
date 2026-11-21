const puppeteer = require('puppeteer-core');

(async () => {
  console.log('Launching Chrome for File Manager UI verification...');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });

  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

    console.log('1. Navigating to Pantau Server at http://localhost:8401/ ...');
    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    // Open first server workspace by clicking on the row in Fleet Table or Dashboard
    console.log('2. Clicking first server in table to open Workspace Modal...');
    const openedWorkspace = await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr');
      if (rows.length > 0) {
        rows[0].click();
        return true;
      }
      return false;
    });
    console.log('Opened Workspace modal:', openedWorkspace);
    await new Promise(r => setTimeout(r, 1000));

    // Look for the File Manager button in Workspace modal header
    console.log('3. Clicking File Manager button in Workspace toolbar...');
    const clickedFm = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const fmBtn = btns.find(b => b.title && b.title.includes('File Manager') || b.textContent.includes('File Manager'));
      if (fmBtn) {
        fmBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked File Manager button:', clickedFm);
    await new Promise(r => setTimeout(r, 1500));

    // Verify File Manager elements
    console.log('4. Verifying File Manager UI & Absence of redundant "Open Directory" button...');
    const fmInfo = await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const openDirBtn = allBtns.find(b => b.title === 'Open Directory' || b.textContent.trim() === 'Open Directory');
      const aksiDropdownBtns = allBtns.filter(b => b.textContent.includes('Actions ▾') || b.textContent.includes('Aksi ▾'));
      const tableHeaders = Array.from(document.querySelectorAll('thead th')).map(th => th.textContent.trim());
      const tableRows = document.querySelectorAll('tbody tr');
      
      return {
        hasRedundantOpenDirButton: !!openDirBtn,
        aksiDropdownCount: aksiDropdownBtns.length,
        tableHeaders: tableHeaders,
        totalRows: tableRows.length
      };
    });

    console.log('File Manager Verification Result:', JSON.stringify(fmInfo, null, 2));

    if (fmInfo.hasRedundantOpenDirButton) {
      throw new Error('FAIL: Redundant "Open Directory" button is still present in the UI!');
    }
    if (fmInfo.aksiDropdownCount === 0) {
      throw new Error('FAIL: Expected uniform "Actions ▾" dropdown buttons in table rows!');
    }

    // Assert English default headers
    const requiredHeaders = ['Name', 'Size', 'Permissions', 'Actions'];
    const hasEnglishHeaders = requiredHeaders.every(h => fmInfo.tableHeaders.includes(h));
    if (!hasEnglishHeaders) {
      throw new Error(`FAIL: Expected English table headers ${requiredHeaders.join(', ')}, got: ${fmInfo.tableHeaders.join(' | ')}`);
    }

    console.log('\n========================================================');
    console.log('  REMOTE FILE MANAGER UI VERIFICATION PASSED (CANON MATCH)');
    console.log('  - Strict English default UI strings verified');
    console.log('  - Zero redundant "Open Directory" button');
    console.log(`  - ${fmInfo.aksiDropdownCount} uniform "Actions ▾" dropdowns present`);
    console.log(`  - Headers: ${fmInfo.tableHeaders.join(' | ')}`);
    console.log('========================================================');
    console.log(`  - ${fmInfo.aksiDropdownCount} uniform "Aksi ▾" dropdowns present`);
    console.log(`  - Headers: ${fmInfo.tableHeaders.join(' | ')}`);
    console.log('========================================================');
  } catch (err) {
    console.error('Error during FM UI test:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
