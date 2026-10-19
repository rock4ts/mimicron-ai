from pydantic import UUID4, BaseModel, Field


class DeviceInfo(BaseModel):
    device_id: UUID4
    device_name: str | None = None


class RequestMeta(BaseModel):
    ip_address: str | None = None
    user_agent: str | None = Field(default=None)
