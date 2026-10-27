#!/usr/bin/env python3
"""The collector of the cicd dashboard (docs/dashboard.md).

Every run (a systemd timer, every 30 s) does three things:

- **Live snapshot** (`www/estado.json`, read by the page every 10 s): the machine (load, memory,
  free space, the last 24 h of load and running jobs), every runner, the runs in progress with
  the step each job is at, and the queue.
- **History** (`historico.db`, SQLite, outside the served folder): every finished run, recorded
  once, with its jobs: runner, result, and when each was queued, started and finished. A job
  that ran on THIS machine is marked `aqui`. GitHub keeps no cheap history to ask again, so the
  numbers of the page come from here.
- **Export** (`www/historico.json`): the runs of the last 90 days that ran here, in a compact
  form the page aggregates by itself (period, repository filter, rankings). Rewritten only when
  something was recorded, once an hour, or when this script changes.

Which repositories: the ones this machine has a runner for. Each runner's own `.runner` file
names its repository (`gitHubUrl`), so registering a runner here is all it takes to put a
repository on the dashboard. The token must reach it too (see the runbook): a repository the
token does not cover shows up with that error, never as an empty chart.

Standard library only, on purpose: the machine is a CI runner, and a dashboard that needs its
own dependency tree would be one more thing that breaks with the jobs it watches.

The token is read from a file (`--token-file`), never from an argument: an argument shows up in
`ps` to every user of the machine, and the jobs run as another user of this machine. It needs
read-only access to the repositories: Actions (read) and Administration (read). GitHub serves
the list of self-hosted runners only under Administration. Without a readable token the snapshot
still carries the machine's numbers and says why GitHub is missing.

The lists are asked with ETags. An unchanged list comes back 304, and a 304 does not count
against the token's 5,000 requests an hour, so a quiet repository costs almost nothing.
"""
import argparse
import calendar
import glob
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.github.com"
VOLUMES = ["/", "/var", "/var/lib/containerd", "/var/lib/docker", "/srv/runners", "/tmp"]
# The first runner went live on 28/09/2026. Earlier runs ran on GitHub-hosted runners, or not
# at all (the budget had run out), so the history starts here.
DESDE = "2026-09-28T00:00:00Z"
RUNS_POR_LISTA = 30
# Once an hour, one paginated pass over everything since the previous pass (minus a day of
# margin) records what the 30-run lists missed: the machine was off, the token was missing, or
# a burst of more than 30 runs. The first pass is the backfill from DESDE.
VARREDURA_S = 3600
MARGEM_VARREDURA_S = 86400
# At most this many job lookups per repository per collector run, so a backfill never stalls
# the live view. The rest waits for the next run.
JOBS_POR_RODADA = 40
EXPORTA_S = 90 * 86400
REEXPORTA_S = 3600
TITULOS_RECENTES = 60
AMOSTRAS_S = 7 * 86400
BALDE_AMOSTRA_S = 300

ESQUEMA = """
CREATE TABLE IF NOT EXISTS runs (
  repo TEXT NOT NULL, id INTEGER NOT NULL, tentativa INTEGER NOT NULL,
  workflow TEXT, evento TEXT, branch TEXT, pr INTEGER, ator TEXT, titulo TEXT, conclusao TEXT,
  criado INTEGER, inicio INTEGER, fim INTEGER,
  PRIMARY KEY (repo, id, tentativa));
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, repo TEXT NOT NULL, run_id INTEGER NOT NULL, tentativa INTEGER NOT NULL,
  nome TEXT, runner TEXT, aqui INTEGER NOT NULL, conclusao TEXT, esperado INTEGER NOT NULL,
  criado INTEGER, inicio INTEGER, fim INTEGER);
CREATE INDEX IF NOT EXISTS jobs_do_run ON jobs (repo, run_id, tentativa);
CREATE TABLE IF NOT EXISTS amostras (
  ts INTEGER PRIMARY KEY, carga REAL, memoria REAL, rodando INTEGER, fila INTEGER);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
"""


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def epoca(texto):
    try:
        return calendar.timegm(time.strptime(texto, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def ler_json(caminho, padrao):
    try:
        with open(caminho) as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def escrever_json(caminho, dados):
    """Atomic: the page never reads half a file."""
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, caminho)


class GitHub:
    """Requests with the token. A list asked with `resumir` goes with If-None-Match, and `cache`
    keeps, per path, the ETag and the SUMMARY of the last 200, so a 304 hands the summary back."""

    def __init__(self, token, cache):
        self.token = token
        self.cache = cache
        self.cota = None
        self.pedidos = 0
        self.nao_mudou = 0

    def pedir(self, caminho, resumir=None):
        cabecalhos = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cicd-painel",
        }
        guardado = self.cache.get(caminho) if resumir else None
        if guardado:
            cabecalhos["If-None-Match"] = guardado["etag"]
        req = urllib.request.Request(API + caminho, headers=cabecalhos)
        self.pedidos += 1
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                self._anotar(r.headers)
                dados = json.load(r)
                etag = r.headers.get("ETag")
        except urllib.error.HTTPError as e:
            if e.code == 304 and guardado:
                self.nao_mudou += 1
                self._anotar(e.headers)
                return guardado["dados"]
            raise
        if resumir:
            dados = resumir(dados)
            if etag:
                self.cache[caminho] = {"etag": etag, "dados": dados}
        return dados

    def _anotar(self, h):
        try:
            restante = int(h.get("X-RateLimit-Remaining"))
        except (TypeError, ValueError):
            return
        if self.cota is None or restante < self.cota["restante"]:
            self.cota = {"restante": restante, "limite": int(h.get("X-RateLimit-Limit") or 0),
                         "reset": int(h.get("X-RateLimit-Reset") or 0)}


