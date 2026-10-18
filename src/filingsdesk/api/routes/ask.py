from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from filingsdesk.api.schemas import AskRequest, AskResponse, CitationOut
from filingsdesk.db.session import get_session
from filingsdesk.rag import answer_question

router = APIRouter(prefix="/ask", tags=["rag"])


@router.post("", response_model=AskResponse)
def ask(request: AskRequest, session: Session = Depends(get_session)) -> AskResponse:
    """Citation-grounded Q&A over ingested filings, with refusal guardrails."""
    result = answer_question(session, request.question, top_k=request.top_k)
    return AskResponse(
        answer=result.answer,
        citations=[CitationOut(**vars(c)) for c in result.citations],
        confidence=result.confidence,
        refused=result.refused,
        injection_flagged=result.injection_flagged,
        answered_by=result.answered_by,
    )
