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
    """Get a nested value from dict using dot-separated keys."""
    v = obj
    for k in keys.split('.'):
        if k not in v:
            return default
        v = v[k]
    return v


def reconcile_certificate(crds, namespace, name, secretname, routes, annotations):
    """Create or patch Certificate when annotations or hosts change."""
    # Skip if ignore annotation set
    if annotations.get('cert-manager.io/ignore', '').lower() == 'true':
        logging.info(f"Ignoring {namespace}/{secretname} (ignore=true)")
        return

    # Handle missing secretName
    if not secretname and PATCH_SECRETNAME:
        logging.info(f"{namespace}/{name}: no secretName, patching")
        patch = {'spec': {'tls': {'secretName': name}}}
        crds.patch_namespaced_custom_object(
            CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, name, patch
        )
        secretname = name
    else:
        logging.info(f"{namespace}/{name}: no secretName, skipping")
        return

    # Resolve desired issuerRef
    if 'cert-manager.io/cluster-issuer' in annotations:
        desired_kind = 'ClusterIssuer'
        desired_name = annotations['cert-manager.io/cluster-issuer']
    elif 'cert-manager.io/issuer' in annotations:
        desired_kind = annotations.get('cert-manager.io/issuer-kind', 'Issuer')
        desired_name = annotations['cert-manager.io/issuer']
    else:
        desired_kind = ISSUER_KIND_DEFAULT
        desired_name = ISSUER_NAME_DEFAULT

    # Collect hosts
    desired_hosts = []
    for route in routes or []:
        if route.get('kind') == 'Rule' and 'Host' in route.get('match', ''):
            hostmatch = re.findall(r"Host\(([^)]+)\)", route['match'])
            desired_hosts.extend(re.findall(r'`([^`]+)`', ','.join(hostmatch)))
    if not desired_hosts:
        logging.info(f"{namespace}/{secretname}: no hosts, skipping")
        return

    # Desired spec
    desired_spec = {
        'issuerRef': {'name': desired_name, 'kind': desired_kind},
        'dnsNames': desired_hosts,
    }

    try:
        # Fetch existing
        cert = crds.get_namespaced_custom_object(
            CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname
        )
        existing = cert.get('spec', {})
        existing_ref = existing.get('issuerRef', {})
        existing_hosts = existing.get('dnsNames', [])
        # Compare
        if (existing_ref.get('kind') != desired_kind or
                existing_ref.get('name') != desired_name or
                set(existing_hosts) != set(desired_hosts)):
            # Patch
            patch_body = {'spec': desired_spec}
            crds.patch_namespaced_custom_object(
                CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname, patch_body
            )
            logging.info(
                f"Patched Certificate {secretname} (issuerRef {existing_ref}→{desired_kind}/{desired_name}; "
                f"hosts {existing_hosts}→{desired_hosts})"
            )
        else:
            logging.info(f"No update required for Certificate {secretname}")
    except ApiException:
        # Create new
        body = {
            'apiVersion': f"{CERT_GROUP}/{CERT_VERSION}",
            'kind': CERT_KIND,
            'metadata': {'name': secretname},
            'spec': {'secretName': secretname, **desired_spec}
        }
        crds.create_namespaced_custom_object(
            CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, body
        )
        logging.info(f"Requested Certificate {secretname} for hosts {desired_hosts}")


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
                "Exception when calling CustomObjectsApi->delete_namespaced_custom_object:", e
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
                group=group, version=version, plural=plural,
                resource_version=resource_version
            )
            for event in stream:
                t = event['type']
                obj = event['object']

                resource_version = safe_get(
                    obj, 'metadata.resourceVersion', resource_version
                )
                ns = safe_get(obj, 'metadata.namespace')
                name = safe_get(obj, 'metadata.name')
                annotations = obj.get('metadata', {}).get('annotations', {})
                cls = annotations.get('kubernetes.io/ingress.class', '')
                secretname = safe_get(obj, 'spec.tls.secretName')
                routes = safe_get(obj, 'spec.routes')

                # Skip or filter
                if annotations.get('cert-manager.io/ignore', '').lower() == 'true':
                    logging.info(f"Ignoring {ns}/{name}")
                    continue
                if FILTER_SET and cls not in FILTER_SET:
                    logging.info(f"Skipping {ns}/{name} ingress.class={cls}")
                    continue

                if t in ('ADDED', 'MODIFIED'):
                    reconcile_certificate(
                        crds, ns, name, secretname, routes, annotations
                    )
                elif t == 'DELETED':
                    delete_certificate(crds, ns, name)
                else:
                    logging.info(f"{ns}/{name} : unknown event type: {t}")
                    logging.debug(json.dumps(obj, indent=2))

        except Exception as e:
            logging.warning(f"Stream failed: {e}")
            time.sleep(1)
            continue


def exit_gracefully(signum, frame):
    """Handle termination signals and exit cleanly."""
    logging.info(f"Shutting down gracefully on signal: {signal.Signals(signum).name}")
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
    logging.info("Exiting")
    sys.exit(0)
