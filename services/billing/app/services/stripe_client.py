import stripe

from app.core.config import PLAN_PRICE_IDS, settings

stripe.api_key = settings.stripe_secret_key


def create_customer(email: str) -> str:
    customer = stripe.Customer.create(email=email)
    return customer.id


def create_checkout_session(
    customer_id: str, plan: str, success_url: str, cancel_url: str
) -> str:
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"Plan '{plan}' has no Stripe Price configured.")

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def create_one_time_checkout_session(
    customer_id: str,
    amount_cents: int,
    currency: str,
    description: str,
    metadata: dict[str, str],
    success_url: str,
    cancel_url: str,
) -> str:
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": description},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        metadata=metadata,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def modify_subscription(subscription_id: str, plan: str) -> None:
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"Plan '{plan}' has no Stripe Price configured.")

    subscription = stripe.Subscription.retrieve(subscription_id)
    item_id = subscription["items"]["data"][0]["id"]
    stripe.Subscription.modify(
        subscription_id,
        items=[{"id": item_id, "price": price_id}],
        # "create_prorations" (the old value) only adds proration line
        # items to be billed on the *next* regular invoice — nothing is
        # charged at the moment of the switch. That silently broke the
        # product expectation that upgrading to a paid tier gets you that
        # tier's features and credits right away: those are both driven by
        # a real invoice.paid webhook (see services/billing/app/events.py
        # and services/credits/app/events.py), which never fires until
        # Stripe actually invoices something. "always_invoice" makes
        # Stripe generate and immediately attempt payment on an invoice
        # for the prorated difference as part of this same call, so a
        # Pro -> Team switch charges now and unlocks/grants immediately
        # once that payment succeeds, via the existing webhook pipeline.
        proration_behavior="always_invoice",
    )


def cancel_subscription(subscription_id: str) -> None:
    """Called when a refund is issued for a subscription invoice — refunding
    a past charge but leaving the Stripe subscription active would just bill
    the account again next cycle and silently flip its plan_tier back to
    paid on the next invoice.paid webhook, contradicting the refund."""
    stripe.Subscription.cancel(subscription_id)


def create_refund(payment_intent_id: str, amount_cents: int, reason: str | None) -> stripe.Refund:
    # amount is explicit (95% of the original charge, per policy — see
    # REFUND_RETENTION_RATE in app/config.py) rather than omitted, since
    # omitting it tells Stripe to refund the full remaining charge amount.
    return stripe.Refund.create(payment_intent=payment_intent_id, amount=amount_cents, reason=reason)


def construct_webhook_event(payload: bytes, sig_header: str, webhook_secret: str) -> stripe.Event:
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
