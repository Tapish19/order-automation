from datetime import timedelta

from .timeutils import past_expected, timestamp

DEFAULT_RULES = {
    "unconfirmed_hours": 2,
    "dispatch_hours": 24,
    "high_value_rupees": 5000,
    "follow_up_hours": 4,
}
CATEGORIES = {
    "unconfirmed": "Unconfirmed > 2h",
    "dispatch_delay": "Dispatch delay",
    "delivery_delay": "Delivery delay",
    "failed_delivery": "Failed delivery",
    "high_value_delay": "High-value delay",
}
TERMINAL = {"delivered", "cancelled", "returned"}
SHIPPED = {"dispatched", "out_for_delivery", "failed_delivery"}
STATUSES = TERMINAL | SHIPPED | {"unconfirmed", "confirmed"}


def detect(order, config, now):
    """Evaluate only validated orders. Missing prerequisites belong in DataIssue."""
    found = {}
    if order.status in TERMINAL:
        return found

    def add(category, reason, priority, action, immediate=False):
        found[category] = {
            "reason": reason, "priority": priority, "recommended_action": action,
            "deadline": now if immediate else now + timedelta(hours=config["follow_up_hours"]),
        }

    if order.status == "unconfirmed":
        if now - timestamp(order.order_date) > timedelta(hours=config["unconfirmed_hours"]):
            add("unconfirmed", f"Order remains unconfirmed for more than {config['unconfirmed_hours']:g} hours.",
                "medium", "Call the customer to confirm the order and payment preference.")
    if order.status == "confirmed":
        reference = order.confirmed_at or order.order_date
        if now - timestamp(reference) >= timedelta(hours=config["dispatch_hours"]):
            basis = "confirmation timestamp" if order.confirmed_at else "order timestamp (confirmation time unavailable)"
            add("dispatch_delay", f"Confirmed order has no dispatch after {config['dispatch_hours']:g} hours, measured from {basis}.",
                "high", "Contact the warehouse, unblock dispatch, and update the customer.")
    if order.status in SHIPPED and past_expected(order.expected_delivery_date, now):
        add("delivery_delay", "Shipment is past expected delivery and remains undelivered.",
            "high", "Check with the courier and give the customer a revised delivery plan.")
    if order.status == "failed_delivery":
        add("failed_delivery", "Failed delivery attempt requires immediate follow-up.", "urgent",
            "Call the customer now, confirm the address and availability, and arrange another attempt.", immediate=True)
    if order.value_paise > round(config["high_value_rupees"] * 100) and past_expected(order.expected_delivery_date, now):
        add("high_value_delay", f"Order value exceeds ₹{config['high_value_rupees']:g} and expected delivery has passed.",
            "urgent", "Escalate to the manager and courier; personally update this high-value customer.")
    return found
