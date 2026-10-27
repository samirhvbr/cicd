#!/usr/bin/env python3
"""cicd-vigia: runs the CI of the ShvIA repositories on this machine, without GitHub Actions.

Why it exists (docs/watcher.md): on 26/10/2026 the `samirhvbr` account was
locked for billing, and a locked account gets no job at all — not on GitHub's runners and not on
the self-hosted ones here, because GitHub is what hands a job to a runner. Measured on 27/10: the
four `cicd-web` runners online and idle, the run created with zero jobs. The owner's decision the
same day: the CI runs here, triggered from here, and GitHub keeps the code, the pull requests and
the Releases.

What it does, every `--intervalo` seconds, for each repository in the config:

- Asks GitHub for the open pull requests (one request with an ETag; an unchanged list is a 304,
  which costs nothing) and `git ls-remote` for the default branch.
- **Only pull requests whose head branch lives in the repository itself are built.** A fork's pull
  request never runs here: its code would run on this machine, with the token in reach. Dependabot's
  branches live in the repository, so they run.
- A pull request runs on GitHub's merge ref (`refs/pull/N/merge`), the same tree GitHub Actions
  tests; one that conflicts has no merge ref and gets a failure that says so, as GitHub shows no run.
- The workflows are the ones in `.github/workflows/`, executed by `act`. Nothing is rewritten: the
  YAML stays the definition of the CI.
- Each job's result goes back as a **commit status** whose context is the job's name, so `gh pr
  checks`, `gh pr view --json statusCheckRollup` and SHVIA-WEB's `scripts/checks-verdes.py` read it
  like the check it replaces. The status links to the job's log on the dashboard.
- A push to the default branch runs the `push` workflows, the Release one included, so
  `tools/release.sh --current` publishes the version as `release.yml` did.

Standard library only, like the dashboard's collector: the machine is a CI runner, and a watcher
with its own dependency tree would be one more thing that breaks with the jobs it runs.

The token is read from a file (`--token-file`), never from an argument or the environment of the
service: an argument shows up in `ps`. It reaches `git` through GIT_ASKPASS and `act` through the
environment of that one child, as the GITHUB_TOKEN secret.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

API = "https://api.github.com"
# The image `conteiner` jobs run in, built on this machine by instalar.sh from image/Dockerfile:
# act's Ubuntu 24.04 plus what GitHub's ubuntu-latest ships and a workflow here needs (PowerShell).
# Tools a job installs itself (apt, rustup, setup-node) come in at run time, as on GitHub.
IMAGEM = "shvia/act-ubuntu:24.04"
# `act` resolves an action pinned to a commit that is no longer the tip of any branch only with the
# new action cache (it fetches the SHA itself). dtolnay/rust-toolchain regenerates its branches, so
# every pin of it is such a commit. Measured on 27/10/2026: "reference not found" without the flag.
# `--pull=false`: the image is local, and act would otherwise try to pull it from a registry.
# `--rm`: act removes a job's containers when the job passes and LEAVES them running when it fails —
# a failed WEB run left its job container, MariaDB and pgvector up (27/10/2026). This machine's disk
# has filled with leaked containers before (runbook, "Orphaned volumes").
ACT_BASE = ["act", "--json", "--rm", "--use-new-action-cache", "--pull=false", "--container-architecture", "linux/amd64"]
LOG_MAX = 20 * 1024 * 1024


def agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"{agora()} {msg}", flush=True)


class GitHub:
    """The few REST calls the watcher needs, with ETags for the lists it repeats."""

    def __init__(self, token, ensaio=False):
        self.token = token
        self.ensaio = ensaio
        self.etags = {}
        self.cache = {}

    def pedir(self, metodo, caminho, corpo=None, etag=False):
        url = caminho if caminho.startswith("http") else API + caminho
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if dados is not None:
            req.add_header("Content-Type", "application/json")
        if etag and url in self.etags:
            req.add_header("If-None-Match", self.etags[url])
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo_resp = json.loads(r.read() or b"null")
                if etag and r.headers.get("ETag"):
                    self.etags[url] = r.headers["ETag"]
                    self.cache[url] = corpo_resp
                return corpo_resp
        except urllib.error.HTTPError as e:
            if e.code == 304 and url in self.cache:
                return self.cache[url]
            raise

    def prs_abertos(self, repo):
        return self.pedir("GET", f"/repos/{repo}/pulls?state=open&per_page=100", etag=True) or []

    def mescavel(self, repo, numero):
        """True, False (conflicts with its base) or None (GitHub is still computing it). The list of pull
        requests does not carry it, and the merge ref alone cannot tell: a pull request that started to
        conflict keeps its OLD merge ref, made against an old base (measured on 27/10 with desktop #151,
        whose merge ref still had the current head as its second parent)."""
        return (self.pedir("GET", f"/repos/{repo}/pulls/{numero}") or {}).get("mergeable")

    def status(self, repo, sha, estado, contexto, descricao, url):
        corpo = {"state": estado, "context": contexto[:255], "description": descricao[:140]}
        if url:
            corpo["target_url"] = url
        if self.ensaio:
            log(f"(rehearsal) status {repo}@{sha[:8]} {estado:8} {contexto} — {descricao}")
            return
        self.pedir("POST", f"/repos/{repo}/statuses/{sha}", corpo)


class AindaNao(Exception):
    """GitHub has not caught up with the pull request yet (its merge ref is older than its head or its
    base). The build is forgotten, not failed, so the next poll tries again."""


class Vigia:
    def __init__(self, args):
        self.args = args
        with open(args.config, encoding="utf-8") as f:
            self.config = json.load(f)
        self.dono = self.config["dono"]
        self.dados = args.dados
        self.logs = args.logs
        os.makedirs(os.path.join(self.dados, "espelhos"), exist_ok=True)
        os.makedirs(os.path.join(self.dados, "trabalho"), exist_ok=True)
        os.makedirs(self.logs, exist_ok=True)
        self.token = ""
        if args.token_file and os.path.exists(args.token_file):
            with open(args.token_file, encoding="utf-8") as f:
                self.token = f.read().strip()
        self.gh = GitHub(self.token, ensaio=args.ensaio)
        self.db = sqlite3.connect(os.path.join(self.dados, "vigia.db"), check_same_thread=False)
        self.db_lock = threading.Lock()
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS builds (id INTEGER PRIMARY KEY, repo TEXT, ref TEXT, sha TEXT,"
            " evento TEXT, estado TEXT, inicio TEXT, fim TEXT, log TEXT, detalhe TEXT,"
            " UNIQUE(repo, sha, evento))"
        )
        self.db.commit()
        self.espelho_locks = {}
        # act names a job's container after its workflow and job names only, so two runs of the same job
        # at once fight over one container ("No such container", measured in the first rehearsal with two
        # desktop pull requests). Same-named jobs, from any repository, take turns; different ones run
        # in parallel.
        self.job_locks = {}
        self.job_locks_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=int(self.config.get("paralelo", 2)))
        self.askpass = None

    # ── the database ───────────────────────────────────────────────────────────────────────────

    def conhecido(self, repo):
        with self.db_lock:
            return self.db.execute("SELECT 1 FROM builds WHERE repo=? LIMIT 1", (repo,)).fetchone()

    def ja_visto(self, repo, sha, evento):
        with self.db_lock:
            return self.db.execute("SELECT 1 FROM builds WHERE repo=? AND sha=? AND evento=?", (repo, sha, evento)).fetchone()

    def registrar(self, repo, ref, sha, evento):
        with self.db_lock:
            cur = self.db.execute(
                "INSERT INTO builds (repo, ref, sha, evento, estado, inicio) VALUES (?,?,?,?, 'na fila', ?)",
                (repo, ref, sha, evento, agora()),
            )
            self.db.commit()
            return cur.lastrowid

    def atualizar(self, build_id, **campos):
        nomes = ", ".join(f"{k}=?" for k in campos)
        with self.db_lock:
            self.db.execute(f"UPDATE builds SET {nomes} WHERE id=?", (*campos.values(), build_id))
            self.db.commit()
        self.exportar()

    def exportar(self):
        """`builds.json` and a plain index next to the logs, for the dashboard and for a person."""
        with self.db_lock:
            linhas = self.db.execute(
                "SELECT id, repo, ref, sha, evento, estado, inicio, fim, log, detalhe FROM builds ORDER BY id DESC LIMIT 300"
            ).fetchall()
        campos = ["id", "repo", "ref", "sha", "evento", "estado", "inicio", "fim", "log", "detalhe"]
        lista = [dict(zip(campos, l)) for l in linhas]
        tmp = os.path.join(self.logs, ".builds.json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"gerado": agora(), "builds": lista}, f)
        os.replace(tmp, os.path.join(self.logs, "builds.json"))
        html = ["<!doctype html><meta charset=utf-8><title>cicd-vigia</title>",
                "<style>body{font:14px system-ui;margin:16px}td{padding:2px 8px}</style>",
                f"<h1>cicd-vigia</h1><p>{agora()}</p><table>"]
        for b in lista:
            link = f"<a href='{b['log']}'>log</a>" if b["log"] else ""
            html.append(
                f"<tr><td>{b['id']}</td><td>{b['repo']}</td><td>{b['ref']}</td><td>{(b['sha'] or '')[:8]}</td>"
                f"<td>{b['evento']}</td><td>{b['estado']}</td><td>{b['inicio'] or ''}</td><td>{b['fim'] or ''}</td>"
                f"<td>{link}</td><td>{b['detalhe'] or ''}</td></tr>"
            )
        html.append("</table>")
        tmp = os.path.join(self.logs, ".index.html")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(html))
        os.replace(tmp, os.path.join(self.logs, "index.html"))

    # ── git ────────────────────────────────────────────────────────────────────────────────────

    def git_env(self):
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        if self.token:
            if not self.askpass:
                fd, caminho = tempfile.mkstemp(prefix="vigia-askpass-", dir=self.dados)
                with os.fdopen(fd, "w") as f:
                    f.write(f"#!/bin/sh\ncase \"$1\" in Username*) echo x-access-token;; *) cat {self.args.token_file};; esac\n")
                os.chmod(caminho, 0o700)
                self.askpass = caminho
            env["GIT_ASKPASS"] = self.askpass
        return env

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, env=self.git_env(), check=True,
                              capture_output=True, text=True, timeout=900).stdout

    def espelho(self, repo):
        """A bare mirror per repository: branches and the merge refs of OUR pull requests only."""
        lock = self.espelho_locks.setdefault(repo, threading.Lock())
        caminho = os.path.join(self.dados, "espelhos", repo.replace("/", "__") + ".git")
        with lock:
            if not os.path.isdir(caminho):
                self.git("init", "--bare", "-q", caminho)
                self.git("-C", caminho, "remote", "add", "origin", f"https://github.com/{repo}.git")
        return caminho, lock

    def ls_remote_padrao(self, repo, ramo):
        saida = self.git("ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{ramo}")
        return saida.split()[0] if saida.strip() else None

    # ── the poll ───────────────────────────────────────────────────────────────────────────────

    def varrer(self):
        for nome, conf in self.config["repos"].items():
            if not conf.get("ativo", True):
                continue
            repo = f"{self.dono}/{nome}"
            try:
                self.varrer_repo(repo, conf)
            except Exception as e:  # one repository failing must not stop the others
                log(f"{repo}: poll failed: {e}")

    def varrer_repo(self, repo, conf):
        ramo = conf.get("ramo", "master")
        sha = self.ls_remote_padrao(repo, ramo)
        if sha and not self.ja_visto(repo, sha, "push"):
            if self.conhecido(repo) or self.args.backfill:
                self.agendar(repo, conf, f"refs/heads/{ramo}", sha, "push", None)
            else:
                # First sight of a repository: record its current head without building it, so turning
                # the watcher on does not run every repository's default branch (and its Release job)
                # at once. The next push builds.
                self.marcar_visto(repo, f"refs/heads/{ramo}", sha, "push")
        for pr in self.gh.prs_abertos(repo):
            head = pr.get("head") or {}
            if (head.get("repo") or {}).get("full_name") != repo:
                continue  # a fork: never run here
            if pr.get("draft") and not conf.get("rascunhos", True):
                continue
            sha_pr = head.get("sha")
            if not sha_pr or self.ja_visto(repo, sha_pr, "pull_request"):
                continue
            mescavel = self.gh.mescavel(repo, pr["number"])
            if mescavel is None:
                continue  # GitHub has not computed it yet: the next poll asks again
            ref = f"refs/pull/{pr['number']}/merge"
            if mescavel is False:
                build_id = self.registrar(repo, ref, sha_pr, "pull_request")
                self.gh.status(repo, sha_pr, "failure", "cicd-vigia",
                               "Conflicts with the base branch: rebase or merge it, then push", None)
                self.atualizar(build_id, estado="conflito", fim=agora(), detalhe="mergeable=false")
                log(f"{repo}: #{pr['number']} conflicts with its base; not built")
                continue
            self.agendar(repo, conf, ref, sha_pr, "pull_request", pr)

    def marcar_visto(self, repo, ref, sha, evento):
        build_id = self.registrar(repo, ref, sha, evento)
        self.atualizar(build_id, estado="ignorado", fim=agora(), detalhe="head when the watcher started")

    def agendar(self, repo, conf, ref, sha, evento, pr):
        build_id = self.registrar(repo, ref, sha, evento)
        log(f"{repo}: queued #{build_id} {evento} {ref} {sha[:8]}")
        self.pool.submit(self.construir_seguro, build_id, repo, conf, ref, sha, evento, pr)

    # ── one build ──────────────────────────────────────────────────────────────────────────────

    def construir_seguro(self, *a):
        try:
            self.construir(*a)
        except AindaNao as e:
            log(f"build #{a[0]}: GitHub has not updated the merge ref yet ({e}); the next poll retries")
            with self.db_lock:
                self.db.execute("DELETE FROM builds WHERE id=?", (a[0],))
                self.db.commit()
            self.exportar()
        except Exception as e:
            log(f"build #{a[0]} crashed: {e}\n{traceback.format_exc()}")
            self.atualizar(a[0], estado="erro", fim=agora(), detalhe=str(e)[:300])

    def url_log(self, nome):
        return f"{self.config['url_logs'].rstrip('/')}/{nome}" if self.config.get("url_logs") else None

    def construir(self, build_id, repo, conf, ref, sha, evento, pr):
        self.atualizar(build_id, estado="rodando")
        espelho, lock = self.espelho(repo)
        destino = os.path.join(self.dados, "trabalho", f"{repo.replace('/', '__')}-{build_id}")
        nome_log = f"{repo.split('/')[1]}-{build_id}-{sha[:8]}.log"
        caminho_log = os.path.join(self.logs, nome_log)
        url = self.url_log(nome_log)
        try:
            with lock:
                try:
                    self.git("-C", espelho, "fetch", "-q", "--force", "origin", f"+{ref}:{ref}", f"+{sha}")
                except subprocess.CalledProcessError as e:
                    if evento == "pull_request":
                        # No merge ref: the pull request conflicts with its base. GitHub runs nothing then.
                        self.gh.status(repo, sha, "failure", "cicd-vigia", "Conflicts with the base branch: no merge ref to test", url)
                        self.atualizar(build_id, estado="conflito", fim=agora(), detalhe="no merge ref")
                        return
                    raise RuntimeError(f"fetch failed: {e.stderr.strip()[:200]}")
                alvo = self.git("-C", espelho, "rev-parse", ref).strip()
                base_testada = None
                if evento == "pull_request":
                    # The merge ref must merge THIS head; GitHub rewrites it some time after a push.
                    # Its base is another matter: GitHub recomputes it when the head moves, not when the
                    # base does (measured on 27/10: desktop #161's merge ref still sat on a master three
                    # merges old, and `base.sha` in the API is older still, from when the PR was opened).
                    # Actions behaves the same, so the base is accepted and named in every status.
                    pais = self.git("-C", espelho, "rev-parse", f"{ref}^1", f"{ref}^2").split()
                    if pais[1] != sha:
                        raise AindaNao(f"{ref} merges {pais[1][:8]}, the head is {sha[:8]}")
                    base_testada = pais[0][:8]
                # A full local clone, not a `git worktree`: a worktree's `.git` is a file pointing back to the
                # mirror, a path that does not exist inside a job's container, and a workflow step that runs
                # git there fails (`git ls-files`: "not a git repository", measured in the second rehearsal).
                # A local clone hard-links the mirror's objects, so it costs almost nothing. `origin` points
                # at GitHub because tools read the repository from it (tools/release.sh does). Under the
                # mirror's lock, so no fetch rewrites it while it is being copied.
                self.git("clone", "-q", "--no-checkout", espelho, destino)
            self.git("-C", destino, "checkout", "-q", "--detach", alvo)
            self.git("-C", destino, "remote", "set-url", "origin", f"https://github.com/{repo}.git")
            # A loose ref, so `.git/refs/` holds a file. act copies the checkout into the container file by
            # file, and a local clone keeps every ref in `packed-refs`, leaving `refs/heads` and `refs/tags`
            # empty: the empty directories do not travel, and git does not recognise a `.git` without
            # `refs/` (third rehearsal, 27/10/2026: `ls .git` worked, `git rev-parse` did not).
            self.git("-C", destino, "update-ref", "refs/heads/cicd-vigia", alvo)
            evento_json = os.path.join(destino, "..", f"evento-{build_id}.json")
            with open(evento_json, "w", encoding="utf-8") as f:
                json.dump(self.payload(repo, conf, ref, sha, alvo, evento, pr), f)
            todos = self.listar_jobs(destino, evento, evento_json, conf, com_fora=True)
            mac = conf.get("mac") or {}
            jobs_mac = [j for j in todos if j["id"] in mac.get("jobs", [])] if mac.get("host") else []
            jobs = [j for j in todos if j["id"] not in set(conf.get("fora", []))] + jobs_mac
            onde = f"on cicd, base {base_testada}" if base_testada else "on cicd"
            for job in jobs:
                self.gh.status(repo, sha, "pending", job["nome"], f"Running {onde}", url)
            chaves = sorted({f"{j['workflow']}/{j['nome']}" for j in jobs if j not in jobs_mac})
            with self.locks_dos_jobs(chaves):
                resultados = self.rodar_act(destino, evento, evento_json, conf, caminho_log)
            if jobs_mac:
                resultados.update(self.rodar_no_mac(repo, mac, ref, alvo, evento, evento_json, jobs_mac, caminho_log))
            falhou = False
            for job in jobs:
                r = resultados.get(job["id"]) or resultados.get(job["nome"])
                if r == "success":
                    self.gh.status(repo, sha, "success", job["nome"], f"Passed {onde}", url)
                elif r == "skipped":
                    self.gh.status(repo, sha, "success", job["nome"], f"Skipped {onde} (its if: was false)", url)
                else:
                    falhou = True
                    self.gh.status(repo, sha, "failure", job["nome"], f"Failed {onde} ({r or 'did not finish'})", url)
            self.atualizar(build_id, estado="falhou" if falhou else "passou", fim=agora(), log=nome_log,
                           detalhe=", ".join(f"{j['id']}={resultados.get(j['id'], '?')}" for j in jobs)[:300])
        finally:
            shutil.rmtree(destino, ignore_errors=True)
            try:
                os.remove(os.path.join(self.dados, "trabalho", f"evento-{build_id}.json"))
            except OSError:
                pass

    def locks_dos_jobs(self, chaves):
        """Takes the lock of every job name in this run, always in the same (sorted) order, so two runs
        that share several job names cannot each hold one and wait for the other."""
        vigia = self

        class Varios:
            def __enter__(self):
                with vigia.job_locks_lock:
                    self.locks = [vigia.job_locks.setdefault(c, threading.Lock()) for c in chaves]
                for l in self.locks:
                    l.acquire()

            def __exit__(self, *exc):
                for l in reversed(self.locks):
                    l.release()

        return Varios()

    def payload(self, repo, conf, ref, sha, alvo, evento, pr):
        repositorio = {"full_name": repo, "name": repo.split("/")[1], "owner": {"login": self.dono},
                       "default_branch": conf.get("ramo", "master")}
        if evento == "pull_request":
            return {"action": "synchronize", "number": pr["number"], "pull_request": pr, "repository": repositorio}
        return {"ref": ref, "after": sha, "head_commit": {"id": sha}, "repository": repositorio}

    def plataformas(self, conf):
        """`vm` runs like the self-hosted runner did (on this machine, as this user); `conteiner` runs
        `ubuntu-latest` in the act image. Jobs for macOS or Windows map to nothing and act skips them."""
        if conf.get("modo") == "vm":
            rotulo = conf.get("rotulo", "shvia-ci")
            return ["-P", f"{rotulo}=-self-hosted", "-P", "ubuntu-latest=-self-hosted", "--var", f"CI_RUNNER={rotulo}"]
        # `--init`: act's container has no init, so a process a test kills stays a zombie under PID 1
        # and still "exists". GitHub's VM reaps it. Measured on 27/10/2026: three of shvia-desktop's
        # PTY tests (`code_bridge::assinatura::pty`) failed in act without it.
        return ["-P", f"ubuntu-latest={IMAGEM}", "--container-options", "--init"]

    def listar_jobs(self, destino, evento, evento_json, conf, com_fora=False):
        saida = subprocess.run(["act", evento, "-e", evento_json, "-l"], cwd=destino, capture_output=True,
                               text=True, timeout=120).stdout
        fora = set(conf.get("fora", []))
        jobs = []
        linhas = saida.splitlines()
        cab = next((l for l in linhas if l.startswith("Stage")), None)
        if not cab:
            return jobs
        col = [cab.index(n) for n in ("Job ID", "Job name", "Workflow name", "Workflow file")]
        for l in linhas[linhas.index(cab) + 1:]:
            if not l.strip() or not l[0].isdigit():
                continue
            job_id = l[col[0]:col[1]].strip()
            nome = l[col[1]:col[2]].strip()
            workflow = l[col[2]:col[3]].strip()
            if job_id in fora and not com_fora:
                continue
            jobs.append({"id": job_id, "nome": nome, "workflow": workflow})
        return jobs

    def rodar_act(self, destino, evento, evento_json, conf, caminho_log):
        # Every job of the event runs; a job whose `runs-on` maps to no platform (macOS, Windows) is
        # skipped by act itself, and `fora` only keeps such jobs from getting a pending status.
        cmd = [*ACT_BASE, evento, "-e", evento_json, *self.plataformas(conf)]
        env = dict(os.environ)
        if self.token:
            # `-s NAME` without a value makes act read it from the environment of this one child. With an
            # empty value act asks on the terminal instead (measured in the first rehearsal), so the
            # secret is only declared when there is one.
            cmd += ["-s", "GITHUB_TOKEN"]
            env["GITHUB_TOKEN"] = self.token
        resultados = {}
        with open(caminho_log, "w", encoding="utf-8") as saida:
            proc = subprocess.Popen(cmd, cwd=destino, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            escrito = 0
            for linha in proc.stdout:
                try:
                    j = json.loads(linha)
                except ValueError:
                    j = None
                if isinstance(j, dict):
                    texto = f"[{j.get('job', '')}] {j.get('msg', '')}".rstrip() + "\n"
                    if j.get("jobResult"):
                        resultados[j.get("jobID") or j.get("job")] = j["jobResult"]
                else:
                    texto = linha
                if escrito < LOG_MAX:
                    saida.write(texto)
                    escrito += len(texto)
            proc.wait(timeout=self.args.limite)
        return resultados

    def rodar_no_mac(self, repo, mac, ref, alvo, evento, evento_json, jobs, caminho_log):
        """The jobs only a Mac can run, on the owner's Mac over SSH (owner's decision, 27/10/2026). The
        Mac keeps its own clone in `mac.dir`; it fetches the same tree this machine tested, by SHA,
        and runs the job on itself with act (`-P macos-latest=-self-hosted`). Only same-repository
        pull requests reach this point, so nothing from a fork runs there either."""
        destino = f"{mac.get('dir', 'ci')}/{repo.split('/')[1]}"
        resultados = {}
        for job in jobs:
            script = (
                "set -e; "
                f"mkdir -p {mac.get('dir', 'ci')}; "
                f"[ -d {destino}/.git ] || git clone -q https://github.com/{repo}.git {destino}; "
                f"cd {destino}; git fetch -q origin {ref}; "
                f"[ \"$(git rev-parse FETCH_HEAD)\" = {alvo} ]; git checkout -q -f --detach {alvo}; "
                "cat > ../.evento-vigia.json; "
                f"act {evento} -e ../.evento-vigia.json -j {job['id']} --json --use-new-action-cache "
                "-P macos-latest=-self-hosted"
            )
            # The key is the runner's own (`~/.ssh/id_ed25519_mac`), made for this and nothing else.
            cmd = ["ssh", "-i", os.path.expanduser(mac.get("chave", "~/.ssh/id_ed25519_mac")), "-o", "IdentitiesOnly=yes",
                   "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", f"{mac['usuario']}@{mac['host']}", script]
            with open(evento_json, encoding="utf-8") as ev, open(caminho_log, "a", encoding="utf-8") as saida:
                saida.write(f"\n===== macOS: {job['nome']} on {mac['host']} =====\n")
                proc = subprocess.Popen(cmd, stdin=ev, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for linha in proc.stdout:
                    try:
                        j = json.loads(linha)
                    except ValueError:
                        j = None
                    if isinstance(j, dict):
                        saida.write(f"[{j.get('job', '')}] {j.get('msg', '')}".rstrip() + "\n")
                        if j.get("jobResult"):
                            resultados[job["id"]] = j["jobResult"]
                    else:
                        saida.write(linha)
                proc.wait(timeout=self.args.limite)
            if job["id"] not in resultados:
                resultados[job["id"]] = f"mac unreachable or act failed (exit {proc.returncode})"
        return resultados

    def laco(self):
        ativos = [n for n, c in self.config["repos"].items() if c.get("ativo", True)]
        log(f"watching {len(ativos)} repositories every {self.args.intervalo} s: {', '.join(ativos)}")
        while True:
            self.varrer()
            if self.args.uma_vez:
                self.pool.shutdown(wait=True)
                return
            time.sleep(self.args.intervalo)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--config", default="/etc/cicd-vigia/repos.json")
    p.add_argument("--token-file", default="/etc/cicd-vigia/token")
    p.add_argument("--dados", default="/srv/runners/_vigia")
    p.add_argument("--logs", default="/var/lib/cicd-painel/www/vigia")
    p.add_argument("--intervalo", type=int, default=60)
    p.add_argument("--limite", type=int, default=3 * 3600, help="seconds one act run may take")
    p.add_argument("--uma-vez", action="store_true", help="one poll, wait for its builds, exit")
    p.add_argument("--backfill", action="store_true", help="build the default branch head on first sight too")
    p.add_argument("--ensaio", action="store_true",
                   help="rehearsal: print each status instead of posting it (public repositories run without a token)")
    args = p.parse_args()
    if not args.ensaio and (not args.token_file or not os.path.exists(args.token_file)):
        print(f"no token at {args.token_file}: the watcher cannot post a status (see the runbook)", file=sys.stderr)
        return 2
    Vigia(args).laco()
    return 0


if __name__ == "__main__":
    sys.exit(main())
