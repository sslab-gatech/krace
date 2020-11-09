from typing import cast, Any, Type, TypeVar, Generic, Set, Dict, Optional, \
    no_type_check

from enum import Enum

from collections import OrderedDict


class Attr(object):
    __slots__ = ('init', 'data')

    def __init__(self, data: Any) -> None:
        self.init = True
        self.data = data

    @classmethod
    def dup(cls, data: Any, ctxt: Dict['Bean', 'Bean']) -> Any:
        if data is None:
            return data

        if isinstance(data, (int, str, bytes, Enum)):
            return data

        if isinstance(data, Bean):
            if data not in ctxt:
                data.clone(ctxt)
            return ctxt[data]

        if isinstance(data, BeanRef):
            bean = data.bean
            if bean not in ctxt:
                bean.clone(ctxt)
            return BeanRef(ctxt[bean])

        if isinstance(data, list):
            return [Attr.dup(i, ctxt) for i in data]

        if isinstance(data, dict):
            return {Attr.dup(k, ctxt): Attr.dup(v, ctxt)
                    for k, v in data.items()}

        if isinstance(data, set):
            return {Attr.dup(i, ctxt) for i in data}

        raise RuntimeError('Invalid attribute type')

    @classmethod
    def chk(cls, data: Any, ctxt: Set['Bean']) -> None:
        if data is None:
            return

        if isinstance(data, (int, str, bytes, Enum)):
            return

        if isinstance(data, Bean):
            if data not in ctxt:
                data.check(ctxt)
            return

        if isinstance(data, BeanRef):
            bean = data.bean
            if bean not in ctxt:
                bean.check(ctxt)
            return

        if isinstance(data, list):
            for i in data:
                Attr.chk(i, ctxt)
            return

        if isinstance(data, dict):
            for k, v in data.items():
                Attr.chk(k, ctxt)
                Attr.chk(v, ctxt)
            return

        if isinstance(data, set):
            for i in data:
                Attr.chk(i, ctxt)
            return

        raise RuntimeError('Invalid attribute type')

    @classmethod
    def lnk(cls, d1: Any, d2: Any, ctxt: Dict['Bean', 'Bean']) -> None:
        assert isinstance(d2, type(d1))

        if d1 is None:
            return

        if isinstance(d1, (int, str, bytes, Enum)):
            return

        if isinstance(d1, Bean):
            if d1 not in ctxt:
                ctxt[d1] = d2
                d1.unite(d2, ctxt)
            return

        if isinstance(d1, BeanRef):
            bean = d1.bean
            if bean not in ctxt:
                ctxt[bean] = d2.bean
                bean.unite(d2.bean, ctxt)
            return

        if isinstance(d1, list):
            for i1, i2 in zip(d1, d2):
                Attr.lnk(i1, i2, ctxt)
            return

        if isinstance(d1, dict):
            for k1, k2 in zip(sorted(d1.keys()), sorted(d2.keys())):
                Attr.lnk(k1, k2, ctxt)
                Attr.lnk(d1[k1], d2[k2], ctxt)
            return

        if isinstance(d1, set):
            for i1, i2 in zip(sorted(d1), sorted(d2)):
                Attr.lnk(i1, i2, ctxt)
            return

    def get(self) -> Any:
        assert self.init
        return self.data

    def set(self, data: Any) -> None:
        assert self.init
        self.data = data


B = TypeVar('B', bound='Bean')


