"""Minimal inline HTML templates — no templating engine needed for this
scope's small, fixed set of transactional emails."""
from app.core.config import settings


def verification_email(token: str) -> tuple[str, str]:
    link = f"{settings.frontend_base_url}/verify-email?token={token}"
    return "Verify your CreditFlow email", f"<p>Welcome to CreditFlow! Click below to verify your email:</p><p><a href='{link}'>{link}</a></p>"


def invite_email(token: str, role: str) -> tuple[str, str]:
    link = f"{settings.frontend_base_url}/accept-invite?token={token}"
    return (
        "You've been invited to a CreditFlow team",
        f"<p>You've been invited to join a CreditFlow team as <b>{role}</b>.</p><p><a href='{link}'>{link}</a></p>",
    )


def member_joined_email(role: str) -> tuple[str, str]:
    return "Welcome to the team", f"<p>You're now a member of a CreditFlow team account with the role <b>{role}</b>.</p>"


def invoice_paid_email(amount_cents: int, plan_tier: str) -> tuple[str, str]:
    return (
        "Your CreditFlow payment receipt",
        f"<p>We received your payment of ${amount_cents / 100:.2f} for the <b>{plan_tier}</b> plan. Thank you!</p>",
    )


def payment_failed_email() -> tuple[str, str]:
    return (
        "Action needed: CreditFlow payment failed",
        "<p>Your most recent payment failed. Please update your payment method to avoid a plan downgrade.</p>",
    )


def post_published_email(linkedin_post_id: str) -> tuple[str, str]:
    return (
        "Your post was published to LinkedIn",
        f"<p>Your scheduled post is now live on LinkedIn (post id: {linkedin_post_id}).</p>",
    )


def post_failed_email(reason: str) -> tuple[str, str]:
    return "Your scheduled post failed to publish", f"<p>We couldn't publish your scheduled post: {reason}</p>"


def password_reset_email(otp: str) -> tuple[str, str]:
    return (
        "Your CreditFlow password reset code",
        f"<p>Use this one-time code to reset your password: <b>{otp}</b></p>"
        "<p>This code expires shortly and can only be used once. If you didn't request this, you can ignore this email.</p>",
    )


def usage_threshold_email(threshold: int, used_tokens: int, quota_tokens: int) -> tuple[str, str]:
    return (
        f"You've used {threshold}% of your usage quota",
        f"<p>Your account has used {used_tokens:,} of its {quota_tokens:,} token quota this period ({threshold}%).</p>",
    )


def refund_issued_email(amount_cents: int) -> tuple[str, str]:
    return (
        "Your CreditFlow refund has been issued",
        f"<p>We've refunded ${amount_cents / 100:.2f} to your original payment method — it should appear within "
        "5-10 business days depending on your bank. Your plan has been switched to Free.</p>",
    )


def marketplace_purchase_email(amount_cents: int) -> tuple[str, str]:
    return (
        "Your marketplace credit purchase is complete",
        f"<p>Your purchase of ${amount_cents / 100:.2f} on the credits marketplace is complete — "
        "the credits have been added to your balance.</p>",
    )


def marketplace_sale_email(amount_cents: int) -> tuple[str, str]:
    return (
        "Your marketplace listing sold",
        f"<p>Your credits marketplace listing sold for ${amount_cents / 100:.2f}. "
        "The credits have been deducted from your balance and the sale is complete.</p>",
    )


def credits_purchased_email(credits_amount: int) -> tuple[str, str]:
    return (
        "Your credit purchase is complete",
        f"<p>You've successfully purchased <b>{credits_amount:,} credits</b> — they've been added to your balance.</p>",
    )
