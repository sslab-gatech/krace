from typing import Optional

import os

from util import Singleton


class Option(metaclass=Singleton):

    def __init__(self) -> None:
        self._flavor = os.environ.get('F', None)  # type: Optional[str]
        self._intent = os.environ.get('I', None)  # type: Optional[str]
        self._action = os.environ.get('A', None)  # type: Optional[str]
        self._tag = os.environ.get('T', None)  # type: Optional[str]

    # single properties
    @property
    def flavor(self) -> str:
        assert self._flavor is not None
        return self._flavor

    @flavor.setter
    def flavor(self, value: str) -> None:
        assert self._flavor is None
        self._flavor = value

    @property
    def intent(self) -> str:
        assert self._intent is not None
        return self._intent

    @intent.setter
    def intent(self, value: str) -> None:
        assert self._intent is None
        self._intent = value

    @property
    def action(self) -> str:
        assert self._action is not None
        return self._action

    @action.setter
    def action(self, value: str) -> None:
        assert self._action is None
        self._action = value

    @property
    def tag(self) -> str:
        assert self._tag is not None
        return self._tag

    @tag.setter
    def tag(self, value: str) -> None:
        assert self._tag is None
        self._tag = value

    # composed properties
    @property
    def shape(self) -> str:
        return '-'.join([self.flavor, self.intent])

    @property
    def label(self) -> str:
        return '-'.join([self.flavor, self.intent, self.action])
