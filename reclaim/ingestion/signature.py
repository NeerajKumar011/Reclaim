"""Razorpay webhook signature verification.

Razorpay signs webhooks with HMAC-SHA256:
  signature = HMAC-SHA256(webhook_secret, raw_request_body)

The signature is sent in the X-Razorpay-Signature header.
We verify using constant-time comparison to prevent timing attacks.
"""

import hashlib
import hmac


def compute_signature(raw_body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for Razorpay webhook payload."""
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_razorpay_signature(
    raw_body: bytes,
    signature: str,
    secret: str,
) -> bool:
    """Verify a Razorpay webhook signature.

    Args:
        raw_body: The raw, unparsed request body bytes.
        signature: The value of the X-Razorpay-Signature header.
        secret: The webhook secret configured in the Razorpay dashboard.

    Returns:
        True if the signature is valid, False otherwise.
    """
    expected = compute_signature(raw_body, secret)
    return hmac.compare_digest(expected, signature)
