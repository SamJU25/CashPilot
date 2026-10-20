"""FastAPI router for the Autonomous AI Copilot Agent.

Exposes conversational financial participant endpoints with deterministic tool dispatching
and multi-provider LLM bridge support.
"""

from __future__ import annotations

import logging

import json
from typing import Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from api.dependencies import require_tenant
from services.agent.llm_bridge import fetch_remote_models, test_llm_connection
from services.security.tenant_token import (
    TenantTokenError,
    require_tenant_identity,
    resolve_tenant_identity,
    resolve_verified_tenant,
)
from services.agent.schema import (
    AgentChatRequest,
    CopilotResponse,
    DeleteModelRequest,
    DeleteModelResponse,
    DownloadModelRequest,
    DownloadModelResponse,
    FetchModelsRequest,
    FetchModelsResponse,
    LLMConfig,
    TestConnectionRequest,
    TestConnectionResponse,
    RegisterGGUFRequest,
    RegisterGGUFResponse,
    UploadGGUFResponse,
)
from services.agent.supervisor import run_copilot_supervisor

from services.agent.session_store import session_store, SessionRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["Autonomous Agent"])


@router.post(
    "/test-connection",
    response_model=TestConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Test LLM Provider Connection",
    description="Validates API key, Base URL, and model responsiveness for configured LLM provider before saving.",
)
async def agent_test_connection(
    request: TestConnectionRequest,
    tenant: str = Depends(require_tenant),
) -> TestConnectionResponse:
    """Sends a lightweight verification probe to the target LLM provider."""
    return await run_in_threadpool(test_llm_connection, request)


@router.post(
    "/fetch-models",
    response_model=FetchModelsResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch Available Models from Provider",
    description="Queries the target provider's live endpoint to discover supported models in real time.",
)
async def agent_fetch_models(
    request: FetchModelsRequest,
    tenant: str = Depends(require_tenant),
) -> FetchModelsResponse:
    """Dynamically queries the target provider's models catalog."""
    return await run_in_threadpool(fetch_remote_models, request)


@router.post(
    "/download-model",
    response_model=DownloadModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Download Local Model Weights on Demand",
    description="Explicitly downloads weights for supported local models with robust exception handling.",
)
async def agent_download_model(
    request: DownloadModelRequest,
    tenant: str = Depends(require_tenant),
) -> DownloadModelResponse:
    """Explicitly downloads target model weights on demand without silent auto-downloads."""
    from services.agent.local_transformers import LocalTransformersEngine
    engine = LocalTransformersEngine.get_instance()
    res = await run_in_threadpool(engine.download_model, request.model_name)
    return DownloadModelResponse(**res)


@router.post(
    "/delete-model",
    response_model=DeleteModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete Downloaded AI Model",
    description="Deletes downloaded model files to free up disk space.",
)
async def agent_delete_model(
    request: DeleteModelRequest,
    tenant: str = Depends(require_tenant),
) -> DeleteModelResponse:
    """Removes downloaded model files to free up disk space."""
    from services.agent.local_transformers import LocalTransformersEngine
    engine = LocalTransformersEngine.get_instance()
    res = await run_in_threadpool(engine.delete_model, request.model_name)
    return DeleteModelResponse(**res)


@router.post(
    "/register-gguf",
    response_model=RegisterGGUFResponse,
    status_code=status.HTTP_200_OK,
    summary="Register Local GGUF Model Path",
    description="Registers an existing .gguf file from local filesystem into the offline models directory.",
)
async def agent_register_gguf(
    request: RegisterGGUFRequest,
    tenant: str = Depends(require_tenant),
) -> RegisterGGUFResponse:
    from services.agent.local_transformers import LocalTransformersEngine
    engine = LocalTransformersEngine.get_instance()
    res = await run_in_threadpool(engine.register_gguf_file, request.file_path)
    return RegisterGGUFResponse(**res)


@router.post(
    "/upload-gguf",
    response_model=UploadGGUFResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload Local GGUF Model File",
    description="Uploads a .gguf model file from disk directly into local models directory.",
)
async def agent_upload_gguf(
    file: UploadFile = File(...),
    tenant: str = Depends(require_tenant),
) -> UploadGGUFResponse:
    from services.agent.local_transformers import LocalTransformersEngine
    engine = LocalTransformersEngine.get_instance()
    res = await run_in_threadpool(engine.save_uploaded_gguf, file.filename, file.file)
    return UploadGGUFResponse(**res)


