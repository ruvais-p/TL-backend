from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """Paginates only when the client asks for it with ``?page`` or ``?page_size``.

    Existing clients that expect a bare list keep working, while large staff
    tables can opt in to bounded pages.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if "page" not in request.query_params and self.page_size_query_param not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)
