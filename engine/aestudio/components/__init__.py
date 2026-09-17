"""Treatment registry: (component type, treatment name) -> builder(ctx, graphic, options)."""
REGISTRY = {}


def register(component: str, treatment: str):
    def wrap(fn):
        REGISTRY[(component, treatment)] = fn
        return fn
    return wrap


from . import notebook  # noqa: E402,F401  (registers treatments)
