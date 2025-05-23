import argparse
import json
import logging
import os
import re
import signal
import sys
import threading
import time
import uuid
from functools import partial

from dotenv import load_dotenv
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from kubernetes.leaderelection import electionconfig, leaderelection
from kubernetes.leaderelection.resourcelock.configmaplock import ConfigMapLock

__version__ = "2.2.2"


class LeaseFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()

        # only drop the library’s own lease‑acquire log
        if msg.startswith("leader ") and msg.endswith(
            "has successfully acquired lease"
        ):
            return False

        # drop “yet to finish lease_duration, lease held by <anything> and has not expired”
        if re.match(
            r"^yet to finish lease_duration, lease held by .+ and has not expired$", msg
        ):
            return False

        return True


logging.basicConfig(level=logging.INFO)
logging.getLogger().addFilter(LeaseFilter())

# Load environment variables
load_dotenv()

# Configuration
INGRESS_CLASS_FILTER = os.getenv("INGRESS_CLASS_FILTER", "")
FILTER_SET = {c.strip() for c in INGRESS_CLASS_FILTER.split(",") if c.strip()}
ISSUER_NAME_DEFAULT = os.getenv("ISSUER_NAME_DEFAULT", "letsencrypt")
ISSUER_KIND_DEFAULT = os.getenv("ISSUER_KIND_DEFAULT", "ClusterIssuer")
CERT_GROUP = "cert-manager.io"
CERT_VERSION = "v1"
CERT_KIND = "Certificate"
CERT_PLURAL = "certificates"
CERT_CLEANUP = os.getenv("CERT_CLEANUP", "false").lower() in ("yes", "true", "t", "1")
PATCH_SECRETNAME = os.getenv("PATCH_SECRETNAME", "false").lower() in (
    "yes",
    "true",
    "t",
    "1",
)
SUPPORT_LEGACY_CRDS = os.getenv("SUPPORT_LEGACY_CRDS", "true").lower() in (
    "yes",
    "true",
    "t",
    "1",
)

# Global stop event for watcher threads
STOP_EVENT = threading.Event()
USE_LOCAL_CONFIG = False  # set in main()


def get_candidate_id():
    """Generate a unique candidate ID for leader election."""
    # 1) Use the K8s‐injected POD_NAME if present
    pod = os.getenv("POD_NAME")
    if pod:
        return pod

    # 2) Otherwise, fall back to HOSTNAME if set
    host = os.getenv("HOSTNAME")
    if host:
        return host

    # 3) Finally, generate a random local ID
    return f"local-{uuid.uuid4().hex[:8]}"


def safe_get(obj, keys, default=None):
    """Get a nested value from dict using dot-separated keys."""
    v = obj
    for k in keys.split("."):
        if k not in v:
            return default
        v = v[k]
    return v


