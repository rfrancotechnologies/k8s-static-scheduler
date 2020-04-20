# Static Scheduler for Kubernetes

This is an static scheduler for kubernetes.

Usually the default kubernetes scheduler is good enough for our requirements, but for databases like Postgres, Mysql/MariaDB, ... it is a pain: you cannot know where your pods are going to run and if they are going to find their previous data.

Using StatefulSets is not enough, because each POD will be exactly equal than others and after a big problem it could shuffle the executions.

So, this static scheduler is useful in these cases.

## How it works

Run it wherever you want: inside kubernetes in any namespace or outside. It doesn't matter but running it as deployment is recommended.

One important thing is to set a name for the scheduler, so you can run more than one instance if required.

Then, you have to mark your StatefulSets to use this scheduler with the `.spec.template.spec.schedulerName`, or your PODs in general with `.spec.schedulerName`. This will prevent the default scheduler to manage them.

After doing this, PODs will stay in `Pending` state.

Then you can label a node to manage the pod with the label `rf.scheduler.<SCHEDULER_NAME>.<NAMESPACE>/<POD NAME>` to empty value, and the POD will be scheduled always to that node.

## Configuration

It can be configured by command line (check the help) or with these environment variables:

- KUBECONFIG: Path to the kubeconfig file.
- SCHED_INCLUSTER_BASE_PATH: Path to search for token and CA. `/var/run/secrets/kubernetes.io/serviceaccount` by default.
- SCHED_NAME: Scheduler name, to avoid collision.
- SCHED_DELAY: Time to sleep between checks.
- SCHED_PROMETHEUS_PORT: Port to expose prometheus metrics.
- SCHED_PROMETHEUS: Disables prometheus metrics if its value is "false".

### In Cluster

It can be run in-cluster. If the token is mounted in the default directory `/var/run/secrets/kubernetes.io/service`, no aditional configuration is required, so just leave the `KUBECONFIG` and `SCHED_INCLUSTER_BASE_PATH` variables undefined.

Anyways, it will require valid permisions, that can be created with something like this:

```
apiVersion: v1
kind: Namespace
metadata:
  name: rfscheduler
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: rfscheduler
  namespace: rfscheduler
automountServiceAccountToken: true
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  annotations:
    rbac.authorization.kubernetes.io/autoupdate: "true"
  name: rfscheduler
  namespace: rfscheduler
rules:
- apiGroups:
  - ""
  resources:
  - nodes
  verbs:
  - list
- apiGroups:
  - ""
  resources:
  - pods
  verbs:
  - list
- apiGroups:
  - ""
  resources:
  - pods/binding
  verbs:
  - create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: rfscheduler
roleRef:
  apiGroup: ""
  kind: ClusterRole
  name: rfscheduler
subjects:
- kind: ServiceAccount
  name: rfscheduler
  namespace: rfscheduler
```

This example will use the `rfscheduler` namespace, but any other can be used. The example is requiring minimum permissions.

## Full Example

