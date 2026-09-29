import os

# app.py reads these at import time and exits if the password is missing, so they must be
# present before any test module imports it. Real credentials are irrelevant: the tests patch
# httpx, so the router is never contacted.
os.environ.setdefault("TPLINK_PASSWORD", "test_password")
os.environ.setdefault("TPLINK_HOST", "192.168.0.1")
