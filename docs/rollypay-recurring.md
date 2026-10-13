# RollyPay recurring VIP billing

## User flow

1. The user pays **17 RUB once** through the ordinary SBP payment API.
2. The bot grants 3 days only after RollyPay reports `status=paid`.
3. The bot then offers a separate, optional consent link for **299 RUB every 3 days**.
4. RollyPay creates the recurring agreement only after the payer confirms it in their banking app.
5. A verified `payment.paid` callback is reconciled with `GET /api/v1/payments/{payment_id}`. Each recurring payment extends access by 3 days once; duplicate callbacks are idempotent.
6. The user can check the agreement state and request cancellation. Cancellation is only reported as complete after the API returns `state=stop` and `billing_status=stopped`.

## Required environment variables

Keep these values in the deployment's private `.env`; never commit live secrets.

```dotenv
ROLLYPAY_API_KEY=...
ROLLYPAY_TERMINAL_ID=...
ROLLYPAY_RECURRING_PLAN_ID=...
ROLLYPAY_SIGNING_SECRET=...
ROLLYPAY_RECURRING_PLAN_CONFIRMED=false
ROLLYPAY_WEBHOOK_ENABLED=true
ROLLYPAY_WEBHOOK_HOST=0.0.0.0
ROLLYPAY_WEBHOOK_PORT=8081
```

- `ROLLYPAY_TERMINAL_ID` is the UUID of the terminal associated with the API key.
- `ROLLYPAY_RECURRING_PLAN_ID` must be the UUID of a plan returned by `GET /api/v1/subscription-plans?terminal_id=...`.
- The plan must charge exactly **299 RUB**. RollyPay configures plans; the bot cannot create a plan or change its interval through the subscription-create request.
- Do **not** set `ROLLYPAY_RECURRING_PLAN_CONFIRMED=true` until RollyPay has confirmed that this exact plan charges every **3 days**. The public plan response may not expose enough detail to prove a three-day cadence; the code intentionally fails closed without this explicit confirmation.
- `ROLLYPAY_SIGNING_SECRET` is the webhook signing secret, not the API key.

## Webhook / HTTPS setup

The bot listens on container port 8081. Compose binds it to `127.0.0.1:8081` on the host, so it is not directly exposed to the public internet. Configure the host's HTTPS reverse proxy to forward:

`https://YOUR_PUBLIC_DOMAIN/webhooks/rollypay` → `http://127.0.0.1:8081/webhooks/rollypay`

Then configure the RollyPay terminal's `callback_url` to that HTTPS URL. Ensure the reverse proxy forwards the raw request body and the `X-Signature` and `X-Timestamp` headers unchanged. Do not point RollyPay at a private IP, localhost, or an HTTP-only public endpoint.

The callback handler verifies HMAC-SHA256 over `timestamp + "." + raw_body`, fetches the payment from RollyPay before granting access, checks the terminal when that field is present, and acknowledges duplicate deliveries with 2xx. Refund/chargeback callbacks are logged for reconciliation; they are not automatically translated into an access revocation.

## Operational checks before launch

- Verify that the terminal has a real, available plan for exactly 299 RUB every 3 days and that the payer-facing consent screen displays those terms.
- Verify the initial 17 RUB payment, then consent to the recurring plan using a test payer agreed with RollyPay.
- Test a recurring successful charge and replay the same callback; VIP expiry must extend only once.
- Test a declined charge, an incomplete consent flow, and cancellation. Access remains available until the already-paid expiry.
- Confirm the HTTPS webhook endpoint is reachable and that the terminal's `callback_url` points to it.

The bot does not simulate a recurring plan with its own timer: only RollyPay performs automatic charges, and access is extended only after a confirmed paid charge.
