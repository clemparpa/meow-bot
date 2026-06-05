# meow-bot review sandbox image.
#
# Base: koyeb/sandbox:v0.0.15-slim (Ubuntu 22.04, ~30 MB).
# The slim variant ships almost nothing, so every tool the review
# activity (or the vibe agent inside it) relies on is installed
# explicitly below with a pinned version.
#
# We deliberately don't override ENTRYPOINT — `/usr/bin/sandbox-executor`
# from the base image is what lets Koyeb drive the sandbox.

FROM koyeb/sandbox:v0.0.15-slim

# --- Versions (bump here, single source of truth) ------------------------
ARG GH_VERSION=2.93.0
ARG UV_VERSION=0.11.17
ARG PYTHON_VERSION=3.13.13
ARG VIBE_VERSION=2.13.0
ARG NODE_VERSION=22.22.3
ARG PNPM_VERSION=11.5.0

# --- Locale + non-interactive apt ---------------------------------------
# C.UTF-8 is built into glibc on Ubuntu 22.04 — no `locales` package needed.
# Without LANG/LC_ALL set, grep/read on non-ASCII files breaks silently.
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/root/.local/bin:${PATH}"

# --- Base OS deps -------------------------------------------------------
# ca-certificates: TLS for git clone / curl / vibe API / gh
# curl:            fetch the installers below
# git:             review activity clones the PR repo at runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
 && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI (pinned tarball, no extra apt repo) ---------------------
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
      -o /tmp/gh.tgz \
 && tar -xzf /tmp/gh.tgz -C /tmp \
 && mv "/tmp/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
 && rm -rf /tmp/gh.tgz "/tmp/gh_${GH_VERSION}_linux_amd64"

# --- uv (pinned, official installer) ------------------------------------
# Drops the binary in /root/.local/bin, already on PATH (see ENV above).
RUN curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh

# --- Python via uv (pinned) ---------------------------------------------
# uv manages its own Python builds; symlink so `python` / `python3` work
# in shells that don't go through `uv run`.
RUN uv python install "${PYTHON_VERSION}" \
 && ln -sf "$(uv python find ${PYTHON_VERSION})" /usr/local/bin/python3 \
 && ln -sf /usr/local/bin/python3 /usr/local/bin/python

# --- mistral-vibe (pinned) ----------------------------------------------
# `uv tool install` puts the entrypoint shim in /root/.local/bin/vibe.
RUN uv tool install "mistral-vibe==${VIBE_VERSION}"

# --- Bake the harness config + skills/agents trees ----------------------
# vibe resolves config in order: <cwd>/.vibe/config.toml then ~/.vibe/config.toml.
# We bake the defaults at home so any sandbox-side `vibe` call works without
# extra setup. Per-run overrides (e.g. enabled_skills) are written to
# <cwd>/.vibe/config.toml by the worker, which takes priority.
COPY sandbox_files/.vibe /root/.vibe

# --- Node.js (pinned tarball, includes corepack) ------------------------
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
      -o /tmp/node.tar.xz \
 && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
      --exclude='CHANGELOG.md' --exclude='LICENSE' --exclude='README.md' \
 && rm /tmp/node.tar.xz

# --- pnpm via corepack (pinned default; package.json#packageManager wins) -
# `corepack enable` registers shims for pnpm/yarn. `corepack prepare … --activate`
# pre-downloads this version so the first sandbox call doesn't pay the cost.
RUN corepack enable \
 && corepack prepare "pnpm@${PNPM_VERSION}" --activate

# --- Sanity check (fails the build if anything is missing) --------------
RUN gh --version \
 && uv --version \
 && python --version \
 && vibe --version \
 && node --version \
 && npm --version \
 && pnpm --version \
 && git --version
