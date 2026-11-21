import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api-singapore.klingai.com"


@dataclass
class KlingConfig:
    api_key: str | None
    access_key: str | None
    secret_key: str | None
    base_url: str
    mock: bool
    live_authorized: bool

    @property
    def configured(self) -> bool:
        return bool(self.api_key or (self.access_key and self.secret_key))

    @property
    def can_call_live(self) -> bool:
        return self.configured and self.live_authorized and not self.mock


def load_kling_config(env: dict | None = None) -> KlingConfig:
    env = os.environ if env is None else env
    return KlingConfig(
        api_key=env.get("KLING_API_KEY"),
        access_key=env.get("KLING_ACCESS_KEY"),
        secret_key=env.get("KLING_SECRET_KEY"),
        base_url=env.get("KLING_BASE_URL", DEFAULT_BASE_URL),
        mock=env.get("KLING_MOCK", "0") == "1",
        live_authorized=env.get("KLING_LIVE_AUTHORIZED", "0") == "1",
    )
