from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from .features import FEATURES, FEATURES_BY_SLUG


@login_required
def index(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/index.html", {"features": FEATURES})


@login_required
def feature_stub(request: HttpRequest, slug: str) -> HttpResponse:
    """Placeholder landing page for a feature not yet built (Phases 2-4).

    A real Django view/URL per feature now, rather than a dead '#' link, so
    the dashboard's "each feature links to its own flow" is true today and
    each stub is swapped for the real feature app's view without the
    dashboard template changing.
    """
    feature = FEATURES_BY_SLUG.get(slug)
    if feature is None:
        raise Http404(f"Unknown feature slug: {slug!r}")
    return render(request, "dashboard/feature_stub.html", {"feature": feature})
