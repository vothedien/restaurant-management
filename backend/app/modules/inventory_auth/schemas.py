from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=50)
    password: SecretStr = Field(min_length=1, max_length=1024)


class InventoryRole(BaseModel):
    role_code: str
    role_name: str


class InventoryUser(BaseModel):
    user_id: int
    username: str
    full_name: str
    roles: list[InventoryRole]
    permissions: list[str]


class LoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: InventoryUser
