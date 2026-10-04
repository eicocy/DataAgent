from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='SANDBOX_', extra='ignore')
    enabled: bool = False
    broker_url: str = 'http://sandbox-broker:8090'
    broker_token: str = Field(default='', repr=False)
    timeout_seconds: int = Field(default=60, ge=1, le=60)

    @model_validator(mode='after')
    def configured(self):
        from urllib.parse import urlsplit
        url = urlsplit(self.broker_url)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}:
            raise ValueError('SANDBOX_BROKER_URL_INVALID')
        if self.enabled and len(self.broker_token) < 32:
            raise ValueError('SANDBOX_TOKEN_REQUIRED')
        return self


@lru_cache
def get_sandbox_settings():
    return SandboxSettings()
