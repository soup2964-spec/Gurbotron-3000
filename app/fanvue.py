"""Async Fanvue REST client (creator token)."""

from typing import Any

import httpx

from app.config import settings


class FanvueClient:
    def __init__(self, token: str | None = None):
        self._token = token or settings.fanvue_access_token
        self._base = settings.fanvue_api_url.rstrip("/")
        self._version = settings.fanvue_api_version

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Fanvue-API-Version": self._version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def list_chats(
        self,
        *,
        page: int = 1,
        size: int = 25,
        filters: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        params: list[tuple[str, str | int]] = [("page", page), ("size", size)]
        if filters:
            for f in filters:
                params.append(("filter", f))
        close = False
        if client is None:
            client = httpx.AsyncClient(timeout=60.0)
            close = True
        try:
            r = await client.get(f"{self._base}/chats", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()
        finally:
            if close:
                await client.aclose()

    async def list_chat_templates(
        self,
        *,
        page: int = 1,
        size: int = 50,
        folder_name: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "size": min(max(size, 1), 50)}
        if folder_name:
            params["folderName"] = folder_name
        close = False
        if client is None:
            client = httpx.AsyncClient(timeout=60.0)
            close = True
        try:
            r = await client.get(
                f"{self._base}/chats/templates",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()
        finally:
            if close:
                await client.aclose()

    async def get_chat_template(
        self,
        template_uuid: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        close = False
        if client is None:
            client = httpx.AsyncClient(timeout=60.0)
            close = True
        try:
            r = await client.get(
                f"{self._base}/chats/templates/{template_uuid}",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()
        finally:
            if close:
                await client.aclose()

    async def list_messages(
        self,
        user_uuid: str,
        *,
        page: int = 1,
        size: int = 50,
        mark_as_read: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        params = {"page": page, "size": size, "markAsRead": str(mark_as_read).lower()}
        close = False
        if client is None:
            client = httpx.AsyncClient(timeout=60.0)
            close = True
        try:
            r = await client.get(
                f"{self._base}/chats/{user_uuid}/messages",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            return r.json()
        finally:
            if close:
                await client.aclose()

    async def send_chat_message(
        self,
        user_uuid: str,
        *,
        text: str | None = None,
        price_cents: int | None = None,
        media_uuids: list[str] | None = None,
        template_uuid: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if text:
            body["text"] = text
        if price_cents is not None:
            body["price"] = price_cents
        if media_uuids:
            body["mediaUuids"] = media_uuids
        if template_uuid:
            body["templateUuid"] = template_uuid
        close = False
        if client is None:
            client = httpx.AsyncClient(timeout=60.0)
            close = True
        try:
            r = await client.post(
                f"{self._base}/chats/{user_uuid}/message",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            return r.json()
        finally:
            if close:
                await client.aclose()
