#!/usr/bin/env node
/**
 * Does `cleanup/cicd-disk-guard.sh` free space in the right order, stop when it is enough, and
 * never touch what it must not — a runner with a job running, a path that goes through a link, an unrelated
 * volume? And does the dashboard say so when a volume is 80% full?
 *
 * ## Why this exists
 *
 * On 15/10/2026 `/var/lib/docker` on the CI machine reached 100%. Almost all of it was two runner volumes of
 * another repository whose `target/debug` only grows. A script that deletes build output inside runners' work
 * folders, on a shared machine, is where the two ways of being wrong are not symmetric:
 *
 * - it removes too little (the disk fills anyway): the next MariaDB cannot create its files and every PR goes
 *   red at "Initialize containers", which reads like a code defect;
 * - it removes too much (a project's build folder while it compiles, a folder reached through a link, data
 *   that is not rebuildable): a build fails for no visible reason, or something is gone for good.
 *
 * ## What it runs
 *
 * The script itself, against fake `docker`, `df`, `ps`, `git` and `rm` first on PATH and a folder tree that
 * looks like `/var/lib/docker/volumes` and `/srv/runners`. The fake `df` reads a level from a file; the fakes
 * lower it by a fixed amount per action, so the stop-when-enough logic is exercised by what it DOES, not by
 * reading its text (the tautological-ruler trap of §15).
 *
 * ## The positive controls
 *
 * Eight mutants of the script, each of which must be CAUGHT by the same scenarios:
 *   1. a running job (`Runner.Worker`) no longer makes a Docker-volume runner busy;
 *   2. a Docker-volume runner whose state cannot be read counts as idle;
 *   3. a job no longer makes an installed runner (`/srv/runners`) busy;
 *   4. the "below the limit, stop" test after the volume prune is gone;
 *   5. the `git clean -fdX` step runs even below the critical level;
 *   6. a path that goes through a link is removed (the glob follows a `target/debug` that is a link, and the
 *      first version of the script, which only looked at the last component, deleted what the link pointed
 *      to: this ruler found it before the script ran anywhere);
 *   7. the biggest checkout is no longer cleaned first;
 *   8. `docker top` is asked without the pid column (the real one refuses with "Couldn't find PID field in
 *      ps output", every runner then reads as unknown, i.e. busy, and nothing in a Docker volume is ever cleaned:
 *      found by running the real command against the runners on the machine, not by reading).
 * and an eighth on the dashboard's warning (the threshold never reached).
 * If this ruler goes green with any mutant, it is not a ruler.
 *
 * Run: `node tests/disk-guard.test.mjs`   (0 = script correct and all mutants caught)
 */
