#!/usr/bin/env node
/**
 * Does the dashboard's collector (`dashboard/coletor.py`) show what the watcher (`cicd-vigia`) is building,
 * and count what it built, once and with the right verdict?
 *
 * ## Why this exists
 *
 * On 28/10/2026 the page said "Nada rodando, fila vazia" while the watcher was building three pull requests
 * of shvia-web. The collector read GitHub Actions only, and since the account was locked for billing on
 * 26/10 every Actions run has zero jobs: the CI runs in the watcher, which writes its builds to
 * `www/vigia/builds.json`, and nothing read that file. The two ways of being wrong here:
 *
 * - it shows too little: a build running or waiting is missing from "Agora", and the page lies the same
 *   way it did;
 * - it counts wrong: a build that ran nothing (`ignorado`, `conflito`) inflates the numbers, a build is
 *   recorded twice, a watcher id collides with a GitHub run id, or shvia-web's expected red `assunto` on a
 *   pull request turns a green build red.
 *
 * ## What it runs
 *
 * The collector itself, twice, with no token (so no network), an empty runners folder, a `builds.json`
 * with every state the watcher writes, and a `historico.db` in the schema from before the watcher (no
 * `log` column), holding one GitHub run; and act logs as the watcher writes them: one of a running build
 * (a job mid-way, a job finished), one of a finished build (the reference for steps and length). It reads what the collector WROTE — `estado.json` and
 * `historico.json` — not the collector's text (the tautological-ruler trap of §15).
 *
 * ## The positive controls
 *
 * Twelve mutants of the collector, each of which must be CAUGHT by the same checks:
 *   1. `ignorado` and `conflito` recorded as runs;
 *   2. the watcher's ids stored positive (they can collide with GitHub's);
 *   3. a build waiting in the watcher's queue left out of the live view;
 *   4. the expected `assunto` red no longer marked expected;
 *   5. the "already recorded" check gone (the second pass records again);
 *   6. the migration gone (an existing database has no `log` column);
 *   7. the log left out of the export (the page cannot link the build);
 *   8. the end of a job ("🏁") ignored in the live log (a finished job reads as running);
 *   9. a build the watcher calls running, with no log yet, shown as running (it waits for a lock);
 *  10. the typical length of a job not read from the finished logs (no bar, no "de ~X");
 *  11. a minute read as a second in act's step durations;
 *  12. a job act skips (macOS, Windows: "🚧 Skipping unsupported platform") read as running forever.
 * If this ruler goes green with any of them, it is not a ruler.
 *
 * Run: `node tests/dashboard-watcher.test.mjs`   (0 = collector correct and every mutant caught)
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Declared ceiling for `execFileSync` output — 64 MiB, the house convention (prova-regua-declara-teto-de-saida). */
const MAX_BUFFER = 64 * 1024 * 1024;

const AQUI = dirname(fileURLToPath(import.meta.url));
const COLETOR = join(AQUI, '..', 'dashboard', 'coletor.py');
const DIR = mkdtempSync(join(tmpdir(), 'prova-painel-vigia-'));

const iso = (horasAtras) => new Date(Date.now() - horasAtras * 3600e3).toISOString().replace(/\.\d+Z$/, 'Z');
const SHA = (c) => c.repeat(40);
const build = (id, repo, ref, evento, estado, inicio, fim, detalhe = null, log = null) =>
  ({ id, repo: `samirhvbr/${repo}`, ref, sha: SHA(String(id % 10)), evento, estado, inicio: iso(inicio),
     fim: fim == null ? null : iso(fim), log, detalhe });

