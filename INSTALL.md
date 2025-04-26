# Install

- [Install CertManager](#install-certmanager)
- [Install Traefik](#install-traefik)
- [Install Traefik CertManager](#install-traefik-certmanager)

## Install CertManager

Either use `helm` install below or with `helmfile` with the provided manifest.

The default values assume you have cert-manager installed, see also [cert-manager installation](https://cert-manager.io/docs/installation/helm/):

> **Helmfile**
>
> ```shell
> helmfile --file ./manifests/cert-manager/helmfile.yaml apply
> ```

> **helm**
>
> ```shell
> helm install \
>  cert-manager jetstack/cert-manager \
>  --namespace cert-manager \
>  --create-namespace \
>  --version v1.17.0 \
>  --set installCRDs=true

## Install Traefik

Either use `helm` install below or with `helmfile` with the provided manifest.

As well as Traefik, see also [traefik installation](https://doc.traefik.io/traefik/getting-started/install-traefik/#use-the-helm-chart):

> **Helmfile**
>
> ```shell
> helmfile --file ./manifests/traefik/helmfile.yaml apply
> ```

> **helmfile**
>
> ```shell
> helm install \
>   traefik traefik/traefik \
>   --namespace traefik \
>   --create-namespace
> ```

## Install Traefik CertManager

The Traefik CertManager is installed within the `traefik` namespace by default.
For installation a standard `helmfile` deployment has been added to this repository in [manifests](../manifests/traefik-certmanager/).

Please see the main [README](../README.md) for configuration.

> **Helmfile**
>
> ```shell
> helmfile --file ./manifests/traefik-certmanager/helmfile.yaml apply
> ```
