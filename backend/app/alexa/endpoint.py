"""Verified FastAPI endpoint for Alexa Custom Skill requests."""
from __future__ import annotations

import json
import logging

from ask_sdk_core.exceptions import AskSdkException
from ask_sdk_webservice_support.webservice_handler import WebserviceSkillHandler
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from app.alexa.skill import skill
from app.core.config import get_settings

logger = logging.getLogger("rasoi.alexa.endpoint")
router = APIRouter()
settings = get_settings()
webservice_handler = WebserviceSkillHandler(
    skill=skill,
    verify_signature=True,
    verify_timestamp=True,
)


@router.post("/api/v1/alexa")
async def alexa_endpoint(request: Request) -> Response:
    skill_id = settings.alexa_skill_id.strip()
    if not skill_id:
        raise HTTPException(
            status_code=503,
            detail={"code": "ALEXA_NOT_CONFIGURED", "message": "Alexa integration is not configured."},
        )

    body = await request.body()
    if not body or len(body) > 256_000:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ALEXA_BODY", "message": "Invalid request body."})

    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ALEXA_JSON", "message": "Invalid Alexa request."}) from exc

    context_system = envelope.get("context", {}).get("System", {})
    context_app_id = context_system.get("application", {}).get("applicationId")
    session_app_id = envelope.get("session", {}).get("application", {}).get("applicationId")
    incoming_skill_id = context_app_id or session_app_id
    if not incoming_skill_id:
        raise HTTPException(status_code=400, detail={"code": "ALEXA_APPLICATION_ID_MISSING", "message": "Alexa application id is missing."})
    if incoming_skill_id != skill_id:
        raise HTTPException(status_code=403, detail={"code": "ALEXA_SKILL_ID_MISMATCH", "message": "Request is for a different Alexa skill."})

    try:
        response_body = webservice_handler.verify_request_and_dispatch(
            {
                "Signature": request.headers.get("signature", ""),
                "SignatureCertChainUrl": request.headers.get("signaturecertchainurl", ""),
            },
            body.decode("utf-8"),
        )
    except AskSdkException as exc:
        logger.warning("alexa_request_rejected", extra={"reason": type(exc).__name__})
        raise HTTPException(status_code=400, detail={"code": "ALEXA_REQUEST_VERIFICATION_FAILED", "message": "Alexa request verification failed."}) from exc
    except Exception as exc:
        logger.exception("alexa_dispatch_failed")
        raise HTTPException(status_code=500, detail={"code": "ALEXA_DISPATCH_FAILED", "message": "Alexa request could not be processed."}) from exc

    return Response(content=response_body, media_type="application/json")
