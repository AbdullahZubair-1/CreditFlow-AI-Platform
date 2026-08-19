import time

import stripe

from app.core.config import PLAN_DISPLAY_PRICES_CENTS, PLAN_PRICE_IDS, PRICE_ID_TO_PLAN, settings

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


def _subscription_item_id(subscription_id: str) -> str:
    subscription = stripe.Subscription.retrieve(subscription_id)
    return subscription["items"]["data"][0]["id"]


def preview_plan_change(subscription_id: str, plan: str) -> int:
    """The amount that should be invoiced/credited for switching to `plan`
    right now — positive for an upgrade (a real charge), negative for a
    downgrade (a credit for unused time on the pricier plan). Computed
    ourselves from the subscription's own current billing period rather
    than asking Stripe's Invoice.create_preview: that API's proration math
    silently breaks after this subscription has ever been modified with
    proration_behavior="none" (which every actual plan change through this
    module uses, to avoid double-charging/crediting) — verified live
    against a real test subscription, where a second preview kept
    comparing against the price from *before* the last "none" change
    instead of the subscription's real current price, netting to a
    confidently wrong $0. A flat monthly-plan model like this one's has no
    coupons/tiers to get right beyond simple time-proration, so computing
    it directly sidesteps that stateful Stripe-side quirk entirely rather
    than working around it."""
    subscription = stripe.Subscription.retrieve(subscription_id).to_dict()
    item = subscription["items"]["data"][0]
    current_plan = PRICE_ID_TO_PLAN.get(item["price"]["id"])
    if current_plan is None or plan not in PLAN_DISPLAY_PRICES_CENTS:
        raise ValueError(f"Unknown plan(s) in change from price {item['price']['id']!r} to {plan!r}.")

    period_start = item["current_period_start"]
    period_end = item["current_period_end"]
    remaining_fraction = max(0.0, min(1.0, (period_end - time.time()) / (period_end - period_start)))

    unused_credit_cents = round(PLAN_DISPLAY_PRICES_CENTS[current_plan] * remaining_fraction)
    new_plan_charge_cents = round(PLAN_DISPLAY_PRICES_CENTS[plan] * remaining_fraction)
    return new_plan_charge_cents - unused_credit_cents


def modify_subscription(subscription_id: str, plan: str, proration_behavior: str) -> None:
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"Plan '{plan}' has no Stripe Price configured.")

    item_id = _subscription_item_id(subscription_id)
    stripe.Subscription.modify(
        subscription_id,
        items=[{"id": item_id, "price": price_id}],
        # Callers now handle collecting/crediting the price difference
        # themselves (a one-time Checkout for an upgrade, a wallet credit
        # for a downgrade — see preview_plan_change and
        # PATCH /subscription) before calling this, so Stripe must never
        # *also* apply its own proration here — "none" is the only choice
        # that doesn't double-charge or double-credit. "always_invoice"
        # (the old unconditional behavior) charged/credited the customer's
        # default payment method directly and activated the new plan
        # regardless of whether that charge actually succeeded.
        proration_behavior=proration_behavior,
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
