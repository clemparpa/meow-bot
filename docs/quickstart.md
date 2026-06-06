# Quickstart

> Cible : passer d'un VPS vierge à `@<bot> review` qui répond sur une vraie PR, en ~30 minutes la première fois (puis ~10 min les fois suivantes une fois les comptes externes créés).

Ce guide vise un développeur à l'aise en ligne de commande mais pas forcément DevOps. On t'accompagne sur le provisioning, le DNS, et la création de la GitHub App.

Pour la vue d'ensemble du fonctionnement, voir [architecture.md](architecture.md). Pour la spec complète, voir [../SPEC.md](../SPEC.md).

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Provisionner le VPS](#2-provisionner-le-vps)
3. [Cloner et préparer le repo](#3-cloner-et-préparer-le-repo)
4. [Créer la GitHub App](#4-créer-la-github-app-flow-manifest)
5. [Provisionner Mistral Workflows](#5-provisionner-mistral-workflows)
6. [Provisionner Koyeb](#6-provisionner-koyeb)
7. [Configurer `.env`](#7-configurer-env)
8. [Récupérer le bot login](#8-récupérer-le-bot-login)
9. [Lancer le stack](#9-lancer-le-stack)
10. [Installer l'App sur un repo de test](#10-installer-lapp-sur-un-repo-de-test)
11. [Premier `@<bot> review`](#11-premier-bot-review)
12. [Troubleshooting](#12-troubleshooting)
13. [Mises à jour et désinstallation](#13-mises-à-jour-et-désinstallation)

---

## 1. Prérequis

### 1.1 Comptes externes à créer (gratuits ou ~5€/mois)

| Service | Pour quoi faire | Coût indicatif |
|---|---|---|
| **GitHub** | Créer la GitHub App qui représente ton bot | Gratuit |
| **Mistral** ([console.mistral.ai](https://console.mistral.ai)) | API key LLM + Workflows orchestration | Pay-as-you-go (Medium 3.5 ≈ $0.002 par review courte) |
| **Koyeb** ([app.koyeb.com](https://app.koyeb.com)) | API token pour sandboxes éphémères | Free tier (50h/mois de sandbox sur la base de la doc Koyeb actuelle — vérifier) |
| **VPS provider** (Hetzner / DigitalOcean / OVH / etc.) | Héberger les 3 services Docker | ~5€/mois (Hetzner CX22) |
| **Registrar DNS** (où ton domaine est enregistré) | Pointer un sous-domaine vers le VPS | Coût du domaine seul (~10€/an) |

### 1.2 VPS

Recommandation testée : **Hetzner Cloud CX22** (2 vCPU x86, 4 Go RAM, 40 Go SSD, ~5€/mois). Ubuntu 24.04 LTS comme image de base.

Toute autre offre équivalente fonctionne : DigitalOcean Droplet 4Go, OVH VPS, Scaleway DEV1-M, etc. Critères :

- **AMD64 ou ARM64** (les images Docker meow-bot sont multi-arch).
- **≥ 2 vCPU, ≥ 2 Go RAM** (le worker est I/O-bound, le gros du travail tourne chez Koyeb).
- **Docker installable** (Debian 12, Ubuntu 22.04/24.04 OK).
- **IP publique + ports 80/443 ouverts**.

### 1.3 Domaine + A record DNS

Tu as besoin d'un FQDN qui pointe vers l'IP publique du VPS — sans ça, pas de HTTPS, donc pas de webhook GitHub.

**Étapes** (varient selon ton registrar — exemple Cloudflare) :

1. Identifie l'IP publique de ton VPS (affichée dans le dashboard du provider).
2. Connecte-toi à ton registrar (Cloudflare, OVH, Gandi, Namecheap, etc.).
3. Crée un enregistrement DNS :
   - **Type** : `A`
   - **Name** : `meow` (par exemple → produira `meow.ton-domaine.com`) ou `@` pour la racine.
   - **Value** : IP publique du VPS.
   - **TTL** : auto (5 min par défaut OK).
4. Sauvegarde et attends la propagation (souvent < 5 min, jusqu'à 1h dans le pire cas).

Vérifie depuis ta machine :

```bash
dig +short meow.ton-domaine.com
# devrait afficher l'IP du VPS
```

> **Tip** : pour le smoke initial, tu peux utiliser un sous-domaine jetable comme `meow.<truc>.duckdns.org` (gratuit) si tu n'as pas encore de domaine perso.

---

## 2. Provisionner le VPS

### 2.1 SSH initial et hardening basique

Après création du VPS :

```bash
ssh root@<IP_DU_VPS>
```

Au premier login, configure un user non-root pour le quotidien :

```bash
adduser meow
usermod -aG sudo meow
# Optionnel mais fortement recommandé : copier ta clé SSH
mkdir -p /home/meow/.ssh
cp ~/.ssh/authorized_keys /home/meow/.ssh/
chown -R meow:meow /home/meow/.ssh
chmod 700 /home/meow/.ssh
chmod 600 /home/meow/.ssh/authorized_keys
```

Désactive le login root par mot de passe (édite `/etc/ssh/sshd_config`) :

```text
PermitRootLogin no
PasswordAuthentication no
```

Puis :

```bash
systemctl restart sshd
exit
# Re-login en tant que meow
ssh meow@<IP_DU_VPS>
```

### 2.2 Installer Docker + Compose plugin

Script officiel Docker (Ubuntu/Debian) :

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Re-login pour que le groupe prenne effet
exit
ssh meow@<IP_DU_VPS>
```

Vérifie :

```bash
docker --version          # Docker version 28.x ou récent
docker compose version    # Docker Compose version v2.x
```

### 2.3 Ouvrir les ports 80 et 443

Si UFW est actif (par défaut sur Ubuntu) :

```bash
sudo ufw allow OpenSSH    # ne te laisse jamais bloquer dehors !
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status           # vérifier
```

Si tu utilises un security group cloud (Hetzner Firewall, DigitalOcean Cloud Firewall, etc.), ouvre 80 et 443 entrants depuis `0.0.0.0/0`. Pour 22 (SSH), restreins à ton IP perso si possible.

---

## 3. Cloner et préparer le repo

```bash
git clone https://github.com/clemparpa/meow-bot.git
cd meow-bot
```

Crée les répertoires de volumes (Docker créerait des `root:root`, on préfère cadrer dès le début) :

```bash
mkdir -p secrets data
chmod 700 secrets       # secrets/ contiendra la PEM, on restreint l'accès
```

---

## 4. Créer la GitHub App (flow manifest)

`meow-bot` n'est **pas une App centralisée** — chaque self-hoster crée la sienne. On utilise le [flow "manifest" de GitHub](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest) pour pré-remplir le formulaire de création.

### 4.1 Éditer le manifest

Le fichier [manifest/app-manifest.yml](../manifest/app-manifest.yml) contient les permissions et events. Remplace `MEOW_DOMAIN_PLACEHOLDER` par ton FQDN réel :

```bash
sed -i.bak "s|MEOW_DOMAIN_PLACEHOLDER|meow.ton-domaine.com|g" manifest/app-manifest.yml
diff manifest/app-manifest.yml.bak manifest/app-manifest.yml
# Doit montrer la substitution sur hook_attributes.url
rm manifest/app-manifest.yml.bak
```

### 4.2 Convertir le YAML en JSON

GitHub veut le manifest en JSON pour le POST :

```bash
python3 -c "import yaml, json; print(json.dumps(yaml.safe_load(open('manifest/app-manifest.yml'))))" > manifest/app-manifest.json
cat manifest/app-manifest.json
```

> Si `python3` n'est pas dispo : `apt install -y python3 python3-yaml` (le module `yaml` se nomme `python3-yaml` sur Debian/Ubuntu).

### 4.3 POST le manifest à GitHub via un mini form HTML

GitHub n'accepte pas le manifest en query string — il faut un POST de form. Sur **ta machine locale** (pas le VPS), crée `install-app.html` :

```html
<!DOCTYPE html>
<html>
<body>
  <form action="https://github.com/settings/apps/new?state=meow-install" method="post">
    <input type="hidden" name="manifest" id="manifest"/>
    <button type="submit">Create my Meow App</button>
  </form>
  <script>
    document.getElementById('manifest').value = `COLLE_LE_JSON_ICI`;
  </script>
</body>
</html>
```

1. Remplace `COLLE_LE_JSON_ICI` par le contenu de `manifest/app-manifest.json` (récupéré du VPS via `scp` ou copier-coller).
2. Ouvre `install-app.html` dans ton navigateur.
3. Clique sur **Create my Meow App**.
4. GitHub te demande de confirmer le nom de l'App (par défaut `meow-bot`, tu peux personnaliser : `<orgname>-meow` par exemple).
5. Une fois confirmée, GitHub te redirige sur la page de ton App nouvellement créée.

### 4.4 Récupérer les 3 secrets

Sur la page de l'App fraîchement créée (`https://github.com/settings/apps/<ton-app-slug>`) :

1. **App ID** : affiché tout en haut → `App ID: 123456`. Note-le.
2. **Webhook secret** : descend jusqu'à "Webhook secret (optional)". GitHub a généré une valeur via le manifest. Si elle n'apparaît pas, clique sur "Generate a new webhook secret", choisis une string aléatoire forte (`openssl rand -hex 32`) et **save**.
3. **Private key** : descend jusqu'à "Private keys". Clique sur **Generate a private key**. Un fichier `.pem` se télécharge.

### 4.5 Déposer la PEM sur le VPS

Depuis ta machine locale, transfère la PEM :

```bash
scp ~/Downloads/<ton-app-slug>.<date>.private-key.pem meow@<IP_DU_VPS>:~/meow-bot/secrets/github-app.pem
```

Sur le VPS, restreins les droits :

```bash
chmod 600 secrets/github-app.pem
ls -la secrets/
# -rw------- 1 meow meow ... github-app.pem
```

---

## 5. Provisionner Mistral Workflows

### 5.1 API key

1. Va sur [console.mistral.ai](https://console.mistral.ai).
2. Section "API Keys" → **Create new key**.
3. Note la valeur (elle ne sera plus affichée ensuite).

### 5.2 Choisir un `DEPLOYMENT_NAME`

Un *deployment* Mistral Workflows groupe le receiver et le worker d'une même instance. Le nom est libre mais doit être stable.

Convention suggérée :

- `meow-bot` si tu n'as qu'une instance.
- `meow-bot-staging` / `meow-bot-prod` si tu sépares environnements.

Tu le mettras dans `.env` à l'étape 7.

> Tu n'as **rien à provisionner activement** côté Mistral : le deployment est créé implicitement quand le worker démarre et heartbeat.

---

## 6. Provisionner Koyeb

### 6.1 API token

1. Va sur [app.koyeb.com](https://app.koyeb.com).
2. Profil → "API" ou "Settings → API".
3. **Create API token**, copie la valeur.

### 6.2 Pas de provisioning sandbox manuel

Le worker provisionne les sandboxes à la demande via le SDK Koyeb. L'image `meow-base` est tirée depuis `ghcr.io/clemparpa/meow-bot/meow-base:latest` (poussée par notre CI [.github/workflows/sandbox-image.yml](../.github/workflows/sandbox-image.yml)) — le self-hoster n'a rien à builder.

> Si tu veux build ta propre image (forks, customisations), reproduis le job CI localement avec :
> ```bash
> docker buildx build -t mon-meow-base src/meow/worker/sandbox/
> ```

---

## 7. Configurer `.env`

Sur le VPS, copie le template :

```bash
cp .env.example .env
nano .env       # ou vim / l'éditeur de ton choix
```

Renseigne :

| Variable | Valeur | Source |
|---|---|---|
| `MEOW_DOMAIN` | `meow.ton-domaine.com` | Le FQDN choisi à l'étape 1.3 |
| `GITHUB_APP_ID` | `123456` | App ID récupéré à l'étape 4.4 |
| `GITHUB_WEBHOOK_SECRET` | `abcd1234...` | Webhook secret de l'étape 4.4 |
| `GITHUB_APP_PRIVATE_KEY_PATH` | `/secrets/github-app.pem` | Laisse la valeur par défaut |
| `MISTRAL_API_KEY` | `your_mistral_key` | API key de l'étape 5.1 |
| `DEPLOYMENT_NAME` | `meow-bot` | Choix à l'étape 5.2 |
| `KOYEB_API_TOKEN` | `koy_xxx` | Token de l'étape 6.1 |
| `MEOW_BOT_LOGIN` | (cf. étape 8) | Sera renseigné après le premier boot |

> **`MEOW_BOT_LOGIN` reste vide pour l'instant.** On a un problème poule-œuf : le bot login dépend du slug GitHub que tu as choisi à l'étape 4.3, mais GitHub forge le slug avec `[bot]` suffixé. On le récupère à l'étape suivante.

Vérifie que tous les autres champs sont remplis avec un `grep` :

```bash
grep -E "^[A-Z_]+=\s*$" .env
# Ne doit afficher QUE la ligne MEOW_BOT_LOGIN= ; toutes les autres doivent avoir une valeur.
```

---

## 8. Récupérer le bot login

1. Va sur la page publique de ton App : `https://github.com/apps/<ton-app-slug>`.
2. Note le slug exact dans l'URL (souvent identique au nom de l'App, mais GitHub peut le normaliser : minuscules, tirets).
3. Le **bot login** est de la forme `<slug>[bot]`. Exemples :
   - App nommée `meow-bot` → bot login = `meow-bot[bot]`.
   - App nommée `Acme Meow` → slug `acme-meow` → bot login = `acme-meow[bot]`.

Édite `.env` pour renseigner :

```bash
MEOW_BOT_LOGIN=meow-bot[bot]
```

---

## 9. Lancer le stack

```bash
docker compose pull
docker compose up -d
```

Le premier `up` build les images (ou pull si tu as les images publiées). Compte ~2 min.

### 9.1 Vérifier que les 3 services sont up

```bash
docker compose ps
```

Tu dois voir 3 services en état **`Up`** :

```text
NAME                IMAGE              STATUS
meow-bot-caddy-1    caddy:2            Up X seconds
meow-bot-receiver-1 meow-bot-receiver  Up X seconds
meow-bot-worker-1   meow-bot-worker    Up X seconds
```

### 9.2 Vérifier que Caddy provisionne le cert Let's Encrypt

```bash
docker compose logs caddy | grep -i "certificate\|tls"
```

Tu dois voir des lignes du type `certificate obtained successfully` ou similaires. Si Caddy ne trouve pas le domaine, vérifie que ton A record est propagé (`dig +short $MEOW_DOMAIN`).

### 9.3 Healthcheck depuis ta machine locale

```bash
curl -fsS https://meow.ton-domaine.com/healthz
# {"status":"ok"}
```

Si tu obtiens un certificat valide et la réponse JSON, le receiver tourne et est joignable depuis Internet. C'est ce dont GitHub a besoin pour les webhooks.

### 9.4 Vérifier que le worker se connecte à Mistral Workflows

```bash
docker compose logs worker | grep "worker.started\|worker.ready"
```

Tu dois voir un événement `worker.started`. Si tu vois un `ValidationError` ou des erreurs d'auth Mistral, retourne à l'étape 7 et vérifie les valeurs.

---

## 10. Installer l'App sur un repo de test

1. Crée (ou identifie) un repo de test GitHub. Préfère un repo privé pour les essais initiaux.
2. Va sur `https://github.com/apps/<ton-app-slug>` → **Install** → choisis le compte / l'organisation cible.
3. Sélectionne **Only select repositories** et coche le repo de test.
4. Confirme.

GitHub envoie immédiatement un webhook `installation.created` à ton receiver. Vérifie côté logs :

```bash
docker compose logs receiver | grep "webhook"
```

Tu dois voir `webhook.skipped` avec `reason: event-not-handled` (les events `installation.*` sont ignorés en v0.1.0 — cf. story S15 reportée). C'est attendu.

---

## 11. Premier `@<bot> review`

1. Sur ton repo de test, ouvre une PR (n'importe quel diff, même trivial : ajoute un fichier `hello.md`).
2. Dans le fil de commentaires de la PR, écris **exactement** :

   ```text
   @<ton-bot-login> review
   ```

   Exemple : `@meow-bot[bot] review` — **sans** les crochets `[bot]` quand tu le tapes dans GitHub (GitHub ne les affiche pas en autocomplete). En pratique, tape `@meow-bot` et GitHub complétera ; ce qui compte côté code, c'est que `sender.login` du webhook match `MEOW_BOT_LOGIN`.

3. Poste le commentaire. GitHub envoie un webhook `issue_comment.created`.
4. Suis les logs en temps réel :

   ```bash
   docker compose logs -f worker
   ```

   Tu dois voir successivement :

   ```text
   workflow.pr_review.started
   activity.fetch_pr_context.started
   activity.fetch_meow_config.started
   activity.run_vibe.started
   ... (durée 30s à plusieurs minutes selon la PR et les budgets)
   activity.post_pr_comment.started
   workflow.pr_review.done
   ```

5. Refresh la PR sur GitHub : un nouveau commentaire signé par ton bot doit être apparu avec le rapport de review.

---

## 12. Troubleshooting

### Le receiver crash au boot : `koyeb_api_token Field required`

`KOYEB_API_TOKEN` est vide dans `.env`. Mets une valeur (même un placeholder fonctionne pour booter le receiver, mais le worker en aura besoin pour vraiment review une PR).

### Le receiver crash au boot : `bot_login Field required`

`MEOW_BOT_LOGIN` est vide. Renseigne-le (cf. étape 8).

### Caddy ne provisionne pas le cert : `certificate signed by unknown authority`

Le DNS A record n'est pas propagé. Vérifie :

```bash
dig +short $MEOW_DOMAIN
# doit afficher l'IP du VPS
```

Si ça ne renvoie rien, attends 5-30 min (TTL DNS). Si ça renvoie une mauvaise IP, corrige côté registrar.

### GitHub affiche le webhook delivery en rouge : `401 Unauthorized`

Le `GITHUB_WEBHOOK_SECRET` dans `.env` ne match pas celui configuré côté GitHub App.

1. Va sur `https://github.com/settings/apps/<ton-app-slug>` → "Webhook secret".
2. Compare avec `.env`. Mets-les à la même valeur.
3. `docker compose restart receiver` pour recharger.

### GitHub affiche le webhook delivery en rouge : `400 Bad Request`

Le body du webhook est mal formé (rare). Lis les logs du receiver — généralement un `webhook.malformed_payload` indique que `githubkit.webhooks.parse` a refusé la structure.

### Le bot ne répond pas à mon commentaire

1. Vérifie que tu utilises le bon `MEOW_BOT_LOGIN`. Si tu écris `@meowbot` mais que le login est `meow-bot[bot]`, l'intent detect ne match pas.
2. Vérifie que le commentaire est bien sur une **PR**, pas une issue classique. `MENTION_REVIEW` ne se déclenche que sur les PR.
3. Regarde `docker compose logs receiver` : tu dois voir `webhook.dispatched`. Si tu vois `webhook.skipped` avec `reason: no-intent`, c'est que le regex n'a pas matché.

### Une activity échoue avec un timeout Mistral Workflows

L'activity `run_vibe` peut prendre longtemps (jusqu'à 35 min selon les budgets). Si Mistral Workflows timeout, c'est probablement un souci côté Koyeb (sandbox lente à provisionner, ou hit le free-tier limit). Vérifie ton dashboard Koyeb.

### Voir les exécutions en détail

Mistral Workflows expose toutes les exécutions et leurs traces OTel via [console.mistral.ai](https://console.mistral.ai) → Workflows → ton deployment. Utile pour debugger les chains d'activities qui échouent.

---

## 13. Mises à jour et désinstallation

### Mettre à jour le bot

```bash
cd ~/meow-bot
git pull
docker compose pull       # tire les nouvelles images si publiées
docker compose up -d      # recrée les containers qui ont changé
docker compose logs -f    # vérifier le bon redémarrage
```

Les volumes (`./data`, `./secrets`, `caddy_data`) sont préservés.

### Désinstaller

```bash
docker compose down       # arrête et supprime les containers
docker compose down -v    # AJOUTE -v pour supprimer aussi les volumes (cert Let's Encrypt)
```

Pour révoquer côté GitHub :

1. `https://github.com/settings/apps/<ton-app-slug>` → **Delete GitHub App**.
2. Optionnel : révoque les API keys Mistral / Koyeb depuis leurs consoles respectives.

---

## Pour aller plus loin

- **Comment ça marche en interne** → [architecture.md](architecture.md).
- **Spec complète et choix techniques** → [../SPEC.md](../SPEC.md).
- **Personnaliser le comportement du bot par repo** → ajoute un `.meow.yml` à la racine du repo cible (cf. [../SPEC.md §10](../SPEC.md) et [../README.md](../README.md)).
- **Contribuer** → [../CONTRIBUTING.md](../CONTRIBUTING.md).
- **Reporter une faille de sécurité** → [../SECURITY.md](../SECURITY.md).
