# Turning on the Azure AI Foundry narrator

Truecast runs offline by default. This enables the Foundry-hosted model for
the Explainer. The Verifier still checks the model's output, so grounding holds
either way. Budget ~15 minutes once your subscription is active.

The reliable path is the Foundry portal for the model deployment, plus a couple
of CLI reads for the endpoint and key. Resource kinds and model availability
vary by region and subscription, so if a CLI command is rejected, use the portal
step beside it.

## 0. Prerequisites

- An Azure subscription (any tier that can deploy an Azure OpenAI / AI Foundry model).
- Azure CLI: `az login`, then `az account set --subscription <id>`.

## 1. Create a resource group

```bash
az group create -n rg-truecast -l eastus
```

## 2. Create the AI Foundry resource and deploy a chat model

**Portal (recommended):**
1. Open https://ai.azure.com → create a project (this provisions the AI Foundry resource).
2. Go to **Models + endpoints → Deploy model → gpt-4.1-mini**.
3. Name the deployment `gpt-4.1-mini`.

**CLI (alternative):**
```bash
az cognitiveservices account create \
  -n truecast-foundry -g rg-truecast -l eastus \
  --kind AIServices --sku S0 --yes

az cognitiveservices account deployment create \
  -n truecast-foundry -g rg-truecast \
  --deployment-name gpt-4.1-mini \
  --model-name gpt-4.1-mini --model-version "2025-04-14" \
  --model-format OpenAI --sku-capacity 10 --sku-name Standard
```

## 3. Read the endpoint and key

```bash
az cognitiveservices account show \
  -n truecast-foundry -g rg-truecast \
  --query properties.endpoint -o tsv

az cognitiveservices account keys list \
  -n truecast-foundry -g rg-truecast \
  --query key1 -o tsv
```

(Portal: the same values are under the deployment's **Endpoint** panel.)

## 4. Point Truecast at it

```bash
cp .env.example .env
```

Fill in `.env`:

```
AZURE_AI_FOUNDRY_ENDPOINT=https://truecast-foundry.openai.azure.com
AZURE_AI_FOUNDRY_API_KEY=<key1>
AZURE_AI_FOUNDRY_DEPLOYMENT=gpt-4.1-mini
AZURE_AI_FOUNDRY_API_VERSION=2024-10-21
```

Then export it (or use a dotenv loader / your shell):

```bash
set -a; . ./.env; set +a
```

## 5. Verify

```bash
truecast check-foundry
```

Expected:

```
configured mode: foundry
endpoint:   https://truecast-foundry.openai.azure.com
deployment: gpt-4.1-mini
probe:      OK — model responded ('OK')
```

Then launch the UI and confirm the mode badge reads **foundry**:

```bash
truecast serve
# open http://127.0.0.1:8000  — top-right badge shows "foundry"
```

## 6. Grounding still applies

With Foundry on, the Explainer's lines come from the model, but the Verifier
rebuilds its allow-list from the event log and rejects any line that adds a
number or a player the data doesn't support — the rejected line is rewritten.
Watch the **Rewritten** / **Blocked** counters in the Production panel: with a
live model they will occasionally tick up, which is the guardrail doing its job.

## Deploy the whole app to Azure

Once the model is live, deploy the container to Azure Container Apps with
`infra/main.bicep` (see `infra/deploy.md`), passing `foundryEndpoint` and
`foundryApiKey` so the hosted app uses Foundry too.
