/**
 * Fila de análise PLD numa planilha Google — automação de baixo custo.
 *
 * O problema: o job de monitoramento (Databricks) seleciona os alertas, mas a
 * fila de análise vive em planilha, prazo é contado na mão e ninguém fica
 * sabendo de manhã o que vence hoje. Montar isso em sistema pede squad de
 * engenharia; em Apps Script é uma tarde.
 *
 * O que este script faz:
 *   1. montarFila()     — lê a aba "alertas" (exportada do job), agrupa por
 *                         cliente, calcula prazo de análise (45 dias corridos,
 *                         Circular 3.978, art. 43, § 1º), ordena vencidos
 *                         primeiro e depois por prioridade, e reescreve a aba
 *                         "fila" preservando as decisões já digitadas.
 *   2. aoEditar(e)      — quando a analista preenche a decisão, exige
 *                         justificativa (art. 43, § 2º), carimba data e
 *                         e-mail e, se for comunicação, calcula o prazo de
 *                         envio: dia útil seguinte (art. 48, § 2º).
 *   3. resumoDoDia()    — manda no Slack o que venceu, o que vence em 7 dias
 *                         e os cinco primeiros da fila.
 *   4. instalar()       — cria os gatilhos (todo dia útil às 8h e onEdit) e
 *                         protege as colunas calculadas.
 *
 * Configuração (Extensões > Apps Script > Configurações do projeto >
 * Propriedades do script):
 *   SLACK_WEBHOOK   URL do webhook de entrada do canal de Compliance
 *
 * Abas esperadas na planilha:
 *   alertas   — CSV de scripts/exportar_fila.py (uma linha por alerta aberto)
 *   feriados  — coluna A com as datas sem expediente
 *   fila      — criada e mantida pelo script
 *   log       — criada pelo script; trilha de auditoria das decisões
 *
 * Dados de exemplo são SIMULADOS. Nada aqui deve receber CPF sem máscara:
 * a planilha é compartilhada, e a comunicação ao Coaf é sigilosa
 * (Lei 9.613/1998, art. 11).
 */

const PRAZO_ANALISE_DIAS = 45;
const COLUNAS_FILA = [
  'Cliente', 'Tipo', 'Prioridade', 'Regras abertas', 'Carta Circular 4.001',
  'Valor envolvido', 'Seleção mais antiga', 'Prazo de análise',
  'Dias para o prazo', 'Situação', 'Decisão', 'Justificativa',
  'Decidido em', 'Decidido por', 'Enviar ao Coaf até',
];
const DECISOES = ['Descartar', 'Monitoramento reforçado', 'Comunicar ao Coaf'];
const COL = Object.fromEntries(COLUNAS_FILA.map((c, i) => [c, i + 1]));


// --------------------------------------------------------------------------
// Datas
// --------------------------------------------------------------------------

function feriados_() {
  const aba = SpreadsheetApp.getActive().getSheetByName('feriados');
  if (!aba || aba.getLastRow() < 1) return new Set();
  return new Set(aba.getRange(1, 1, aba.getLastRow(), 1).getValues()
    .flat().filter(Boolean).map(d => chave_(new Date(d))));
}

function chave_(d) {
  return Utilities.formatDate(d, 'America/Sao_Paulo', 'yyyy-MM-dd');
}

function hoje_() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function ehDiaUtil_(d, fer) {
  const dia = d.getDay();
  return dia !== 0 && dia !== 6 && !fer.has(chave_(d));
}

/** O primeiro dia útil DEPOIS de d — prazo do art. 48, § 2º. */
function proximoDiaUtil_(d, fer) {
  const x = new Date(d.getTime());
  do { x.setDate(x.getDate() + 1); } while (!ehDiaUtil_(x, fer));
  return x;
}


// --------------------------------------------------------------------------
// 1. Fila
// --------------------------------------------------------------------------

