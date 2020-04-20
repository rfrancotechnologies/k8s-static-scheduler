#!/usr/bin/env python
import argparse
import logging
import os
import random
import sys
import time

import kubernetes
from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def configure_logging(verbosity):
    msg_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    VERBOSITIES = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]
    level = VERBOSITIES[min(int(verbosity), len(VERBOSITIES) - 1)]
    formatter = logging.Formatter(msg_format)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)


def parse_args():
    parser = argparse.ArgumentParser(description="Custom scheduler for Kubernetes PODs")
    parser.add_argument(
        "--name",
        default=os.getenv("SCHED_NAME", "rfcustom"),
        help="Scheduler name, to avoid collision",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase verbosity"
    )
    parser.add_argument(
        "--kubeconfig",
        default=os.getenv("KUBECONFIG", ""),
        help="Path to kubeconfig file.",
    )
    parser.add_argument(
        "--incluster-base-path",
        default=os.getenv("SCHED_INCLUSTER_BASE_PATH", ""),
        help="Path to directory containing the token.",
    )
    parser.add_argument(
        "-d", "--daemon", default=False, action="store_true", help="Run forever"
    )
    parser.add_argument(
        "--delay",
        default=float(os.getenv("SCHED_DELAY", 10)),
        type=float,
        help="time to wait between schedulings",
    )
    parser.add_argument(
        "--prometheus-port",
        default=int(os.getenv("SCHED_PROMETHEUS_PORT", 8000)),
        type=int,
        help="Prometheus Exporter port",
    )
    parser.add_argument(
        "--prometheus-disable",
        action="store_true",
        default=os.getenv("SCHED_PROMETHEUS", "true") == "false",
        help="Prometheus Exporter disable",
    )
    result = parser.parse_args()

    return result


class Scheduler:
    def __init__(self, name, kubernetes_client):
        self.name = name
        self.kclient = kubernetes_client

    def is_schedulable(self, pod):
        try:
            if pod.spec.scheduler_name != self.name:
                return False
            if getattr(pod.spec, "node_name", None) is not None:
                return False
        except:
            return False
        return True

    def label_for_pod(self, pod):
        return "rf.scheduler.{scheduler}.{namespace}/{pod}".format(
            namespace=pod.metadata.namespace,
            scheduler=self.name,
            pod=pod.metadata.name,
        )

    def run(self):
        for pod in self.kclient.get_pods():
            if not self.is_schedulable(pod):
                continue
            podname = pod.metadata.name
            namespace = pod.metadata.namespace
            logger.debug("Scheduling pod %s" % podname)
            label = self.label_for_pod(pod)

            nodes = self.kclient.get_nodes()
            random.shuffle(nodes)
            for node in nodes:
                nodename = node.metadata.name
                logger.debug("Checking node {node}".format(node=nodename))
                if label in node.metadata.labels:
                    self.kclient.schedule(pod=pod, node=node)
                    break
                else:
                    logger.debug(
                        "Pod {pod} is not schedulable on {node}".format(
                            pod=podname, node=nodename
                        )
                    )


class KubernetesClient:
    def __init__(self, name, kubeconfig, token_path):
        token_path = token_path or "/var/run/secrets/kubernetes.io/serviceaccount"
        self.name = name
        if kubeconfig and os.path.exists(kubeconfig):
            logger.debug("Using configuration from kubeconfig %s" % kubeconfig)
            kubernetes.config.load_kube_config(config_file=kubeconfig)
        elif os.path.exists(token_path):
            logger.debug("Using configuration from token in %s" % token_path)
            loader = kubernetes.config.incluster_config.InClusterConfigLoader(
                os.path.join(token_path, "token"), os.path.join(token_path, "ca.crt"),
            )
            loader.load_and_set()
        else:
            raise Exception("No kubeconfig or token found")

        if True or token_file:
            loader = kubernetes.config.incluster_config.InClusterConfigLoader(
                "/var/run/secrets/kubernetes.io/serviceaccount/token",
                "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
            )
            configuration = kubernetes.client.Configuration()
            configuration.host = "https://192.168.1.10:6443"
            loader.load_and_set()

        self.v1 = kubernetes.client.CoreV1Api()
        self.client = kubernetes.client.ApiClient()
        self.counter_total = Counter(
            "schedule_request_total",
            "Total binding requests",
            ["pod", "node", "scheduler", "namespace"],
        )
        self.counter_success = Counter(
            "schedule_request_success",
            "Binding successful requests",
            ["pod", "node", "scheduler", "namespace"],
        )
        self.counter_failure = Counter(
            "schedule_request_failure",
            "Binding failed requests",
            ["pod", "node", "scheduler", "namespace", "http_status", "reason"],
        )

    def get_nodes(self):
        return self.v1.list_node().items

    def get_pods(self):
        return self.v1.list_pod_for_all_namespaces().items

    def schedule(self, pod, node):
        nodename = node.metadata.name
        namespace = pod.metadata.namespace
        podname = pod.metadata.name

        self.counter_total.labels(
            pod=podname, node=nodename, scheduler=self.name, namespace=namespace
        ).inc()

        object_ref = kubernetes.client.V1ObjectReference(kind="Node", name=nodename)
        metadata = kubernetes.client.V1ObjectMeta(name=podname)
        body = kubernetes.client.V1Binding(
            kind="Binding", metadata=metadata, target=object_ref
        )
        result = self.v1.create_namespaced_pod_binding(
            name=podname, namespace=namespace, body=body, _preload_content=False,
        )
        if 200 <= result.status < 300:
            self.counter_success.labels(
                pod=podname, node=nodename, scheduler=self.name, namespace=namespace
            ).inc()
        else:
            self.counter_failure.labels(
                pod=podname,
                node=nodename,
                scheduler=self.name,
                namespace=namespace,
                http_status=result.status,
                reason=result.reason,
            ).inc()

        return result


def main():
    args = parse_args()
    configure_logging(args.verbose)
    logger.debug("Arguments: {args}".format(args=args))

    if not args.prometheus_disable:
        logger.debug(
            "Starting prometheus exporter on {port}".format(port=args.prometheus_port)
        )
        start_http_server(args.prometheus_port)

    kclient = KubernetesClient(args.name, args.kubeconfig, args.incluster_base_path)
    scheduler = Scheduler(args.name, kclient)
    while True:
        logger.debug("Running scheduler")
        scheduler.run()
        if not args.daemon:
            break
        logger.debug(
            "Scheduler finished. Sleeping for {delay}".format(delay=args.delay)
        )
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
