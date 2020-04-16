from unittest.mock import MagicMock, patch

from faker import Faker
from scheduler import Scheduler

fake = Faker()


class FakeDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def test_label_for_pod():
    name = "myscheduler"
    pod = FakeDict(
        spec=FakeDict(node_name="whatever",),
        metadata=FakeDict(namespace="default", name="pod1",),
    )
    client = MagicMock()

    s = Scheduler(name, client)
    label = s.label_for_pod(pod)
    assert "rf.scheduler.myscheduler.default/pod1" == label


def test_no_pods():
    name = fake.name()
    client = MagicMock()

    s = Scheduler(name, client)
    s.run()
    client.get_pods.assert_called()
    assert client.get_nodes.mock_calls == []
    assert client.schedule.mock_calls == []


def test_pod_no_schedulable():
    name = fake.name()
    pod = FakeDict(
        spec=FakeDict(scheduler_name="another", node_name=None,),
        metadata=FakeDict(namespace="default", name="pod1",),
    )
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])

    s = Scheduler(name, client)
    s.run()
    client.get_pods.assert_called()
    assert client.get_nodes.mock_calls == []
    assert client.schedule.mock_calls == []


def test_pod_but_no_nodes():
    name = fake.name()
    pod = FakeDict(
        spec=FakeDict(scheduler_name=name, node_name=None,),
        metadata=FakeDict(namespace="default", name="pod1",),
    )
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])

    s = Scheduler(name, client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    assert client.schedule.mock_calls == []


def test_pod_and_unlabeled():
    name = fake.name()
    pod = FakeDict(
        spec=FakeDict(scheduler_name=name, node_name=None,),
        metadata=FakeDict(namespace="default", name="pod1",),
    )
    node = FakeDict(metadata=FakeDict(name="node1", labels={},))
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    client.get_nodes = MagicMock(return_value=[node])

    s = Scheduler(name, client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    assert client.schedule.mock_calls == []


def test_pod_and_labeled():
    name = fake.name()
    podname = "pod1"
    nodename = "node1"
    namespace = "default"
    labels = {}
    labels[
        "rf.scheduler.{name}.{ns}/{pod}".format(ns=namespace, name=name, pod=podname)
    ] = ""
    pod = FakeDict(
        spec=FakeDict(scheduler_name=name, node_name=None,),
        metadata=FakeDict(namespace=namespace, name=podname,),
    )
    node = FakeDict(metadata=FakeDict(name=nodename, labels=labels,))
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    client.get_nodes = MagicMock(return_value=[node])

    s = Scheduler(name, client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    assert client.schedule.called_with(pod, node)


def test_pod_and_labeled_incorrectly():
    name = fake.name()
    podname = "pod1"
    nodename = "node1"
    namespace = "default"
    labels = {}
    labels[
        "rf.scheduler.{name}.{ns}/{pod}-invalid".format(
            ns=namespace, name=name, pod=podname
        )
    ] = ""
    pod = FakeDict(
        spec=FakeDict(scheduler_name=name, node_name=None,),
        metadata=FakeDict(namespace=namespace, name=podname,),
    )
    node = FakeDict(metadata=FakeDict(name=nodename, labels=labels,))
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    client.get_nodes = MagicMock(return_value=[node])

    s = Scheduler(name, client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    assert client.schedule.mock_calls == []
