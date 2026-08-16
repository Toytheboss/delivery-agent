import base64
import hashlib
import os
import unittest
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.dashboard_http import register_dashboard_routes


def password_hash(password: str) -> str:
    rounds = 10_000
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return "pbkdf2_sha256${}${}${}".format(
        rounds,
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


class DashboardAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config = SimpleNamespace(
            dashboard_enabled=True,
            dashboard_admin_users=["Roy", "Grace", "Josh"],
            dashboard_admin_password_hash=password_hash("TestPass9"),
            dashboard_session_secret="test-session-secret",
            dashboard_cookie_secure=False,
            dashboard_path_prefix="/dashboard",
        )
        app = web.Application()
        register_dashboard_routes(app, config)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_old_token_does_not_authorize(self):
        response = await self.client.get(
            "/dashboard?token=legacy", allow_redirects=False
        )
        self.assertEqual(response.status, 302)
        self.assertTrue(response.headers["Location"].endswith("/dashboard/login"))

    async def test_all_admins_can_sign_in_and_open_settings(self):
        for username in ("Roy", "Grace", "Josh"):
            response = await self.client.post(
                "/dashboard/api/login",
                json={"username": username, "password": "TestPass9"},
            )
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["user"], username)
            response = await self.client.get(
                "/dashboard/settings", allow_redirects=False
            )
            self.assertEqual(response.status, 200)

    async def test_wrong_password_and_logout(self):
        response = await self.client.post(
            "/dashboard/api/login",
            json={"username": "Roy", "password": "wrong"},
        )
        self.assertEqual(response.status, 401)

        await self.client.post(
            "/dashboard/api/login",
            json={"username": "Roy", "password": "TestPass9"},
        )
        response = await self.client.post("/dashboard/api/logout")
        self.assertEqual(response.status, 200)
        response = await self.client.get(
            "/dashboard/settings", allow_redirects=False
        )
        self.assertEqual(response.status, 302)


if __name__ == "__main__":
    unittest.main()