import './lib/git-sem-faxina.mjs';
import { execFileSync, spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Declared ceiling for subprocess output — 64 MiB, the house convention (prova-regua-declara-teto-de-saida). */
const MAX_BUFFER = 64 * 1024 * 1024;

const AQUI = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(AQUI, '..', 'cleanup', 'cicd-disk-guard.sh');
const COLETOR = join(AQUI, '..', 'dashboard', 'coletor.py');
const DIR = mkdtempSync(join(tmpdir(), 'prova-guarda-disco-'));
const ALVO = join(DIR, 'alvo');
const RUNNERS = join(DIR, 'runners');
const BIN = join(DIR, 'bin');
mkdirSync(BIN);

const ALTO = 75;
const CRITICO = 85;

// Fakes. `df` prints the level of the place asked about; `docker` lowers it per action and answers `ps`/`top`;
// `ps` lists the busy installed runner; `git` and `rm` log what they are asked to touch under the two places and
// lower the level of the place the path is in; `rm` then really removes (a link is removed, never followed).
writeFileSync(
  join(BIN, 'df'),
  `#!/bin/bash
p="\${@: -1}"
case "$p" in ${ALVO}) f="${DIR}/nivel";; ${RUNNERS}) f="${DIR}/nivel-runners";; *) exit 1;; esac
[[ -f "$f" ]] || exit 1
printf 'Use%%\\n%s%%\\n' "$(cat "$f")"
`,
);
writeFileSync(
  join(BIN, 'docker'),
  `#!/bin/bash
log="${DIR}/docker.log"; nivel="${DIR}/nivel"
baixa() { echo $(( $(cat "$nivel") - $1 )) > "$nivel"; }
# The real \`docker top\` refuses a ps format without the pid column; the fake does the same.
top_pid() { [[ "$*" == *pid* ]] || { echo "Couldn't find PID field in ps output" >&2; return 1; }; }
echo "$*" >> "$log"
case "$1 $2" in
  "volume prune") baixa "\${VP:-0}" ;;
  "image prune") baixa "\${IP:-0}" ;;
  "builder prune") baixa "\${BP:-0}" ;;
  "ps -q")
    for a in "$@"; do case "$a" in volume=*) v="\${a#volume=}";; esac; done
    case "$v" in tura-ci-1) echo idle1;; tura-ci-2) echo busy2;; tura-ci-3) echo mystery;; esac ;;
  "top busy2") top_pid "$@" && printf 'PID COMMAND\\n10 Runner.Listener\\n11 Runner.Worker\\n' ;;
  "top idle1") top_pid "$@" && printf 'PID COMMAND\\n10 Runner.Listener\\n' ;;
  "top mystery") exit 1 ;;
  *) echo "unexpected: docker $*" >> "$log.erro"; exit 98 ;;
esac
`,
);
writeFileSync(
  join(BIN, 'ps'),
  `#!/bin/bash
printf '%s\\n' '/usr/sbin/sshd -D' '${RUNNERS}/sshvterm-desktop/bin/Runner.Listener run' '${RUNNERS}/sshvterm-desktop/bin/Runner.Worker spawnclient 1 2' '${RUNNERS}/web/bin/Runner.Listener run'
`,
);
writeFileSync(
  join(BIN, 'git'),
  `#!/bin/bash
# git -c safe.directory=* -C <dir> clean -fdXq
while [[ $# -gt 0 ]]; do case "$1" in -C) d="$2"; shift 2;; *) shift;; esac; done
echo "$d" >> "${DIR}/git.log"
case "$d" in ${ALVO}/*) f="${DIR}/nivel";; ${RUNNERS}/*) f="${DIR}/nivel-runners";; esac
echo $(( $(cat "$f") - \${GIT:-8} )) > "$f"
`,
);
writeFileSync(
  join(BIN, 'rm'),
  `#!/bin/bash
for a in "$@"; do
  case "$a" in
    ${ALVO}/*) echo "$a" >> "${DIR}/rm.log"; echo $(( $(cat "${DIR}/nivel") - \${INC:-6} )) > "${DIR}/nivel";;
    ${RUNNERS}/*) echo "$a" >> "${DIR}/rm.log"; echo $(( $(cat "${DIR}/nivel-runners") - \${INC:-6} )) > "${DIR}/nivel-runners";;
  esac
done
exec /bin/rm "$@"
`,
);
for (const f of ['df', 'docker', 'ps', 'git', 'rm']) chmodSync(join(BIN, f), 0o755);

const coDocker = (v) => join(ALVO, 'volumes', v, '_data', '_work', 'proj', 'proj');
const coNativo = (r) => join(RUNNERS, r, '_work', r, r);
const grande = (caminho, kb) => { mkdirSync(dirname(caminho), { recursive: true }); writeFileSync(caminho, 'x'.repeat(kb * 1024)); };

/** A fresh tree: Docker-volume runners (idle, busy, unknown, a link trap, another project), installed runners. */
function montar() {
  rmSync(ALVO, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  rmSync(RUNNERS, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  for (const v of ['tura-ci-1', 'tura-ci-2', 'tura-ci-3']) {
    mkdirSync(join(coDocker(v), '.git'), { recursive: true });
    mkdirSync(join(coDocker(v), 'target', 'debug', 'incremental'), { recursive: true });
    grande(join(coDocker(v), 'target', 'debug', 'deps', 'libx.rlib'), 100);
  }
  // Another project, not Rust: a big folder its own .gitignore names. Only `git clean -fdX` can reach it.
  mkdirSync(join(coDocker('tura-ci-5'), '.git'), { recursive: true });
  grande(join(coDocker('tura-ci-5'), 'dist', 'bundle.js'), 200);
  // The trap: a checkout whose target/debug is a link to somewhere outside.
  mkdirSync(join(coDocker('tura-ci-4'), '.git'), { recursive: true });
  mkdirSync(join(coDocker('tura-ci-4'), 'target'), { recursive: true });
  mkdirSync(join(ALVO, 'elsewhere', 'incremental'), { recursive: true });
  writeFileSync(join(ALVO, 'elsewhere', 'incremental', 'keep'), 'keep');
  symlinkSync(join(ALVO, 'elsewhere'), join(coDocker('tura-ci-4'), 'target', 'debug'));
  // A volume with no work folder at all.
  mkdirSync(join(ALVO, 'volumes', 'mariadb-data', '_data', 'mysql'), { recursive: true });
  writeFileSync(join(ALVO, 'volumes', 'mariadb-data', '_data', 'mysql', 'ibdata1'), 'precious');
  // Installed runners: `web` idle, `sshvterm-desktop` has a Worker.
  for (const r of ['web', 'sshvterm-desktop']) {
    mkdirSync(join(coNativo(r), '.git'), { recursive: true });
    grande(join(coNativo(r), 'build', 'out.bin'), r === 'web' ? 150 : 120);
  }
  for (const f of ['docker.log', 'docker.log.erro', 'rm.log', 'git.log']) rmSync(join(DIR, f), { force: true });
}

/** Runs one script variant on one scenario; returns what it did, so each scenario can say what was wrong. */
function rodar(caminho, { docker = 50, runners = 40, env = {}, argumentos = [], raizRunners = RUNNERS } = {}) {
  montar();
  if (docker !== null) writeFileSync(join(DIR, 'nivel'), String(docker)); else rmSync(join(DIR, 'nivel'), { force: true });
  writeFileSync(join(DIR, 'nivel-runners'), String(runners));
  const r = spawnSync('bash', [caminho, ...argumentos], {
    encoding: 'utf8',
    maxBuffer: MAX_BUFFER,
    env: { ...process.env, PATH: `${BIN}:${process.env.PATH}`, ALVO, RUNNERS: raizRunners, ALTO: String(ALTO), CRITICO: String(CRITICO), ...env },
  });
  const ler = (f) => (existsSync(join(DIR, f)) ? readFileSync(join(DIR, f), 'utf8').split('\n').filter(Boolean) : []);
  const curto = (c) => c.replace(`${ALVO}/volumes/`, '').replace(`${RUNNERS}/`, 'runners/').replace('/_data/_work/proj/proj', '').replace(/\/_work\/(\w+)\/\1/, '');
  return {
    status: r.status,
    saida: `${r.stdout}${r.stderr}`,
    docker: ler('docker.log'),
    erro: ler('docker.log.erro'),
    removidos: ler('rm.log').map(curto),
    limpos: ler('git.log').map(curto),
    ligacaoIntacta: existsSync(join(ALVO, 'elsewhere', 'incremental', 'keep')),
    dadosIntactos: existsSync(join(ALVO, 'volumes', 'mariadb-data', '_data', 'mysql', 'ibdata1')),
    ocupadosIntactos: ['tura-ci-2', 'tura-ci-3'].every((v) => existsSync(join(coDocker(v), 'target', 'debug', 'incremental'))),
  };
}

const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const prunes = (r) => r.docker.filter((l) => /prune/.test(l));

/** Every scenario returns a list of sentences about what the script got wrong (empty = correct). */
function cenarios(caminho) {
  const p = [];
  const quando = (nome, cond, msg) => { if (!cond) p.push(`${nome}: ${msg}`); };

  // 1. Both places below the limit: it does nothing at all.
  let r = rodar(caminho, { docker: 50, runners: 40 });
  quando('abaixo do limite', r.status === 0 && r.docker.length === 0 && r.removidos.length === 0 && r.limpos.length === 0,
    `touched something: docker ${JSON.stringify(r.docker)}, removed ${JSON.stringify(r.removidos)}, cleaned ${JSON.stringify(r.limpos)}`);

  // 2. Above the limit, the volume prune is enough: it stops there.
  r = rodar(caminho, { docker: 80, env: { VP: '10' } });
  quando('so o prune de volumes', r.status === 0 && igual(r.docker, ['volume prune -f']) && r.removidos.length === 0 && r.limpos.length === 0,
    `docker ${JSON.stringify(r.docker)}, removed ${JSON.stringify(r.removidos)}, cleaned ${JSON.stringify(r.limpos)}`);

  // 3. Above the limit, under the critical level: the three prunes in order, then ONLY the incremental builds of
  //    idle runners. Not a runner with a job, not one it cannot read, not through a link, no `git clean`.
  r = rodar(caminho, { docker: 90, env: { VP: '2', IP: '1', BP: '3', INC: '6' } });
  quando('incremental de runner ocioso', igual(r.removidos, ['tura-ci-1/target/debug/incremental']) && r.status === 0,
    `removed ${JSON.stringify(r.removidos)} (status ${r.status}), expected only tura-ci-1's incremental`);
  quando('ordem dos prunes', igual(prunes(r), ['volume prune -f', 'image prune -f', 'builder prune -f --filter until=24h']), `prunes ${JSON.stringify(prunes(r))}`);
  quando('runner ocupado ou ilegivel', r.ocupadosIntactos, 'a runner with a job running, or one it could not read, lost its incremental folder');
  quando('ligacao e dados', r.ligacaoIntacta && r.dadosIntactos, 'what a link points to, or an unrelated volume, was touched');
  quando('git clean abaixo do critico', r.limpos.length === 0, `cleaned ${JSON.stringify(r.limpos)} below the critical level`);

  // 4. At the critical level: the ignored files of the idle checkouts, the BIGGEST first, until below the limit.
  r = rodar(caminho, { docker: 95, env: { INC: '6', GIT: '8' } });
  quando('git clean do maior para o menor', igual(r.limpos, ['tura-ci-5', 'tura-ci-1']), `cleaned ${JSON.stringify(r.limpos)}, expected the 200 KB one first, then the 100 KB one`);
  quando('critico respeita ocupados', r.ocupadosIntactos && !r.limpos.some((x) => x === 'tura-ci-2' || x === 'tura-ci-3'), `cleaned ${JSON.stringify(r.limpos)}`);
  quando('critico e dados', r.ligacaoIntacta && r.dadosIntactos, 'what a link points to, or an unrelated volume, was touched');

  // 5. The installed runners (/srv/runners) are the second place: same rules, a job is a Worker process.
  r = rodar(caminho, { docker: 50, runners: 90, env: { GIT: '8' } });
  quando('runners instalados', igual(r.limpos, ['runners/web']) && r.docker.length === 0 && r.status === 0,
    `cleaned ${JSON.stringify(r.limpos)}, docker ${JSON.stringify(r.docker)} (status ${r.status}); only the idle web runner may be cleaned`);

  // 6. Nothing it may remove is enough: it fails and says what holds the space.
  r = rodar(caminho, { docker: 99, env: { INC: '0', GIT: '0' } });
  quando('ainda cheio', r.status === 1 && /still at 99%/.test(r.saida) && /What holds it/.test(r.saida) && /lvextend/.test(r.saida),
    `status ${r.status}, output: ${r.saida.trim().split('\n').slice(-4).join(' | ')}`);

  // 7. A dry run removes nothing and runs no prune.
  r = rodar(caminho, { docker: 99, runners: 99, argumentos: ['--dry-run'] });
  quando('dry run', r.status === 0 && r.removidos.length === 0 && r.limpos.length === 0 && prunes(r).length === 0 && r.ocupadosIntactos && /dry run: rm -rf /.test(r.saida) && /dry run: git -C /.test(r.saida),
    `status ${r.status}, removed ${JSON.stringify(r.removidos)}, cleaned ${JSON.stringify(r.limpos)}, docker ${JSON.stringify(r.docker)}`);

  // 8. It cannot read the disk: "did not measure" is exit 2, never a quiet 0.
  r = rodar(caminho, { docker: null });
  quando('sem medir', r.status === 2, `status ${r.status}`);

  // 9. A place that is not on this machine is skipped, not an error.
  r = rodar(caminho, { docker: 50, raizRunners: join(DIR, 'nao-existe') });
  quando('lugar ausente', r.status === 0 && /does not exist here/.test(r.saida), `status ${r.status}`);

  if (rodar(caminho, { docker: 90, env: { VP: '2' } }).erro.length) p.push('called docker in a way the fake does not know');
  return p;
}

/** A mutant of the script: one replacement that must change it, else the control controls nothing. */
function mutante(nome, de, para) {
  const fonte = readFileSync(SCRIPT, 'utf8');
  if (!fonte.includes(de)) throw new Error(`mutant "${nome}": the text to replace is not in the script any more (${de})`);
  const caminho = join(DIR, `mutante-${nome}.sh`);
  writeFileSync(caminho, fonte.replace(de, para));
  return caminho;
}

/** The collector's disk warning, on a table of volumes. Returns what it got wrong (empty = correct). */
function avisoDeDisco(caminho) {
  const programa = `
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("coletor", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
G = 2 ** 30
vols = [
  {"ponto": "/var/lib/docker", "total": 49 * G, "livre": 7 * G},   # 86%: warns
  {"ponto": "/srv/runners", "total": 137 * G, "livre": 86 * G},    # 37%: quiet
  {"ponto": "/boundary", "total": 100 * G, "livre": 20 * G},       # exactly 80%: warns
  {"ponto": "/empty", "total": 0, "livre": 0},                      # no size: skipped, never a division by zero
]
print(json.dumps(m.avisos_de_disco(vols)))
`;
  const r = spawnSync('python3', ['-I', '-c', programa, caminho], { encoding: 'utf8', maxBuffer: MAX_BUFFER });
  if (r.status !== 0) return [`the collector did not run: ${r.stderr.trim().slice(0, 200)}`];
  const avisos = JSON.parse(r.stdout);
  const problemas = [];
  if (avisos.length !== 2) problemas.push(`expected 2 warnings (86% and exactly 80%), got ${avisos.length}: ${JSON.stringify(avisos)}`);
  if (!avisos.some((a) => a.includes('/var/lib/docker') && a.includes('86%'))) problemas.push('the 86% volume is not named with its percentage');
  if (avisos.some((a) => a.includes('/srv/runners') || a.includes('/empty'))) problemas.push('a quiet or empty volume was warned about');
  return problemas;
}

function mutanteColetor(nome, de, para) {
  const fonte = readFileSync(COLETOR, 'utf8');
  if (!fonte.includes(de)) throw new Error(`mutant "${nome}": the text to replace is not in the collector any more (${de})`);
  const caminho = join(DIR, `coletor-${nome}.py`);
  writeFileSync(caminho, fonte.replace(de, para));
  return caminho;
}

execFileSync('bash', ['-n', SCRIPT], { maxBuffer: MAX_BUFFER });
const resultado = {
  real: cenarios(SCRIPT),
  painel: avisoDeDisco(COLETOR),
  semDetectarJob: cenarios(mutante('sem-job', `grep -q 'Runner\\.Worker' <<<"$saida" && return 1`, ':')),
  ilegivelContaOcioso: cenarios(mutante('ilegivel-ocioso', '    else\n      return 1\n    fi\n  done\n  return 0\n}\n\nocioso_nativo()', '    else\n      :\n    fi\n  done\n  return 0\n}\n\nocioso_nativo()')),
  topSemPid: cenarios(mutante('top-sem-pid', 'docker top "$id" -eo pid,comm', 'docker top "$id" -eo comm')),
  runnerInstaladoSemJob: cenarios(mutante('nativo-sem-job', 'grep -qF "${1}/bin/Runner.Worker" <<<"$saida" && return 1', ':')),
  semParadaCedo: cenarios(mutante('sem-parada', `abaixo "$raiz" && { echo "cicd-disk-guard: \${raiz} at $(uso "$raiz")% after the volume prune"; return 0; }`, ':')),
  gitCleanSempre: cenarios(mutante('git-clean-sempre', 'if [[ "$(uso "$raiz")" -ge "$CRITICO" ]]; then\n    limpar_ignorados', 'if true; then\n    limpar_ignorados')),
  atravessaLigacao: cenarios(mutante('atravessa-ligacao', '[[ "$real" == "$(realpath -e -- "$d")/target/debug/incremental" ]] ||', 'true ||')),
  menorPrimeiro: cenarios(mutante('menor-primeiro', '| sort -rn | cut -f2-)', '| sort -n | cut -f2-)')),
  painelSemLimite: avisoDeDisco(mutanteColetor('sem-limite', 'if usado >= limite:', 'if usado >= 2:')),
};
rmSync(DIR, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });

const certo = resultado.real.length === 0 && resultado.painel.length === 0;
const controles = ['semDetectarJob', 'topSemPid', 'ilegivelContaOcioso', 'runnerInstaladoSemJob', 'semParadaCedo', 'gitCleanSempre', 'atravessaLigacao', 'menorPrimeiro', 'painelSemLimite'];
const controlesPegam = controles.every((k) => resultado[k].length > 0);
console.log(JSON.stringify({ certo, controlesPegam, ...resultado }, null, 1));
process.exit(certo && controlesPegam ? 0 : 1);