class Bean(object):
    """
    Interface class, allows an object to be properly copied

    This requires subclasses to
        - have only zero-argument constructor in non-abstract class
        - declaring fields in the dataclass style
    """

    def __init__(self) -> None:
        bean_type = Bean.__collect__(type(self))

        type_bean = OrderedDict()  # type: Dict[Type[Bean], Dict[str, bool]]
        for k, v in bean_type.items():
            if v not in type_bean:
                type_bean[v] = OrderedDict()
            type_bean[v][k] = False

        object.__setattr__(self, '__bean_type__', bean_type)
        object.__setattr__(self, '__type_bean__', type_bean)

    @classmethod
    def __collect__(cls, cur: Type) -> Dict[str, Type['Bean']]:
        bean_type = OrderedDict()  # type: Dict[str, Type[Bean]]

        if not issubclass(cur, Bean):
            return bean_type

        if cur != Bean:
            for i in cur.__bases__:
                sub = Bean.__collect__(i)
                for k, v in sub.items():
                    assert k not in bean_type
                    bean_type[k] = v

        if not hasattr(cur, '__annotations__'):
            return bean_type

        for k, _ in cur.__annotations__.items():
            if k not in bean_type:
                bean_type[k] = cur

        return bean_type

    @no_type_check
    def __setattr__(self, attr: str, data: Any) -> None:
        # check if this is a bean attr
        bean_type = cast(
            Dict[str, Type[Bean]],
            object.__getattribute__(self, '__bean_type__')
        )
        if attr not in bean_type:
            return object.__setattr__(self, attr, data)

        # check whether this bean attr has been set
        type_bean = cast(
            Dict[Type[Bean], Dict[str, bool]],
            object.__getattribute__(self, '__type_bean__')
        )

        kind = bean_type[attr]
        info = type_bean[kind]

        if info[attr]:
            # attribute set
            item = object.__getattribute__(self, attr)
            assert isinstance(item, Attr)
            item.set(data)
        else:
            # attribute ini
            item = Attr(data)
            info[attr] = True
            object.__setattr__(self, attr, item)

    @no_type_check
    def __getattribute__(self, attr: str) -> Any:
        item = object.__getattribute__(self, attr)

        # allow pickle to work
        if attr == '__dict__':
            return item

        # check if this is a bean attr
        bean_type = cast(
            Dict[str, Type[Bean]],
            object.__getattribute__(self, '__bean_type__')
        )
        if attr not in bean_type:
            return item

        # check whether this bean attr has been set
        type_bean = cast(
            Dict[Type[Bean], Dict[str, bool]],
            object.__getattribute__(self, '__type_bean__')
        )
        assert type_bean[bean_type[attr]][attr]

        # attribute get
        assert isinstance(item, Attr)
        return item.get()

    def clone(self: B, ctxt: Optional[Dict['Bean', 'Bean']] = None) -> B:
        if ctxt is None:
            ctxt = {}

        copy = type(self)()  # type: B
        assert self not in ctxt
        ctxt[self] = copy

        bean_type = cast(
            Dict[str, Type[Bean]],
            object.__getattribute__(self, '__bean_type__')
        )

        for attr in bean_type:
            item = object.__getattribute__(self, attr)
            assert isinstance(item, Attr)
            setattr(copy, attr, Attr.dup(item.get(), ctxt))

        return copy

    def check(self, ctxt: Optional[Set['Bean']] = None) -> None:
        # no double checking
        assert not hasattr(self, '__bean__')

        if ctxt is None:
            ctxt = set()

        assert self not in ctxt
        ctxt.add(self)

        type_bean = cast(
            Dict[Type[Bean], Dict[str, bool]],
            object.__getattribute__(self, '__type_bean__')
        )

        for kind, info in type_bean.items():
            # make sure all fields exist
            for k, v in info.items():
                if not v:
                    raise RuntimeError('Attr {} not set'.format(k))

                item = object.__getattribute__(self, k)
                assert isinstance(item, Attr)
                Attr.chk(item.get(), ctxt)

            # validate all fields
            kind.validate(self)

        # mark when all checks passed
        object.__setattr__(self, '__bean__', True)

    def unite(self, bean: 'Bean', ctxt: Optional[Dict['Bean', 'Bean']]) -> None:
        if ctxt is None:
            ctxt = {}

        bean_type = cast(
            Dict[str, Type[Bean]],
            object.__getattribute__(self, '__bean_type__')
        )

        for attr in bean_type:
            item = object.__getattribute__(self, attr)
            assert isinstance(item, Attr)

            pair = object.__getattribute__(bean, attr)
            assert isinstance(pair, Attr)

            Attr.lnk(item.get(), pair.get(), ctxt)

    def ready(self) -> bool:
        return hasattr(self, '__bean__')

    @classmethod
    def setup(cls: Type[B], bean: B, **kwargs: Any) -> B:
        bean_type = cast(
            Dict[str, Type[Bean]],
            object.__getattribute__(bean, '__bean_type__')
        )

        # set the given values
        for attr, data in kwargs.items():
            assert attr in bean_type
            setattr(bean, attr, data)

        # set default values
        for attr in bean_type:
            if attr in kwargs:
                continue

            defv = getattr(bean, 'default_{}'.format(attr), None)
            if defv is not None:
                setattr(bean, attr, defv())

        return bean

    @classmethod
    def build(cls: Type[B], **kwargs: Any) -> B:
        return cls.setup(cls(), **kwargs)

    # per-bean methods
    def validate(self) -> None:
        pass


class BeanRef(Generic[B]):

    def __init__(self, bean: B) -> None:
        self.bean = bean
