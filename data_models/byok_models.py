from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class APIKeyUploadRequest(BaseModel):
    provider: str = Field(..., description="The LLM provider name, e.g., 'groq' or 'cohere'")
    api_key: str = Field(..., min_length=10, description="The raw API key to encrypt and store")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, val: str) -> str:
        prov = val.strip().lower()
        allowed = ["groq", "cohere"]
        if prov not in allowed:
            raise ValueError(f"Unsupported provider: '{val}'. Supported: {allowed}")
        return prov

    @field_validator("api_key")
    @classmethod
    def validate_key_format(cls, val: str, info) -> str:
        key = val.strip()
        provider = info.data.get("provider", "").lower()
        if provider == "groq" and not key.startswith("gsk_"):
            raise ValueError("Groq API keys must begin with 'gsk_' prefix")
        return key


class APIKeyMetadataResponse(BaseModel):
    provider: str = Field(..., description="The LLM provider")
    exists: bool = Field(..., description="Indicates if the API key is configured")
    key_masked: Optional[str] = Field(None, description="Masked version of the key (e.g. gsk_abc...xyz)")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActiveProviderRequest(BaseModel):
    provider: str = Field(..., description="The LLM provider to set as active (e.g., 'groq', 'cohere')")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, val: str) -> str:
        prov = val.strip().lower()
        allowed = ["groq", "cohere"]
        if prov not in allowed:
            raise ValueError(f"Unsupported provider: '{val}'. Supported: {allowed}")
        return prov


class ActiveProviderResponse(BaseModel):
    user_id: str
    active_provider: str


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    provider: str
