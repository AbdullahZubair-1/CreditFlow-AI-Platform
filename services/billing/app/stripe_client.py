import stripe

from app.config import PLAN_PRICE_IDS, settings

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
        proration_behavior="create_prorations",
    )


def create_refund(payment_intent_id: str, reason: str | None) -> stripe.Refund:
    return stripe.Refund.create(payment_intent=payment_intent_id, reason=reason)


def construct_webhook_event(payload: bytes, sig_header: str, webhook_secret: str) -> stripe.Event:
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
