// Abre a amostra em largura de celular, troca de domínio e reporta erros.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ARQ = 'file://' + path.resolve(__dirname, '../amostra/amostra.html');
const OUT = '/tmp/amostra';
fs.mkdirSync(OUT, { recursive: true });

const problemas = [];

(async () => {
  const browser = await chromium.launch({
    executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  });

  for (const tema of ['light', 'dark']) {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
      colorScheme: tema,
    });
    const page = await ctx.newPage();
    page.on('pageerror', e => problemas.push(`[${tema}] pageerror: ${e.message}`));
    page.on('console', m => {
      if (m.type() === 'error') problemas.push(`[${tema}] console: ${m.text()}`);
    });

    await page.goto(ARQ, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);

    // Sanidade: painéis montados?
    const n = await page.locator('.painel').count();
    if (n !== 3) problemas.push(`[${tema}] esperava 3 painéis, achei ${n}`);
    const kpis = await page.locator('.painel:not([hidden]) .kpi').count();
    if (kpis < 4) problemas.push(`[${tema}] poucos KPIs: ${kpis}`);

    // Overflow horizontal do corpo é bug de layout em celular.
    const largura = await page.evaluate(() =>
      [document.documentElement.scrollWidth, window.innerWidth]);
    if (largura[0] > largura[1] + 1) {
      problemas.push(`[${tema}] a página rola de lado: ${largura[0]}px em ${largura[1]}px`);
    }

    const nomes = ['marketing', 'credito', 'produto'];
    for (let i = 0; i < nomes.length; i++) {
      await page.locator('.aba').nth(i).click();
      await page.waitForTimeout(600);
      const vis = await page.locator('.painel:not([hidden])').count();
      if (vis !== 1) problemas.push(`[${tema}] ${nomes[i]}: ${vis} painéis visíveis`);
      await page.screenshot({
        path: `${OUT}/${tema}-${i}-${nomes[i]}.png`, fullPage: true });
    }

    // Abre um "como foi montada" para conferir o SQL
    await page.locator('.aba').nth(0).click();
    await page.waitForTimeout(400);
    await page.locator('details.tecnico').first().click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/${tema}-detalhe.png`, fullPage: false });

    await ctx.close();
  }

  await browser.close();

  if (problemas.length) {
    console.log(`\n>>> ${problemas.length} PROBLEMA(S):`);
    problemas.forEach(p => console.log('  - ' + p));
    process.exit(1);
  }
  console.log('\n>>> Amostra ok nos dois temas, sem erro de JS e sem rolagem lateral.');
})();
