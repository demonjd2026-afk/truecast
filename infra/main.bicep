// Truecast on Azure Container Apps.
// Deploys a Log Analytics workspace, a Container Apps environment, and the
// app itself, wired to Azure AI Foundry through app secrets. The narrator runs
// offline when the Foundry secret is empty, so this template is safe to deploy
// before a model is provisioned.

@description('Base name for all resources')
param name string = 'truecast'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Container image, e.g. <registry>.azurecr.io/truecast:latest')
param image string

@description('Azure AI Foundry endpoint (optional; blank = offline narrator)')
param foundryEndpoint string = ''

@secure()
@description('Azure AI Foundry API key (optional)')
param foundryApiKey string = ''

@description('Foundry chat deployment name')
param foundryDeployment string = 'gpt-4o-mini'

@description('Container registry login server, e.g. myreg.azurecr.io (blank for a public image)')
param registryServer string = ''

@description('Container registry username')
param registryUsername string = ''

@secure()
@description('Container registry password')
param registryPassword string = ''

var logName = '${name}-logs'
var envName = '${name}-env'

// Build secret and registry arrays conditionally so the template deploys with
// a private ACR, a public image, or no Foundry key.
var secrets = union(
  [ { name: 'foundry-api-key', value: foundryApiKey } ],
  registryPassword != '' ? [ { name: 'acr-password', value: registryPassword } ] : []
)
var registries = registryServer != '' ? [
  { server: registryServer, username: registryUsername, passwordSecretRef: 'acr-password' }
] : []

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: secrets
      registries: registries
    }
    template: {
      containers: [
        {
          name: name
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: foundryEndpoint }
            { name: 'AZURE_AI_FOUNDRY_API_KEY', secretRef: 'foundry-api-key' }
            { name: 'AZURE_AI_FOUNDRY_DEPLOYMENT', value: foundryDeployment }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 3
              periodSeconds: 15
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scale'
            http: { metadata: { concurrentRequests: '40' } }
          }
        ]
      }
    }
  }
}

output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
