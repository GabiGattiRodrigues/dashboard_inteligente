// Percorre o app inteiro no navegador e reporta qualquer excecao do Streamlit.
const { chromium } = require('playwright');

const URL = process.env.VULC_URL || 'http://localhost:8511';
const OUT = process.env.VULC_OUT || '/tmp/shots';
const fs = require('fs');
fs.mkdirSync(OUT, { recursive: true });

const problemas = [];

async function calma(page, ms = 1600) {
  await page.waitForTimeout(ms);
  // Espera o "running" do Streamlit sumir
  for (let i = 0; i < 40; i++) {
    const rodando = await page.locator('[data-testid="stStatusWidget"]').count();
    if (rodando === 0) break;
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(400);
}

async function checarErros(page, onde) {
  const ex = page.locator('[data-testid="stException"], .stException');
  const n = await ex.count();
  if (n > 0) {
    const txt = (await ex.first().innerText()).slice(0, 700);
    problemas.push(`EXCECAO em ${onde}:\n${txt}`);
    return true;
  }
  const al = page.locator('[data-testid="stAlert"]');
  const na = await al.count();
  for (let i = 0; i < na; i++) {
    const t = await al.nth(i).innerText();
    if (/Traceback|Error|Exception/i.test(t)) {
      problemas.push(`ALERTA DE ERRO em ${onde}: ${t.slice(0, 400)}`);
    }
  }
  return false;
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1100 } });

  page.on('pageerror', e => problemas.push(`JS pageerror: ${e.message}`));

  await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
  await calma(page, 3000);
  await checarErros(page, 'capa');
  await page.screenshot({ path: `${OUT}/00-capa.png`, fullPage: true });

  const dominios = ['Marketing e CRM', 'Crédito', 'Produto e Operação'];
  // A aba do agente muda de nome por dominio: casada por prefixo.
  // "à" para a Abigail, "ao" para o Bailey e o R2 -- o painel conjuga
  // pelo genero do agente, entao o teste tem de aceitar os dois.
  const abas = ['Alertas', /^Pergunte a?[oà] /, 'Visão geral',
                'Comparação de períodos', 'Causa raiz', 'Sobre os dados'];

  for (let di = 0; di < dominios.length; di++) {
    const nome = dominios[di];
    // volta para a capa
    if (di > 0) {
      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(300);
      const voltar = page.getByRole('button', { name: /Voltar para a capa/ });
      if (await voltar.count()) { await voltar.first().click(); await calma(page, 2500); }
    }
    const btn = page.getByRole('button', { name: new RegExp(`Abrir ${nome}`) });
    if (!(await btn.count())) { problemas.push(`botao "Abrir ${nome}" nao encontrado`); continue; }
    await btn.first().click();
    await calma(page, 3000);
    if (await checarErros(page, `${nome} / carregamento`)) continue;

    for (let ai = 0; ai < abas.length; ai++) {
      // Fecha qualquer popover/dialogo aberto (calendario do date_input)
      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(300);
      if (await page.locator('[data-testid="stDialog"]').count()) {
        await page.mouse.click(5, 5).catch(() => {});
        await page.keyboard.press('Escape').catch(() => {});
        await page.waitForTimeout(400);
      }
      const alvo = abas[ai];
      const rotulo = (alvo instanceof RegExp) ? alvo.source : alvo;
      const aba = page.getByRole('tab', { name: alvo });
      if (!(await aba.count())) { problemas.push(`aba "${rotulo}" ausente em ${nome}`); continue; }
      await aba.first().click({ timeout: 15000, force: true }).catch(e => {
        problemas.push(`nao consegui clicar em "${rotulo}" de ${nome}: ${e.message.slice(0,120)}`);
      });
      await calma(page, 2200);
      await checarErros(page, `${nome} / ${rotulo}`);
      const slug = `${di}${ai}-${nome.split(' ')[0]}-${rotulo.replace(/[^A-Za-zÀ-ÿ]/g,'').slice(0,12)}`;
      await page.screenshot({ path: `${OUT}/${slug}.png`, fullPage: true });

      // Na aba do agente, faz de fato uma pergunta e confere a resposta.
      if (alvo instanceof RegExp) {
        const exemplos = page.locator('button:has-text("?")');
        const n = await exemplos.count();
        if (n === 0) { problemas.push(`sem exemplos de pergunta em ${nome}`); continue; }
        for (const idx of [0, Math.min(2, n - 1)]) {
          await exemplos.nth(idx).click({ force: true }).catch(() => {});
          await calma(page, 3500);
          await checarErros(page, `${nome} / pergunta ${idx}`);
          const corpo = await page.locator('[data-testid="stChatMessage"]').last()
            .innerText().catch(() => '');
          if (!corpo || corpo.trim().length < 25) {
            problemas.push(`resposta vazia ou curta em ${nome} (exemplo ${idx}): "${corpo.slice(0,80)}"`);
          }
          // LaTeX vazando: cifrao sobrevivente vira formula e some da tela
          if (/R\s*\d/.test(corpo) && !/R\$/.test(corpo)) {
            problemas.push(`possivel cifrao comido pelo LaTeX em ${nome}: "${corpo.slice(0,120)}"`);
          }
          await page.screenshot({ path: `${OUT}/${slug}-p${idx}.png`, fullPage: true });
        }
      }
    }
  }

  await browser.close();

  if (problemas.length) {
    console.log(`\n>>> ${problemas.length} PROBLEMA(S):\n`);
    problemas.forEach(p => console.log('- ' + p + '\n'));
    process.exit(1);
  }
  console.log('\n>>> Sem excecoes em nenhuma aba de nenhum dominio.');
})();
