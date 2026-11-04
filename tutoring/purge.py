PURGE_BATCH_SIZE = 500


def delete_in_batches(queryset, batch_size=PURGE_BATCH_SIZE) -> int:
    """Delete rows in primary-key batches so a large backlog never holds long locks."""
    deleted = 0
    while True:
        ids = list(queryset.order_by("pk").values_list("pk", flat=True)[:batch_size])
        if not ids:
            return deleted
        queryset.model.objects.filter(pk__in=ids).delete()
        deleted += len(ids)
