# Spec — `meow-bot`

> Statut : draft v0.2 · à itérer
> License : Apache-2.0
> Modèle de distribution : **OSS self-host, BYOK**

## 1. Objectif

`meow-bot` est un **collaborateur agentique GitHub** qui se comporte comme un membre d'équipe humain : on le tag dans une **issue** ou une **PR**, il répond, code, review.

Distribué comme un **projet OSS self-hostable**. Chaque utilisateur :

- crée sa propre GitHub App via un **manifest** fourni (flow en 1 clic),
- héberge le worker chez lui (`docker compose up`) sur n'importe quel VPS Docker-capable,
- fournit ses propres clés (Mistral, GitHub App, Daytona) — **BYOK strict**.

Aucun mode SaaS pour l'instant. Aucune dépendance vers un service hébergé par les mainteneurs. Pas de quotas, pas de billing, pas d'analytics centralisée.

### Principes

- **OSS-first** : tout le code, prompts, manifest, compose sont dans le repo. Apache-2.0.
- **BYOK** : zéro secret partagé entre instances. Chaque self-hoster paie ses appels.
- **Self-host friendly** : quickstart visé `< 15 min` pour un dev qui sait lancer Docker sur un VPS.
- **Durable** : un crash worker ou sandbox ne perd pas la tâche en cours (Mistral Workflows).
- **Isolation forte** : tout code généré ou exécuté tourne dans un sandbox Daytona éphémère, jamais sur l'hôte.
- **Read-only par défaut** : v0.1 ne modifie aucun repo. Les modes write arrivent plus tard, conditionnés à l'implémentation des budgets.
- **Pas de boucle** : le bot ne se répond jamais à lui-même.

### Non-objectifs (v0.x)

