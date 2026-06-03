import os
import sys
import unittest
from pathlib import Path
from dotenv import load_dotenv

# Resolve paths to allow correct imports when running from terminal
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "preprocessing"))
sys.path.insert(0, str(ROOT_DIR))

# Load .env variables before importing application components
load_dotenv(os.path.join(ROOT_DIR, ".env"))


from fastapi.testclient import TestClient
from main import app
from core.database import SessionLocal, engine
from schemas.byok_schema import UserAPIKey, UserSetting
from core.security import EncryptionUtility
from service.byok_service import provider_manager, APIKeyService

client = TestClient(app)


class TestBYOKSystem(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Clean up existing test records to ensure clean environment
        self.db.query(UserAPIKey).filter(UserAPIKey.user_id.like("test_user_%")).delete()
        self.db.query(UserSetting).filter(UserSetting.user_id.like("test_user_%")).delete()
        self.db.commit()

        self.test_user = "test_user_123"
        self.headers = {"X-User-ID": self.test_user}

    def tearDown(self):
        # Clean up test records
        self.db.query(UserAPIKey).filter(UserAPIKey.user_id.like("test_user_%")).delete()
        self.db.query(UserSetting).filter(UserSetting.user_id.like("test_user_%")).delete()
        self.db.commit()
        self.db.close()

    def test_01_upload_validation(self):
        """
        Verify that key uploads are validated correctly.
        """
        print("\n[Test] Running key upload validation checks...")

        # 1. Invalid provider
        res = client.post(
            "/byok/keys",
            json={"provider": "openai", "api_key": "sk-1234567890abcdef"},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 422, "Should reject unsupported provider 'openai'")
        self.assertIn("Unsupported provider", res.text)

        # 2. Too short key
        res = client.post(
            "/byok/keys",
            json={"provider": "groq", "api_key": "short"},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 422, "Should reject extremely short key")

        # 3. Invalid Groq key prefix
        res = client.post(
            "/byok/keys",
            json={"provider": "groq", "api_key": "notgsk_1234567890abcdef"},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 422, "Should reject Groq key not starting with 'gsk_'")
        self.assertIn("Groq API keys must begin with 'gsk_'", res.text)

    def test_02_upload_encryption_and_storage(self):
        """
        Verify that uploaded keys are encrypted in the database and masked in responses.
        """
        print("\n[Test] Running encryption and database storage verification...")

        raw_groq_key = "gsk_my_secret_groq_key_987654321"
        res = client.post(
            "/byok/keys",
            json={"provider": "groq", "api_key": raw_groq_key},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["provider"], "groq")
        self.assertTrue(data["exists"])
        self.assertEqual(data["key_masked"], "gsk_my_s...4321")

        # Directly query DB to check encryption
        db_key_record = self.db.query(UserAPIKey).filter(
            UserAPIKey.user_id == self.test_user,
            UserAPIKey.provider == "groq"
        ).first()

        self.assertIsNotNone(db_key_record, "Key must be saved in database")
        self.assertNotEqual(
            db_key_record.encrypted_key,
            raw_groq_key,
            "Key must not be stored in plaintext"
        )

        # Verify decryption works correctly
        decrypted = EncryptionUtility.decrypt(db_key_record.encrypted_key)
        self.assertEqual(decrypted, raw_groq_key, "Decrypted key must match original raw key")

    def test_03_metadata_list_and_masking(self):
        """
        Verify that GET /keys returns masked key list and does not leak keys.
        """
        print("\n[Test] Running GET /byok/keys metadata and masking tests...")

        raw_cohere_key = "cohere_secret_key_abcdef_123456789"
        
        # Upload cohere key
        res_upload = client.post(
            "/byok/keys",
            json={"provider": "cohere", "api_key": raw_cohere_key},
            headers=self.headers
        )
        self.assertEqual(res_upload.status_code, 201)

        # Retrieve metadata list
        res_list = client.get("/byok/keys", headers=self.headers)
        self.assertEqual(res_list.status_code, 200)
        keys_meta = res_list.json()

        self.assertEqual(len(keys_meta), 2, "Should return metadata structures for all 2 support providers")
        
        # Find cohere metadata
        cohere_meta = next(k for k in keys_meta if k["provider"] == "cohere")
        self.assertTrue(cohere_meta["exists"])
        self.assertEqual(cohere_meta["key_masked"], "cohe...789")
        self.assertNotIn(raw_cohere_key, str(keys_meta), "Raw key must never be leaked in list payload")

        # Find groq metadata (not uploaded yet in this clean run)
        groq_meta = next(k for k in keys_meta if k["provider"] == "groq")
        self.assertFalse(groq_meta["exists"])
        self.assertIsNone(groq_meta["key_masked"])

    def test_04_multi_user_isolation(self):
        """
        Verify that keys are isolated between users.
        """
        print("\n[Test] Running multi-user isolation checks...")

        # 1. Upload key for User A
        user_a_key = "gsk_user_a_secret_key_11111111"
        client.post(
            "/byok/keys",
            json={"provider": "groq", "api_key": user_a_key},
            headers={"X-User-ID": "test_user_A"}
        )

        # 2. Upload key for User B
        user_b_key = "gsk_user_b_secret_key_22222222"
        client.post(
            "/byok/keys",
            json={"provider": "groq", "api_key": user_b_key},
            headers={"X-User-ID": "test_user_B"}
        )

        # 3. Read metadata of User A and check it is User A's key
        res_a = client.get("/byok/keys", headers={"X-User-ID": "test_user_A"})
        meta_a = next(k for k in res_a.json() if k["provider"] == "groq")
        self.assertEqual(meta_a["key_masked"], "gsk_user...1111")

        # 4. Read metadata of User B and check it is User B's key
        res_b = client.get("/byok/keys", headers={"X-User-ID": "test_user_B"})
        meta_b = next(k for k in res_b.json() if k["provider"] == "groq")
        self.assertEqual(meta_b["key_masked"], "gsk_user...2222")

    def test_05_active_provider_configuration(self):
        """
        Verify settings management for active LLM provider.
        """
        print("\n[Test] Running active provider selection checks...")

        # Check default provider
        res_get = client.get("/byok/active-provider", headers=self.headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["active_provider"], "groq", "Default active provider should be groq")

        # Change to cohere
        res_set = client.post(
            "/byok/active-provider",
            json={"provider": "cohere"},
            headers=self.headers
        )
        self.assertEqual(res_set.status_code, 200)
        self.assertEqual(res_set.json()["active_provider"], "cohere")

        # Get settings again and verify change is persisted
        res_get_new = client.get("/byok/active-provider", headers=self.headers)
        self.assertEqual(res_get_new.json()["active_provider"], "cohere")

    def test_06_connection_testing_sanitized_errors(self):
        """
        Verify connection testing endpoint.
        Verify that connection errors and exceptions do not leak decrypted/raw API keys.
        """
        print("\n[Test] Running connection testing and error sanitization checks...")

        # Upload an invalid groq key to force verification failure
        invalid_key = "gsk_invalid_groq_key_value_abcdef"
        client.post(
            "/byok/keys",
            json={"provider": "groq", "api_key": invalid_key},
            headers=self.headers
        )

        # Trigger connection test (runs minimal chat completion ping)
        res_test = client.post(
            "/byok/test-connection",
            params={"provider": "groq"},
            headers=self.headers
        )
        self.assertEqual(res_test.status_code, 200)
        data = res_test.json()
        self.assertFalse(data["success"], "Test connection must fail for invalid key")
        self.assertNotIn(invalid_key, data["message"], "Error payload must not leak key content")
        self.assertIn("Connection test failed", data["message"])
        print(f"   Sanitized Error Response: '{data['message']}'")

    def test_07_provider_manager_and_caching(self):
        """
        Verify ProviderManager initializes client and invalidates cache when keys update.
        """
        print("\n[Test] Running ProviderManager client resolution and caching checks...")

        test_key_1 = "gsk_key_first_version_xxxxxxxxx"
        test_key_2 = "gsk_key_second_version_yyyyyyyyy"

        # 1. Upload Key 1
        APIKeyService.save_api_key(self.db, self.test_user, "groq", test_key_1)

        # 2. Retrieve client through ProviderManager
        client_v1 = provider_manager.get_client(self.db, self.test_user, "groq")
        self.assertEqual(client_v1.api_key, test_key_1)

        # 3. Retrieve client again (should hit memory cache)
        client_v1_cached = provider_manager.get_client(self.db, self.test_user, "groq")
        self.assertIs(client_v1, client_v1_cached, "Should return identical cached instance")

        # 4. Upload Key 2 (updates record in database)
        APIKeyService.save_api_key(self.db, self.test_user, "groq", test_key_2)

        # 5. Retrieve client again (should bypass old cache and return updated client)
        client_v2 = provider_manager.get_client(self.db, self.test_user, "groq")
        self.assertEqual(client_v2.api_key, test_key_2, "Must return dynamic updated client version")
        self.assertNotEqual(client_v1.api_key, client_v2.api_key)


if __name__ == "__main__":
    unittest.main()