def _resolve_agent_tenant(
    x_tenant_token: Optional[str] = None,
    authorization: Optional[str] = None,
    x_tenant_id: Optional[str] = None,
    fallback_id: Optional[str] = None,
) -> str:
    # A signed token is authoritative and verifies the identity.
    # An invalid or expired token raises 401. Unverified requests strictly fall back
    # to SME-DEFAULT to prevent session hijacking via spoofed X-Tenant-ID headers.
    has_token = bool((x_tenant_token and x_tenant_token.strip()) or (authorization and authorization.strip()))
    if has_token:
        try:
            return require_tenant_identity(x_tenant_token=x_tenant_token, authorization=authorization)
        except TenantTokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return "SME-DEFAULT"


@router.get(
    "/session/{session_id}",
    response_model=Optional[SessionRecord],
    status_code=status.HTTP_200_OK,
    summary="Retrieve Active Agent Session",
    description="Fetches full session history, cached transactional dossier, and episodic memory facts.",
)
async def get_session(
    session_id: str,
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> Optional[SessionRecord]:
    """Retrieves session record from the persistent store."""
    tenant = _resolve_agent_tenant(x_tenant_token, authorization, x_tenant_id)
    # The record holds the raw statement: another tenant gets the same 404 as a missing session.
    rec = session_store.get_for_tenant(session_id, tenant)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return rec


@router.delete(
    "/session/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Clear Active Agent Session",
    description="Wipes session conversation history, statement cache, and episodic facts from memory and disk.",
)
async def clear_session(
    session_id: str,
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict:
    """Clears session record from memory and removes serialized disk cache."""
    tenant = _resolve_agent_tenant(x_tenant_token, authorization, x_tenant_id)
    owned = session_store.get_for_tenant(session_id, tenant) is not None
    removed = session_store.clear(session_id) if owned else False
    return {"session_id": session_id, "cleared": removed}


@router.delete(
    "/session/{session_id}/statement",
    status_code=status.HTTP_200_OK,
    summary="Clear Statement from Active Session",
    description="Purges uploaded CSV statement and cached calculations from the session while preserving conversation history.",
)
async def clear_session_statement(
    session_id: str,
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict:
    """Clears statement CSV and cached calculation metrics for the session."""
    tenant = _resolve_agent_tenant(x_tenant_token, authorization, x_tenant_id)
    owned = session_store.get_for_tenant(session_id, tenant) is not None
    rec = session_store.clear_statement(session_id) if owned else None
    return {"session_id": session_id, "statement_cleared": rec is not None}


@router.post(
    "/chat",
    response_model=CopilotResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with Autonomous SME Finance Copilot",
    description="Conversational agent interface that invokes deterministic tools for cash flow diagnostics, digital underwriting, and Tier 2 action staging.",
)
async def agent_chat(
    request: AgentChatRequest,
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    x_llm_config: Optional[str] = Header(default=None, alias="X-LLM-Config"),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
) -> CopilotResponse:
    """Dispatches user prompt to the Agent Supervisor with authoritative header-based tenant and session isolation."""
    try:
        # A signed token is authoritative. Without one, chat stays usable read-only, but staging
        # is refused inside the supervisor so no ledger entry can be created anonymously.
        verified_tenant = resolve_verified_tenant(x_tenant_token, authorization)
        effective_tenant = verified_tenant or _resolve_agent_tenant(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
            fallback_id=request.tenant_id,
        )
        effective_session_id = x_session_id or request.session_id
        if not effective_session_id:
            import uuid
            effective_session_id = f"sess_{uuid.uuid4().hex[:12]}"
        effective_llm_config = request.llm_config

        if x_llm_config:
            try:
                effective_llm_config = LLMConfig(**json.loads(x_llm_config))
            except (ValueError, TypeError):
                # Silently ignoring it used to answer from a different provider than the user chose.
                # The detail never echoes the header: it can carry an API key.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-LLM-Config header is not valid JSON matching the provider settings schema.",
                )

        response = await run_in_threadpool(
            run_copilot_supervisor,
            request,
            tenant_id=effective_tenant,
            llm_config=effective_llm_config,
            session_id=effective_session_id,
            allow_staging=verified_tenant is not None,
        )
        response.session_id = effective_session_id
        return response
    except HTTPException:
        raise
    except Exception:
        # Full trace goes to the server log; the client never sees internal exception text.
        logger.exception("Agent chat failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The copilot hit an internal error answering that message. Please try again.",
        )
