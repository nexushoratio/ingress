"""Create and save routes between portals."""

from ingress import bookmarks


def route(args, dbc):
    """Calculate an optimal route between portals."""
    portals = bookmarks.load(args.bookmarks)
