# Deploying Truecast to Azure

The app is a single container. It runs offline out of the box and switches to
the Azure AI Foundry narrator when the Foundry endpoint + key are supplied.

> For a start-to-finish walkthrough (account signup → Foundry model → deploy →
> record the demo), see [`../AZURE_SETUP.md`](../AZURE_SETUP.md), which uses the
> simpler one-command `az containerapp up`. The steps below are the
> infrastructure-as-code path via Bicep.

## 1. Build and push the image

```bash
az group create -n <rg> -l eastus
az acr create -g <rg> -n <registry> --sku Basic --admin-enabled true
az acr build -r <registry> -t truecast:latest .
```

## 2. (Optional) Provision an Azure AI Foundry model

In the Azure AI Foundry portal, deploy a chat model (e.g. `gpt-4o-mini`) and
copy its endpoint and key. Skip this to run the deterministic narrator.

## 3. Deploy the infrastructure

```bash
# Registry credentials so the Container App can pull the private image
ACR_USER=$(az acr credential show -n <registry> --query username -o tsv)
ACR_PWD=$(az acr credential show -n <registry> --query 'passwords[0].value' -o tsv)

az deployment group create -g <rg> \
  --template-file infra/main.bicep \
  --parameters image=<registry>.azurecr.io/truecast:latest \
               registryServer=<registry>.azurecr.io \
               registryUsername=$ACR_USER \
               registryPassword=$ACR_PWD \
               foundryEndpoint=<endpoint-or-blank> \
               foundryApiKey=<key-or-blank>
```

The deployment outputs `appUrl`; open it to reach the live broadcast UI.

## What this uses

- **Azure Container Apps** — serverless container host with HTTP autoscaling.
- **Azure Container Registry** — image storage.
- **Log Analytics** — container logs.
- **Azure AI Foundry** — the narrative model (optional; graceful offline fallback).
