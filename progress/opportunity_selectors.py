from django.db.models import Q
from django.utils import timezone

from progress.models import CareerOpportunity


def audience_query(user):
    return Q(audience_scope=CareerOpportunity.AudienceScope.ALL_LEARNERS) | Q(
        audience_scope=CareerOpportunity.AudienceScope.SELECTED_GROUPS,
        audience_groups__memberships__student=user,
    )


def learner_catalog_opportunities(
    user, *, search="", employment_type="", workplace_mode=""
):
    queryset = (
        CareerOpportunity.objects.select_related("company_logo")
        .prefetch_related("audience_groups")
        .filter(
            audience_query(user),
            lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED,
        )
        .filter(
            Q(application_deadline__isnull=True)
            | Q(application_deadline__gt=timezone.now())
        )
    )
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(company_name__icontains=search)
            | Q(summary__icontains=search)
        )
    if employment_type:
        queryset = queryset.filter(employment_type=employment_type)
    if workplace_mode:
        queryset = queryset.filter(workplace_mode=workplace_mode)
    return queryset.distinct()


def learner_detail_opportunities(user):
    open_and_visible = audience_query(user) & Q(
        lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED
    ) & (
        Q(application_deadline__isnull=True)
        | Q(application_deadline__gt=timezone.now())
    )
    existing_applicant = Q(applications__applicant=user)
    return (
        CareerOpportunity.objects.select_related("company_logo")
        .prefetch_related("audience_groups")
        .filter(open_and_visible | existing_applicant)
        .distinct()
    )