// Newest first, as vigia.py writes it.
const BUILDS = [
  build(9, 'shvia-web', 'refs/pull/613/merge', 'pull_request', 'rodando', 0.3, null),
  build(8, 'shvia-desktop', 'refs/heads/master', 'push', 'na fila', 0.01, null),
  build(7, 'shvia-web', 'refs/pull/612/merge', 'pull_request', 'rodando', 0.2, null),
  build(6, 'shvia-web', 'refs/heads/master', 'push', 'interrompido', 3, 2.9),
  build(5, 'shvia-web', 'refs/heads/master', 'push', 'falhou', 4, 3.5, 'test=failure, assunto=?, release=success', 'shvia-web-5-55555555.log'),
  build(4, 'shvia-web', 'refs/pull/607/merge', 'pull_request', 'falhou', 5, 4.5, 'test=success, assunto=failure', 'shvia-web-4-44444444.log'),
  build(3, 'shvia-desktop', 'refs/pull/161/merge', 'pull_request', 'passou', 6, 5.8, 'provas=success, windows=success', 'shvia-desktop-3-33333333.log'),
  build(2, 'shvia-desktop', 'refs/pull/151/merge', 'pull_request', 'conflito', 7, 7, 'mergeable=false'),
  build(1, 'shvia-desktop', 'refs/heads/master', 'push', 'ignorado', 8, 8, 'head when the watcher started'),
];
// act's output as the watcher writes it, with the padding act puts after a job's name.
const LOGS = {
  'shvia-web-4-44444444.log': [
    '[CI/test   ] ⭐ Run Set up job', '[CI/test   ]   ✅  Success - Set up job [1.5s]',
    '[CI/test   ] ⭐ Run Main Testes', '[CI/test   ]   ✅  Success - Main Testes [2m30s]',
    '[CI/test   ] ⭐ Run Complete job', '[CI/test   ]   ✅  Success - Complete job [500ms]',
    '[CI/test   ] 🏁  Job succeeded',
    '[CI/assunto] ⭐ Run Main Assunto', '[CI/assunto]   ❌  Failure - Main Assunto [1s]', '[CI/assunto] 🏁  Job failed',
  ],
  'shvia-web-7-77777777.log': [
    '[CI/test   ] ⭐ Run Set up job', '[CI/test   ]   ✅  Success - Set up job [2s]', '[CI/test   ] ⭐ Run Main Testes',
    'a line that is not act\'s',
    '[Platforms/macOS (clippy + test)] 🚧  Skipping unsupported platform -- Try running with `-P macos-latest=...`',
    '[CI/assunto] ⭐ Run Main Assunto', '[CI/assunto]   ❌  Failure - Main Assunto [1s]', '[CI/assunto] 🏁  Job failed',
  ],
};
// What the history must hold for the watcher: run id → verdict. 1 and 2 ran nothing.
const VEREDITOS = { '-3': 'success', '-4': 'success', '-5': 'failure', '-6': 'cancelled' };

/** A database in the schema from before the watcher, with one GitHub run that ran here. */
function bancoAntigo(caminho) {
  const agora = Math.floor(Date.now() / 1000) - 3600;
  execFileSync('python3', ['-c', `
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.executescript("""
CREATE TABLE runs (repo TEXT NOT NULL, id INTEGER NOT NULL, tentativa INTEGER NOT NULL,
  workflow TEXT, evento TEXT, branch TEXT, pr INTEGER, ator TEXT, titulo TEXT, conclusao TEXT,
  criado INTEGER, inicio INTEGER, fim INTEGER, PRIMARY KEY (repo, id, tentativa));
CREATE TABLE jobs (id INTEGER PRIMARY KEY, repo TEXT NOT NULL, run_id INTEGER NOT NULL, tentativa INTEGER NOT NULL,
  nome TEXT, runner TEXT, aqui INTEGER NOT NULL, conclusao TEXT, esperado INTEGER NOT NULL,
  criado INTEGER, inicio INTEGER, fim INTEGER);
""")
t = int(sys.argv[2])
db.execute("INSERT INTO runs VALUES ('samirhvbr/shvia-site', 111, 1, 'CI', 'push', 'master', NULL, 'samir', 'x', 'success', ?, ?, ?)", (t, t, t + 60))
db.execute("INSERT INTO jobs VALUES (222, 'samirhvbr/shvia-site', 111, 1, 'build', 'cicd-site', 1, 'success', 0, ?, ?, ?)", (t, t, t + 60))
db.commit()
`, caminho, String(agora)]);
}