- GitLab/Bitbucket.
- GitHub Enterprise Server (à garder en tête pour plus tard — variable d'env, mais pas de tests).
- Multi-provider LLM (Mistral only).
- Cron proactif / RepoScanner (reporté à v0.5).
- Mode SaaS hébergé par les mainteneurs (peut-être un jour, sous-projet séparé).
- Daytona self-host (managé only).
- UI web, dashboard, métriques Prometheus.

## 2. Stack

| Couche | Choix | Pourquoi |
|---|---|---|
| Orchestration | `mistralai-workflows` (service managé Mistral) | Durabilité, cron futur, signals, retries. Le user a déjà un compte Mistral pour la clé LLM, le surcoût d'inscription est nul. |
| Agent codeur | `mistral-vibe` OSS en mode `vibe.core.run_programmatic` | Harness mature, Apache-2.0, API Python programmatique. |
| Sandbox | Daytona managé | Démarrage <100ms, snapshots, SDK Python. Self-host différé. |
| Webhook receiver | FastAPI minimal | Mince, juste valider HMAC + `start_execution`. |
| Worker | Process Python (`workflows.run_worker`) | Tourne 24/7, idle quand rien à faire. |
| Auth GitHub | GitHub App + JWT → installation tokens | Standard. |
| Hébergement | VPS Linux + Docker Compose | Simplicité, contrôle. |
| LLM | Mistral Medium 3.5 (par défaut, surchargeable) | — |
| Persistance | **Aucune en v0.1.** SQLite à partir de v0.2 pour les budgets. | YAGNI. |
| Python tooling | `uv`, `ruff`, `ty`, `pytest` (stack Astral) | Cohérent, rapide, moderne. |

## 3. Architecture

```mermaid
flowchart LR
    GH[GitHub] -->|webhook| RX[meow-receiver<br/>FastAPI]
    RX -->|start_execution| WF[Mistral Workflows<br/>managed]
    WF -.->|dispatch| W[meow-worker<br/>VPS du self-hoster]
    W -->|REST/GraphQL| GH
    W -->|spawn| DS[Daytona Sandbox<br/>éphémère]
    DS -->|vibe.core.run_programmatic| DS
```

Trois services à faire tourner soi-même (tout sur le même VPS) :

1. **`receiver`** — FastAPI exposé en HTTPS, reçoit les webhooks GitHub.
2. **`worker`** — process Python long-running, connecté au control plane Mistral Workflows.
3. **`caddy`** — reverse proxy + TLS automatique (Let's Encrypt).

Daytona et Mistral Workflows sont des **services managés externes** auxquels le self-hoster s'inscrit. Les sandboxes sont créés à la demande et détruits après usage.

## 4. Onboarding self-hoster

Cible : **un dev capable de lancer `docker compose up` sur un VPS, en moins de 15 minutes** d'effort.

### 4.1 Prérequis

- VPS Linux (Hetzner CX22 ~5€/mois suffit), Docker + Docker Compose installés.
- Un nom de domaine pointant sur le VPS (pour HTTPS du webhook).
- Comptes : **Mistral** (API key + Workflows), **Daytona** (API key).

### 4.2 Flow

1. **Cloner le repo** : `git clone https://github.com/clemparpa/meow-bot && cd meow-bot`.
2. **Créer la GitHub App via manifest** : cliquer sur le lien `Create my Meow App` du README. GitHub redirige vers une page qui crée l'App à partir de [`manifest/app-manifest.yml`](manifest/app-manifest.yml) (permissions, events, webhook URL pré-remplie). En retour : `app_id`, `private_key.pem`, `webhook_secret`.
3. **Renseigner `.env`** depuis `.env.example` :
   - `MEOW_DOMAIN`, `GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET`, `MISTRAL_API_KEY`, `DAYTONA_API_KEY`
   - Déposer `github-app.pem` dans `./secrets/`.
4. **Lancer** : `docker compose up -d`. Caddy obtient le certificat Let's Encrypt automatiquement.
5. **Installer l'App sur ses repos** depuis l'UI GitHub.
6. **Tester** : commenter `@<bot-login> review` sur une PR. Le bot répond.

### 4.3 GitHub App Manifest

Fichier [`manifest/app-manifest.yml`](manifest/app-manifest.yml) versionné dans le repo. Le README contient un lien du type :

```
https://github.com/settings/apps/new?manifest=<base64(JSON du manifest)>
```

Détails du flow : [GitHub docs — Registering a GitHub App from a manifest](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest).

**Le slug GitHub App est choisi par le self-hoster** (pas par nous) — il peut nommer son instance comme il veut. Par convention, on suggère `meow-bot` ou `<orgname>-meow`. Le `BOT_LOGIN` est lu depuis la GitHub API au démarrage (`GET /app`), pas hardcodé.

## 5. GitHub App — permissions & events v0.1

Profil minimal pour `REVIEW` read-only.

| Resource | Accès |
|---|---|
| Contents | **Read** (clone repo pour diff) |
| Issues | Read & write (commenter) |
| Pull requests | Read & write (commenter) |
| Metadata | Read (obligatoire) |

**Subscribed events :**

- `issue_comment` (pour détecter `@bot review`)
- `pull_request` (pour `opened`/`synchronize` futurs déclencheurs auto)
- `installation`, `installation_repositories` (lifecycle)

> **v0.2+ ajoutera** : `Contents: write` pour CODE_REQUEST, événements `discussion*`, `pull_request_review*`.

## 6. Webhook Receiver

Rôle : **recevoir, valider, dispatcher**. Aucune logique métier.

```python
@app.post("/gh/webhook")
async def webhook(request: Request):
    body = await request.body()
    verify_hmac(request.headers["X-Hub-Signature-256"], body, WEBHOOK_SECRET)
    event = request.headers["X-GitHub-Event"]
    payload = json.loads(body)

    if payload.get("sender", {}).get("login") == bot_login():
        return {"skipped": "self"}
    if event not in HANDLED_EVENTS:
        return {"skipped": "event"}

    workflow_id = build_idempotent_id(event, payload)
    await mistral.workflows.executions.start(
        name="github_event_handler",
        id=workflow_id,
        input={"event": event, "payload": payload},
    )
    return {"queued": True}
```

Doit répondre **<10s** sous peine de timeout GitHub.

**`HANDLED_EVENTS` en v0.1** : `issue_comment`, `installation`, `installation_repositories`.

## 7. Worker

Process Python qui appelle `workflows.run_worker(...)`.

```python
async def main():
    await workflows.run_worker(
        workflows=[GithubEventHandler, InstallLifecycle],
        activities=[
            fetch_pr_context,
            run_review_in_sandbox,
            post_pr_comment,
            register_installation,
        ],
    )
```

Scaling : 1 replica suffit pour un self-host individuel. À terme, N replicas se partagent la charge via le control plane Mistral (Temporal dessous).

## 8. Workflows et activities — v0.1

### 8.1 `GithubEventHandler`

Seul intent v0.1 : **`MENTION_REVIEW`** déclenché par un commentaire de la forme `@<bot-login> review` sur une **PR** (issue commentée qui a un `pull_request` field).

```
input: { event: "issue_comment", payload: {...} }

steps:
  1. intent = parse_mention(payload.comment.body)
       → MENTION_REVIEW si match `@<bot-login>\s+review\b`
       → IGNORE sinon
  2. si IGNORE → exit
  3. ctx = fetch_pr_context(repo, pr_number, installation_id)
       → diff, fichiers modifiés, .meow.yml du repo cible
  4. result = run_review_in_sandbox(repo, ctx, cfg)
       → spawn Daytona, clone repo (read-only token), lance vibe en mode read-only
       → renvoie un rapport markdown
  5. post_pr_comment(repo, pr_number, result.report)
```

**Pas de classifier LLM en v0.1** : un simple regex sur le corps du commentaire suffit pour 1 seul intent. Le classifier (Mistral Small) sera introduit en v0.2 quand on aura ≥2 intents conversationnels.

**Idempotence** : `workflow_id = f"issue_comment-{repo}-{comment_id}"`. Un retry GitHub réutilise le même ID, Mistral Workflows déduplique.

### 8.2 `InstallLifecycle`

Déclenché sur `installation.created` / `installation_repositories.added` / `installation.deleted`.

v0.1 : se contente de **logger** l'événement dans le journal d'audit (cf §13). Pas de persistance (la liste des installations est requérable à la volée via `GET /app/installations`).

v0.2+ : créera les schedules `RepoScanner` (cron proactif) par installation.

### 8.3 Activities

| Activity | Effet | Retries |
|---|---|---|
| `fetch_pr_context` | Charge PR + diff + `.meow.yml` via PyGithub | 3, exp backoff |
| `run_review_in_sandbox` | **Spawn Daytona + clone + `vibe.core.run_programmatic` read-only + capture rapport** | 1, non-idempotent |
| `post_pr_comment` | POST commentaire via GitHub API (scrubbing secrets en amont) | 5, idempotence par hash du body |
| `register_installation` | Log dans `events.jsonl` | 3 |

### 8.4 Activity clé : `run_review_in_sandbox`

```python
@workflows.activity.defn
async def run_review_in_sandbox(
    repo: str,
    pr_number: int,
    installation_id: int,
    cfg: RepoConfig,  # vient de .meow.yml
) -> ReviewResult:
    token = mint_installation_token(installation_id, repo, permissions={"contents": "read"})
    prompt = render_template("review.md", pr_diff=cfg.diff, agents_md=cfg.agents_md)

    async with daytona.create(snapshot="meow-base") as sandbox:
        await sandbox.exec(f"git clone https://x-access-token:{token}@github.com/{repo} /work")
        await sandbox.exec(f"gh pr checkout {pr_number}", cwd="/work")
        result = await sandbox.run_python(
            "from vibe.core import run_programmatic; "
            "from vibe.core.config import VibeConfig; "
            "print(run_programmatic(config=VibeConfig(...), prompt=PROMPT, "
            f"max_turns={cfg.max_turns}, max_price={cfg.max_price}, "
            f"allowed_tools={REVIEW_PROFILE.tools}))"
        )
    return ReviewResult.parse(result.stdout)
```

`start_to_close_timeout` côté workflow : **35 min**. **Pas de retry automatique**.

### 8.5 Snapshot Daytona `meow-base`

Pré-construit, contient :

- Ubuntu + Python 3.13 + git + `gh` CLI
- `mistral-vibe` installé en venv système
- Pré-configuration `.vibe/` minimale

Auto-pause à **30 secondes** (vs 15 min default).

## 9. Profils d'intent — sécurité par action

Chaque intent a un **profil** qui contraint les outils Vibe activés. Pour v0.1, un seul profil :

| Profil | Intent | Allowed tools | Write au repo ? |
|---|---|---|---|
| `READ_ONLY` | `MENTION_REVIEW` | `read_file`, `grep`, `bash` (read-only) | Non — commentaire de PR uniquement |

Profils prévus pour les versions suivantes (non implémentés en v0.1) :

| Profil | Intent futur | Allowed tools | Write au repo ? |
|---|---|---|---|
| `WRITE_BRANCH` | `CODE_REQUEST` | `read_file`, `write_file`, `grep`, `bash` | Oui, sur une **nouvelle branche** uniquement, jamais sur la default. PR ouverte pour review humaine. |
| `SECURITY_SAST` | `SECURITY_REVIEW` | `read_file`, `grep` (pas de `bash`) | Non |

Le profil est **hardcodé par intent** dans le code, pas configurable côté repo (sécurité par construction).

## 10. Configuration repo cible : `.meow.yml`

Fichier optionnel à la racine du repo cible. Tous les champs ont un default sain. **Aucune configuration n'est requise pour utiliser le bot.**

```yaml
# .meow.yml — configuration meow-bot (v0.1)

# Modèle Mistral utilisé pour les invocations Vibe sur ce repo
model: mistral-medium-3.5

# Garde-fous coût/turn par invocation
max_turns: 15
max_price_usd: 0.50

# Langue de réponse du bot. "auto" → détectée depuis le thread.
language: auto

# Chemin vers AGENTS.md à injecter dans le contexte Vibe (cf convention agents.md).
# Empty = désactivé.
agents_md_path: AGENTS.md

# Globs exclus de l'analyse de diff (review mode).
exclude_paths:
  - "vendor/**"
  - "**/*.lock"
  - "**/generated/**"
```

**Philosophie** : config minimale, defaults sains. On ajoute des clés au fil des modes (`review.tone`, `triage.label_suggestions`, etc.). Toute clé inconnue → warning au démarrage du workflow, pas d'erreur fatale.

Parsing : pydantic, validation stricte des types. Chargé depuis la branche **default** du repo (pas de la PR, pour éviter qu'un PR malveillant change la config qui s'applique à elle-même).

## 11. Authentification GitHub App

Flow standard à trois étages :

1. **App Private Key** — montée depuis `/secrets/github-app.pem` (read-only) dans le worker.
2. **JWT** signé avec la private key (10 min TTL).
3. **Installation token** obtenu en échangeant le JWT, scopé à l'installation cible (1h TTL).

```python
def installation_token(installation_id: int, permissions: dict | None = None) -> str:
    cached = _cache.get((installation_id, freeze(permissions)))
    if cached and cached.expires_at > now() + 60:
        return cached.token
    jwt = make_jwt(app_id=APP_ID, private_key=APP_KEY, ttl=600)
    resp = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"permissions": permissions} if permissions else {},
    )
    token, exp = resp.json()["token"], resp.json()["expires_at"]
    _cache[(installation_id, freeze(permissions))] = CachedToken(token, parse_dt(exp))
    return token
```

**Best practice** : pour `run_review_in_sandbox`, on **down-scope** le token à `{"contents": "read"}` quand on appelle `access_tokens`. Le sandbox ne peut alors ni commenter ni push, même si Vibe est compromis par prompt injection.

## 12. Sécurité

### 12.1 Loop prevention

- Filtre `sender.login == bot_login()` au niveau du receiver, **avant** d'invoquer le workflow.
- v0.2+ : budget par thread (max 5 réponses/24h dans un même thread) en SQLite.

### 12.2 Validation webhook

HMAC-SHA256 sur le body avec `GITHUB_WEBHOOK_SECRET`, comparaison constante-time (`hmac.compare_digest`). Rejet 401 sinon.

### 12.3 Sandbox

- Pas de mounting de secrets de l'hôte dans le sandbox.
- Seul un **installation token down-scopé** (`contents: read` en v0.1) est passé, valable 1h.
- `max_turns` et `max_price` toujours fournis à `run_programmatic`.
- v0.x+ : whitelist d'égress (registries de packages + `api.github.com` + `api.mistral.ai`).

### 12.4 Modèle de menace v0.1

Surface réduite parce que tout est read-only :

| Menace | Mitigation |
|---|---|
| Prompt injection via diff PR fork | (a) Read-only ; le bot peut au pire poster un commentaire bizarre. (b) Sanitisation Unicode du diff (zero-width, bidi overrides, BOM) côté `fetch_pr_context`. |
| Exfiltration via `bash` | Sandbox Daytona isolé, pas de secrets de l'hôte montés, token GH scopé `contents: read`. Egress whitelist v0.x+. |
| Burn de tokens Mistral du self-hoster | `max_turns` + `max_price` cappés (defaults : 15 turns / $0.50). Budgets par thread arrivent v0.2. |
| Loop bot↔bot | Filtre `sender.login` au receiver. |
| Webhook spoofing | HMAC obligatoire. |

### 12.5 Lifting des modes write (v0.2+)

Les modes write (`CODE_REQUEST`) ne sont **pas** introduits sans :
- Budgets par thread implémentés (anti-spam).
- Token down-scopé à `contents: write` seulement sur la nouvelle branche.
- Recommandation explicite dans le README : **activer la branch protection sur la default branch**.
- Sanitization étendue (commit messages, noms de branches).

## 13. Observabilité

### 13.1 Logs structurés stdout

Tous les services émettent du JSON ligne-par-ligne sur stdout. Visualisation via `docker compose logs -f`.

```json
{"ts":"2026-05-20T10:11:12Z","svc":"receiver","level":"info","event":"webhook.received","gh_event":"issue_comment","action":"created","repo":"foo/bar","delivery":"abcd-1234"}
```

### 13.2 Journal d'audit append-only

Fichier `./data/events.jsonl` monté en volume dans le worker. **Append-only**, jamais rotaté par l'app (à la charge du self-hoster).

Schéma :

```json
{"ts":"...","installation_id":12345,"repo":"foo/bar","actor":"alice","intent":"MENTION_REVIEW","pr":42,"turns":8,"cost_usd":0.12,"status":"ok"}
```

Un event par invocation terminée (succès ou échec). Permet de relire l'historique en local sans dépendre de Mistral Studio. Suffit aussi pour les budgets en v0.2 (read-back du fichier au démarrage, puis SQLite quand le volume devient gênant).

### 13.3 Mistral Studio

Le control plane Mistral Workflows fournit déjà l'historique détaillé des exécutions, le replay, les retries. Pas de surcouche à construire.

## 14. Comportement quand `max_price` ou `max_turns` est atteint

Vibe s'arrête. L'activity `run_review_in_sandbox` **rapporte ce qui a été produit jusqu'ici** (rapport partiel) + un flag `terminated_early: true` avec la raison.

`post_pr_comment` ajoute alors un **header explicite** au début du commentaire :

```markdown
> Note : analyse interrompue (budget atteint : max_price=$0.50). Le rapport ci-dessous est partiel.
```

Pas d'erreur silencieuse, pas de retry coûteux.

## 15. Déploiement

### 15.1 `compose.yml`

```yaml
services:
  receiver:
    build:
      context: .
      target: receiver
    env_file: .env
    restart: always
    expose: ["8000"]
    volumes:
      - ./secrets:/secrets:ro
      - ./data:/data

  worker:
    build:
      context: .
      target: worker
    env_file: .env
    restart: always
    volumes:
      - ./secrets:/secrets:ro
      - ./data:/data

  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    restart: always

volumes:
  caddy_data:
```

### 15.2 `Caddyfile`

```
{$MEOW_DOMAIN} {
  reverse_proxy receiver:8000
}
```

TLS automatique via Let's Encrypt.

### 15.3 Secrets

Montés read-only dans `/secrets/` :

- `github-app.pem` — clé privée de l'App.
- `.env` — `MISTRAL_API_KEY`, `DAYTONA_API_KEY`, `GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET`, `MEOW_DOMAIN`.

### 15.4 Sizing recommandé

VPS modeste : **2 vCPU / 4 Go RAM** (Hetzner CX22 ~5€/mois). Le worker est I/O bound — l'essentiel du travail tourne chez Daytona.

## 16. Structure du repo

```text
meow-bot/
├── compose.yml
├── Caddyfile
├── Dockerfile                       # multi-stage avec targets `receiver` et `worker`
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
├── LICENSE                          # Apache-2.0
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── SPEC.md                          # ce fichier
├── manifest/
│   └── app-manifest.yml             # GitHub App manifest pour le flow 1-clic
├── prompts/
│   └── review.md
├── src/
│   └── meow/
│       ├── __init__.py
│       ├── common/
│       │   ├── config.py            # env vars + .meow.yml parsing (pydantic)
│       │   ├── logging.py           # JSON structured + events.jsonl writer
│       │   ├── github/
│       │   │   ├── auth.py          # JWT + installation token cache
│       │   │   ├── api.py           # PyGithub wrappers
│       │   │   └── webhook.py       # HMAC verification
│       │   └── secrets.py           # scrubbing patterns (Mistral key, gh_* tokens)
│       ├── receiver/
│       │   ├── __main__.py          # uvicorn entry
│       │   └── app.py               # FastAPI routes
│       └── worker/
│           ├── __main__.py          # workflows.run_worker entry
│           ├── workflows/
│           │   ├── github_event_handler.py
│           │   └── install_lifecycle.py
│           ├── activities/
│           │   ├── fetch_pr_context.py
│           │   ├── run_review_in_sandbox.py
│           │   ├── post_pr_comment.py
│           │   └── register_installation.py
│           └── sandbox/
│               └── daytona.py       # wrapper SDK Daytona
├── docs/
│   ├── quickstart.md                # le quickstart 15-min
│   ├── self-hosting.md              # tuning, backups, troubleshooting
│   └── architecture.md              # diagrammes, decision records
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                   # ruff + ty + pytest
│   │   └── dogfood.yml              # le bot review ses propres PRs (v0.1.1+)
│   ├── dependabot.yml
│   ├── CODEOWNERS
│   └── ISSUE_TEMPLATE/
└── tests/
    ├── conftest.py
    ├── fixtures/
    └── ...
```

## 17. Roadmap

| Version | Périmètre | Critère de sortie |
|---|---|---|
| `v0.0.x` | Scaffold : compose qui boot, receiver qui valide HMAC et log, manifest App fonctionnel. | `curl` un webhook factice signé → 200 + log JSON. |
| **`v0.1.0`** | **`MENTION_REVIEW` end-to-end** : `@bot review` sur une PR → rapport posté. Read-only. `events.jsonl`. Quickstart doc. | Dogfood : meow-bot review ses propres PRs sans intervention manuelle pendant 1 semaine. |
| `v0.2.0` | Classifier Mistral Small (préparation multi-intents). Budgets par thread (SQLite introduit). Intent `MENTION_QUESTION` (Q&A sur le repo, read-only). | Bot ne loop pas sur lui-même même en cas de provocation. |
| `v0.3.0` | Intent `CODE_REQUEST` (profil `WRITE_BRANCH`). Token down-scopé `contents: write`. Branch protection recommandée doc. Sanitization étendue. | Une PR fonctionnelle ouverte par le bot, mergeable. |
| `v0.4.0` | Intent `TRIAGE` (issues ouvertes). Profil `READ_ONLY` + labels. | Labels suggérés cohérents sur 20 issues réelles du dogfood. |
| `v0.5.0` | `RepoScanner` cron proactif, opt-in via `.meow.yml`. | Pas de faux positifs gênants sur 1 mois de dogfood. |
| `v1.0.0` | API stable, doc complète, ≥ 3 users externes confirment usage, marketplace listing optionnel. | Voir §19. |
| `v2.x` (?) | Mode SaaS expérimental (sous-projet séparé). | À évaluer. |

## 18. Tests & dogfood

- **Unit / intégration** : `pytest` sur les modules `common/*` et `workflows/*` avec mocks pour Mistral Workflows et Daytona. CI verte requise pour merge.
- **Dogfood** : dès v0.1, l'instance officielle (hébergée par le mainteneur) est installée sur `clemparpa/meow-bot`. Workflow `.github/workflows/dogfood.yml` n'est **pas nécessaire** (c'est le bot lui-même qui s'auto-applique via webhooks). Si une régression échappe au CI, elle se voit sur la prochaine PR.
- **Smoke e2e** : checklist manuelle (~10 min) avant chaque release tag, documentée dans [docs/release.md](docs/release.md) à créer.

## 19. Critères d'acceptation v1.0

- [ ] Fichiers OSS obligatoires complets et à jour (`LICENSE`, `README`, `CHANGELOG`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `CODEOWNERS`, `SPEC`).
- [ ] CI verte (`ci.yml`) ≥ 30 jours sans rollback.
- [ ] README documente le quickstart 15-min testé sur VPS vierge.
- [ ] App manifest validé : un nouvel utilisateur peut créer son App + lancer le worker en < 15 min.
- [ ] Profils `READ_ONLY` et `WRITE_BRANCH` opérationnels avec down-scoping de token.
- [ ] Budgets par thread fonctionnels (anti-loop, anti-burn).
- [ ] Dogfood actif sur le repo officiel depuis ≥ 60 jours.
- [ ] ≥ 3 self-hosters externes ont signalé une instance opérationnelle.
- [ ] SECURITY.md testé : un report fictif a reçu réponse < 7 jours.

## 20. Questions encore ouvertes

- **Repo : compte perso ou org `flush` ?** Pour l'instant `clemparpa/meow-bot`. Transfert envisagé après v0.1.
- **Versioning de `mistral-vibe`** : pin strict dans le Dockerfile vs floating ? Le repo dogfood servira de canary.
- **Sub-issues / draft PRs** : faut-il les traiter différemment ? Probablement skip silencieux en v0.1.
- **Multi-langues du bot** : le `.meow.yml` expose `language: auto`. La détection effective (LLM ? heuristique simple ?) reste à décider à l'implémentation.
- **Mode SaaS futur** : si jamais on le fait, sous-projet séparé (`meow-cloud` ?) pour ne pas polluer le core OSS.

---

*Document vivant — itérer librement au fil des décisions.*
