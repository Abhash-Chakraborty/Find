"""
Which media rows a browse surface may show
"""

from find_api.models.media import Media


def browsable_media():
    """Filter clauses for media that belongs on browse surfaces.

    A row is browsable when it is not in the vault, not archived and not in
    the trash. Pass the result to ``query.filter(*browsable_media())``.
    """
    return (
        Media.is_hidden.is_(False),
        Media.is_archived.is_(False),
        Media.deleted_at.is_(None),
    )
