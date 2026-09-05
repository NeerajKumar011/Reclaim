"""Razorpay Executor — executes real payment link generation in Razorpay test mode."""

import logging
from typing import Any, Optional

from reclaim.config import get_settings
from reclaim.db.models import Customer

logger = logging.getLogger(__name__)


class RazorpayExecutor:
    """Executor for real Razorpay test-mode API calls."""

    def __init__(self, key_id: Optional[str] = None, key_secret: Optional[str] = None):
        settings = get_settings()
        self.key_id = key_id or settings.RAZORPAY_KEY_ID
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET
        self._client = None

    @property
    def client(self):
        """Lazy-initialize Razorpay client."""
        if self._client is None:
            if not self.key_id or not self.key_secret:
                logger.warning("Razorpay API credentials not configured.")
                return None
            import razorpay
            self._client = razorpay.Client(auth=(self.key_id, self.key_secret))
        return self._client

    def create_payment_link(
        self,
        amount_paise: int,
        customer: Customer,
        description: str = "Reclaim Payment Recovery Link",
    ) -> dict[str, Any]:
        """Create a Razorpay payment link.

        Args:
            amount_paise: Amount in paise (integer).
            customer: Customer model.
            description: Payment link description.

        Returns:
            Dict containing created payment link metadata (id, short_url, status, etc.)
        """
        if self.client is None:
            # Fallback mock payload if keys are missing
            logger.info("Razorpay client missing; returning mock payment link response.")
            return {
                "id": "plink_mock_123456789",
                "short_url": "https://rzp.io/i/mocklink",
                "status": "created",
                "amount": amount_paise,
                "description": description,
            }

        payload = {
            "amount": int(amount_paise),
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "customer": {
                "name": customer.name or "Customer",
                "email": customer.email or "",
                "contact": customer.phone or "",
            },
            "notify": {
                "sms": bool(customer.phone),
                "email": bool(customer.email),
            },
            "reminder_enable": True,
        }

        try:
            response = self.client.payment_link.create(payload)
            logger.info(f"Created Razorpay payment link {response.get('id')} for customer {customer.id}")
            return response
        except Exception as e:
            logger.error(f"Failed to create Razorpay payment link: {e}")
            raise

    def retry_payment(self, order_id: str) -> dict[str, Any]:
        """Attempt to fetch or retry an order payment via Razorpay.

        Args:
            order_id: Razorpay order ID.

        Returns:
            Dict containing order/payment status.
        """
        if self.client is None:
            return {"id": order_id, "status": "retried_mock"}

        try:
            order = self.client.order.fetch(order_id)
            logger.info(f"Retried/fetched Razorpay order {order_id}: status={order.get('status')}")
            return order
        except Exception as e:
            logger.error(f"Failed to retry Razorpay order {order_id}: {e}")
            raise