/** Runs one collector variant twice and returns what it did wrong, as a list of sentences (empty = correct). */
function avaliar(coletor) {
  const caso = mkdtempSync(join(DIR, 'caso-'));
  const www = join(caso, 'www');
  mkdirSync(join(www, 'vigia'), { recursive: true });
  mkdirSync(join(caso, 'runners'));
  writeFileSync(join(www, 'vigia', 'builds.json'), JSON.stringify({ gerado: iso(0), builds: BUILDS }));
  for (const [nome, linhas] of Object.entries(LOGS)) writeFileSync(join(www, 'vigia', nome), linhas.join('\n') + '\n');
  bancoAntigo(join(caso, 'historico.db'));
  const problemas = [];
  for (const passada of [1, 2]) {
    try {
      execFileSync('python3', [coletor, '--token-file', '/dev/null', '--dados', caso, '--www', www, '--runners', join(caso, 'runners')],
        { encoding: 'utf8', maxBuffer: MAX_BUFFER, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) {
      return [`pass ${passada}: the collector failed: ${String(e.stderr || e.message).trim().split('\n').slice(-1)[0].slice(0, 200)}`];
    }
  }
  const estado = JSON.parse(readFileSync(join(www, 'estado.json'), 'utf8'));
  const hist = JSON.parse(readFileSync(join(www, 'historico.json'), 'utf8'));

  // The live view.
  const vivos = Object.fromEntries(estado.vivos.map((v) => [v.id, v]));
  if (JSON.stringify(Object.keys(vivos).sort()) !== JSON.stringify(['-7', '-8', '-9'])) problemas.push(`live runs [${Object.keys(vivos)}], expected [-7, -8, -9]`);
  if (vivos[-7] && (vivos[-7].status !== 'in_progress' || vivos[-7].pr !== 612 || vivos[-7].url !== 'vigia/shvia-web-7-77777777.log'))
    problemas.push(`the running build reads wrong: ${JSON.stringify({ status: vivos[-7].status, pr: vivos[-7].pr, url: vivos[-7].url })}`);
  if (vivos[-8] && (vivos[-8].status !== 'queued' || vivos[-8].branch !== 'master')) problemas.push(`the queued build reads wrong: ${vivos[-8].status} ${vivos[-8].branch}`);
  if (vivos[-9] && vivos[-9].status !== 'queued') problemas.push(`a running build with no log yet reads ${vivos[-9].status}, expected queued (it waits for its turn)`);
  // The running build's jobs, read from its live log, with the reference of build 4.
  const jv = Object.fromEntries(((vivos[-7] || {}).jobs || []).map((j) => [j.nome, j]));
  const teste = jv['CI/test'], assunto = jv['CI/assunto'];
  if (!teste || teste.status !== 'in_progress' || JSON.stringify(teste.passo) !== JSON.stringify({ numero: 2, total: 3, nome: 'Testes' }))
    problemas.push(`CI/test live reads wrong: ${JSON.stringify(teste && { status: teste.status, passo: teste.passo })}`);
  if (!teste || !teste.tipico || teste.tipico.med !== 152) problemas.push(`CI/test typical length ${JSON.stringify(teste && teste.tipico)}, expected med 152 s`);
  const mac = jv['Platforms/macOS (clippy + test)'];
  if (!mac || mac.status !== 'completed' || mac.conclusao !== 'skipped')
    problemas.push(`a job act skips reads ${JSON.stringify(mac && { status: mac.status, conclusao: mac.conclusao })}, expected completed/skipped`);
  if (!assunto || assunto.status !== 'completed' || assunto.conclusao !== 'failure' || assunto.esperado !== true)
    problemas.push(`CI/assunto live reads wrong: ${JSON.stringify(assunto && { status: assunto.status, conclusao: assunto.conclusao, esperado: assunto.esperado })}`);
  const vigia = estado.runners.find((r) => r.nome === 'cicd-vigia');
  if (!vigia || vigia.ocupado !== true || vigia.rodando !== 1) problemas.push(`the watcher's runner row is wrong: ${JSON.stringify(vigia)}`);

  // The history, after two passes.
  const d = hist.dicionarios;
  const doVigia = hist.runs.filter((r) => d.workflows[r[2]] === 'cicd-vigia');
  const vereditos = Object.fromEntries(doVigia.map((r) => [String(r[0]), d.conclusoes[r[11]]]));
  if (doVigia.length !== Object.keys(vereditos).length) problemas.push(`a watcher run was exported twice (${doVigia.length} rows)`);
  if (JSON.stringify(vereditos, Object.keys(vereditos).sort()) !== JSON.stringify(VEREDITOS, Object.keys(VEREDITOS).sort()))
    problemas.push(`watcher verdicts ${JSON.stringify(vereditos)}, expected ${JSON.stringify(VEREDITOS)}`);
  const github = hist.runs.find((r) => r[0] === 111);
  if (!github || github[12] !== null) problemas.push(`the GitHub run from the old database is missing or carries a log: ${JSON.stringify(github)}`);
  const logs = Object.fromEntries(doVigia.map((r) => [r[0], r[12]]));
  if (logs[-3] !== 'shvia-desktop-3-33333333.log') problemas.push(`the log of build 3 did not reach the export: ${logs[-3]}`);
  const indice = Object.fromEntries(hist.runs.map((r, i) => [r[0], i]));
  const jobs = (id) => hist.jobs.filter((j) => j[0] === indice[id]).map((j) => `${d.jobs[j[1]]}=${d.conclusoes[j[3]]}${j[4] ? '(esperado)' : ''}`).sort();
  const quer = {
    '-4': ['assunto=failure(esperado)', 'test=success'],
    '-5': ['assunto=failure', 'release=success', 'test=failure'],
    '-6': ['act=cancelled'],
  };
  for (const [id, lista] of Object.entries(quer)) {
    if (JSON.stringify(jobs(Number(id))) !== JSON.stringify(lista)) problemas.push(`jobs of ${id}: [${jobs(Number(id))}], expected [${lista}]`);
  }
  return problemas;
}

/** A mutant of the collector: one replacement that must change it, else the control controls nothing. */
function mutante(nome, de, para) {
  const fonte = readFileSync(COLETOR, 'utf8');
  if (!fonte.includes(de)) throw new Error(`mutant "${nome}": the text to replace is not in the collector any more (${de})`);
  const caminho = join(DIR, `mutante-${nome}.py`);
  writeFileSync(caminho, fonte.replace(de, para));
  return caminho;
}

const resultado = {
  real: avaliar(COLETOR),
  gravaOQueNaoRodou: avaliar(mutante('nao-rodou', 'VIGIA_CONCLUSAO = {', 'VIGIA_CONCLUSAO = {"ignorado": "success", "conflito": "failure", ')),
  idPositivo: avaliar(mutante('id-positivo', 'repo, run_id = b["repo"], -b["id"]', 'repo, run_id = b["repo"], b["id"]')),
  semFila: avaliar(mutante('sem-fila', 'not in ("rodando", "na fila")', 'not in ("rodando",)')),
  semEsperado: avaliar(mutante('sem-esperado', 'int(esperado(repo, evento, nome, c))', '0')),
  gravaDeNovo: avaliar(mutante('grava-de-novo', 'if (repo, run_id) in gravados:', 'if False:')),
  semMigracao: avaliar(mutante('sem-migracao', '    migrar(db)\n', '')),
  semLog: avaliar(mutante('sem-log', 'd["conclusoes"](ver), r[13]])', 'd["conclusoes"](ver)])')),
  semFimDeJob: avaliar(mutante('sem-fim-de-job', 'elif msg.startswith("🏁"):', 'elif False:')),
  semLogRodando: avaliar(mutante('sem-log-rodando', '        return None\n    return jobs', '        return {}\n    return jobs')),
  semReferencia: avaliar(mutante('sem-referencia', '            if j["fim"] == "success":', '            if False:')),
  minutoComoSegundo: avaliar(mutante('minuto-segundo', '"m": 60,', '"m": 1,')),
  puladoRodando: avaliar(mutante('pulado-rodando', 'j["fim"] = "skipped"', 'pass')),
};
rmSync(DIR, { recursive: true, force: true });

const certo = resultado.real.length === 0;
const controlesPegam = Object.entries(resultado).every(([k, v]) => k === 'real' || v.length > 0);
console.log(JSON.stringify({ certo, controlesPegam, ...resultado }, null, 1));
process.exit(certo && controlesPegam ? 0 : 1);
