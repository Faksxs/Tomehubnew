# -*- coding: utf-8 -*-
"""
Layer 4: Flow API Routes
=========================
FastAPI routes for the Knowledge Stream feature.
"""

import logging
import traceback
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, Body

from models.flow_models import (
    FlowStartRequest, FlowStartResponse,
    FlowNextRequest, FlowNextResponse,
    FlowFeedbackRequest
)
from services.flow_service import get_flow_service
from services.flow_session_service import get_flow_session_manager
from middleware.auth_middleware import verify_firebase_token

logger = logging.getLogger("tomehub_api")

# Create Router
router = APIRouter(prefix="/api/flow", tags=["Knowledge Stream (Layer 4)"])


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/start", response_model=FlowStartResponse)
async def flow_start(
    request: Request,
    flow_request: FlowStartRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Start a new Knowledge Stream session.
    """
    print(f"\n[FLOW-API] Incoming request: {flow_request}")
    print(f"[FLOW-API] Authenticated UID: {user_id}")
    # SECURITY: Enforce UID from token
    # We ignore the body's firebase_uid or strictly validate it.
    # Here we override it to ensure the service layer ALWAYS uses the authenticated user.
    flow_request.firebase_uid = user_id
    
    logger.info(f"[FLOW] Starting session for UID: {user_id}")
    
    try:
        flow_service = get_flow_service()
        response = flow_service.start_session(flow_request)
        
        # Prefetch next batch in background
        background_tasks.add_task(
            _prefetch_flow_batch,
            response.session_id,
            flow_request.firebase_uid
        )
        
        return response
        
    except Exception as e:
        logger.error(f"[FLOW] Start failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/next", response_model=FlowNextResponse)
async def flow_next(
    request: Request,
    flow_request: FlowNextRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Get the next batch of cards in the Knowledge Stream.
    """
    # SECURITY: Enforce UID from token
    flow_request.firebase_uid = user_id
    logger.info(f"[FLOW] Next batch for session: {flow_request.session_id}")
    
    try:
        flow_service = get_flow_service()
        response = flow_service.get_next_batch(flow_request)
        
        # Prefetch next batch in background
        if response.has_more:
            background_tasks.add_task(
                _prefetch_flow_batch,
                flow_request.session_id,
                flow_request.firebase_uid
            )
        
        return response
        
    except Exception as e:
        logger.error(f"[FLOW] Next failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def flow_feedback(
    request: Request,
    feedback: FlowFeedbackRequest,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Submit feedback on a card (like, dislike, skip, save).
    Used to adjust the stream in real-time.
    """
    # SECURITY: Enforce UID from token
    feedback.firebase_uid = user_id
    logger.info(f"[FLOW] Feedback: {feedback.action} on {feedback.chunk_id}")
    
    try:
        flow_service = get_flow_service()
        success = flow_service.handle_feedback(
            session_id=feedback.session_id,
            chunk_id=feedback.chunk_id,
            action=feedback.action,
            firebase_uid=feedback.firebase_uid
        )
        
        return {"success": success, "action": feedback.action}
        
    except Exception as e:
        logger.error(f"[FLOW] Feedback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adjust")
async def flow_adjust(
    request: Request,
    session_id: str = Body(...),
    horizon_value: float = Body(..., ge=0.0, le=1.0),
    user_id: str = Depends(verify_firebase_token)
):
    """
    Adjust the Horizon Slider mid-session.
    """
    logger.info(f"[FLOW] Adjusting horizon to {horizon_value} for session {session_id}")
    
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
    session_id: str = Body(...),
    anchor_type: str = Body(...),
    anchor_id: str = Body(...),
    firebase_uid: str = Body(...),
    resource_type: Optional[str] = Body(None),
    user_id: str = Depends(verify_firebase_token)
):
    """
    Explicitly reset the session anchor (Change Topic).
    """
    # SECURITY: Enforce UID from token
    effective_uid = user_id
    logger.info(f"[FLOW] Resetting anchor for session {session_id} to {anchor_type}:{anchor_id}")
    
    try:
        flow_service = get_flow_service()
        new_label, pivot_info = flow_service.reset_anchor(
            session_id=session_id,
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            firebase_uid=effective_uid,
            resource_type=resource_type
        )
        
        return {
            "success": True, 
            "topic_label": new_label,
            "pivot_info": pivot_info.dict() if pivot_info else None
        }
        
    except Exception as e:
        logger.error(f"[FLOW] Reset anchor failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session_info(
    session_id: str,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Get current session state (for debugging/UI sync).
    """
    try:
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


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

def _prefetch_flow_batch(session_id: str, firebase_uid: str):
    """
    Background task to prefetch the next batch of cards.
    This runs after responding to the user to minimize latency.
    """
    try:
        logger.info(f"[FLOW] Prefetching for session {session_id}")
        
        flow_service = get_flow_service()
        prefetch_request = FlowNextRequest(
            firebase_uid=firebase_uid,
            session_id=session_id,
            batch_size=10  # Prefetch larger batch
        )
        
        # This populates the internal queue (if implemented)
        flow_service.get_next_batch(prefetch_request)
        
        logger.info(f"[FLOW] Prefetch complete for session {session_id}")
        
    except Exception as e:
        logger.warning(f"[FLOW] Prefetch failed (non-critical): {e}")
