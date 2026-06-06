# Architecture

Vue d'ensemble du fonctionnement interne de `meow-bot`. Pour le pas-à-pas de déploiement, voir [quickstart.md](quickstart.md). Pour la spec complète et les choix techniques, voir [../SPEC.md](../SPEC.md).

---

## 1. Vue d'ensemble

`meow-bot` est composé de **3 services locaux** (que le self-hoster fait tourner sur son VPS via `docker compose`) et de **2 services managés externes** (auxquels il s'abonne).

```text
                                                            ┌────────────────────┐
                                                            │  Mistral Workflows │
                                                            │      (managed)     │
                                                            └──────────┬─────────┘
                                                                       │
                                                       start_execution │  dispatch
                                                                       │
   ┌──────────┐   webhook    ┌──────────────┐ ──────────────────┐      │
   │  GitHub  │ ───────────▶ │  Caddy (TLS) │                   │      │
   │          │              └──────┬───────┘                   ▼      ▼
   │          │                     │ :8000        ┌─────────────────────────────┐
   │          │              ┌──────▼───────┐      │           Worker            │
   │          │              │   Receiver   │      │  (mistralai-workflows poll) │
   │          │              │   (FastAPI)  │      └────────────┬────────────────┘
   │          │              └──────────────┘                   │ spawn
   │          │                                                 ▼
   │          │                                       ┌──────────────────┐
   │          │                                       │  Koyeb Sandbox   │
   │          │                                       │  (meow-base img) │
   │          │                                       │   mistral-vibe   │
   │          │                                       └─────────┬────────┘
   │          │                                                 │
   │          │ ◀─────────── post comment ───────────────────────┘
   └──────────┘                                       (via githubkit, depuis le worker)
```

**Sur le VPS du self-hoster** : `caddy` + `receiver` + `worker`.
**Services managés externes** : Mistral Workflows (orchestration durable, retries, traces OTel) + Koyeb (sandboxes éphémères avec image custom `meow-base`).

---

## 2. Flow webhook end-to-end (`MENTION_REVIEW`)

Scénario : un mainteneur ouvre une PR et commente `@<bot-login> review` pour déclencher une review.

1. **GitHub émet le webhook.** Action `issue_comment.created`, body signé HMAC-SHA256 via `X-Hub-Signature-256`. Envoi vers `https://<MEOW_DOMAIN>/gh/webhook`.

2. **Caddy termine TLS** (cert Let's Encrypt auto-provisionné) et reverse-proxy vers `receiver:8000`.

3. **Le receiver valide et dispatche** ([src/meow/receiver/app.py](../src/meow/receiver/app.py)) :
   - `verify_signature` (HMAC SHA-256) via `githubkit`.
   - `parse` via `githubkit.webhooks` — modèle Pydantic typé (`WebhookIssueCommentCreated`).
   - Filtres : self-deliveries (`sender.login == MEOW_BOT_LOGIN`), events non gérés, actions hors scope.
   - Routage via le mécanisme `@on_event` ([src/meow/receiver/controllers/issue_comment.py](../src/meow/receiver/controllers/issue_comment.py)) : si le commentaire matche `@<bot> review` sur une PR, un handler renvoie un `IssueCommentInput` typé.

4. **Le receiver appelle Mistral Workflows** (`workflows.execute_workflow`, [src/meow/receiver/client.py](../src/meow/receiver/client.py)) avec l'ID de workflow `PR_REVIEW_WORKFLOW` et l'`IssueCommentInput` en payload. Idempotence assurée par un `execution_id` dérivé de `X-GitHub-Delivery`.

5. **Mistral Workflows persiste l'exécution** (history append-only, retries, durabilité) puis dispatche une tâche au worker via le mécanisme de polling.

6. **Le worker exécute `PrReviewWorkflow`** ([src/meow/worker/workflows/pr_review_handler.py](../src/meow/worker/workflows/pr_review_handler.py)). Le workflow lui-même ne fait pas d'I/O : il orchestre 4 activities séquentielles.

   1. `fetch_pr_context` — appelle l'API GitHub via `githubkit` (auth `AppInstallationAuthStrategy`), récupère diff + base_sha + head_sha.
   2. `fetch_meow_config` — pull le `.meow.yml` depuis la branche `base_sha` du repo. Defaults silencieux si absent ou malformé.
   3. `run_vibe` — provisionne une sandbox Koyeb à partir de l'image `meow-base`, monte `mistral-vibe` + un prompt task-spécifique, exécute `vibe.core.run_programmatic` sous les budgets `max_turns` / `max_price_usd`, capture le rapport, détruit la sandbox.
   4. `post_pr_comment` — POST le rapport en commentaire sur la PR via l'API GitHub.

7. **L'utilisateur voit le commentaire du bot** sur sa PR. Fin de l'exécution. Tout est journalisé côté Mistral Workflows (consultable via Mistral Studio).

---

## 3. Composants

### 3.1 Receiver (FastAPI)

- **Entrypoint** : [src/meow/receiver/__main__.py](../src/meow/receiver/__main__.py) → uvicorn binds `0.0.0.0:8000`.
- **Routes** :
  - `GET /healthz` — liveness probe (`{"status": "ok"}`).
  - `POST /gh/webhook` — webhook endpoint.
- **Doit répondre en < 10s** (timeout GitHub). Toute logique métier est déportée au worker.
- **Variables d'env consommées** : `GITHUB_WEBHOOK_SECRET`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `MISTRAL_API_KEY`, `DEPLOYMENT_NAME`, `MEOW_BOT_LOGIN`, `KOYEB_API_TOKEN`.
- **Pourquoi `KOYEB_API_TOKEN` côté receiver** : la `Settings` Pydantic est globale (DI unique), même si seul le worker l'utilise effectivement. Aucune fuite — la valeur n'est lue qu'au moment de spawn une sandbox.

### 3.2 Worker (Mistral Workflows worker)

- **Entrypoint** : [src/meow/worker/__main__.py](../src/meow/worker/__main__.py) → `workflows.run_worker([PrReviewWorkflow])`.
- **Long-running** : poll permanent contre le control plane Mistral. Idle quand rien à faire (≈ pas de coût CPU/RAM).
- **Workflows enregistrés** : `PrReviewWorkflow` (S10.5).
- **Activities** : `fetch_pr_context`, `fetch_meow_config`, `run_vibe`, `post_pr_comment` ([src/meow/worker/activities/](../src/meow/worker/activities/)).
- **Sandbox builder** : [src/meow/worker/sandbox/builder.py](../src/meow/worker/sandbox/builder.py) (wrapper SDK Koyeb).
- **Variables d'env consommées** : mêmes que le receiver, mais `KOYEB_API_TOKEN` est cette fois vraiment utilisé.

### 3.3 Caddy (reverse proxy + TLS)

- Image `caddy:2`. Lit `$MEOW_DOMAIN` depuis son env (injecté par compose).
- **TLS** : si `MEOW_DOMAIN` est un vrai FQDN avec un A record valide → certificat Let's Encrypt automatique. Si `MEOW_DOMAIN=localhost` → CA interne Caddy (utile pour smoke local).
- **Pas de logique au-delà du reverse_proxy** ([Caddyfile](../Caddyfile)).

### 3.4 Mistral Workflows (managé)

- Control plane externe (`api.mistral.ai`). Fournit : durabilité (replay sur crash), retries configurables par activity, traces OTel par exécution, et **Mistral Studio** (UI web pour inspecter les exécutions).
- Voir [documentations/mistral-workflows/](../documentations/mistral-workflows/) pour la doc complète.
- **Le `DEPLOYMENT_NAME` groupe receiver et worker(s)** d'une même instance. Plusieurs workers partageant le même `DEPLOYMENT_NAME` partagent leur task queue (scaling horizontal).

### 3.5 Koyeb Sandbox

- Sandbox éphémère provisionnée à la demande pour chaque activity `run_vibe`.
- **Image** : `meow-base`, construite et poussée sur GHCR par [.github/workflows/sandbox-image.yml](../.github/workflows/sandbox-image.yml) — contient Python 3.13, git, `gh` CLI, `mistral-vibe`, configs `.vibe/` minimales (cf. [src/meow/worker/sandbox/sandbox_files/](../src/meow/worker/sandbox/sandbox_files/)).
- **Lifecycle** : créée par le worker en début d'activity, détruite en fin d'activity (succès ou échec). Pas d'état persistant entre runs.

---

## 4. Volumes et secrets

| Hôte | Container | Mode | Contenu |
|---|---|---|---|
| `./secrets/github-app.pem` | `/secrets/github-app.pem` | read-only | Clé privée RSA de la GitHub App (signature des JWT) |
| `./data/` | `/data/` | read-write | Réservé pour un futur audit log local (S14 reportée — voir [stories/v0.1.0.md](../stories/v0.1.0.md)) |
| `caddy_data` (volume nommé) | `/data` (dans le container caddy) | read-write | Certificats Let's Encrypt persistés (survit aux `docker compose down`) |

Tous les autres secrets (Mistral API key, GitHub webhook secret, Koyeb token) transitent par `.env` lu par `docker-compose` au boot.

---

## 5. Pour creuser

- **Vision et choix techniques** → [SPEC.md §3](../SPEC.md), [SPEC.md §8](../SPEC.md) (workflows et activities en détail).
- **Threat model** → [SPEC.md §12](../SPEC.md).
- **Déploiement pas-à-pas** → [quickstart.md](quickstart.md).
- **Sécurité, vulnérabilités** → [../SECURITY.md](../SECURITY.md).
- **Contributions et développement parallèle** → [parallel-development.md](parallel-development.md).
