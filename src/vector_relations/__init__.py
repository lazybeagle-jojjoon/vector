"""Tools for building ticker relationship snapshots."""

__all__ = ["RelationSnapshot", "build_relation_snapshot"]


def __getattr__(name: str):
    if name in __all__:
        from .pipeline import RelationSnapshot, build_relation_snapshot

        exports = {
            "RelationSnapshot": RelationSnapshot,
            "build_relation_snapshot": build_relation_snapshot,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
