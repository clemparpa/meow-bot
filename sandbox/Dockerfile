# syntax=docker/dockerfile:1.7

# Base image for the ephemeral Daytona sandboxes that run mistral-vibe
# reviews (spec §8.5). One image, versioned, pushed as the `meow-base`
# snapshot via `sandbox/build-and-push.sh`. Re-build manually when
# bumping `mistral-vibe` or system tooling — never in CI.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# git for `git clone`, curl for the gh keyring/install, ca-certificates
# for HTTPS, gnupg to dearmor the gh signing key, then `gh` itself from
# the official GitHub apt repo. Single RUN layer to keep the apt cache
# scrub effective.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git ca-certificates curl gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# mistral-vibe pinned — bump manually, document the new version in
# sandbox/README.md. We let dependabot ignore this file.
RUN pip install --no-cache-dir mistral-vibe==2.10.1

# Skeleton `.vibe/` directory. S12 will populate it once the real call
# site knows what config files `vibe.core.run_programmatic` expects.
RUN mkdir -p /root/.vibe

WORKDIR /work
