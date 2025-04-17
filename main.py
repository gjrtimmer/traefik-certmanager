import argparse
import json
import logging
import os
import re
import signal
import sys
import threading
import time

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
INGRESS_CLASS_FILTER = os.getenv("INGRESS_CLASS_FILTER", "")
FILTER_SET = {c.strip() for c in INGRESS_CLASS_FILTER.split(',') if c.strip()}
ISSUER_NAME_DEFAULT = os.getenv("ISSUER_NAME_DEFAULT", "letsencrypt")
ISSUER_KIND_DEFAULT = os.getenv("ISSUER_KIND_DEFAULT", "ClusterIssuer")
CERT_GROUP = "cert-manager.io"
CERT_VERSION = "v1"
CERT_KIND = "Certificate"
CERT_PLURAL = "certificates"
CERT_CLEANUP = os.getenv("CERT_CLEANUP", "false").lower() in ("yes", "true", "t", "1")
PATCH_SECRETNAME = os.getenv("PATCH_SECRETNAME", "false").lower() in ("yes", "true", "t", "1")
SUPPORT_LEGACY_CRDS = os.getenv("SUPPORT_LEGACY_CRDS", "true").lower() in ("yes", "true", "t", "1")


def safe_get(obj, keys, default=None):
    """Get a value from the given dict. The key is in json format, separated by a period."""
    v = obj
    for k in keys.split('.'):
        if k not in v:
            return default
        v = v[k]
    return v


def create_certificate(crds, namespace, secretname, routes, cls, annotations):
    """Create or update a cert-manager Certificate per route Rule hosts."""
    # Skip if ignore annotation set
    if annotations.get('cert-manager.io/ignore', '').lower() == 'true':
        logging.info(f"Ignoring {namespace}/{secretname} (ignore=true)")
        return

    # Determine issuerRef priority
    if 'cert-manager.io/cluster-issuer' in annotations:
        issuer_kind = 'ClusterIssuer'
        issuer_name = annotations['cert-manager.io/cluster-issuer']
    elif 'cert-manager.io/issuer' in annotations:
        issuer_kind = annotations.get('cert-manager.io/issuer-kind', 'Issuer')
        issuer_name = annotations['cert-manager.io/issuer']
    else:
        issuer_kind = ISSUER_KIND_DEFAULT
        issuer_name = ISSUER_NAME_DEFAULT

    # Per-route rule certificate
    for route in routes or []:
        if route.get('kind') != 'Rule' or 'Host' not in route.get('match', ''):
            continue

        hostmatch = re.findall(r"Host\(([^\)]*)\)", route["match"])
        hosts = re.findall(r'`([^`]*?)`', ",".join(hostmatch))

        if not hosts:
            logging.info(f"No hosts for {namespace}/{secretname} rule; skipping")
            continue

        logging.info(
            f"Processing {namespace}/{secretname} class={cls or 'none'} "
            f"issuerRef={issuer_kind}/{issuer_name} hosts={hosts}"
        )

        body = {
            'apiVersion': f"{CERT_GROUP}/{CERT_VERSION}",
            'kind': CERT_KIND,
            'metadata': {'name': secretname},
            'spec': {
                'dnsNames': hosts,
                'secretName': secretname,
                'issuerRef': {'name': issuer_name, 'kind': issuer_kind},
            },
        }
        try:
            crds.get_namespaced_custom_object(
                CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname
            )
            crds.patch_namespaced_custom_object(
                CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, body
            )
        except ApiException as e:
            logging.exception(
                "Exception when calling CustomObjectsApi->create_namespaced_custom_object:",
                e,
            )


def delete_certificate(crds, namespace, secretname):
    """Delete a cert-manager Certificate if cleanup is enabled."""
    if CERT_CLEANUP:
        logging.info(f"Removing Certificate {secretname}")
        try:
            crds.delete_namespaced_custom_object(
                CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname
            )
            logging.info(f"Deleted Certificate {secretname}")
        except ApiException as e:
            logging.exception(
                "Exception when calling CustomObjectsApi->delete_namespaced_custom_object:",
                e,
            )


