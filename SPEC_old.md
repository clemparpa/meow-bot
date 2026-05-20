# Spec — `ci-vibe`

> GitHub Action OSS qui encapsule [Mistral Vibe](https://github.com/mistralai/mistral-vibe) en mode programmatique (`vibe --prompt`) pour automatiser code review, security review et triage d'issues dans n'importe quel repo GitHub.

**Version de la spec :** 1.1 (pivot Python, intégration patterns OpenHands)
**Statut :** À implémenter
**Licence :** Apache-2.0 (alignée sur Mistral Vibe upstream)
**Runtime :** Python 3.12 via `uv run --no-project`

---

## 1. Objectifs et non-objectifs

### Objectifs

- Fournir **une action GitHub réutilisable** (`uses: clemparpa/ci-vibe@v1`) qui exécute Mistral Vibe en headless sur un repo cible.
- Couvrir **trois modes natifs** : `review` (code review de PR), `security` (security review SAST-like de PR), `triage` (analyse d'issue à l'ouverture).
- Permettre un **mode `custom`** avec prompt arbitraire pour des usages non prévus (doc, tests, refactor…).
- Garantir un **niveau de sécurité acceptable par défaut** : permissions minimales, allowlist d'outils stricte, cap de coût, scrubbing des secrets.
- Être **maintenable comme un projet OSS sérieux** : CI verte, dependabot, releases versionnées, doc utilisateur claire, security policy.

### Non-objectifs

- Pas d'orchestration multi-modèle dans v1 (Mistral uniquement via `MISTRAL_API_KEY`). Le support de providers custom via `config.toml` reste possible mais non documenté en v1.
- Pas de support GitLab/Bitbucket dans v1 (uniquement GitHub Actions).
- Pas de bridge avec Linear/Jira/Sentry dans v1 (Vibe en local le permet, on n'expose pas ces intégrations côté action).
- Pas de fine-tuning ni d'évaluation/benchmark embarqué.

---

## 2. Choix techniques structurants

### Type d'action : **composite (orchestration YAML, logique en Python)**

- Pas Docker (cold start lent, complication multi-arch).
- Pas JavaScript / TypeScript (Vibe est Python, écrire un wrapper Node ajoute une couche inutile).
- **Composite YAML** pour l'orchestration GitHub (setup Python/uv, préflight, upload artifact).
- **Module Python** (`ci_vibe`) pour la logique métier (diff sanitization, invocation Vibe, parsing output, post comment).
- Pattern inspiré du plugin [`OpenHands/extensions/plugins/pr-review`](https://github.com/OpenHands/extensions/tree/main/plugins/pr-review) : `action.yml` minimal, le gros du code dans un script Python invoqué via `uv run`.

### Stack

- **Runtime** : `ubuntu-latest` (testé aussi sur `ubuntu-22.04` et `ubuntu-24.04`).
- **Python** : 3.12 (cohérent avec `mistralai/mistral-vibe` et `OpenHands`). Installé via `actions/setup-python@v5`.
- **Gestion deps** : `uv` (`astral-sh/setup-uv@v8`). Cache **désactivé par défaut** pour des raisons de sécurité (cf §7).
- **API Vibe** : `from vibe.core import run_programmatic` (API publique, re-exportée explicitement dans `vibe/core/__init__.py`, listée dans `__all__`).
- **Version Vibe** : pinnée par défaut (`mistral-vibe==2.9.6` au moment de la rédaction), surchargeable via input `vibe-version`.
- **Wrapper interne** : module `ci_vibe` (4 sous-modules : `context`, `runner`, `parser`, `commenter`). Layout `src/ci_vibe/`.
- **Tooling Python** : stack Astral cohérente — [`uv`](https://docs.astral.sh/uv/) (deps), [`ruff`](https://docs.astral.sh/ruff/) (lint + format), [`ty`](https://docs.astral.sh/ty/) (type-checking, en preview début 2026). Tests via `pytest`. Pas de `mypy`, pas de `black`, pas de `flake8`.
- **Templates de prompts** : fichiers markdown dans `prompts/` (review.md, security.md, triage.md) chargés et interpolés via `string.Template` de la stdlib. Jinja2 différé à v0.4+ si la logique conditionnelle devient nécessaire.

### Versionnage de l'action

- Semver strict : `v1.2.3`.
- **Tag majeur flottant** (`v1`) re-pointé à chaque release mineure/patch (convention GitHub Actions).
- Les utilisateurs externes consomment `@v1` par défaut, ou `@v1.2.3` pour figer.

---

## 3. Interface de l'action — `action.yml`

```yaml
name: 'ci-vibe'
description: 'Run Mistral Vibe headless for code review, security review, or issue triage.'
author: 'clemparpa'
branding:
  icon: 'cpu'
  color: 'orange'

inputs:
  mistral-api-key:
    description: 'Mistral API key. Required.'
    required: true

  mode:
    description: 'review | security | triage | custom'
    required: false
    default: 'review'

  prompt:
    description: 'Custom prompt. Required when mode=custom, ignored otherwise unless `prompt-override` is true.'
    required: false
    default: ''

  prompt-override:
    description: 'If true, use `prompt` even for non-custom modes (appended to the template).'
    required: false
    default: 'false'

  model:
    description: 'Mistral model identifier (e.g. mistral-medium-3.5, devstral-2).'
    required: false
    default: 'mistral-medium-3.5'

  max-turns:
    description: 'Maximum agent turns. Hard cap to avoid runaway loops.'
    required: false
    default: '10'

  max-price:
    description: 'Maximum cost in USD. Vibe stops if exceeded.'
    required: false
    default: '1.00'

  allowed-tools:
    description: 'Comma-separated list of Vibe tools to enable. Defaults depend on mode (see README).'
    required: false
    default: ''

  comment-pr:
    description: 'Post result as a PR/issue comment.'
    required: false
    default: 'true'

  upload-artifact:
    description: 'Upload the raw output as a workflow artifact.'
    required: false
    default: 'true'

  exclude-paths:
    description: 'Comma-separated globs to exclude from analysis.'
    required: false
    default: ''

  agents-md-path:
    description: 'Path to AGENTS.md in the target repo. Copied to .vibe/AGENTS.md before running Vibe. Pass empty string to disable.'
    required: false
    default: 'AGENTS.md'

  vibe-version:
    description: 'Pin a specific Mistral Vibe version. Defaults to the version tested by this release.'
    required: false
    default: ''

  github-token:
    description: 'Token used to comment on PRs/issues. Defaults to github.token.'
    required: false
    default: ${{ github.token }}

  fail-on-findings:
    description: 'For mode=security: fail the job if any high-confidence finding is reported.'
    required: false
    default: 'false'

  enable-uv-cache:
    description: |
      Enable setup-uv's GitHub Actions cache for Python dependencies.
      Default is 'false' for security: a prompt-injected reviewer could write a malicious wheel
      into a shared cache, which a subsequent higher-privilege workflow would then consume.
      Only opt in when you control the runner environment (e.g. self-hosted, single-tenant).
      Pattern adapted from OpenHands/extensions/plugins/pr-review.
    required: false
    default: 'false'

outputs:
  result-path:
    description: 'Path to the markdown report produced by Vibe.'
  findings-count:
    description: 'Number of findings detected (security mode) or suggestions (review mode).'
  cost-usd:
    description: 'Approximate cost of the run in USD. **Returns 0 in v0.x**: `vibe --output json` does not expose `AgentStats.session_cost` (tracked upstream in mistralai/mistral-vibe). Output is kept for forward-compatibility.'

runs:
  using: 'composite'
  steps:
    # ... see §5 Implementation
```

---

## 4. Modes — comportement attendu

### 4.1 `mode: review`

- **Déclencheur typique** : `pull_request` (`opened`, `synchronize`).
- **Contexte injecté** : diff `origin/<base>...HEAD`, contenu des fichiers modifiés, `AGENTS.md`.
- **Outils par défaut** : `read_file, grep, bash` (lecture seule sur git/diff).
- **Sortie** : commentaire markdown structuré sur la PR avec sections `Bugs`, `Style`, `Performance`, `Suggestions`.
- **Prompt template** : `prompts/review.md`.

### 4.2 `mode: security`

- **Déclencheur typique** : `pull_request`, idéalement gated par "Require approval for all external contributors".
- **Contexte injecté** : diff complet + fichiers touchés, `AGENTS.md`, `exclude-paths` honoré.
- **Outils par défaut** : `read_file, grep` (pas de `bash`, principe du moindre privilège).
- **Sortie** : commentaire markdown avec findings notés par sévérité (`High` / `Medium` / `Low`, aligné sur `anthropics/claude-code-security-review`) et score de confiance 1–10. Findings filtrés à **≥ 8 de confiance** par défaut.
- **Prompt template** : `prompts/security.md`. Adapté du prompt de `anthropics/claude-code-security-review` mais réécrit pour Vibe + Mistral (style de réponse, formats d'outputs).
- **Si `fail-on-findings: true`** : exit code 1 si au moins un finding `High` est confirmé.

### 4.3 `mode: triage`

- **Déclencheur typique** : `issues` (`opened`).
- **Contexte injecté** : titre et corps de l'issue, structure du repo (sortie `tree -L 2`), `AGENTS.md`.
- **Outils par défaut** : `read_file, grep` (analyse sans modification).
- **Sortie** : commentaire markdown avec hypothèse de root cause, fichiers probablement concernés, suggestion de labels (`bug`, `enhancement`, `priority/*`, `area/*`), estimation de complexité.
- **Prompt template** : `prompts/triage.md`.

### 4.4 `mode: custom`

- L'utilisateur fournit `prompt:` directement. Les autres inputs (model, max-turns, max-price, allowed-tools) restent applicables.
- Aucun template chargé. L'utilisateur est responsable du contenu.

---

## 5. Structure du dépôt

Le projet sera initialisé via `uv init --package --lib ci-vibe` (layout `src/`). L'arborescence cible :

```text
ci-vibe/
├── action.yml                    # Manifest de l'action (composite, orchestration)
├── pyproject.toml                # Métadonnées + deps dev (ruff, ty, pytest). mistral-vibe est injecté via `uv run --with`, pas en dep.
├── uv.lock                       # Lockfile (commité)
├── README.md                     # Doc utilisateur (voir §9)
├── LICENSE                       # Apache-2.0
├── CHANGELOG.md                  # Keep a Changelog format
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md            # Contributor Covenant 3.0
├── SECURITY.md                   # GitHub Private Vulnerability Reporting
├── .markdownlint.json
├── prompts/
│   ├── review.md
│   ├── security.md               # v0.2+
│   └── triage.md                 # v0.3+
├── src/
│   └── ci_vibe/
│       ├── __init__.py
│       ├── __main__.py           # entrée: `python -m ci_vibe`
│       ├── config.py             # parsing/validation des env vars (inputs action)
│       ├── context.py            # diff + sanitization + AGENTS.md
│       ├── runner.py             # invocation `vibe.core.run_programmatic`
│       ├── parser.py             # extraction findings, écriture GITHUB_OUTPUT
│       ├── commenter.py          # scrubbing secrets + gh pr comment
│       └── templates.py          # chargement et interpolation prompts/
├── examples/                     # Workflows clés-en-main à recopier
│   ├── pr-review.yml
│   ├── security-review.yml       # v0.2+
│   ├── issue-triage.yml          # v0.3+
│   └── custom-prompt.yml         # v0.4+
├── .github/
│   ├── CODEOWNERS
│   ├── workflows/
│   │   ├── ci.yml                # ruff + ty + pytest + actionlint + markdownlint
│   │   ├── dogfood.yml           # v0.2+ — l'action s'auto-applique sur ses PRs
│   │   ├── release.yml           # v0.5+ — tag + release notes auto
│   │   └── major-tag.yml         # v1.0+ — repoint v1 → vX.Y.Z après release
│   ├── dependabot.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml
│   │   ├── feature_request.yml
│   │   └── config.yml            # Renvoie SECURITY.md pour les bugs sécu
│   └── pull_request_template.md
└── tests/
    ├── conftest.py
    ├── fixtures/                 # diffs/issues de test, vibe.json factices
    ├── test_context.py
    ├── test_parser.py
    ├── test_commenter.py
    └── test_runner.py            # avec mocks de vibe.core.run_programmatic
```

**Décision : pas de pyproject.toml `[project.dependencies]` pour `mistral-vibe`.** L'action installe Vibe via `uv run --no-project --with "mistral-vibe==${VIBE_VERSION}" --with "${{ github.action_path }}" python -m ci_vibe`. Cela permet :

1. Versioning indépendant de Vibe (input `vibe-version` override) sans toucher au lockfile.
2. Pas de conflit de résolution si le repo cible a aussi un environnement Python.
3. Le pyproject.toml reste léger : il décrit le module `ci_vibe` (importable) + les deps de dev (`ruff`, `ty`, `pytest`).

Pattern repris de [`OpenHands/extensions`](https://github.com/OpenHands/extensions/blob/main/plugins/pr-review/action.yml) qui fait `uv run --no-project --with openhands-sdk --with openhands-tools python script.py`.

---

## 6. Implémentation — détails clés

### 6.1 Orchestration `action.yml` (composite minimal)

L'action.yml ne contient **que** l'orchestration : setup Python/uv, validation des inputs, préflight permission check, invocation Python, upload artifact. Aucune logique métier.

```yaml
runs:
  using: composite
  steps:
    - uses: actions/setup-python@v5
      with: { python-version: '3.12' }

    - uses: astral-sh/setup-uv@v8
      with: { enable-cache: ${{ inputs.enable-uv-cache }} }

    - name: Preflight permission check
      if: github.event_name == 'pull_request' && inputs.comment-pr == 'true'
      shell: bash
      env: { GH_TOKEN: ${{ inputs.github-token }} }
      run: |
        # Crée puis supprime un commentaire vide pour valider que le token
        # a `pull-requests: write`. Économise un appel LLM si misconfig.
        if ! gh pr comment "${{ github.event.pull_request.number }}" \
             --body '<!-- ci-vibe preflight -->' >/dev/null; then
          echo "::error::github-token lacks pull-requests: write permission"
          exit 1
        fi

    - name: Run ci-vibe
      shell: bash
      env:
        MISTRAL_API_KEY: ${{ inputs.mistral-api-key }}
        GH_TOKEN: ${{ inputs.github-token }}
        CI_VIBE_MODE: ${{ inputs.mode }}
        CI_VIBE_MODEL: ${{ inputs.model }}
        CI_VIBE_MAX_TURNS: ${{ inputs.max-turns }}
        CI_VIBE_MAX_PRICE: ${{ inputs.max-price }}
        # ... (toutes les autres inputs en CI_VIBE_*)
      run: |
        VIBE_PIN="${{ inputs.vibe-version }}"
        VIBE_PIN="${VIBE_PIN:-2.9.6}"
        uv run --no-project \
          --with "mistral-vibe==${VIBE_PIN}" \
          --with "${{ github.action_path }}" \
          python -m ci_vibe

    - uses: actions/upload-artifact@v7
      if: inputs.upload-artifact == 'true' && always()
      with:
        name: ci-vibe-output-${{ github.run_id }}
        path: |
          ${{ runner.temp }}/report.md
          ${{ runner.temp }}/vibe.json
```

### 6.2 Module Python `ci_vibe` (cœur de la logique)

Entrée : `python -m ci_vibe` → `src/ci_vibe/__main__.py` :

```python
# src/ci_vibe/__main__.py (pseudo-code)
from ci_vibe.config import load_config_from_env
from ci_vibe.context import prepare_context
from ci_vibe.runner import run_vibe
from ci_vibe.parser import write_outputs
from ci_vibe.commenter import post_pr_comment

def main() -> int:
    cfg = load_config_from_env()  # parse les CI_VIBE_* env vars, valide
    if cfg.mode != "review":
        print(f"::error::mode '{cfg.mode}' not implemented in v0.1")
        return 2

    ctx = prepare_context(cfg)         # diff, sanitization, AGENTS.md → .vibe/
    result = run_vibe(cfg, ctx)        # vibe.core.run_programmatic(...)
    findings = write_outputs(result)   # parse report.md + écrit GITHUB_OUTPUT
    if cfg.comment_pr and cfg.pr_number:
        post_pr_comment(cfg, result.report_path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Pattern d'invocation Vibe dans `runner.py` :

```python
from vibe.core import run_programmatic
from vibe.core.config import VibeConfig
from vibe.core.output import OutputFormat

def run_vibe(cfg: Config, ctx: Context) -> RunResult:
    vibe_cfg = VibeConfig(
        api_key=cfg.mistral_api_key,
        model=cfg.model,
        # ... mapping cfg → VibeConfig
    )
    prompt = render_template(cfg.mode, ctx)
    json_str = run_programmatic(
        config=vibe_cfg,
        prompt=prompt,
        max_turns=cfg.max_turns,
        max_price=cfg.max_price,
        output_format=OutputFormat.JSON,
    )
    # json_str est une string JSON (LLMMessage[]); on l'écrit sur disque
    # pour l'artefact debug. Le rapport markdown est écrit par Vibe via le prompt.
    (cfg.runner_temp / "vibe.json").write_text(json_str or "[]")
    return RunResult(report_path=cfg.runner_temp / "report.md", messages_json=json_str)
```

Détails à finaliser à l'implémentation :

- **Signature exacte de `VibeConfig`** : à confirmer avec un `inspect` ou un coup d'œil au code Vibe pendant le scaffold. Deepwiki donne la signature de `run_programmatic` mais pas la structure complète de `VibeConfig`.
- **Sanitisation du diff** (`context.py`) : Python `re.sub` pour HTML comments et caractères invisibles (cf §7), bien plus lisible que le `perl -0777 -pe` initial.
- **Scrubbing des secrets** (`commenter.py`) : `re.sub` sur `MISTRAL_API_KEY` (exact match) + patterns GH tokens.

### 6.3 Convention des templates et extraction des métadonnées

Chaque template termine par une instruction du type :

> Save the final markdown report to `$RUNNER_TEMP/report.md`. At the end of the file, append a single line `<!-- findings:N -->` where N is the number of findings.

`parser.py` extrait :

- **`findings-count`** depuis le marqueur HTML en fin de rapport (`<!-- findings:N -->`). C'est le LLM qui connaît la sémantique « finding » selon le mode, donc impossible de l'extraire autrement.
- **`cost-usd`** : **non disponible en v0.x**. Vérification deepwiki : `run_programmatic` retourne `str | None` (le JSON sérialisé des `LLMMessage`), pas l'objet `AgentStats` (où vit `session_cost`). On retourne `0` et on documente la limitation. Issue upstream à ouvrir sur `mistralai/mistral-vibe` pour soit (a) exposer `AgentStats` dans le `RunResult`, soit (b) inclure les métadonnées dans le JSON `output_format`.

Le fichier `vibe.json` brut est uploadé en artefact si `upload-artifact: true`, pour debug (post-mortem des messages assistant).

### 6.4 Gestion des permissions et secrets

- L'action **ne demande jamais** `contents: write`. Toute modification de code est hors scope v1.
- `github-token` n'est utilisé que pour `gh pr comment` / `gh issue comment`. Permission requise : `pull-requests: write` ou `issues: write` selon le mode.
- **Préflight permission check** : avant d'invoquer le LLM, l'action poste un commentaire factice puis le supprime, pour vérifier que le token a bien la permission requise. Fail-fast : si misconfig, on n'a pas dépensé de tokens Mistral.
- `MISTRAL_API_KEY` est passé en `env:` au step Python, **jamais en argument CLI** (évite le leak dans les logs). Dans le code Python il vit dans `Config.mistral_api_key`, jamais loggé.
- **Scrubbing** : avant `gh ... comment`, le rapport est filtré via `re.sub` pour retirer toute occurrence du `MISTRAL_API_KEY` exact + patterns GitHub tokens (`ghp_*`, `gho_*`, `ghs_*`, `ghr_*`, `github_pat_*`).
- **`persist-credentials: false`** recommandé sur le `actions/checkout` du repo cible (documenté dans le README quickstart) — empêche que le token GH leak via `git push` accidentel par Vibe.

### 6.5 Convention `AGENTS.md`

Mistral Vibe charge ses instructions agent depuis `.vibe/AGENTS.md` (projet) ou `~/.vibe/AGENTS.md` (user). Pour respecter la convention `AGENTS.md` exposée par l'écosystème (fichier à la racine du repo cible), `context.py` **copie** le fichier indiqué par `agents-md-path` (défaut : `AGENTS.md` à la racine du repo cible) vers `${GITHUB_WORKSPACE}/.vibe/AGENTS.md` avant l'invocation de Vibe.

- Si le fichier source n'existe pas, l'étape est skip silencieusement (pas d'erreur).
- Le fichier n'est jamais modifié dans le repo cible (copie unidirectionnelle vers `.vibe/`).
- L'utilisateur peut désactiver le mécanisme en passant `agents-md-path: ''`.

### 6.6 Cache `uv` partagé — désactivé par défaut

`setup-uv@v8` propose un `enable-cache` qui partage le cache `~/.cache/uv` entre workflows. Risque identifié dans [`OpenHands/extensions/plugins/pr-review`](https://github.com/OpenHands/extensions/blob/main/plugins/pr-review/action.yml) :

> *« Prompt-injected reviewer could write a malicious wheel into the shared cache; subsequent higher-privilege workflow hits poisoned cache. »*

Mitigation imposée :

- `enable-uv-cache` input expose le choix, **défaut `false`**.
- Documentation explicite : opt-in uniquement pour runners self-hosted single-tenant.

---

## 7. Modèle de sécurité

### 7.1 Menaces considérées

1. **Prompt injection via PR fork** — un contributeur externe place des instructions cachées dans le diff ou la description.
2. **Exfiltration via outils** — Vibe exécute `bash` et fait sortir des secrets via curl.
3. **Coût runaway** — boucle infinie ou prompt malicieux qui crame le budget API.
4. **Modification non-désirée** — Vibe écrit dans le repo en accept-edits.
5. **Cache poisoning via `uv` partagé** — un prompt-injected reviewer place une wheel malicieuse dans le cache, qu'un workflow plus privilégié consomme ensuite. Identifié par OpenHands.
6. **Token leak via `git push`** — Vibe pousse accidentellement avec le token de l'action persistant dans la config git du checkout.

### 7.2 Mitigations imposées par défaut

| Menace | Mitigation |
|--------|------------|
| Prompt injection | Sanitisation du diff dans `context.py` (`re.sub` sur HTML comments + caractères Unicode invisibles : zero-width, bidi overrides, BOM). Documentation explicite recommandant `Require approval for all external contributors`. |
| Exfiltration | Liste d'outils stricte (`read_file,grep,bash` pour review ; `bash` exclu en `security`). Jamais de wildcard. |
| Cost runaway | `max-turns` et `max-price` cappés (default 10 / $1). Préflight permission check pour ne pas brûler de tokens en cas de misconfig. |
| Modification | v1 = lecture seule, `write_file` absent des defaults. Si l'utilisateur force `allowed-tools: ...,write_file`, doc explicite que ce n'est plus une action de review. |
| Cache poisoning | `enable-uv-cache: false` par défaut (cf §6.6). Opt-in uniquement sur runner self-hosted single-tenant. |
| Token leak | Documentation README recommande `persist-credentials: false` sur `actions/checkout` du repo cible. Préflight check avec un commentaire factice = no-op visible plutôt que tentative de write opaque. |

### 7.3 Recommandations utilisateur (à mettre dans README)

- Activer "Require approval for all external contributors" dans Settings → Actions.
- Permissions du workflow au minimum : `contents: read`, `pull-requests: write`.
- Clé API Mistral dédiée à la CI, avec usage cap dans la console.
- `persist-credentials: false` sur `actions/checkout` du repo cible.
- Garder `enable-uv-cache: false` (default) sauf si runner single-tenant.
- Combiner avec un outil StepSecurity (`harden-runner`) si déploiement entreprise.

---

## 8. Maintenance OSS — fichiers et processus

### 8.1 Fichiers obligatoires v1.0

- **`LICENSE`** : Apache-2.0.
- **`README.md`** : voir §9 pour le contenu attendu.
- **`CHANGELOG.md`** : format [Keep a Changelog](https://keepachangelog.com/), section `## [Unreleased]` toujours présente.
- **`CONTRIBUTING.md`** : setup local (uv, ruff, ty, pytest), conventions de commit (Conventional Commits), processus de PR, comment lancer les tests.
- **`CODE_OF_CONDUCT.md`** : Contributor Covenant 3.0.
- **`SECURITY.md`** : instructions pour utiliser le **GitHub Private Vulnerability Reporting** natif (onglet *Security* → *Report a vulnerability*). Délai de réponse cible : 7 jours. Pas d'email exposé, pas de GPG key requise.
- **`CODEOWNERS`** : `.github/CODEOWNERS` avec au moins un mainteneur sur chaque chemin sensible (`action.yml`, `src/ci_vibe/`, `prompts/`).

### 8.2 Templates GitHub

- `.github/ISSUE_TEMPLATE/bug_report.yml` (formulaire structuré : version, mode utilisé, workflow snippet, logs).
- `.github/ISSUE_TEMPLATE/feature_request.yml`.
- `.github/ISSUE_TEMPLATE/config.yml` : `blank_issues_enabled: false`, contact link vers `SECURITY.md` pour les vulnerabilities.
- `.github/pull_request_template.md` : checklist (tests passent, CHANGELOG mis à jour, doc mise à jour).

### 8.3 Branch protection sur `main`

- Required reviews : 1 mainteneur.
- Required status checks : `ci`, `dogfood`, `actionlint`.
- Linear history requise.
- Signed commits requis pour les mainteneurs (commit signing setup dans `CONTRIBUTING.md`).

---

## 9. README — sections obligatoires

1. **Badges** : CI status, latest release, marketplace, license.
2. **TL;DR** : un workflow de 10 lignes qui marche.
3. **Quickstart** : prérequis (clé API), copy-paste d'un workflow pour `review`.
4. **Usage par mode** : un exemple complet pour `review`, `security`, `triage`, `custom`.
5. **Reference complète des inputs/outputs** : tableau avec defaults.
6. **Modèles supportés** : liste, recommandations (Medium 3.5 par défaut, Devstral pour cost-conscious).
7. **AGENTS.md** : comment l'utiliser pour customiser le style/les conventions.
8. **Sécurité** : pointage vers `SECURITY.md`, recommandations clés.
9. **Coût** : estimation par run selon mode (review ~ $0.10–0.30, security ~ $0.50–1.50).
10. **FAQ / Troubleshooting**.
11. **Comparaison avec `anthropics/claude-code-action`** : tableau honnête (non, ce n'est pas le même modèle, oui c'est moins cher, etc.).
12. **Contributing** : lien vers `CONTRIBUTING.md`.
13. **License**.

---

## 10. CI/CD du repo

### 10.1 `ci.yml` — sur push et PR

Jobs (en parallèle quand possible) :

- **`lint`** : `uv run ruff check .` + `uv run ruff format --check .` (lint + format check, stack Astral).
- **`typecheck`** : `uv run ty check` (type-checker Astral, preview en 2026 — fallback `--exit-zero` possible si trop instable, à juger pendant l'implémentation).
- **`test`** : `uv run pytest` sur `tests/`. Matrice Python : `3.12`, `3.13` si stable.
- **`action-lint`** : [`actionlint`](https://github.com/rhysd/actionlint) sur `action.yml` et tous les workflows.
- **`md-lint`** : `markdownlint-cli2` sur `*.md` et `prompts/*.md`.
- Matrice OS : `ubuntu-22.04`, `ubuntu-24.04` (Python est cross-platform donc on couvre les deux pour détecter les régressions runner).

**Outils retirés** vs. spec d'origine :

- `shellcheck`, `shfmt`, `bats-core` : plus pertinents — aucun script bash custom (les quelques lignes inline dans `action.yml` sont triviales et couvertes par `actionlint`).
- `mypy`, `black`, `flake8` : remplacés par `ty` et `ruff`.

### 10.2 `dogfood.yml` — l'action s'auto-applique

- Sur chaque PR du repo, exécute l'action en mode `review` sur la PR elle-même.
- Sur chaque issue ouverte, exécute `triage`.
- Validation immédiate qu'une régression est détectable.
- Requiert un secret `MISTRAL_API_KEY` au niveau du repo (compte dédié, faible budget).

### 10.3 `release.yml` — sur push de tag `v*.*.*`

- Génère les release notes via `release-drafter` ou Conventional Commits.
- Publie la release GitHub.
- Met à jour le marketplace (auto si action publiée).
- Trigger `major-tag.yml`.

### 10.4 `major-tag.yml`

- Force-push de `v1` vers le tag annotated qui vient d'être publié (si la version est `v1.x.y`).
- Pareil pour `v2` à terme.

---

## 11. Dependabot

`.github/dependabot.yml` :

```yaml
version: 2
updates:
  # Actions GitHub utilisées dans nos workflows internes
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "github-actions"
    commit-message:
      prefix: "chore(deps)"

  # Actions GitHub utilisées dans les workflows d'exemples
  - package-ecosystem: "github-actions"
    directory: "/examples"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "examples"

  # Dev deps Python (ruff, ty, pytest) — déclarées dans pyproject.toml
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "python"
```

**Note Dependabot + uv** : Dependabot `pip` lit `[project.dependencies]` et `[project.optional-dependencies]` du `pyproject.toml`. Pour que les dev deps soient bumpées automatiquement, on les déclare en `[project.optional-dependencies.dev]` (PEP 621, supporté) plutôt qu'en `[dependency-groups]` (PEP 735, non supporté par Dependabot début 2026). À évaluer pendant l'init.

**Particularité importante** : `mistral-vibe` lui-même n'est **pas** géré par Dependabot (il est pinné dans `action.yml` en argument de `uv run --with`, pas dans `pyproject.toml`). Il faut donc un job **`update-vibe-version.yml`** dédié (v0.2+) :

- Tourne chaque lundi (`schedule: cron`).
- Query l'API GitHub releases de `mistralai/mistral-vibe` pour la dernière version stable.
- Si différente du pin par défaut dans `action.yml`, ouvre une PR.
- La PR déclenche `dogfood.yml`, qui valide que la nouvelle version ne casse rien.

---

## 12. Stratégie de release

- **Versionnage** : SemVer 2.0.0.
- **Tags** : `v1.0.0`, `v1.0.1`, …
- **Floating major tag** : `v1` re-pointé après chaque release non-breaking.
- **Breaking changes** : majeure incrémentée, jamais sans entrée dans `CHANGELOG.md` + section "Migration" dans le README.
- **Pre-releases** : `v1.0.0-rc.1` pour les RC, testées via le repo dogfood pendant ≥ 1 semaine avant promotion.
- **Marketplace** : publication officielle à partir de `v1.0.0`.

---

## 13. Roadmap

| Version | Contenu | Critère de sortie |
|---------|---------|-------------------|
| `v0.1.0` | MVP : `mode: review` uniquement, module Python `ci_vibe`, prompt minimal, doc README basique. | `ci.yml` vert (ruff + ty + pytest + actionlint + markdownlint) + 1 smoke test e2e manuel sur une PR factice sur `clemparpa/ci-vibe`. |
| `v0.2.0` | Ajout `mode: security`, prompt SAST-style adapté de claude-code-security-review. | Faux positifs < 30% sur un set de 10 PRs annotées manuellement. |
| `v0.3.0` | Ajout `mode: triage`, label suggestion via `gh issue edit`. | Labels suggérés cohérents sur 20 issues réelles. |
| `v0.4.0` | `mode: custom`, support `agents-md-path`, hooks pre/post via `vibe-args`. | Doc utilisateur complète, ≥ 3 utilisateurs externes confirment usage. |
| `v0.5.0` | `fail-on-findings`, outputs structurés, SARIF upload optionnel. | Intégration avec Code Scanning testée. |
| **`v1.0.0`** | API stable, marketplace publié, security audit interne, comparaison documentée vs claude-code-action. | Voir §14. |

---

## 14. Critères d'acceptation v1.0

- [ ] Tous les fichiers OSS obligatoires présents et à jour (`LICENSE`, `README`, `CHANGELOG`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `CODEOWNERS`).
- [ ] CI verte (`ci.yml`, `dogfood.yml`) depuis ≥ 30 jours sans rollback.
- [ ] README documente les 4 modes avec exemples copy-pastable testés.
- [ ] `actionlint`, `shellcheck`, `markdownlint`, `shfmt`, `bats-core` tous en passing.
- [ ] Dependabot actif et au moins une PR mergée.
- [ ] `update-vibe-version.yml` a tourné au moins 2 fois sans intervention.
- [ ] Branch protection active sur `main` avec required reviews et required checks.
- [ ] `SECURITY.md` testé : un report fictif a reçu réponse en < 7 jours.
- [ ] Au moins 3 utilisateurs externes (hors mainteneurs) ont consommé l'action sur leurs repos.
- [ ] Publication marketplace effective.
- [ ] Coût moyen par mode documenté avec données réelles (≥ 50 runs).

---

## 15. Décisions enregistrées et questions ouvertes

### Décisions prises (Étape 0)

1. **Nom du repo** : `clemparpa/ci-vibe`. Transfert futur envisagé vers l'org `flush` (à créer).
2. **Organisation GitHub** : compte perso `clemparpa` d'abord. Transfert vers org `flush` plus tard, après v0.1.0 minimum.
3. **Sécurité** : utilisation du **GitHub Private Vulnerability Reporting** natif. Pas d'email de contact exposé.
4. **Dogfood** : différé à v0.2+. Pas de workflow `dogfood.yml` en v0.1.
5. **Politique de support des versions Vibe** : **dernière version stable uniquement** en v0.x. La règle « dernière + n-1 » sera évaluée à partir de v1.0.

### Décisions prises (Pivot v1.1 de la spec)

1. **Implémentation : Python** au lieu de bash. Déclencheur : la lib `mistral-vibe` expose une API publique `from vibe.core import run_programmatic` (re-exportée, listée dans `__all__`). Bash aurait demandé 5 scripts + `envsubst` + `perl` + `sed`/`jq` ; Python rassemble la logique dans un module testable, avec stack trace lisible et tests `pytest`.
2. **Tooling Python = stack Astral** : `uv` (deps), `ruff` (lint + format), `ty` (type-check, en preview). Pas de `mypy`, pas de `black`, pas de `flake8`.
3. **`uv run --no-project --with mistral-vibe==<pin>`** au lieu d'épingler Vibe dans `pyproject.toml`. Pattern repris d'OpenHands. Permet le versioning indépendant via input `vibe-version`.
4. **Inspirations OpenHands** intégrées : préflight permission check, `enable-uv-cache: false` par défaut, recommandation `persist-credentials: false`. Pas intégrés en v0.1 : A/B testing modèles, inline review comments, sub-agents, Laminar observability.

### Questions encore ouvertes

1. **SARIF output** : reporter dans le mode security pour intégrer GitHub Code Scanning ? Forte valeur ajoutée, coût d'implémentation moyen. À trancher pour la v0.5 (cf. roadmap §13).
2. **Self-hosted runner support** : documenté ou explicitement non supporté en v1 ? À trancher après le premier feedback utilisateur externe.

---

## 16. Références

- [Mistral Vibe — repo](https://github.com/mistralai/mistral-vibe)
- [Mistral Vibe — docs agents & skills](https://docs.mistral.ai/mistral-vibe/agents-skills)
- [`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action) — référence de design
- [`anthropics/claude-code-security-review`](https://github.com/anthropics/claude-code-security-review) — référence pour le prompt SAST
- [AGENTS.md spec](https://agents.md/)
- [GitHub Actions — creating composite actions](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
- [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
