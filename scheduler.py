#!/usr/bin/env python
import os
import sys
import time
import random
import argparse
import logging
import kubernetes
from prometheus_client import start_http_server, Counter

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
        "name", help="Scheduler name, to avoid collision"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity"
    )
    parser.add_argument(
        "--kubeconfig",
        default=os.getenv('KUBECONFIG', '~/.kube/config'),
        help="Path to kubeconfig file."
    )
    parser.add_argument(
        "-d", "--daemon", 
        default=False,
        action="store_true",
        help="Run forever"
    )
    parser.add_argument(
        "--delay", 
        default=10, 
        type=float, 
        help="time to wait between schedulings"
    )
    parser.add_argument(
        "-n", "--namespace", 
        default=os.getenv("SCHED_NAMESPACES", "default").split(','), 
        nargs="*", 
        help="namespaces to be managed"
    )
    parser.add_argument(
        "--prometheus-port", 
        default=int(os.getenv("SCHED_PROMETHEUS_PORT", 8000)), 
        type=int, 
        help="Prometheus Exporter port"
    )
    parser.add_argument(
        "--prometheus-disable", 
        action="store_true", 
        default=os.getenv("SCHED_PROMETHEUS", "true")=="false", help="Prometheus Exporter disable"
    )
    return parser.parse_args()


class Scheduler:
    def __init__(self, name, namespaces, kubernetes_client):
        self.name = name
        self.namespaces = namespaces
        self.kclient = kubernetes_client

    def is_schedulable(self, pod):
        try:
            if pod.spec.scheduler_name != self.name:
                return False
            if getattr(pod.spec, "node_name", None) is not None:
                return False
            if pod.metadata.namespace not in self.namespaces:
                return False
        except:
            return False
        return True

    def run(self):
        for pod in self.kclient.get_pods():
            if not self.is_schedulable(pod):
                continue
            podname = pod.metadata.name
            logger.debug("Scheduling pod %s" % podname)
            label = "rf.scheduler.{name}/{pod}".format(name=self.name, pod=podname)
   
            nodes = self.kclient.get_nodes()
            random.shuffle(nodes)
            for node in nodes:
                nodename = node.metadata.name
                logger.debug("Checking node {node}".format(node=nodename))
                if label in node.metadata.labels:
                    self.kclient.schedule(pod=pod, node=node)
                    break
                else:
                    logger.debug("Pod {pod} is not schedulable on {node}".format(pod=podname, node=nodename))


class KubernetesClient:
    def __init__(self, name, kubeconfig):
        self.name = name
        kubernetes.config.load_kube_config(config_file=kubeconfig)
        self.v1 = kubernetes.client.CoreV1Api()
        self.client = kubernetes.client.ApiClient()
        self.counter_total = Counter("schedule_request_total", "Total binding requests", ['pod', 'node', 'scheduler', 'namespace'])
        self.counter_success = Counter("schedule_request_success", "Binding successful requests", ['pod', 'node', 'scheduler', 'namespace'])
        self.counter_failure = Counter("schedule_request_failure", "Binding failed requests", ['pod', 'node', 'scheduler', 'namespace'])
       
    def get_nodes(self): 
        return self.v1.list_node().items

    def get_pods(self):
        return self.v1.list_pod_for_all_namespaces().items

    def schedule(self, pod, node):
        podname = pod.metadata.name
        nodename = node.metadata.name
        namespace = pod.metadata.namespace
        logger.debug("Scheduling pod {node} on node {node}".format(node=nodename, pod=podname))
        self.counter_total.labels(pod=podname, node=nodename, scheduler=self.name, namespace=namespace).inc()
        params = {
            "apiVersion": "v1",
            "kind": "Binding",
            "metadata": {
                "name": podname,
            },
            "target": {
                "apiVersion": "v1",
                "kind": "Node",
                "name": nodename,
            },
        }
        try:
            r = self.client.call_api(
                '/api/v1/namespaces/{ns}/pods/{pod}/binding/'.format(ns=namespace, pod=podname),
                'POST',
                body=params
            )
            if 200 <= r[1] <= 201:
                self.counter_success.labels(pod=podname, node=nodename, scheduler=self.name, namespace=namespace).inc()
                logger.info("Pod {pod} scheduled on node {node}".format(node=nodename, pod=podname))
                return True
            else:
                logger.warning("Pod {pod} scheduled on node {node}".format(node=nodename, pod=podname))
                self.counter_failure.labels(pod=podname, node=nodename, scheduler=self.name, namespace=namespace).inc()
        except:
            logger.exception("Pod {pod} could not be scheduled on node {node}".format(node=nodename, pod=podname))
            self.counter_failure.labels(pod=podname, node=nodename, scheduler=self.name, namespace=namespace).inc()
        return False


def main():
    args = parse_args()
    configure_logging(args.verbose)
    logger.debug("Arguments: {args}".format(args=args))
   
    if not args.prometheus_disable:
        logger.debug("Starting prometheus exporter on {port}".format(port=args.prometheus_port))
        start_http_server(args.prometheus_port)

    kclient =  KubernetesClient(args.name, args.kubeconfig)
    scheduler = Scheduler(args.name, args.namespace, kclient)
    while True:
        logger.debug("Running scheduler")
        scheduler.run()
        if not args.daemon:
            break
        logger.debug("Scheduler finished. Sleeping for {delay}".format(delay=args.delay))
        time.sleep(args.delay)

if __name__ == "__main__":
    main()