def motivo(e):
    if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
        return f"cota da API esgotada até {time.strftime('%H:%M', time.localtime(int(e.headers.get('X-RateLimit-Reset') or 0)))}"
    if e.code in (403, 404):
        return f"HTTP {e.code}: o token do painel não alcança este repositório (inclua-o no token)"
    return f"HTTP {e.code}"


def runners_locais(pasta):
    """Every runner registered on this machine, read from its own `.runner` file (JSON with a
    BOM): its name and its repository. A runner registered for an organization names only the
    organization, and the dashboard does not list an organization's runs (yet)."""
    achados = []
    for arq in sorted(glob.glob(os.path.join(pasta, "*", ".runner"))):
        try:
            with open(arq, encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        url = (d.get("gitHubUrl") or "").rstrip("/")
        partes = url.split("github.com/", 1)[1].split("/") if "github.com/" in url else []
        achados.append({
            "nome": d.get("agentName"),
            "repo": "/".join(partes[:2]) if len(partes) >= 2 else None,
            "org": partes[0] if len(partes) == 1 else None,
        })
    return achados


def jobs_rodando():
    """Runner.Worker processes: one per job running on this machine. Read from /proc, so the
    count holds without the token."""
    n = 0
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open(f"/proc/{pid}/comm") as f:
                    n += f.read().strip() == "Runner.Worker"
            except OSError:
                pass
    return n


def passo_atual(job):
    """The step running now, or the last one that finished, with its position in the list.

    The position, not GitHub's `number`: the numbering counts steps the API does not list
    (a finished job showed "11 of 7")."""
    passos = job.get("steps") or []
    total = len(passos)
    for i, p in enumerate(passos, 1):
        if p.get("status") == "in_progress":
            return {"numero": i, "total": total, "nome": p.get("name")}
    feitos = [(i, p) for i, p in enumerate(passos, 1) if p.get("status") == "completed"]
    if feitos:
        i, p = feitos[-1]
        return {"numero": i, "total": total, "nome": p.get("name")}
    return None


def esperado(repo, evento, nome, conclusao):
    """shvia-web's `assunto` job refuses a commit whose subject still carries the version
    placeholder, and a pull request stays unstamped until `aterrissar.sh` lands it. So on a
    pull-request run that red is the guard doing its job (CLAUDE.md, "Stamp last"): shown grey
    and left out of the run's verdict, or every open PR would read "falhou". Decided by the
    EVENT: on a push to master the same red is real, and stays red. Decided here and not in the
    page, so the live view and the numbers agree."""
    return (repo == "samirhvbr/shvia-web" and nome == "assunto" and conclusao == "failure"
            and evento == "pull_request")


def veredito(conclusao_run, jobs):
    """The run's verdict without the expected red: green when every other job is."""
    if not jobs:
        return conclusao_run or "neutral"
    outros = [j for j in jobs if not j["esperado"]]
    if any(j["conclusao"] in ("failure", "timed_out") for j in outros):
        return "failure"
    if any(j["conclusao"] == "cancelled" for j in outros):
        return "cancelled"
    if all(j["conclusao"] in ("success", "skipped") for j in outros):
        return "success"
    return conclusao_run or "neutral"


def run_resumido(repo, run):
    prs = run.get("pull_requests") or []
    return {
        "repo": repo,
        "id": run.get("id"),
        "tentativa": run.get("run_attempt") or 1,
        "workflow": run.get("name"),
        "titulo": run.get("display_title"),
        "branch": run.get("head_branch"),
        "evento": run.get("event"),
        "pr": prs[0].get("number") if prs else None,
        "ator": (run.get("triggering_actor") or run.get("actor") or {}).get("login"),
        "status": run.get("status"),
        "conclusao": run.get("conclusion"),
        "criado": run.get("created_at"),
        "inicio": run.get("run_started_at"),
        "atualizado": run.get("updated_at"),
        "url": run.get("html_url"),
    }


def job_resumido(repo, evento, j, nomes_locais):
    runner = j.get("runner_name") or None
    return {
        "id": j.get("id"),
        "tentativa": j.get("run_attempt") or 1,
        "nome": j.get("name"),
        "status": j.get("status"),
        "conclusao": j.get("conclusion"),
        "runner": runner,
        # `shvia-ci` is our label (runbook, "The switch"); the local names catch a job that
        # asked for plain `self-hosted`.
        "aqui": bool(runner) and (runner in nomes_locais or "shvia-ci" in (j.get("labels") or [])),
        "esperado": esperado(repo, evento, j.get("name"), j.get("conclusion")),
        "criado": j.get("created_at"),
        "inicio": j.get("started_at"),
        "fim": j.get("completed_at"),
        "passo": passo_atual(j),
        "url": j.get("html_url"),
    }


def coletar_repo(gh, repo, gravados, nomes_locais, varrer_desde):
    """One repository: its runners, its live runs (with their jobs), and the finished runs not
    recorded yet (with their jobs, for the main thread to record). HTTP only: the database is
    the main thread's."""
    saida = {"repo": repo, "runners": [], "vivos": [], "novos": [], "erros": [], "varreu": False}
    try:
        try:
            saida["runners"] = gh.pedir(f"/repos/{repo}/actions/runners?per_page=100", resumir=lambda d: [
                {"nome": x.get("name"), "status": x.get("status"), "ocupado": bool(x.get("busy"))}
                for x in d.get("runners", [])])
        except urllib.error.HTTPError as e:
            saida["erros"].append("runners: " + motivo(e))
        runs = []
        try:
            runs = gh.pedir(f"/repos/{repo}/actions/runs?per_page={RUNS_POR_LISTA}", resumir=lambda d: [
                run_resumido(repo, r) for r in d.get("workflow_runs", [])])
        except urllib.error.HTTPError as e:
            saida["erros"].append("runs: " + motivo(e))
        for run in runs:
            if run["status"] == "completed":
                continue
            # A live run costs one request per snapshot: the page shows its running step.
            run = dict(run)
            try:
                d = gh.pedir(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")
                run["jobs"] = [job_resumido(repo, run["evento"], j, nomes_locais) for j in d.get("jobs", [])]
            except urllib.error.HTTPError:
                run["jobs"] = []
            saida["vivos"].append(run)

        candidatos = {(repo, r["id"], r["tentativa"]): r for r in runs if r["status"] == "completed"}
        completa = True
        if varrer_desde is not None:
            filtro = urllib.parse.quote(">=" + time.strftime("%Y-%m-%d", time.gmtime(varrer_desde)))
            for pagina in range(1, 11):   # the API stops at 1,000 results for a filtered list
                try:
                    d = gh.pedir(f"/repos/{repo}/actions/runs?status=completed&per_page=100"
                                 f"&page={pagina}&created={filtro}")
                except urllib.error.HTTPError as e:
                    saida["erros"].append("varredura: " + motivo(e))
                    completa = False
                    break
                lista = d.get("workflow_runs", [])
                for r in lista:
                    run = run_resumido(repo, r)
                    candidatos.setdefault((repo, run["id"], run["tentativa"]), run)
                if len(lista) < 100:
                    break

        desde = epoca(DESDE)
        orcamento = JOBS_POR_RODADA
        for chave, run in sorted(candidatos.items(), key=lambda kv: kv[1]["criado"] or ""):
            if chave in gravados or (epoca(run["criado"]) or 0) < desde:
                continue
            if orcamento == 0:
                completa = False
                break
            orcamento -= 1
            try:
                # Every attempt: a re-run found by the backfill brings its earlier attempts along.
                # One page: no workflow here has more than 100 jobs.
                d = gh.pedir(f"/repos/{repo}/actions/runs/{run['id']}/jobs?filter=all&per_page=100")
            except urllib.error.HTTPError:
                completa = False
                continue
            jobs = d.get("jobs", [])
            if any(j.get("status") != "completed" for j in jobs if (j.get("run_attempt") or 1) == run["tentativa"]):
                completa = False   # the run says finished, a job not yet: ask again next time
                continue
            saida["novos"].append((run, jobs))
        saida["varreu"] = varrer_desde is not None and completa
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        saida["erros"].append(f"rede: {getattr(e, 'reason', e)}")
    return saida


def gravar(db, run, jobs, nomes_locais):
    repo = run["repo"]
    resumidos = [job_resumido(repo, run["evento"], j, nomes_locais) for j in jobs]
    por_tentativa = {}
    for j in resumidos:
        por_tentativa.setdefault(j["tentativa"], []).append(j)
    for t in set(por_tentativa) | {run["tentativa"]}:
        lista = por_tentativa.get(t, [])
        fins = [x for x in (epoca(j["fim"]) for j in lista) if x]
        if t == run["tentativa"]:
            # The end is the last job's: `updated_at` moves after the run finished (a re-run
            # request, a PR linked or unlinked).
            inicio = epoca(run["inicio"]) or epoca(run["criado"])
            fim = max(fins) if fins else epoca(run["atualizado"])
            conclusao, verbo = run["conclusao"], "REPLACE"
        else:
            # An earlier attempt, seen only through its jobs.
            inicios = [x for x in (epoca(j["inicio"] or j["criado"]) for j in lista) if x]
            inicio = min(inicios) if inicios else None
            fim = max(fins) if fins else None
            conclusao, verbo = None, "IGNORE"
        db.execute(f"INSERT OR {verbo} INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            repo, run["id"], t, run["workflow"], run["evento"], run["branch"], run["pr"], run["ator"],
            run["titulo"], conclusao, epoca(run["criado"]), inicio, fim))
    for j in resumidos:
        db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            j["id"], repo, run["id"], j["tentativa"], j["nome"], j["runner"], int(j["aqui"]),
            j["conclusao"], int(j["esperado"]), epoca(j["criado"]), epoca(j["inicio"]), epoca(j["fim"])))


