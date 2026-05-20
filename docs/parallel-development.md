# Développement parallèle avec `git worktree`

Quand plusieurs stories sont indépendantes (cf. [Phases de parallélisation](../stories/v0.0.x.md)), on peut les implémenter en parallèle sur des branches distinctes via `git worktree`. Chaque worktree est un dossier physique séparé, sur sa propre branche, partageant le `.git` du repo principal.

## Pourquoi worktree (et pas plusieurs clones)

- Pas de duplication du `.git` (économise disque et réseau).
- `git fetch` dans le repo principal met à jour tous les worktrees.
- Les branches sont visibles depuis tous les worktrees (`git branch -a`).

## Convention de rangement

Worktrees rangés **à côté** du repo principal, pas dedans, sinon `ruff`, `pytest`, et toi-même les confondent avec du code du repo.

```text
/Users/clement/flush/
├── meow-bot/                 # repo principal (main)
└── meow-bot-worktrees/
    ├── s2/                   # feat/s2-layout
    ├── s10/                  # feat/s10-app-manifest
    └── s11/                  # feat/s11-ci
```

Setup une fois :

```bash
mkdir -p /Users/clement/flush/meow-bot-worktrees
```

## Créer un worktree par story

Depuis le repo principal, sur `main` à jour :

```bash
git fetch origin
git worktree add ../meow-bot-worktrees/s2  -b feat/s2-layout        origin/main
git worktree add ../meow-bot-worktrees/s10 -b feat/s10-app-manifest origin/main
git worktree add ../meow-bot-worktrees/s11 -b feat/s11-ci           origin/main
```

Chaque commande crée un dossier complet (checkout de la branche) qui partage le `.git` du repo principal.

## Préparer chaque worktree

Une fois par worktree :

```bash
cd ../meow-bot-worktrees/s2
uv sync                  # crée sa propre .venv locale
uv run lefthook install  # réinstalle les hooks (.git/hooks est par-worktree)
```

> `.venv` et `.git/hooks` ne sont **pas partagés** entre worktrees — chacun a les siens. À refaire à chaque création.

## Lancer Claude Code dans chaque worktree

Trois terminaux (ou trois fenêtres VSCode) :

```bash
cd /Users/clement/flush/meow-bot-worktrees/s2 && claude
```

Brief court à donner à chaque instance, par exemple :

> Implémente S2 selon `stories/v0.0.x.md`. Commit + ouvre une PR `feat/s2-layout` vers `main` à la fin.

Les instances bossent en silos, ne se voient pas.

## Cycle d'une story

Dans le worktree :

```bash
# travail normal : edit, commit
git push -u origin feat/s2-layout
gh pr create --base main --title "feat(s2): layout src/meow/" --body "..."
```

Une fois la PR mergée sur GitHub, retour au repo principal :

```bash
cd /Users/clement/flush/meow-bot
git pull
git worktree remove ../meow-bot-worktrees/s2
git branch -d feat/s2-layout
```

## Pièges concrets

- **Pas la même branche dans deux worktrees** : git refuse, par design.
- **Conflits de merge entre worktrees** : si S10 et S11 touchent `README.md`, la deuxième PR à arriver devra rebaser sur `main` après merge de la première. Garde les diffs petits et localisés.
- **Statut dans `stories/v0.0.x.md`** : chaque PR met son `✅` → mini-conflit récurrent à régler à la main au rebase.
- **Oublier `lefthook install`** : le pre-push ne tournera pas. Fais-le tout de suite après `worktree add`.

## Lister et nettoyer

```bash
git worktree list             # voir tous les worktrees actifs
git worktree prune            # nettoyer les entrées orphelines
git worktree remove <path>    # supprimer un worktree (refuse si modifications)
```
