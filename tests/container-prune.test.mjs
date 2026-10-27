#!/usr/bin/env node
/**
 * Does `cleanup/cicd-container-prune.sh` remove the SHVIA test containers a CI job left
 * behind — and only those?
 *
 * ## Why this exists
 *
 * On 13/10/2026 the CI machine (`cicd`) had 45 containers labelled `shvia.workspace` alive, the oldest
 * 13 days: a host-agent test started a real container on every run with an id the suite's sweeper does
 * not recognise. The script removes them by label and age. A script that removes containers on a shared
 * CI machine is exactly where the two ways of being wrong are not symmetric:
 *
 * - it removes too little (a stale container survives): the leak goes on, and nobody sees it, because
 *   the weekly `docker system prune` only removes STOPPED containers and these are running;
 * - it removes too much (a container of the job running now, or of another project on the same
 *   machine such as `tura-ci-1`): a build fails for no visible reason.
 *
 * ## What it runs
 *
 * The script itself, against a fake `docker` first on PATH that serves a table of containers (label
 * set, creation time) and records every `rm`. Reading the script for `--filter label=shvia.` would pass
 * the moment the text exists; this reads what it DOES (the tautological-ruler trap of §15).
 *
 * The fake refuses (exit 99) any `ps` that is not filtered by a `shvia.*` label, so a mutant that lists
 * every container cannot reach the table at all.
 *
 * ## The positive controls
 *
 * Two mutants of the script, each of which must be CAUGHT by the same checks:
 *   1. the age test replaced by `true` (removes the container of the job running now);
 *   2. `sort -u` replaced by `cat` (a container with two labels is removed twice).
 * If this ruler goes green with either mutant, it is not a ruler.
 *
 * Run: `node tests/container-prune.test.mjs`   (0 = script correct and both mutants caught)
 */
import { execFileSync } from 'node:child_process';
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Declared ceiling for `execFileSync` output — 64 MiB, the house convention (prova-regua-declara-teto-de-saida). */
const MAX_BUFFER = 64 * 1024 * 1024;

const AQUI = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(AQUI, '..', 'cleanup', 'cicd-container-prune.sh');
const DIR = mkdtempSync(join(tmpdir(), 'prova-limpeza-cicd-'));

const horasAtras = (h) => new Date(Date.now() - h * 3600e3).toISOString().replace('Z', '000000Z');

// id <TAB> labels (comma-separated) <TAB> created. `sem-rotulo` has no shvia.* label: it is never listed.
const TABELA = [
  ['velho-ws', 'shvia.workspace', horasAtras(30)],
  ['velho-proxy', 'shvia.role', horasAtras(25)],
  ['velho-dois-rotulos', 'shvia.workspace,shvia.sandbox', horasAtras(48)],
  ['novo-ws', 'shvia.workspace', horasAtras(2)],
  ['quase-um-dia', 'shvia.sandbox', horasAtras(23)],
  ['sem-rotulo', 'com.docker.compose.project', horasAtras(100)],
];
const DEVEM_SAIR = ['velho-dois-rotulos', 'velho-proxy', 'velho-ws'];

writeFileSync(join(DIR, 'tabela.tsv'), TABELA.map((l) => l.join('\t')).join('\n') + '\n');
writeFileSync(
  join(DIR, 'docker'),
  `#!/bin/bash
tab="${join(DIR, 'tabela.tsv')}"; log="${join(DIR, 'log')}"
case "$1" in
  ps)
    rot=""
    for a in "$@"; do case "$a" in label=*) rot="\${a#label=}";; esac; done
    [[ "$rot" == shvia.* ]] || { echo "ps without a shvia.* filter: $*" >> "$log.erro"; exit 99; }
    awk -F'\\t' -v r="$rot" '{n=split($2,L,","); for(i=1;i<=n;i++) if(L[i]==r) print $1}' "$tab" ;;
  inspect) id="\${@: -1}"; awk -F'\\t' -v i="$id" '$1==i{print $3}' "$tab" ;;
  rm) shift; for a in "$@"; do [[ "$a" == -* ]] || echo "$a" >> "$log.rm"; done ;;
  *) echo "unexpected: docker $*" >> "$log.erro"; exit 98 ;;
esac
`,
);
chmodSync(join(DIR, 'docker'), 0o755);

/** Runs one script variant and returns what it did wrong, as a list of sentences (empty = correct). */
function avaliar(caminho, argumentos = []) {
  rmSync(join(DIR, 'log.rm'), { force: true });
  rmSync(join(DIR, 'log.erro'), { force: true });
  let saida = '';
  try {
    saida = execFileSync('bash', [caminho, ...argumentos], {
      encoding: 'utf8',
      maxBuffer: MAX_BUFFER,
      env: { ...process.env, PATH: `${DIR}:${process.env.PATH}` },
    });
  } catch (e) {
    return [`the script failed: ${String(e.stderr || e.message).trim().slice(0, 200)}`];
  }
  const problemas = [];
  const removidos = existsSync(join(DIR, 'log.rm')) ? readFileSync(join(DIR, 'log.rm'), 'utf8').split('\n').filter(Boolean).sort() : [];
  const esperados = argumentos.includes('--dry-run') ? [] : DEVEM_SAIR;
  if (JSON.stringify(removidos) !== JSON.stringify(esperados)) {
    problemas.push(`removed [${removidos.join(', ')}], expected [${esperados.join(', ')}]`);
  }
  if (existsSync(join(DIR, 'log.erro'))) problemas.push(`called docker wrongly: ${readFileSync(join(DIR, 'log.erro'), 'utf8').trim()}`);
  if (!/\b3 of 5 shvia\.\* containers\b/.test(saida)) problemas.push(`the summary line is wrong: ${saida.split('\n')[0]}`);
  return problemas;
}

/** A mutant of the script: one replacement that must change it, else the control controls nothing. */
function mutante(nome, de, para) {
  const fonte = readFileSync(SCRIPT, 'utf8');
  if (!fonte.includes(de)) throw new Error(`mutant "${nome}": the text to replace is not in the script any more (${de})`);
  const caminho = join(DIR, `mutante-${nome}.sh`);
  writeFileSync(caminho, fonte.replace(de, para));
  return caminho;
}

const resultado = {
  real: avaliar(SCRIPT),
  realDryRun: avaliar(SCRIPT, ['--dry-run']),
  semTesteDeIdade: avaliar(mutante('sem-idade', 'if [[ "$criado" < "$corte" ]]; then', 'if true; then')),
  semSortU: avaliar(mutante('sem-sort-u', '| sort -u)', '| cat)')),
};
rmSync(DIR, { recursive: true, force: true });

const certo = resultado.real.length === 0 && resultado.realDryRun.length === 0;
const controlesPegam = resultado.semTesteDeIdade.length > 0 && resultado.semSortU.length > 0;
console.log(JSON.stringify({ certo, controlesPegam, ...resultado }, null, 1));
process.exit(certo && controlesPegam ? 0 : 1);
