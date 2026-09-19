from __future__ import annotations

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .conversation import pending_question_for, start_session, submit_turn
from .models import ChatSession


@login_required
def start(request: HttpRequest) -> HttpResponse:
    error = None
    if request.method == "POST":
        patient_id = request.POST.get("patient_id", "").strip()
        if not patient_id:
            # Explicit missing input -> reprompt, never a placeholder id
            # that could collide with another patient's session.
            error = "Patient ID is required."
        else:
            session = start_session(patient_id)
            return redirect("chat-intake-session", session_id=session.id)
    return render(request, "chat_intake/start.html", {"error": error})


@login_required
def session_view(request: HttpRequest, session_id) -> HttpResponse:
    session = get_object_or_404(ChatSession, id=session_id)
    error = None

    if request.method == "POST":
        if session.status != ChatSession.Status.ACTIVE:
            error = "This intake session is already complete."
        else:
            patient_text = request.POST.get("patient_text", "").strip()
            if not patient_text:
                error = "Please enter a response."
            else:
                submit_turn(session, patient_text)
                session.refresh_from_db()

    return render(
        request,
        "chat_intake/session.html",
        {
            "session": session,
            "turns": session.turns.order_by("turn_index"),
            "pending_question": pending_question_for(session),
            "error": error,
        },
    )


@login_required
@permission_required("chat_intake.view_chatsession", raise_exception=True)
def summary_view(request: HttpRequest, session_id) -> HttpResponse:
    """Doctor-facing view of a completed session's summary (issue #15) --
    gated on the `view_chatsession` permission (`Doctors` group) rather than
    on being logged in alone, since it's not meant for the patient filling
    out the intake."""
    session = get_object_or_404(ChatSession, id=session_id)
    return render(request, "chat_intake/summary.html", {"session": session})