class Dicionario:
    """Repeated strings go once: the rows carry their index."""

    def __init__(self):
        self.lista, self.indice = [], {}

    def __call__(self, valor):
        valor = "" if valor is None else valor
        if valor not in self.indice:
            self.indice[valor] = len(self.lista)
            self.lista.append(valor)
        return self.indice[valor]


def exportar(db, agora):
    """The runs of the last 90 days with at least one job that ran here, and those jobs.

    runs: [id, repo, workflow, evento, ator, branch, pr, tentativa, criado, inicio, fim, veredito]
    jobs: [run (index in runs), nome, runner, conclusao, esperado, criado, inicio, fim]
    Strings are indices into `dicionarios`; times are Unix seconds. The verdict counts only the
    jobs that ran here."""
    limite = agora - EXPORTA_S
    runs = db.execute("""
        SELECT repo, id, tentativa, workflow, evento, branch, pr, ator, titulo, conclusao, criado, inicio, fim
        FROM runs WHERE COALESCE(inicio, criado) >= ? ORDER BY COALESCE(inicio, criado), id""", (limite,)).fetchall()
    jobs = {}
    for j in db.execute("""
        SELECT j.repo, j.run_id, j.tentativa, j.nome, j.runner, j.conclusao, j.esperado, j.criado, j.inicio, j.fim
        FROM jobs j JOIN runs r ON r.repo = j.repo AND r.id = j.run_id AND r.tentativa = j.tentativa
        WHERE j.aqui = 1 AND COALESCE(r.inicio, r.criado) >= ? ORDER BY j.inicio, j.id""", (limite,)):
        jobs.setdefault(j[:3], []).append(j)
    d = {k: Dicionario() for k in ("repos", "workflows", "eventos", "atores", "branches", "jobs", "runners", "conclusoes")}
    saida_runs, saida_jobs, titulos = [], [], []
    for r in runs:
        js = jobs.get(r[:3])
        if not js:
            continue   # nothing of it ran here
        i = len(saida_runs)
        ver = veredito(r[9], [{"conclusao": j[5], "esperado": bool(j[6])} for j in js])
        saida_runs.append([r[1], d["repos"](r[0]), d["workflows"](r[3]), d["eventos"](r[4]), d["atores"](r[7]),
                           d["branches"](r[5]), r[6], r[2], r[10], r[11], r[12], d["conclusoes"](ver)])
        titulos.append(r[8] or "")
        for j in js:
            saida_jobs.append([i, d["jobs"](j[3]), d["runners"](j[4]), d["conclusoes"](j[5]), j[6], j[7], j[8], j[9]])
    n = len(saida_runs)
    total = db.execute("""
        SELECT COUNT(DISTINCT repo || '/' || run_id || '/' || tentativa), COUNT(*),
               COALESCE(SUM(fim - inicio), 0), MIN(inicio)
        FROM jobs WHERE aqui = 1 AND inicio IS NOT NULL AND fim IS NOT NULL""").fetchone()
    return {
        "gerado": iso(agora),
        "dicionarios": {k: v.lista for k, v in d.items()},
        "runs": saida_runs,
        "jobs": saida_jobs,
        # Titles are long and only the recent table shows them.
        "titulos": {str(i): titulos[i] for i in range(max(0, n - TITULOS_RECENTES), n)},
        "total": {"runs": total[0], "jobs": total[1], "segundos": total[2], "desde": total[3]},
    }