function montarFila() {
  const pl = SpreadsheetApp.getActive();
  const origem = pl.getSheetByName('alertas');
  if (!origem) throw new Error('Falta a aba "alertas" com o export do job.');

  const [cab, ...linhas] = origem.getDataRange().getValues();
  const i = Object.fromEntries(cab.map((c, k) => [c, k]));
  const exigidas = ['codigo', 'tipo_cliente', 'regra_id', 'enquadramento',
                    'valor_envolvido', 'data', 'prioridade'];
  exigidas.forEach(c => {
    if (!(c in i)) throw new Error(`A aba "alertas" não tem a coluna ${c}.`);
  });

  // decisões já digitadas sobrevivem à reconstrução da fila
  const fila = pl.getSheetByName('fila') || pl.insertSheet('fila');
  const anteriores = {};
  if (fila.getLastRow() > 1) {
    fila.getRange(2, 1, fila.getLastRow() - 1, COLUNAS_FILA.length).getValues()
      .forEach(r => {
        if (r[COL['Decisão'] - 1]) anteriores[r[0]] = r.slice(COL['Decisão'] - 1);
      });
  }

  // agrupa por cliente: o prazo é o do alerta mais antigo aberto
  const porCliente = {};
  linhas.filter(r => r[i.codigo]).forEach(r => {
    const c = r[i.codigo];
    const g = porCliente[c] || (porCliente[c] = {
      codigo: c, tipo: r[i.tipo_cliente], regras: new Set(), enq: new Set(),
      valor: 0, selecao: null, prioridade: 0 });
    g.regras.add(r[i.regra_id]);
    String(r[i.enquadramento]).split(' · ').forEach(x => g.enq.add(x));
    g.valor += Number(r[i.valor_envolvido]) || 0;
    const d = new Date(r[i.data]);
    if (!g.selecao || d < g.selecao) g.selecao = d;
    // a prioridade vem calculada pelo job (vulcano/pld/fila.py): a planilha
    // não reimplementa a regra, para as duas nunca divergirem
    g.prioridade = Math.max(g.prioridade, Number(r[i.prioridade]) || 0);
  });

  const hoje = hoje_();
  const saida = Object.values(porCliente).map(g => {
    const prazo = new Date(g.selecao.getTime());
    prazo.setDate(prazo.getDate() + PRAZO_ANALISE_DIAS);
    const dias = Math.round((prazo - hoje) / 86400000);
    const situacao = dias < 0 ? 'VENCIDO' : dias <= 7 ? 'Vence em 7 dias' : 'No prazo';
    const dec = anteriores[g.codigo] || ['', '', '', '', ''];
    return [g.codigo, g.tipo, g.prioridade, [...g.regras].sort().join(', '),
            [...g.enq].sort().join(' · '), g.valor, g.selecao, prazo, dias,
            situacao, ...dec];
  });

  // vencidos primeiro; depois prioridade; empate, o que vence antes
  saida.sort((a, b) => (a[8] < 0) !== (b[8] < 0) ? (a[8] < 0 ? -1 : 1)
                     : b[2] - a[2] || a[8] - b[8]);

  fila.clearContents();
  fila.getRange(1, 1, 1, COLUNAS_FILA.length).setValues([COLUNAS_FILA])
    .setFontWeight('bold');
  if (saida.length) {
    fila.getRange(2, 1, saida.length, COLUNAS_FILA.length).setValues(saida);
    fila.getRange(2, COL['Valor envolvido'], saida.length, 1)
      .setNumberFormat('"R$" #,##0');
    [COL['Seleção mais antiga'], COL['Prazo de análise'], COL['Decidido em'],
     COL['Enviar ao Coaf até']].forEach(c =>
      fila.getRange(2, c, saida.length, 1).setNumberFormat('dd/mm/yyyy'));
    fila.getRange(2, COL['Decisão'], saida.length, 1).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(DECISOES, true)
        .setAllowInvalid(false).build());
    formatarSituacao_(fila, saida.length);
  }
  fila.setFrozenRows(1);
  return saida.length;
}

function formatarSituacao_(fila, n) {
  const faixa = fila.getRange(2, 1, n, COLUNAS_FILA.length);
  const col = String.fromCharCode(64 + COL['Situação']);
  fila.setConditionalFormatRules([
    SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied(`=$${col}2="VENCIDO"`).setBackground('#fdecea')
      .setFontColor('#a61b1b').setRanges([faixa]).build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied(`=$${col}2="Vence em 7 dias"`).setBackground('#fff6e0')
      .setRanges([faixa]).build(),
  ]);
}


// --------------------------------------------------------------------------
// 2. Decisão
// --------------------------------------------------------------------------

