import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user_id
from data_models.byok_models import (
    APIKeyUploadRequest,
    APIKeyMetadataResponse,
    ActiveProviderRequest,
    ActiveProviderResponse,
    TestConnectionResponse
)
from service.byok_service import APIKeyService, provider_manager, KeyNotFoundError

logger = logging.getLogger("byok_router")

router = APIRouter(prefix="/byok", tags=["Bring Your Own Key (BYOK)"])


@router.post("/keys", response_model=APIKeyMetadataResponse, status_code=status.HTTP_201_CREATED)
def upload_api_key(
    request: APIKeyUploadRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Securely uploads and encrypts an API key for a provider.
    Exposes only metadata in response.
    """
    try:
        logger.info(f"Securely saving API key for user: {user_id}, provider: {request.provider}")
        db_key = APIKeyService.save_api_key(
            db=db,
            user_id=user_id,
            provider=request.provider,
            raw_key=request.api_key
        )
        
        masked = APIKeyService.mask_key(request.provider, request.api_key)
        return {
            "provider": db_key.provider,
            "exists": True,
            "key_masked": masked,
            "created_at": db_key.created_at,
            "updated_at": db_key.updated_at
        }
    except Exception as e:
        logger.error(f"Error saving API key for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save API key due to an internal error."
        )


@router.get("/keys", response_model=List[APIKeyMetadataResponse])
def get_api_keys_metadata(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Lists the configured API keys for the current user.
    Masks the key content to prevent exposure.
    """
    try:
        return APIKeyService.get_all_keys_metadata(db, user_id)
    except Exception as e:
        logger.error(f"Error fetching API keys metadata for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve API keys metadata."
        )


@router.delete("/keys/{provider}", status_code=status.HTTP_200_OK)
def delete_api_key(
    provider: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Deletes the configured API key for a provider.
    """
    provider_clean = provider.strip().lower()
    if provider_clean not in ["groq", "cohere"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: '{provider}'. Supported: ['groq', 'cohere']"
        )
        
    try:
        deleted = APIKeyService.delete_api_key(db, user_id, provider_clean)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key for provider '{provider_clean}' not found."
            )
        return {
            "status": "success",
            "message": f"Successfully deleted API key for provider '{provider_clean}'."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting API key for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete API key."
        )


@router.post("/active-provider", response_model=ActiveProviderResponse)
def set_active_provider(
    request: ActiveProviderRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Sets the active provider selection for the user.
    """
    try:
        active = provider_manager.set_active_provider(db, user_id, request.provider)
        return {
            "user_id": user_id,
            "active_provider": active
        }
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as e:
        logger.error(f"Error setting active provider for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to configure active provider."
        )


@router.get("/active-provider", response_model=ActiveProviderResponse)
def get_active_provider(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Gets the current active provider configuration for the user.
    """
    try:
        active = provider_manager.get_active_provider(db, user_id)
        return {
            "user_id": user_id,
            "active_provider": active
        }
    except Exception as e:
        logger.error(f"Error retrieving active provider for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active provider configuration."
        )


@router.post("/test-connection", response_model=TestConnectionResponse)
def test_provider_connection(
    provider: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Tests if the uploaded API key works for the specified provider.
    Runs a minimal network check and returns success status.
    """
    provider_clean = provider.strip().lower()
    if provider_clean not in ["groq", "cohere"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: '{provider}'. Supported: ['groq', 'cohere']"
        )
        
    try:
        # Resolves client dynamically (will raise KeyNotFoundError if not configured)
        client = provider_manager.get_client(db, user_id, provider_clean)
        
        logger.info(f"Testing connectivity for user: {user_id}, provider: {provider_clean}")
        if provider_clean == "groq":
            # Send a minimal 1-token query to verify connection
            client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0
            )
        elif provider_clean == "cohere":
            # Send a minimal embedding generation request to verify connection
            client.embed(
                texts=["ping"],
                model="embed-english-v3.0",
                input_type="search_query"
            )
            
        return {
            "success": True,
            "message": f"Connection test succeeded for provider '{provider_clean}'.",
            "provider": provider_clean
        }
        
    except KeyNotFoundError as knf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(knf)
        )
    except Exception as err:
        logger.error(f"Connection test failed for user {user_id}, provider {provider_clean}: {err}")
        # Clean the error message: ensure internal stack traces, API keys, or raw details don't leak.
        # We replace any accidental leakage of specific key tokens.
        err_msg = str(err)
        sanitized_msg = err_msg
        if "gsk_" in err_msg:
            sanitized_msg = "Invalid Groq API key."
        elif "cohere" in err_msg.lower() or "unauthorized" in err_msg.lower() or "401" in err_msg:
            sanitized_msg = "Invalid Cohere API key."
            
        return {
            "success": False,
            "message": f"Connection test failed: {sanitized_msg}",
            "provider": provider_clean
        }
