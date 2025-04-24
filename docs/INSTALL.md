# Install Traefik CertManager

### Installing Cert-Manager and Traefik

The default values assume you have cert-manager installed, see also [cert-manager installation](https://cert-manager.io/docs/installation/helm/):

```bash
helm install \
  cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.9.1 \
  --set installCRDs=true
```

As well as Traefik, see also [traefik installation](https://doc.traefik.io/traefik/getting-started/install-traefik/#use-the-helm-chart):

```
helm install \
	traefik traefik/traefik \
  --namespace cert-manager \
  --create-namespace \

```
