/**
 * Turns git's `gc --auto` off for EVERY call made by this process and its children.
 *
 * Copied from shvia-web `scripts/lib/git-sem-faxina.mjs`, where it was written; the comments were
 * translated on the way in.
 *
 * ## The defect this closes, measured on 19/09/2026
 *
 * shvia-web's master CI went RED with:
 *
 *     Error: ENOTEMPTY: directory not empty, rmdir '/tmp/carimbo-nhPCyz/clone/.git'
 *
 * Nothing was wrong with what the ruler measures. What failed was the **cleanup**: `git gc --auto`
 * starts by itself after a handful of loose objects, **forks into the background**, and keeps
 * writing inside `.git` after the foreground command has returned. The ruler then removes the
 * directory under a process that is still writing to it, and `rmSync` throws.
 *
 * 🔴 **A ruler that fails on its cleanup is the worst red there is**, for a precise reason: it
 * blames the code under test when what failed was tidying `/tmp`. Whoever reads the CI looks in
 * the wrong place — and, worse, learns that this red "happens sometimes", which is how a ruler
 * dies.
 *
 * ## Why an environment variable and not `git config` in each repository
 *
 * Several rulers build temporary repositories, each with its own form of `init`/`clone` — some
 * `--bare`, some cloning from a remote that needs the setting too. Getting each of them right by
 * hand leaves out the next one, written next month.
 *
 * `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` is git's own protocol for
 * configuration through the environment: it holds for **every** invocation of this process, for
 * the repositories it creates, and for the ones it has not created yet.
 *
 * ⚠️ It keeps what is already in the environment: if the caller already uses `GIT_CONFIG_COUNT`,
 * the keys here go AFTER its own, without overwriting any index.
 */
const jaTinha = Number.parseInt(process.env.GIT_CONFIG_COUNT ?? '0', 10);
const base = Number.isFinite(jaTinha) && jaTinha > 0 ? jaTinha : 0;

const chaves = [
  ['gc.auto', '0'],
  // `maintenance` is the successor of `gc --auto`, and it forks the same way.
  ['maintenance.auto', 'false'],
];

chaves.forEach(([chave, valor], i) => {
  process.env[`GIT_CONFIG_KEY_${base + i}`] = chave;
  process.env[`GIT_CONFIG_VALUE_${base + i}`] = valor;
});
process.env.GIT_CONFIG_COUNT = String(base + chaves.length);