function aoEditar(e) {
  const aba = e.range.getSheet();
  if (aba.getName() !== 'fila' || e.range.getRow() < 2) return;
  const linha = e.range.getRow();
  const c = e.range.getColumn();
  if (c !== COL['Decisão'] && c !== COL['Justificativa']) return;

  const r = aba.getRange(linha, 1, 1, COLUNAS_FILA.length).getValues()[0];
  const decisao = r[COL['Decisão'] - 1];
  const justificativa = String(r[COL['Justificativa'] - 1] || '').trim();
  if (!decisao) return;

  if (justificativa.length < 15) {
    // sem justificativa não existe dossiê (art. 43, § 2º) — nem no descarte
    aba.getRange(linha, COL['Justificativa']).setNote(
      'Justificativa obrigatória (mín. 15 caracteres) para registrar a decisão.');
    return;
  }
  aba.getRange(linha, COL['Justificativa']).clearNote();

  const agora = new Date();
  const quem = Session.getActiveUser().getEmail() || 'usuário sem e-mail';
  aba.getRange(linha, COL['Decidido em']).setValue(agora);
  aba.getRange(linha, COL['Decidido por']).setValue(quem);
  const envio = decisao === 'Comunicar ao Coaf'
    ? proximoDiaUtil_(hoje_(), feriados_()) : '';
  aba.getRange(linha, COL['Enviar ao Coaf até']).setValue(envio);

  const log = SpreadsheetApp.getActive().getSheetByName('log')
    || SpreadsheetApp.getActive().insertSheet('log');
  if (log.getLastRow() === 0) {
    log.appendRow(['Quando', 'Quem', 'Cliente', 'Decisão', 'Justificativa',
                   'Enviar até']);
  }
  log.appendRow([agora, quem, r[0], decisao, justificativa, envio]);
}


// --------------------------------------------------------------------------
// 3. Resumo no Slack
// --------------------------------------------------------------------------

function resumoDoDia() {
  const fer = feriados_();
  if (!ehDiaUtil_(hoje_(), fer)) return;
  const n = montarFila();
  const fila = SpreadsheetApp.getActive().getSheetByName('fila');
  const linhas = n ? fila.getRange(2, 1, n, COLUNAS_FILA.length).getValues() : [];
  const pendentes = linhas.filter(r => !r[COL['Decisão'] - 1]);
  const vencidos = pendentes.filter(r => r[COL['Dias para o prazo'] - 1] < 0);
  const semana = pendentes.filter(r => {
    const d = r[COL['Dias para o prazo'] - 1];
    return d >= 0 && d <= 7;
  });
  const comunicar = linhas.filter(r => r[COL['Decisão'] - 1] === 'Comunicar ao Coaf'
    && r[COL['Enviar ao Coaf até'] - 1]
    && chave_(new Date(r[COL['Enviar ao Coaf até'] - 1])) === chave_(hoje_()));

  const topo = pendentes.slice(0, 5).map(r =>
    `• *${r[0]}* — prioridade ${r[2]}, ${r[3]}, ${r[8] < 0 ? 'VENCIDO' : r[8] + ' dias'}`);
  const texto = [
    `*Fila PLD — ${Utilities.formatDate(hoje_(), 'America/Sao_Paulo', 'dd/MM/yyyy')}*`,
    `${pendentes.length} clientes sem decisão · ` +
      `:red_circle: ${vencidos.length} vencidos · ` +
      `:large_orange_circle: ${semana.length} vencem em 7 dias`,
    comunicar.length
      ? `:envelope: ${comunicar.length} comunicação(ões) ao Coaf com envio até HOJE`
      : '',
    '', '*Por onde começar*', ...topo,
  ].filter(x => x !== '').join('\n');

  const url = PropertiesService.getScriptProperties().getProperty('SLACK_WEBHOOK');
  if (!url) { console.log(texto); return; }
  UrlFetchApp.fetch(url, { method: 'post', contentType: 'application/json',
                           payload: JSON.stringify({ text: texto }) });
}


// --------------------------------------------------------------------------
// 4. Instalação
// --------------------------------------------------------------------------

function instalar() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('resumoDoDia').timeBased().everyDays(1).atHour(8)
    .inTimezone('America/Sao_Paulo').create();
  ScriptApp.newTrigger('aoEditar').forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit().create();

  montarFila();
  const fila = SpreadsheetApp.getActive().getSheetByName('fila');
  // só as colunas de decisão ficam editáveis; o resto é calculado
  const protecao = fila.protect().setDescription('Colunas calculadas da fila');
  protecao.setUnprotectedRanges([
    fila.getRange(2, COL['Decisão'], fila.getMaxRows() - 1, 2)]);
  protecao.setWarningOnly(true);
}
