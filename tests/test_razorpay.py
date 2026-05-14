import razorpay
import os
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

client = razorpay.Client(auth=(
    os.getenv("RAZORPAY_KEY_ID"),
    os.getenv("RAZORPAY_KEY_SECRET")
))

# Step 1 — Create order
print("=== Creating Order ===")
order = client.order.create({
    "amount": 74900,  # ₹749 in paise
    "currency": "INR",
    "receipt": "test_receipt_1"
})
print(order)

# Step 2 — Verify payment signature
print("\n=== Testing Signature Verification ===")

def verify_payment_signature(order_id, payment_id, signature, secret):
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

test_payment_id = "pay_test_123456"
test_order_id = order["id"]
test_secret = os.getenv("RAZORPAY_KEY_SECRET")

valid_sig = hmac.new(
    test_secret.encode(),
    f"{test_order_id}|{test_payment_id}".encode(),
    hashlib.sha256
).hexdigest()

print(f"Valid signature check: {verify_payment_signature(test_order_id, test_payment_id, valid_sig, test_secret)}")
print(f"Tampered signature check: {verify_payment_signature(test_order_id, test_payment_id, 'fake_signature', test_secret)}")