from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    content_service_url: str = "http://content:8000"

    # Placeholder — every developer registers their own LinkedIn Developer
    # App for local testing (LinkedIn issues API access per app, not
    # shared across a team); required products: "Sign In with LinkedIn
    # using OpenID Connect" and "Share on LinkedIn". Replace before
    # exercising the OAuth flow end-to-end.
    linkedin_client_id: str = "linkedin-client-id-placeholder"
    linkedin_client_secret: str = "linkedin-client-secret-placeholder"
    # Must exactly match a redirect URL registered on the LinkedIn app,
    # and must be reachable directly by the browser (not JWT-protected —
    # see the Gateway's public callback route).
    linkedin_redirect_uri: str = "http://localhost:8080/social/linkedin/callback"
    linkedin_scopes: str = "openid profile email w_member_social"
    frontend_connections_url: str = "http://localhost:5173/linkedin-connections"

    linkedin_auth_base_url: str = "https://www.linkedin.com/oauth/v2/authorization"
    linkedin_token_url: str = "https://www.linkedin.com/oauth/v2/accessToken"
    linkedin_userinfo_url: str = "https://api.linkedin.com/v2/userinfo"
    linkedin_images_register_url: str = "https://api.linkedin.com/v2/assets?action=registerUpload"
    linkedin_ugc_posts_url: str = "https://api.linkedin.com/v2/ugcPosts"

    # Fernet keys — dev-default placeholders generated for this repo, NOT
    # suitable for a real deployment. Rotate via env vars before shipping.
    token_encryption_key: str = "gGLNraB90AVpJD2_S0MA8qURS80AvCLzs96rMpEkCRw="
    oauth_state_key: str = "Pn_HZpWVb9vdcDE5ILlBxerWRG-xM_JIShAh90Gl2y8="
    oauth_state_ttl_seconds: int = 10 * 60

    token_refresh_check_interval_seconds: float = 60 * 60.0
    token_refresh_ahead_of_expiry_seconds: int = 3 * 24 * 60 * 60  # refresh 3 days before expiry

    class Config:
        env_file = ".env"


settings = Settings()
