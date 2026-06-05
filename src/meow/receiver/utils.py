from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

_HANDLES_ATTR = "_meow_handles_type"
_WHEN_ATTR = "_meow_predicate"


@dataclass(frozen=True, slots=True)
class WebhookContext:
    """Request-level metadata forwarded to every controller handler."""

    event_name: str
    delivery: str | None


HandlerFn = Callable[[Any, WebhookContext], Awaitable[dict[str, Any]]]
PredicateFn = Callable[[Any], bool]
InputFactory = Callable[[Any, WebhookContext], Any]


@dataclass(frozen=True)
class Route:
    """Declarative route: when matched, the dispatcher triggers `workflow_id`.

    Held as a class attribute on a controller — `on_event` picks it up
    alongside method handlers and the dispatcher treats both uniformly.
    """

    event_type: type
    when: PredicateFn | None
    workflow_id: str


# `triggers` slot is None for method handlers, set for Route entries.
HandlerEntry = tuple[HandlerFn | None, PredicateFn | None, str | None]


@dataclass
class EventDispatch:
    """Per (event_name, event_type) — factory + ordered handler/predicate list."""

    factory: InputFactory
    handlers: list[HandlerEntry] = field(default_factory=list)


# event_name -> {event_type: EventDispatch}
_CONTROLLERS: dict[str, dict[type, EventDispatch]] = {}


def on(
    event_type: type,
    *,
    when: PredicateFn | None = None,
    triggers: str | None = None,
):
    """Two usages:

    1. As a class attribute (when `triggers` is set) — declarative route:
        review = on(EventType, when=predicate, triggers="WorkflowId")

    2. As a method decorator (when `triggers` is None) — custom logic:
        @on(EventType, when=predicate)
        async def review(self, input_model, ctx): ...
    """
    if triggers is not None:
        return Route(event_type=event_type, when=when, workflow_id=triggers)

    def deco(method: Callable):
        setattr(method, _HANDLES_ATTR, event_type)
        setattr(method, _WHEN_ATTR, when)
        return method

    return deco


def on_event(
    event_name: str,
    *,
    input_factories: dict[type, InputFactory],
):
    """Register a class as the controller for a webhook event family.

    `input_factories` maps each event_type the controller handles to a
    callable `(event, ctx) -> input_model`. Predicates and method
    handlers receive that input_model — not the raw githubkit event.

    The class scanner picks up both `@on(...)`-decorated methods AND
    `Route` class attributes (created by `on(..., triggers="...")`).
    """

    def deco(cls: type) -> type:
        instance = cls()
        dispatch: dict[type, EventDispatch] = {}

        for attr_name, attr in vars(cls).items():
            entry: HandlerEntry | None = None
            event_type: type | None = None

            if isinstance(attr, Route):
                event_type = attr.event_type
                entry = (None, attr.when, attr.workflow_id)
            elif hasattr(attr, _HANDLES_ATTR):
                event_type = getattr(attr, _HANDLES_ATTR)
                predicate = getattr(attr, _WHEN_ATTR, None)
                bound = getattr(instance, attr_name)
                entry = (bound, predicate, None)

            if event_type is None or entry is None:
                continue

            if event_type not in dispatch:
                factory = input_factories.get(event_type)
                if factory is None:
                    raise ValueError(
                        f"{cls.__name__}: no input_factory declared for "
                        f"{event_type.__name__} — add it to `input_factories=` on @on_event."
                    )
                dispatch[event_type] = EventDispatch(factory=factory)

            dispatch[event_type].handlers.append(entry)

        _CONTROLLERS[event_name] = dispatch
        return cls

    return deco
