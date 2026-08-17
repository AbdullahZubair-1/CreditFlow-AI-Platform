from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SignupResponse(BaseModel):
    user_id: str
    email: EmailStr
    dev_verification_token: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
    # The frontend passes along the account_id it was scoped to before the
    # access token expired, so silent refresh doesn't reset the user back
    # to their default account every ~15 minutes if they'd switched away
    # from it. Falls back to the default account if omitted or no longer
    # a member of the requested one.
    account_id: str | None = None


class LogoutRequest(BaseModel):
    access_token: str


class SwitchAccountRequest(BaseModel):
    access_token: str
    account_id: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    dev_otp: str | None = None


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(min_length=8, max_length=128)


class ProfileResponse(BaseModel):
    user_id: str
    email: EmailStr
    name: str | None
    email_verified: bool


class UpdateProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DeleteAccountRequest(BaseModel):
    # Re-entering the password is the actual safety gate for this
    # destructive, irreversible action — the frontend's type-to-confirm
    # dialog is a UX speed bump, not a security control on its own.
    password: str
