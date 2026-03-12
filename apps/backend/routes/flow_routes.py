# -*- coding: utf-8 -*-
import logging
import traceback
from typing import Annotated, List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, Body

from models.flow_models import (
    FlowStartRequest, FlowStartResponse,
    FlowNextRequest, FlowNextResponse,
    FlowFeedbackRequest
)
from services.flow_service import get_flow_service
from services.flow_session_service import get_flow_session_manager
from middleware.auth_middleware import verify_firebase_token
from config import settings

logger = logging.getLogger("tomehub_api")
router = APIRouter(prefix="/api/flow", tags=["Flux (Layer 4)"])

def _resolve_flow_uid(token_uid: Optional[str], body_uid: Optional[str] = None) -> str:
    if token_uid:
        return token_uid
    raise HTTPException(status_code=401, detail="Authentication required")

@router.post("/start", response_model=FlowStartResponse)
async def flow_start(
    request: Request,
    user_id: Annotated[str, Depends(verify_firebase_token)],
    flow_request: FlowStartRequest,
    background_tasks: BackgroundTasks
):
    flow_request.firebase_uid = _resolve_flow_uid(user_id, flow_request.firebase_uid)
    try:
        flow_service = get_flow_service()
        response = flow_service.start_session(flow_request)
        background_tasks.add_task(_prefetch_flow_batch, response.session_id, flow_request.firebase_uid)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW] Start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/next", response_model=FlowNextResponse)
async def flow_next(
    request: Request,
    user_id: Annotated[str, Depends(verify_firebase_token)],
    flow_request: FlowNextRequest,
    background_tasks: BackgroundTasks
):
    flow_request.firebase_uid = _resolve_flow_uid(user_id, flow_request.firebase_uid)
    try:
        flow_service = get_flow_service()
        response = flow_service.get_next_batch(flow_request)
        if response.has_more:
            background_tasks.add_task(_prefetch_flow_batch, flow_request.session_id, flow_request.firebase_uid)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW] Next failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def flow_feedback(
    request: Request,
    user_id: Annotated[str, Depends(verify_firebase_token)],
    feedback: FlowFeedbackRequest
):
    feedback.firebase_uid = _resolve_flow_uid(user_id, feedback.firebase_uid)
    try:
        flow_service = get_flow_service()
        success = flow_service.handle_feedback(
            session_id=feedback.session_id,
            chunk_id=feedback.chunk_id,
            action=feedback.action,
            firebase_uid=feedback.firebase_uid
        )
        return {"success": success, "action": feedback.action}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW] Feedback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/adjust")
async def flow_adjust(
    request: Request,
    user_id: Annotated[str, Depends(verify_firebase_token)],
    session_id: str = Body(...),
    horizon_value: float = Body(..., ge=0.0, le=1.0)
):
    _resolve_flow_uid(user_id)
    try:
        session_manager = get_flow_session_manager()
        state = session_manager.get_session(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        state.horizon_value = horizon_value
        session_manager.update_session(state)
        return {"success": True, "new_horizon": horizon_value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW] Adjust failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset-anchor")
async def flow_reset_anchor(
    request: Request,
    user_id: Annotated[str, Depends(verify_firebase_token)],
    session_id: str = Body(...),
    anchor_type: str = Body(...),
    anchor_id: str = Body(...),
    firebase_uid: str = Body(...),
    resource_type: Optional[str] = Body(None),
    category: Optional[str] = Body(None)
):
    effective_uid = _resolve_flow_uid(user_id, firebase_uid)
    try:
        flow_service = get_flow_service()
        new_label, pivot_info = flow_service.reset_anchor(
            session_id=session_id,
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            firebase_uid=effective_uid,
            resource_type=resource_type,
            category=category
        )
        return {
            "success": True, 
            "topic_label": new_label,
            "pivot_info": pivot_info.dict() if pivot_info else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW] Reset anchor failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/session/{session_id}")
async def get_session_info(
    session_id: str,
    user_id: Annotated[str, Depends(verify_firebase_token)]
):
    try:
        _resolve_flow_uid(user_id)
        session_manager = get_flow_session_manager()
        state = session_manager.get_session(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session_id": state.session_id,
            "cards_shown": state.cards_shown,
            "horizon_value": state.horizon_value,
            "mode": state.mode.value if state.mode else "FOCUS",
            "anchor_id": state.global_anchor_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FLOW] Get session failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _prefetch_flow_batch(session_id: str, firebase_uid: str):
    try:
        flow_service = get_flow_service()
        prefetch_request = FlowNextRequest(firebase_uid=firebase_uid, session_id=session_id, batch_size=10)
        flow_service.get_next_batch(prefetch_request)
    except Exception as e:
        logger.warning(f"[FLOW] Prefetch failed: {e}")
