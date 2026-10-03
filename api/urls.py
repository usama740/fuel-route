from django.urls import path
from .views import RoutePlanView

urlpatterns = [
    path("route/plan-fuel-stops/", RoutePlanView.as_view(), name="route-plan"),
]