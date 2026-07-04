from types import MappingProxyType


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({
            key: freeze(nested)
            for key, nested in value.items()
        })

    if isinstance(value, list):
        return tuple(freeze(item) for item in value)

    if isinstance(value, tuple):
        return tuple(freeze(item) for item in value)

    if isinstance(value, set):
        return frozenset(freeze(item) for item in value)

    return value