def reconcile_certificate(
    crds, namespace, name, secretname, routes, annotations, event
):
    """Create or patch Certificate when annotations or hosts change."""
    # Handle missing secretName on tls spec
    # this means we only patch if the secretName is not set
    # while the tls exists in the `spec`, meaning that we are
    # requesting a certificate
    if not secretname and PATCH_SECRETNAME:
        logging.info(
            "%s/%s: patching: no secretName [event=%s]", namespace, name, event
        )
        patch = {"spec": {"tls": {"secretName": name}}}
        crds.patch_namespaced_custom_object(
            CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, name, patch
        )
        secretname = name
    else:
        logging.info(
            "%s/%s: using existing [secretName=%s event=%s]",
            namespace,
            name,
            secretname,
            event,
        )

    # Resolve desired issuerRef
    if "cert-manager.io/cluster-issuer" in annotations:
        desired_kind = "ClusterIssuer"
        desired_name = annotations["cert-manager.io/cluster-issuer"]
    elif "cert-manager.io/issuer" in annotations:
        desired_kind = annotations.get("cert-manager.io/issuer-kind", "Issuer")
        desired_name = annotations["cert-manager.io/issuer"]
    else:
        desired_kind = ISSUER_KIND_DEFAULT
        desired_name = ISSUER_NAME_DEFAULT

    # Collect hosts
    desired_hosts = []
    for route in routes or []:
        if route.get("kind") == "Rule" and "Host" in route.get("match", ""):
            hostmatch = re.findall(r"Host\(([^)]+)\)", route["match"])
            desired_hosts.extend(re.findall(r"`([^`]+)`", ",".join(hostmatch)))
    if not desired_hosts:
        logging.info("%s/%s: no hosts, skipping", namespace, secretname)
        return

    # Desired spec
    desired_spec = {
        "issuerRef": {"name": desired_name, "kind": desired_kind},
        "dnsNames": desired_hosts,
    }

    try:
        # Fetch existing
        cert = crds.get_namespaced_custom_object(
            CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname
        )
        existing = cert.get("spec", {})
        existing_ref = existing.get("issuerRef", {})
        existing_hosts = existing.get("dnsNames", [])
        # Compare
        if (
            existing_ref.get("kind") != desired_kind
            or existing_ref.get("name") != desired_name
            or set(existing_hosts) != set(desired_hosts)
        ):
            # Patch
            patch_body = {"spec": desired_spec}
            crds.patch_namespaced_custom_object(
                CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname, patch_body
            )
            logging.info(
                "Patched Certificate %s (issuerRef %s→%s/%s hosts %s→%s)",
                secretname,
                existing_ref,
                desired_kind,
                desired_name,
                existing_hosts,
                desired_hosts,
            )
        else:
            logging.info("No update required for Certificate %s", secretname)
    except ApiException:
        # Create new
        body = {
            "apiVersion": f"{CERT_GROUP}/{CERT_VERSION}",
            "kind": CERT_KIND,
            "metadata": {"name": secretname},
            "spec": {"secretName": secretname, **desired_spec},
        }
        crds.create_namespaced_custom_object(
            CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, body
        )
        logging.info("Requested Certificate %s for hosts %s", secretname, desired_hosts)


def delete_certificate(crds, namespace, secretname, event):
    """Delete a cert-manager Certificate if cleanup is enabled."""
    if CERT_CLEANUP:
        logging.info(
            "Received remove request [certificate=%s event=%s]", secretname, event
        )
        try:
            crds.delete_namespaced_custom_object(
                CERT_GROUP, CERT_VERSION, namespace, CERT_PLURAL, secretname
            )
            logging.info("Deleted [certificate=%s event=%s]", secretname, event)
        except ApiException as e:
            logging.exception(
                "Exception when calling CustomObjectsApi->delete_namespaced_custom_object: %s",
                e,
            )


def watch_crd(group, version, plural):
    """Watch Traefik IngressRoute CRD and manage certificates."""
    if USE_LOCAL_CONFIG:
        config.load_kube_config()
    else:
        config.load_incluster_config()
    crds = client.CustomObjectsApi()
    resource_version = ""
    logging.info("Watching %s/%s/%s", group, version, plural)

    retry_delay = 1  # initial retry delay

    while not STOP_EVENT.is_set():
        try:
            w = watch.Watch()
            stream = w.stream(
                crds.list_cluster_custom_object,
                group=group,
                version=version,
                plural=plural,
                resource_version=resource_version,
                timeout_seconds=10,
            )
            for event in stream:
                evn = event["type"].upper()
                obj = event["object"]

                resource_version = safe_get(
                    obj, "metadata.resourceVersion", resource_version
                )
                ns = safe_get(obj, "metadata.namespace")
                name = safe_get(obj, "metadata.name")
                annotations = obj.get("metadata", {}).get("annotations", {})
                cls = annotations.get("kubernetes.io/ingress.class", "")
                tls = safe_get(obj, "spec.tls")
                secretname = safe_get(obj, "spec.tls.secretName")
                routes = safe_get(obj, "spec.routes")

                # Skip or filter
                if annotations.get("cert-manager.io/ignore", "").lower() == "true":
                    logging.info(
                        "Skipping %s/%s [reason=annotation-ignore event=%s]",
                        ns,
                        name,
                        evn,
                    )
                    continue

                if FILTER_SET and cls not in FILTER_SET:
                    logging.info(
                        "Skipping %s/%s [reason=not-in-filter ingress.class=%s event=%s]",
                        ns,
                        name,
                        cls,
                        evn,
                    )
                    continue

                if not tls:
                    logging.info(
                        "Skipping %s/%s [reason=no-tls event=%s]", ns, name, evn
                    )
                    continue

                if evn in ("ADDED", "MODIFIED"):
                    reconcile_certificate(
                        crds, ns, name, secretname, routes, annotations, evn
                    )
                elif evn == "DELETED":
                    delete_certificate(crds, ns, name, evn)
                else:
                    logging.info("%s/%s: unknown event type: %s", name, ns, evn)
                    logging.debug(json.dumps(obj, indent=2))

            retry_delay = 1  # reset delay after successful stream

        except ApiException as e:
            if e.status == 410:
                logging.warning(
                    "Resource version expired (410), resetting to latest..."
                )
                resource_version = ""
            else:
                logging.warning("ApiException when watching: %s", e)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)  # exponential backoff up to 60s

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.warning("Unexpected exception during watch: %s", e)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)  # exponential backoff up to 60s

    logging.info("Watcher for %s/%s/%s exiting", group, version, plural)


