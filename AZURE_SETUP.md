# Azure setup — from zero to a live, Foundry-powered demo

Goal: a public Azure URL where the app runs with **Azure AI Foundry** writing the
lines, so the demo proves real use of the Microsoft stack. Budget ~45 minutes of
hands-on time (plus account-verification wait).

You can do all of this from **Azure Cloud Shell** in the portal (the `>_` icon,
top bar) — it has `az`, `git`, and a build backend, so no local installs.

---

## Phase 0 — Account & tools (start first; verification can lag a day)

1. Sign up: <https://azure.microsoft.com/free> — a card is needed to verify; you
   get free credit.
2. Open **Cloud Shell** → choose **Bash**.
3. Select your subscription and register the resource providers:

```bash
az account set --subscription "<your-subscription-name-or-id>"
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.CognitiveServices --wait
```

---

## Phase 1 — Deploy the AI Foundry model (portal, ~10 min)

1. Go to <https://ai.azure.com> → **Create a project** (this provisions the
   Foundry resource behind it). Choose a region that offers `gpt-4o-mini`
   (East US is a safe default).
2. Left nav → **Models + endpoints** → **Deploy model → Deploy base model** →
   pick **gpt-4o-mini** → name the deployment exactly `gpt-4o-mini` → Confirm.
3. Open the deployment and copy, from the **Endpoint** panel:
   - **Target URI** base — keep only `https://<resource>.openai.azure.com`
     (drop everything after `.com`)
   - **Key**

> If `gpt-4o-mini` shows no quota in your region, pick another region or
> `gpt-4o`. Update the deployment name in the commands below to match.

---

## Phase 2 — Get the code into Cloud Shell

```bash
git clone https://github.com/demonjd2026-afk/truecast.git
cd truecast
```

(Repo not pushed yet? Use Cloud Shell's **Upload** button for `truecast.zip`,
then `unzip truecast.zip && cd truecast`.)

---

## Phase 3 — Verify Foundry works (optional, 2 min)

```bash
pip install -e .
export AZURE_AI_FOUNDRY_ENDPOINT="https://<resource>.openai.azure.com"
export AZURE_AI_FOUNDRY_API_KEY="<key>"
export AZURE_AI_FOUNDRY_DEPLOYMENT="gpt-4o-mini"
truecast check-foundry
```

Expect: `probe: OK — model responded`.

---

## Phase 4 — Deploy to Azure Container Apps (one command, ~10 min)

```bash
az containerapp up \
  --name truecast \
  --resource-group truecast-rg \
  --location eastus \
  --source . \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    AZURE_AI_FOUNDRY_ENDPOINT="https://<resource>.openai.azure.com" \
    AZURE_AI_FOUNDRY_API_KEY="<key>" \
    AZURE_AI_FOUNDRY_DEPLOYMENT="gpt-4o-mini"
```

This builds the image from the `Dockerfile` in the cloud, creates the registry,
environment, and logs, and deploys. It prints a URL like
`https://truecast.<region>.azurecontainerapps.io`. Open it — the top-right badge
should read **foundry**.

> The first run may prompt to install the `containerapp` CLI extension — accept it.
> Passing the key via `--env-vars` is fine for a hackathon; rotate it afterward.

**Infrastructure-as-code alternative:** build/push to ACR, then deploy
`infra/main.bicep` (it configures the registry pull, Foundry secret, and health
probes). See `infra/deploy.md`.

---

## Phase 5 — Record the demo (≤2 min)

Open the live Azure URL and follow `DEMO_SCRIPT.md`. The recording should show:

- the **foundry** badge (the Azure model is writing the lines),
- an evidence chip expanded (event IDs behind a line),
- the **Rewritten / Blocked** counters (the Verifier guarding the live model),
- a persona switch and player focus,
- the `/api/overlays` JSON (machine-readable output).

Upload to YouTube (public or unlisted) and put the link on the project page.

---

## Phase 6 — Submit (by Oct 27)

- Repo public at `github.com/demonjd2026-afk/truecast`.
- Video URL + repo URL on the project page; pitch from `PITCH.md`.

---

## When finished — avoid charges

```bash
az group delete -n truecast-rg --yes --no-wait
```

Also delete the resource group created by the Foundry project (from
`ai.azure.com`) once you no longer need the model.
