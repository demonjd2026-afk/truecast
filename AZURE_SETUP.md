# Azure setup — from zero to a live, Foundry-powered deployment

Goal: a public Azure URL where Truecast runs with **Azure AI Foundry** writing
the lines. Budget about 45 minutes of hands-on time, plus any account
verification wait.

Everything below works from **Azure Cloud Shell** in the portal (the `>_` icon
in the top bar). It has `az`, `git` and a cloud build backend, so nothing needs
installing locally.

> Cloud Shell resets the active subscription each session. If you have more
> than one subscription, run `az account set --subscription <name>` at the
> start of every session before any other command.

---

## Phase 0 — Account and resource providers

1. Sign up at <https://azure.microsoft.com/free> (a card is needed to verify).
2. Open **Cloud Shell** and choose **Bash**.
3. Select the subscription and register the providers used below:

```bash
az account set --subscription "<your-subscription-name-or-id>"
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.CognitiveServices --wait
```

---

## Phase 1 — Deploy the Foundry model (portal, ~10 min)

1. Go to <https://ai.azure.com> and **create a project**; this provisions the
   Foundry resource behind it. Pick a region that offers `gpt-4.1-mini`
   (East US 2 is a safe default).
2. Left nav → **Models + endpoints** → **Deploy model → Deploy base model** →
   choose **gpt-4.1-mini** → name the deployment exactly `gpt-4.1-mini` →
   Confirm.
3. Open the deployment and copy, from the **Endpoint** panel:
   - the **Target URI** base — keep only `https://<resource>.openai.azure.com`
     and drop everything after `.com`
   - the **Key**

> If `gpt-4.1-mini` shows no quota in your region, pick another region. If you
> deploy a different model, use its deployment name wherever `gpt-4.1-mini`
> appears below.

---

## Phase 2 — Get the code into Cloud Shell

```bash
git clone https://github.com/demonjd2026-afk/truecast.git
cd truecast
```

---

## Phase 3 — Check the model responds (optional, 2 min)

```bash
pip install -e .
export AZURE_AI_FOUNDRY_ENDPOINT="https://<resource>.openai.azure.com"
export AZURE_AI_FOUNDRY_API_KEY="<key>"
export AZURE_AI_FOUNDRY_DEPLOYMENT="gpt-4.1-mini"
truecast check-foundry
```

Expected: `probe: OK — model responded`.

---

## Phase 4 — Deploy to Azure Container Apps (one command, ~10 min)

```bash
az containerapp up \
  --name truecast \
  --resource-group rg-truecast \
  --location eastus2 \
  --source . \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    AZURE_AI_FOUNDRY_ENDPOINT="https://<resource>.openai.azure.com" \
    AZURE_AI_FOUNDRY_API_KEY="<key>" \
    AZURE_AI_FOUNDRY_DEPLOYMENT="gpt-4.1-mini"
```

This builds the image from the `Dockerfile` in the cloud, creates the
registry, environment and log workspace, and deploys. It prints a URL like
`https://truecast.<hash>.<region>.azurecontainerapps.io`. Open it: the badge
in the Production panel should read **foundry**.

> The first run may prompt to install the `containerapp` CLI extension; accept.
> Passing the key via `--env-vars` is fine for a demo; rotate it afterwards.

**Redeploying after a code change** is the same command again from a fresh
clone (`--env-vars` can be omitted; the app keeps the ones already set):

```bash
cd ~ && rm -rf truecast && git clone https://github.com/demonjd2026-afk/truecast.git && cd truecast
az account set --subscription "<your-subscription>"
az containerapp up --name truecast --resource-group rg-truecast --source . --ingress external --target-port 8000
```

**Infrastructure-as-code alternative:** build and push to ACR, then deploy
`infra/main.bicep` (registry pull, Foundry secret and health probes). See
[`infra/deploy.md`](infra/deploy.md).

---

## Phase 5 — Confirm it is live

- `https://<your-url>/healthz` returns `{"status": "ok", "narrator": "foundry"}`.
- The app pre-warms a full replay of each featured match at startup; in
  foundry mode that takes roughly 15 minutes, after which the overlay export
  and recap endpoints answer instantly.

---

## Costs

Scale the app to zero when idle so you pay only for storage; the URL stays
reserved and the app starts on the next request:

```bash
az containerapp update -n truecast -g rg-truecast --min-replicas 0   # idle
az containerapp update -n truecast -g rg-truecast --min-replicas 1   # back on
```

When finished for good:

```bash
az group delete -n rg-truecast --yes --no-wait
```

Also delete the resource group created by the Foundry project (from
`ai.azure.com`) once the model is no longer needed.