def on_started_leading(candidate_id):
    """Start watchers when elected leader."""
    logging.info("%s has become leader, starting watchers", candidate_id)
    STOP_EVENT.clear()
    threading.Thread(
        target=watch_crd, args=("traefik.io", "v1alpha1", "ingressroutes"), daemon=True
    ).start()

    if SUPPORT_LEGACY_CRDS:
        # deprecated traefik CRD
        threading.Thread(
            target=watch_crd,
            args=("traefik.containo.us", "v1alpha1", "ingressroutes"),
            daemon=True,
        ).start()


def on_stopped_leading():
    """Stop watchers on leadership loss."""
    logging.info("Lost leadership, stopping watchers")
    STOP_EVENT.set()


def exit_gracefully(signum, frame):  # pylint: disable=unused-argument
    """Handle termination signals and exit cleanly."""
    logging.info(
        "Signal received, shutting down [signal=%s]", signal.Signals(signum).name
    )
    STOP_EVENT.set()
    sys.exit(0)


def main():
    """Parse args, initialize logging, and start leader election."""
    global USE_LOCAL_CONFIG  # pylint: disable=global-statement,global-variable-not-assigned
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Use local kubeconfig")
    args = parser.parse_args()

    USE_LOCAL_CONFIG = args.local
    if args.local:
        config.load_kube_config()
    else:
        config.load_incluster_config()

    logging.info("Starting traefik-cert-manager [version=%s]", __version__)
    logging.info("cert-manager: %s/%s/%s", CERT_GROUP, CERT_VERSION, CERT_PLURAL)
    logging.info("options.ingressClassFilter=%s", INGRESS_CLASS_FILTER)
    logging.info("options.issuer.default.name=%s", ISSUER_NAME_DEFAULT)
    logging.info("options.issuer.default.kind=%s", ISSUER_KIND_DEFAULT)
    logging.info("options.certCleanup=%s", CERT_CLEANUP)
    logging.info("options.patchSecretName=%s", PATCH_SECRETNAME)
    logging.info("options.supportLegacyCRDs=%s", SUPPORT_LEGACY_CRDS)

    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    candidate_id = get_candidate_id()
    namespace = os.getenv("POD_NAMESPACE", "default")
    lock = ConfigMapLock("traefik-cert-manager-leader-lock", namespace, candidate_id)
    onstart = partial(on_started_leading, candidate_id)

    le_cfg = electionconfig.Config(
        lock,
        lease_duration=17,
        renew_deadline=15,
        retry_period=5,
        onstarted_leading=onstart,
        onstopped_leading=on_stopped_leading,
    )

    logging.info("Starting leader election")
    try:
        leaderelection.LeaderElection(le_cfg).run()
    except KeyboardInterrupt:
        logging.info("Shutting down [SIGINT]")
        STOP_EVENT.set()

    # Wait for watcher threads to exit
    STOP_EVENT.wait()
    logging.info("Shutdown completed")


if __name__ == "__main__":
    main()
