from unittest.mock import MagicMock, patch
from scheduler import Scheduler

from faker import Faker
fake = Faker()


class FakeDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def test_no_pods():
    name = fake.name()
    client = MagicMock()
    
    s = Scheduler(name, ["default"], client)
    s.run()
    client.get_pods.assert_called()
    assert client.get_nodes.mock_calls== []
    assert client.schedule.mock_calls == []

def test_pod_no_schedulable():
    name = fake.name()
    pod = FakeDict(
        spec=FakeDict(
            scheduler_name="another",
            node_name=None,
        ),
        metadata=FakeDict(
            namespace="default",
            name="pod1",
        ),
    )
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    
    s = Scheduler(name, ["default"], client)
    s.run()
    client.get_pods.assert_called()
    assert client.get_nodes.mock_calls == []
    assert client.schedule.mock_calls == []

def test_pod_but_no_nodes():
    name = fake.name()
    pod = FakeDict(
        spec=FakeDict(
            scheduler_name=name,
            node_name=None,
        ),
        metadata=FakeDict(
            namespace="default",
            name="pod1",
        ),
    )
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    
    s = Scheduler(name, ["default"], client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    assert client.schedule.mock_calls == []

def test_pod_and_unlabeled():
    name = fake.name()
    pod = FakeDict(
        spec=FakeDict(
            scheduler_name=name,
            node_name=None,
        ),
        metadata=FakeDict(
            namespace="default",
            name="pod1",
        ),
    )
    node = FakeDict(
        metadata=FakeDict(
            name="node1",
            labels={},
        )
    )
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    client.get_nodes = MagicMock(return_value=[node])
    
    s = Scheduler(name, ["default"], client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    assert client.schedule.mock_calls == []

def test_pod_and_labeled():
    name = fake.name()
    podname = "pod1"
    nodename = "node1"
    labels = {}
    labels["rf.scheduler.{name}/{pod}".format(name=name, pod=podname)] = "whatever"
    pod = FakeDict(
        spec=FakeDict(
            scheduler_name=name,
            node_name=None,
        ),
        metadata=FakeDict(
            namespace="default",
            name=podname,
        ),
    )
    node = FakeDict(
        metadata=FakeDict(
            name=nodename,
            labels=labels,
        )
    )
    client = MagicMock()
    client.get_pods = MagicMock(return_value=[pod])
    client.get_nodes = MagicMock(return_value=[node])
    
    s = Scheduler(name, ["default"], client)
    s.run()
    client.get_pods.assert_called()
    client.get_nodes.assert_called()
    client.schedule.called_with(pod, node)
