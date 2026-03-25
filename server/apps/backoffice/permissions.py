from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden


def get_user_organization(user):
    """Return the user's organization, or None if superadmin (no restriction)."""
    if user.is_superuser:
        return None
    try:
        return user.profile.organization
    except Exception:
        return False  # No profile = restricted (see nothing)


def org_qs(user, base_qs, org_path):
    """Filter a queryset by the user's organization. Superadmins see all."""
    if user.is_superuser:
        return base_qs
    org = get_user_organization(user)
    if not org:
        return base_qs.none()
    return base_qs.filter(**{org_path: org})


def superuser_required(view_func):
    """Decorator: requires staff + superuser status."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    return staff_member_required(wrapper)
