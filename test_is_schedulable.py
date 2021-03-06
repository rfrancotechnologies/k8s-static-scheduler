from unittest.mock import MagicMock, PropertyMock

from faker import Faker
from scheduler import Scheduler

fake = Faker()


class FakeDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def test_pod_schedulable():
    pod = FakeDict(
        spec=FakeDict(scheduler_name="foo", node_name=None,),
        metadata=FakeDict(namespace="default",),
    )

    s = Scheduler("foo", None)
    assert s.is_schedulable(pod)


def test_pod_schedulable_but_already_scheduled():
    pod = FakeDict(
        spec=FakeDict(scheduler_name="foo", node_name="bar",),
        metadata=FakeDict(namespace="default",),
    )

    s = Scheduler("foo", None)
    assert not s.is_schedulable(pod)


def test_pod_missing_scheduler_name():
    pod = FakeDict(
        spec=FakeDict(node_name=None,), metadata=FakeDict(namespace="default",),
    )

    s = Scheduler("foo", None)
    assert not s.is_schedulable(pod)


def test_pod_missing_node_name():
    pod = FakeDict(
        spec=FakeDict(scheduler_name="foo",), metadata=FakeDict(namespace="default",),
    )

    s = Scheduler("foo", None)
    assert s.is_schedulable(pod)