def watch_crd(group, version, plural, use_local_config=False):
    """Watch Traefik IngressRoute CRD and manage certificates."""
    if use_local_config:
        config.load_kube_config()
    else:
        config.load_incluster_config()
    crds = client.CustomObjectsApi()
    resource_version = ''

    logging.info(f"Watching {group}/{version}/{plural}")
    while True:
        try:
            stream = watch.Watch().stream(
                crds.list_cluster_custom_object,
                group=group,
                version=version,
                plural=plural,
                resource_version=resource_version
            )
            for event in stream:
                t = event['type']
                obj = event['object']

                resource_version = safe_get(
                    obj, 'metadata.resourceVersion', resource_version
                )
                namespace = safe_get(obj, 'metadata.namespace')
                name = safe_get(obj, 'metadata.name')
                annotations = obj.get('metadata', {}).get('annotations', {})
                cls = annotations.get('kubernetes.io/ingress.class', '')
                secretname = safe_get(obj, 'spec.tls.secretName')
                routes = safe_get(obj, 'spec.routes')

                # Skip or filter
                if annotations.get('cert-manager.io/ignore', '').lower() == 'true':
                    logging.info(f"Ignoring {namespace}/{name}")
                    continue
                if FILTER_SET and cls not in FILTER_SET:
                    logging.info(f"Skipping {namespace}/{name} ingress.class={cls}")
                    continue

                if t in ('ADDED', 'MODIFIED'):
                    if not secretname and PATCH_SECRETNAME:
                        logging.info(
                            f"{namespace}/{name} : No secretName found, patching"
                        )
                        patch = {'spec': {'tls': {'secretName': name}}}
                        crds.patch_namespaced_custom_object(
                            group, version, namespace, plural, name, patch
                        )
                        secretname = name
                    if secretname:
                        create_certificate(
                            crds,
                            namespace,
                            secretname,
                            routes,
                            cls,
                            annotations
                        )
                    else:
                        logging.info(
                            f"{namespace}/{name} : no secretName found, skipping"
                        )
                elif t == 'DELETED':
                    if not secretname and PATCH_SECRETNAME:
                        secretname = name
                    
                    if secretname:
                        delete_certificate(crds, namespace, secretname)
                    else:
                        logging.info(f"{namespace}/{name} : no secretName found in IngressRoute, skipping delete")
                    
                else:
                    logging.info(f"{namespace}/{name} : unknown event type: {t}")
                    logging.debug(json.dumps(obj, indent=2))

        except Exception as e:
            logging.warning(f"Stream failed: {e}")
            time.sleep(1)
            continue


def exit_gracefully(signum, frame):
    """Handle termination signals and exit cleanly."""
    logging.info(f"Shutting down gracefully on signal: {signum}")
    sys.exit(0)


def main():
    """Parse args, initialize logging, and start watchers."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--local", action="store_true", help="Use local kubeconfig"
    )
    args = parser.parse_args()

    if args.local:
        config.load_kube_config()
    else:
        config.load_incluster_config()

    logging.basicConfig(level=logging.INFO)
    logging.info("Starting traefik-cert-manager")
    logging.info(f"Using cert-manager: {CERT_GROUP}/{CERT_VERSION}/{CERT_PLURAL}")
    logging.info(f"Fallback issuer={ISSUER_KIND_DEFAULT}/{ISSUER_NAME_DEFAULT}")
    logging.info(f"Cleanup enabled={CERT_CLEANUP}")
    logging.info(f"Patch secretName={PATCH_SECRETNAME}")
    logging.info(f"Legacy CRDs Support={SUPPORT_LEGACY_CRDS}")

    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    # Start Traefik CRD watchers
    th1 = threading.Thread(
        target=watch_crd,
        args=(
            "traefik.io",
            "v1alpha1",
            "ingressroutes",
            args.local
        ),
        daemon=True
    )
    th1.start()

    if SUPPORT_LEGACY_CRDS:
        # deprecated traefik CRD
        th2 = threading.Thread(
            target=watch_crd, 
            args=(
                "traefik.containo.us",
                "v1alpha1",
                "ingressroutes",
                args.local
            ),
            daemon=True
        )
        th2.start()

        # wait for threads to finish
        while th1.is_alive() and th2.is_alive():
            th1.join()
            th2.join()
        logging.info(f"traefik.containo.us/v1alpha1/ingressroutes watcher exited {th2.is_alive()}")
    else:
        # wait for threads to finish
        while th1.is_alive():
            th1.join()
    logging.info("Watchers exited")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
