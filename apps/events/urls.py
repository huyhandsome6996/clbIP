"""
URLs — Events API (được mount tại /api/v1/events/ từ core/urls.py).
"""
from django.urls import path

from apps.events.views import (
    BudgetView,
    CancelRegistrationView,
    CommunicationView,
    EventDetailView,
    EventListCreateView,
    EventRegisterView,
    EventRegistrationListView,
    EventTaskDetailView,
    EventTaskListCreateView,
    MyTicketsView,
    TaskOrderView,
    VerifyTicketView,
)

urlpatterns = [
    path("", EventListCreateView.as_view(), name="event_list"),
    path("my-tickets/", MyTicketsView.as_view(), name="event_my_tickets"),
    path("<int:pk>/", EventDetailView.as_view(), name="event_detail"),
    path("<int:pk>/tasks/", EventTaskListCreateView.as_view(), name="event_tasks"),
    path(
        "<int:pk>/tasks/<int:task_id>/",
        EventTaskDetailView.as_view(),
        name="event_task_detail",
    ),
    path("<int:pk>/tasks/topological-order/", TaskOrderView.as_view(), name="event_task_order"),
    path("<int:pk>/register/", EventRegisterView.as_view(), name="event_register"),
    path(
        "<int:pk>/cancel-registration/",
        CancelRegistrationView.as_view(),
        name="event_cancel_registration",
    ),
    path("<int:pk>/registrations/", EventRegistrationListView.as_view(), name="event_registrations"),
    path("<int:pk>/verify-ticket/", VerifyTicketView.as_view(), name="event_verify_ticket"),
    path("<int:pk>/budget/", BudgetView.as_view(), name="event_budget"),
    path("<int:pk>/communications/", CommunicationView.as_view(), name="event_communications"),
]
