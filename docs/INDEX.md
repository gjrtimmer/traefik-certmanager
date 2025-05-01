---
title: "Traefik CertManager"
permalink: index.html
---

## Traefik CertManager

The Traefik CertManager manages the handling of certificates of Traefik IngressRoutes.

[Cert Manager](https://cert-manager.io) handles only default Kubernetes `Ingress` kind.
This manager provides the management so that the [Cert Manager](https://cert-manager.io)
can provide certicates for the Traefik `IngressRoute` kind.

> [!NOTE]
> 
> **Current Version: 2.2.2**

### Prerequisites

The following prerequisites must be met before the Traefik CertManager can be used.

- [Cert Manager](https://cert-manager.io)
- [Traefik](https://traefik.io)
- [Traefik Custom Resource Definition (CRD)](https://doc.traefik.io/traefik/reference/dynamic-configuration/kubernetes-crd/)

### Install (helm)

Add repository to helm.

```shell
helm repo add traefik-certmanager https://gjrtimmer.github.io/traefik-certmanager
helm repo update
```

Install Traefik CertManager

```shell
helm install traefik-certmanager traefik-certmanager/traefik-certmanager -n traefik
```

### Install (helmfile)

Install by using helmfile. (GitOps)

```yaml
repositories:
  - name: traefik-certmanager
    url: https://gjrtimmer.github.io/traefik-certmanager

releases:
- name: traefik-certmanager
  namespace: traefik
  chart: traefik-certmanager/traefik-certmanager
  version: 2.2.2
  installed: true
  values:
    - values.yaml
```

#### values.yaml

```yaml
options:
  ingressClassFilter: ""
  issuer:
    default:
      name: letsencrypt
      kind: ClusterIssuer
  certCleanup: "false"
  patchSecretName: "false"
  supportLegacyCRDs: "false"
```
