# Traefik CertManager

> [!NOTE]
>
> Current Release: 2.0.0-rc9

The Traefik CertManager manages the handling of certificates of Traefik IngressRoutes,
this repository is a fork of the original traefik-certmanager which was created by [Rob Kooper](https://github.com/robkooper).

[Cert Manager](https://cert-manager.io) handles only default Kubernetes `Ingress` kind.
This manager provides the management so that the [Cert Manager](https://cert-manager.io)
can provide certicates for the Traefik `IngressRoute` kind.

See documentation @ [gjrtimmer.github.io/traefik-certmanager](https://gjrtimmer.github.io/traefik-certmanager)

## Prerequisites

The following prerequisites must be met before the Traefik CertManager can be used.

- [Cert Manager](https://cert-manager.io)
- [Traefik](https://traefik.io)
- [Traefik Custom Resource Definition (CRD)](https://doc.traefik.io/traefik/reference/dynamic-configuration/kubernetes-crd/)

See the [Install documentation](./INSTALL.md)

## Install

See the [Install documentation](./INSTALL.md) for how to install the Traefik CertManager and all prerequisites.

## Features

The Traefik CertManager comes with several nice features.

- Support Legacy CRD
- Annotation Ignore
- Annotation IngressClass Filtering
- Default Certificate Issuer

The Support for Legacy CRD (Traefik `traefik.containo.us/v1alpha1`) was created as a PR
by [T. Andrew Manning](https://github.com/manning-ncsa) into the upstream of this fork.

## Configuration

| EnvVar               | Default       | Notes                                                                             |
| -------------------- | ------------- | --------------------------------------------------------------------------------- |
| INGRESS_CLASS_FILTER | ""            | Ingress Class to filter on, comma seperated,                                      |
| ISSUER_NAME_DEFAULT  | letsencrypt   | Default `ClusterIssuer`                                                           |
| ISSUER_KIND_DEFAULT  | ClusterIssuer | Default `ClusterIssuer` King                                                      |
| CERT_CLEANUP         | false         | Certificate Cleanup after removal of `IngressRoute`                               |
| PATCH_SECRETNAME     | false         | If there is not a `secretName` in the `IngressRoute` patch it by using the `name` |
| SUPPORT_LEGACY_CRDS  | false         | Support scanning for Traefik legacy CRDs `traefik.containo.us/v1alpha1`           |

### Ingress Class Filter

This will filter the `IngressRoutes` the Traefik CertManager will process set by the annotation `kubernetes.io/ingress.class` on the IngressRoute.

## Annotations

The Traefik CertManager supports multiple annotations to be used within the `IngressRoute`.

| Annotation                     | Description                                                                        |
| ------------------------------ | ---------------------------------------------------------------------------------- |
| cert-manager.io/ignore         | This will cause the `IngressRoute` to be skipped                                   |
| kubernetes.io/ingress.class    | Value checked against `INGRESS_CLASS_FILTER` to determine if we need to process it |
| cert-manager.io/cluster-issuer | Tell Traefik CertManager to use this `ClusterIssuer`                               |
| cert-manager.io/issuer         | Use this issuer, used in combination with `cert-manager.io/issuer-kind`            |
| cert-manager.io/issuer-kind    | Use this issuer kind, user in combination with `cert-manager.io/issuer`            |

> [!WARNING]
>
> Please note that the annotation cluster-issuer is mutualy exclusive with `cert-manager.io/cluster-issuer` and
> `cert-manager.io/issuer-kind`.
>
> This means either use
> `cert-manager.io/cluster-issuer`
> **OR**
> `cert-manager.io/issuer` + `cert-manager.io/issuer-kind`

## Adding ClusterIssuer to Cert-Manager

Next you install the ClusterIssuer using `kubectl apply -f ./manifests/letsencrypt/le-cluster-issuer.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    email: manager@example.com
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: lets-encrypt
    solvers:
      - http01:
          ingress:
            class: ""
```

## Usage

When the Traefik CertManager is starting it will check all existing IngressRoutes.
Then it will check if it must filter based on the IngressClass name and see if there is a certificate for them (only for those that have a secretName).
Next it will watch the addition and/or deleting of IngressRoutes.
If an IngressRoute is removed, it can (false by default) remove the certificate as well.

This is an example of a IngressRoute that will be picked up by this deployment,
if no `INGRESS_CLASS_FILTER` is set.

```yaml
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: traefik-dashboard
  namespace: traefik
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`traefik.example.com`)
      kind: Rule
      services:
        - name: api@internal
          kind: TraefikService
  tls:
    secretName: trafik.example
```

Say that you have an `ClusterIssuer` with the name `k3s-apps-ca` which provides a self-signed certificate
for your `k3.local` domain and want to configure it, you can simple add the required annotation to the
example above and change the `Host`.

```yaml
metadata:
  name: traefik-dashboard
  namespace: traefik
  annotations:
    cert-manager.io/cluster-issuer: "k3s-apps-ca"
```
