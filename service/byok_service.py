import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from sqlalchemy.orm import Session
from schemas.byok_schema import UserAPIKey, UserSetting
from core.security import EncryptionUtility
from groq import Groq
import cohere

logger = logging.getLogger("byok_service")


class KeyNotFoundError(Exception):
    """Exception raised when a user requests a client but has not uploaded the corresponding key."""
    pass


class APIKeyService:
    """
    Business logic for storing, validating, listing, and deleting user API keys.
    """

    @staticmethod
    def mask_key(provider: str, decrypted_key: str) -> str:
        """
        Masks the API key for safe metadata display.
        Examples:
          - Groq (starts with gsk_): gsk_abcd...wxyz
          - Cohere (no prefix): Jf9h...g5Li
        """
        if not decrypted_key:
            return ""
        
        decrypted_key = decrypted_key.strip()
        if provider == "groq" and decrypted_key.startswith("gsk_"):
            prefix = decrypted_key[:8]
            suffix = decrypted_key[-4:] if len(decrypted_key) > 12 else ""
            return f"{prefix}...{suffix}"
        
        # Default masking
        if len(decrypted_key) > 8:
            return f"{decrypted_key[:4]}...{decrypted_key[-3:]}"
        return "****"

    @classmethod
    def save_api_key(cls, db: Session, user_id: str, provider: str, raw_key: str) -> UserAPIKey:
        """
        Encrypts and stores (or updates) an API key for a specific user and provider.
        """
        encrypted = EncryptionUtility.encrypt(raw_key)
        
        # Check if record already exists
        existing = db.query(UserAPIKey).filter(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == provider
        ).first()

        if existing:
            existing.encrypted_key = encrypted
            logger.info(f"Updated existing {provider} API key for user: {user_id}")
            db.commit()
            db.refresh(existing)
            return existing
        else:
            new_key = UserAPIKey(
                user_id=user_id,
                provider=provider,
                encrypted_key=encrypted
            )
            db.add(new_key)
            logger.info(f"Created new {provider} API key record for user: {user_id}")
            db.commit()
            db.refresh(new_key)
            return new_key

    @classmethod
    def get_decrypted_api_key(cls, db: Session, user_id: str, provider: str) -> Optional[str]:
        """
        Retrieves the encrypted API key from DB and returns the decrypted plaintext value.
        """
        record = db.query(UserAPIKey).filter(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == provider
        ).first()
        if not record:
            return None
        return EncryptionUtility.decrypt(record.encrypted_key)

    @classmethod
    def delete_api_key(cls, db: Session, user_id: str, provider: str) -> bool:
        """
        Removes the user's API key for the given provider.
        """
        record = db.query(UserAPIKey).filter(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == provider
        ).first()
        if not record:
            return False
        
        db.delete(record)
        db.commit()
        logger.info(f"Deleted {provider} API key record for user: {user_id}")
        return True

    @classmethod
    def get_all_keys_metadata(cls, db: Session, user_id: str) -> List[Dict[str, Any]]:
        """
        Returns key metadata for all providers for a user.
        Exposes masked keys, never raw.
        """
        records = db.query(UserAPIKey).filter(UserAPIKey.user_id == user_id).all()
        record_map = {r.provider: r for r in records}

        metadata_list = []
        for provider in ["groq", "cohere"]:
            rec = record_map.get(provider)
            if rec:
                decrypted = EncryptionUtility.decrypt(rec.encrypted_key)
                masked = cls.mask_key(provider, decrypted)
                metadata_list.append({
                    "provider": provider,
                    "exists": True,
                    "key_masked": masked,
                    "created_at": rec.created_at,
                    "updated_at": rec.updated_at
                })
            else:
                metadata_list.append({
                    "provider": provider,
                    "exists": False,
                    "key_masked": None,
                    "created_at": None,
                    "updated_at": None
                })
        return metadata_list


# ─────────────────────────────────────────────────────────────
# ProviderManager Service (Dynamic Client Instantiation)
# ─────────────────────────────────────────────────────────────
class ProviderManager:
    """
    ProviderManager is responsible for loading the active provider,
    retrieving/decrypting keys, dynamically initializing raw provider clients
    (Groq/Cohere), and caching them in-memory safely.
    """

    def __init__(self):
        # Maps provider name -> function that creates client from key string
        self._registry: Dict[str, Callable[[str], Any]] = {}
        self._client_cache: Dict[Tuple[str, str, str], Any] = {} # Key: (user_id, provider, encrypted_key_hash)

        # Register core provider client initializers
        self.register_provider("groq", lambda key: Groq(api_key=key))
        self.register_provider("cohere", lambda key: cohere.Client(api_key=key))

    def register_provider(self, name: str, factory: Callable[[str], Any]):
        """
        Allows registering new LLM provider factories, making the service fully provider-agnostic.
        """
        self._registry[name.strip().lower()] = factory

    def get_active_provider(self, db: Session, user_id: str) -> str:
        """
        Retrieves the active provider name for the given user. Defaults to 'groq'.
        """
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if setting:
            return setting.active_provider.lower()
        return "groq"

    def set_active_provider(self, db: Session, user_id: str, provider: str) -> str:
        """
        Sets the user's active provider selection.
        """
        provider_clean = provider.strip().lower()
        if provider_clean not in self._registry:
            raise ValueError(f"Provider '{provider}' is not registered.")
        
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if setting:
            setting.active_provider = provider_clean
            logger.info(f"Updated active provider to '{provider_clean}' for user: {user_id}")
        else:
            setting = UserSetting(user_id=user_id, active_provider=provider_clean)
            db.add(setting)
            logger.info(f"Created active provider settings '{provider_clean}' for user: {user_id}")
        
        db.commit()
        return provider_clean

    def get_client(self, db: Session, user_id: str, provider: str) -> Any:
        """
        Retrieves the decrypted key, instantiates, caches, and returns the requested client.
        """
        provider_clean = provider.strip().lower()
        if provider_clean not in self._registry:
            raise ValueError(f"LLM provider '{provider}' is not registered in ProviderManager.")

        # 1. Fetch encrypted key from DB
        record = db.query(UserAPIKey).filter(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == provider_clean
        ).first()

        if not record:
            raise KeyNotFoundError(
                f"No API key configured for provider '{provider_clean}' and user/session context '{user_id}'."
            )

        # 2. Check memory cache using (user_id, provider, encrypted_key)
        # Using the exact encrypted key string as part of the cache key ensures that
        # if the user updates the key, a cache-miss occurs immediately, and the new key is used.
        cache_key = (user_id, provider_clean, record.encrypted_key)
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # 3. Decrypt and dynamically initialize
        try:
            decrypted_key = EncryptionUtility.decrypt(record.encrypted_key)
            factory_fn = self._registry[provider_clean]
            client = factory_fn(decrypted_key)
            
            # Cache the client instance
            self._client_cache[cache_key] = client
            return client
        except Exception as e:
            logger.error(f"Error dynamically initializing {provider_clean} client: {e}")
            raise RuntimeError(f"Failed to initialize {provider_clean} client. Verify key validity.") from e

    def get_active_client(self, db: Session, user_id: str) -> Tuple[str, Any]:
        """
        Resolves the user's active provider selection, gets the client, and returns a tuple (provider, client).
        """
        active_provider = self.get_active_provider(db, user_id)
        client = self.get_client(db, user_id, active_provider)
        return active_provider, client


# Global ProviderManager singleton
provider_manager = ProviderManager()
