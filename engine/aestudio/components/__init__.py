"""Treatment registry: (component type, treatment name) -> builder(ctx, graphic, options)."""
REGISTRY = {}
DEFAULTS = {}   # component -> treatment used when the design names none


def register(component: str, treatment: str, default: bool = False):
    def wrap(fn):
        REGISTRY[(component, treatment)] = fn
        if default:
            DEFAULTS[component] = treatment
        return fn
    return wrap


from . import blocks, cinematic, editorial, notebook  # noqa: E402,F401  (registers treatments)