# A volume this full is the warning the page shows above everything. On 15/10/2026 `/var/lib/docker` reached
# 100% and the only sign was jobs failing with a disk error that reads like a code defect; the bars of
# "the machine" were there, but nobody was looking at them at that hour. `cicd-disk-guard.sh` starts freeing
# space at 75%; this one says so when it did not manage to get below 80%.
AVISO_DISCO = 0.80


def avisos_de_disco(volumes, limite=AVISO_DISCO):
    """One sentence per volume used above `limite`, from the `volumes` list `maquina()` builds."""
    avisos = []
    for v in volumes:
        if v["total"] <= 0:
            continue
        usado = 1 - v["livre"] / v["total"]
        if usado >= limite:
            avisos.append(
                f"disco: {v['ponto']} está {round(usado * 100)}% cheio, com {round(v['livre'] / 2**30, 1)} GB livres"
            )
    return avisos


def maquina():
    def meminfo():
        d = {}
        with open("/proc/meminfo") as f:
            for linha in f:
                k, v = linha.split(":", 1)
                d[k] = int(v.split()[0]) * 1024
        return d
    m = meminfo()
    vols = []
    for v in VOLUMES:
        try:
            s = os.statvfs(v)
        except OSError:
            continue
        vols.append({"ponto": v, "total": s.f_blocks * s.f_frsize, "livre": s.f_bavail * s.f_frsize})
    with open("/proc/loadavg") as f:
        carga = [float(x) for x in f.read().split()[:3]]
    with open("/proc/uptime") as f:
        uptime = float(f.read().split()[0])
    return {
        "host": os.uname().nodename,
        "cpus": os.cpu_count(),
        "carga": carga,
        "memoria": {"total": m.get("MemTotal", 0), "disponivel": m.get("MemAvailable", 0)},
        "volumes": vols,
        "uptime_s": int(uptime),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", default="/etc/cicd-painel/token")
    ap.add_argument("--dados", default="/var/lib/cicd-painel", help="the database and the ETag cache (not served)")
    ap.add_argument("--www", default="/var/lib/cicd-painel/www", help="the served folder")
    ap.add_argument("--runners", default="/srv/runners", help="where the runners are installed")
    a = ap.parse_args()
    agora = time.time()
    os.makedirs(a.www, exist_ok=True)

    locais = runners_locais(a.runners)
    nomes_locais = {r["nome"] for r in locais if r["nome"]}
    alvos = sorted({r["repo"] for r in locais if r["repo"]})
    m = maquina()
    estado = {"gerado": iso(agora), "maquina": m, "runners": [], "vivos": [], "erros": [], "github": None,
              "cota": None, "amostras": [], "avisos": [
                  f"{r['nome']}: runner da organização {r['org']}; o painel ainda não lista os runs de organização"
                  for r in locais if r["org"]]}
    if not locais:
        estado["avisos"].append(f"nenhum runner encontrado em {a.runners}")
    estado["avisos"] += avisos_de_disco(m["volumes"])

    token = ""
    try:
        with open(a.token_file) as f:
            token = f.read().strip()
    except OSError as e:
        estado["github"] = f"sem token legível em {a.token_file} ({e.strerror})"
    else:
        # A file with nothing in it is not "no error": measured on the first install, a snapshot
        # taken while the token was being written showed an empty page and no reason.
        if not token:
            estado["github"] = f"token vazio em {a.token_file}"

    db = sqlite3.connect(os.path.join(a.dados, "historico.db"))
    db.executescript(ESQUEMA)
    gravou = 0
    por_repo = {}
    if token and alvos:
        arq_etags = os.path.join(a.dados, "etags.json")
        cache = ler_json(arq_etags, {})
        gh = GitHub(token, cache)
        gravados = set(db.execute("SELECT repo, id, tentativa FROM runs"))
        varrer = {}
        for repo in alvos:
            ultima = db.execute("SELECT valor FROM meta WHERE chave = ?", ("varredura:" + repo,)).fetchone()
            if ultima is None:
                varrer[repo] = epoca(DESDE)
            elif agora - float(ultima[0]) >= VARREDURA_S:
                varrer[repo] = max(epoca(DESDE), float(ultima[0]) - MARGEM_VARREDURA_S)
            else:
                varrer[repo] = None
        with ThreadPoolExecutor(max_workers=min(8, len(alvos))) as ex:
            resultados = list(ex.map(lambda r: coletar_repo(gh, r, gravados, nomes_locais, varrer[r]), alvos))
        for res in resultados:
            por_repo[res["repo"]] = res
            for run, jobs in res["novos"]:
                gravar(db, run, jobs, nomes_locais)
                gravou += 1
            if res["varreu"]:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", ("varredura:" + res["repo"], str(agora)))
            estado["erros"] += [f"{res['repo']}: {e}" for e in res["erros"]]
            estado["vivos"] += res["vivos"]
        estado["cota"] = gh.cota and {**gh.cota, "pedidos": gh.pedidos, "nao_mudou": gh.nao_mudou}
        # Keep only the lists still asked, so the cache never outgrows the repositories.
        escrever_json(arq_etags, {k: v for k, v in cache.items() if any(k.startswith(f"/repos/{r}/") for r in alvos)})

    # The runners: what GitHub says (online, busy) for every repository, plus the local ones
    # GitHub did not answer for. `local` tells a runner of this machine from one elsewhere.
    vistos = set()
    for res in por_repo.values():
        for x in res["runners"]:
            estado["runners"].append({**x, "repo": res["repo"], "local": x["nome"] in nomes_locais})
            vistos.add(x["nome"])
    for r in locais:
        if r["nome"] not in vistos:
            estado["runners"].append({"nome": r["nome"], "repo": r["repo"] or r["org"], "status": None,
                                      "ocupado": None, "local": True})
    estado["runners"].sort(key=lambda x: (x["repo"] or "", x["nome"] or ""))

    usada = 1 - m["memoria"]["disponivel"] / m["memoria"]["total"] if m["memoria"]["total"] else 0
    fila = sum(1 for r in estado["vivos"] if r["status"] != "in_progress")
    db.execute("INSERT OR REPLACE INTO amostras VALUES (?,?,?,?,?)",
               (int(agora), m["carga"][0], round(usada, 4), jobs_rodando(), fila))
    db.execute("DELETE FROM amostras WHERE ts < ?", (agora - AMOSTRAS_S,))
    estado["amostras"] = [list(x) for x in db.execute(
        "SELECT (ts / ?) * ?, MAX(carga), MAX(memoria), MAX(rodando), MAX(fila) FROM amostras "
        "WHERE ts >= ? GROUP BY ts / ? ORDER BY 1",
        (BALDE_AMOSTRA_S, BALDE_AMOSTRA_S, agora - 86400, BALDE_AMOSTRA_S))]
    db.commit()

    arq_hist = os.path.join(a.www, "historico.json")
    try:
        idade = agora - os.path.getmtime(arq_hist)
        mais_velho_que_eu = os.path.getmtime(arq_hist) < os.path.getmtime(__file__)
    except OSError:
        idade, mais_velho_que_eu = None, True
    if gravou or mais_velho_que_eu or idade is None or idade >= REEXPORTA_S:
        escrever_json(arq_hist, exportar(db, agora))
    db.close()
    escrever_json(os.path.join(a.www, "estado.json"), estado)


if __name__ == "__main__":
    main()