We can create a new kubernetes cluster locally with [kind](https://kind.sigs.k8s.io/). To to this, we will use the file "example/kind.yaml":


```
$ kind create cluster --config example/kind.yaml
Creating cluster "kind" ...
 ✓ Ensuring node image (kindest/node:v1.15.3) 🖼
 ✓ Preparing nodes 📦📦
 ✓ Creating kubeadm config 📜
 ✓ Starting control-plane 🕹️
 ✓ Installing CNI 🔌
 ✓ Installing StorageClass 💾
 ✓ Joining worker nodes 🚜
Cluster creation complete. You can now use the cluster with:

export KUBECONFIG="$(kind get kubeconfig-path --name="kind")"
kubectl cluster-info
```

So, we can export the KUBECONFIG variable to use it:

```
export KUBECONFIG="$(kind get kubeconfig-path --name="kind")"
```

Now we can deploy the example StatefulSet at "example/statefulset.yaml":

```
kubectl apply -f example/statefulset.yaml
```

And it will be running but not assigned to any node:

```
$ kubectl get pods
NAME    READY   STATUS    RESTARTS   AGE
web-0   0/1     Pending   0          8s
```


Now we can label a node as 'rf.scheduler.test/web-0':

```
kubectl label node kind-worker rf.scheduler.test/web-0=whatever
```

And, finally, run our scheduler. This can be done inside a virtual environment:

```
$ python3 -m venv venv
$ . venv/bin/activate
(venv) $ pip install -r requirements.txt
(venv) $
```

And then just ran:

```
(venv) $ ./scheduler.py --name test
```

The pod will be scheduled on worker node and the new one will wait for a labeled node:

```
$ kubectl get pods
NAME    READY   STATUS              RESTARTS   AGE
web-0   0/1     ContainerCreating   0          5m10s
$ kubectl get pods -o wide
NAME    READY   STATUS    RESTARTS   AGE     IP           NODE          NOMINATED NODE   READINESS GATES
web-0   1/1     Running   0          6m21s   10.244.1.2   kind-worker   <none>           <none>
web-1   0/1     Pending   0          71s     <none>       <none>        <none>           <none>
```

Just a chance matter? Well... let's schedule our three pods to the worker:

```
kubectl label node kind-worker rf.scheduler.test/web-1=whatever rf.scheduler.test/web-2=whatever
```

And schedule them:

```
(venv) $ ./scheduler.py --name test
```

It will be required to schedule several times, because web-1 and web-2 will not be Pending at the same time. But finally:

```
$ kubectl get pods -o wide
NAME    READY   STATUS    RESTARTS   AGE     IP           NODE          NOMINATED NODE   READINESS GATES
web-0   1/1     Running   0          9m35s   10.244.1.2   kind-worker   <none>           <none>
web-1   1/1     Running   0          4m25s   10.244.1.3   kind-worker   <none>           <none>
web-2   1/1     Running   0          47s     10.244.1.4   kind-worker   <none>           <none>
```

## Example 2: Running as daemon

We will continue the previous example, but now we need two windows.

In one of them we will run the scheduler. It has two requirements: to be inside our virtual environment and the KUBECONFIG environment variable defined:

```
(venv) $ ./scheduler.py --name test --daemon -vv
```

In the other window we will remove all previous labels from worker:

```
kubectl label node kind-worker rf.scheduler.test/web-0- rf.scheduler.test/web-1- rf.scheduler.test/web-2-
```

And relabel the mater node:

```
kubectl label node kind-control-plane rf.scheduler.test/web-0=a rf.scheduler.test/web-1=a rf.scheduler.test/web-2=a
```

But nothing happens. This is because we need now to delete the pods to force them to be re-scheduled:

```
kubectl delete pod -l app=nginx
```

After some seconds, the scheduler will do its work:

```
(venv) $ $ ./scheduler.py --name test --daemon -vv
2020-04-03 13:29:47,153 - __main__ - INFO - Pod web-0 scheduled on node kind-control-plane
2020-04-03 13:30:17,293 - __main__ - INFO - Pod web-1 scheduled on node kind-control-plane
2020-04-03 13:30:27,343 - __main__ - INFO - Pod web-2 scheduled on node kind-control-plane
```

## Running tests

Recommended way is installing `pytest` and `pytest-cov` and running them with this line:

```
(venv) $ pip install pytest pytest-cov
(venv) $ pytest . -v --cov scheduler --cov-report term-missing
```

## Prometheus compliant

By default, the scheduler exposes Prometheus metrics at port 8000, despite it can be modified. Any path will receive the metrics.

In order to check if it is working properly, next indices can be used:
- schedule_request_total: total scheduling requests
- schedule_request_success_total: total scheduling success responses
- schedule_request_failure_total: total scheduling failed responses

Example:

```
schedule_request_total{namespace="default",node="kind-control-plane",pod="web-0",scheduler="test"} 1.0
# TYPE schedule_request_created gauge
schedule_request_created{namespace="default",node="kind-control-plane",pod="web-0",scheduler="test"} 1.5859144423931713e+09
# HELP schedule_request_success_total Binding successful requests
# TYPE schedule_request_success_total counter
schedule_request_success_total{namespace="default",node="kind-control-plane",pod="web-0",scheduler="test"} 1.0
# TYPE schedule_request_success_created gauge
schedule_request_success_created{namespace="default",node="kind-control-plane",pod="web-0",scheduler="test"} 1.5859144424013667e+09
# HELP schedule_request_failure_total Binding failed requests
# TYPE schedule_request_failure_total counter
```
