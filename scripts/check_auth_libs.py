# scripts/check_auth_libs.py
# Quick check that the password-hashing and JWT libraries work on this machine.
import jwt
from pwdlib import PasswordHash

ph = PasswordHash.recommended()  # uses the Argon2 hashing method
hashed = ph.hash("correct horse")
print("hash starts with:", hashed[:9])
print("right password:", ph.verify("correct horse", hashed))
print("wrong password:", ph.verify("wrong", hashed))

SECRET = "fake-secret-only-for-this-check-1234567890"  # the real secret will live in .env, never in code
token = jwt.encode({"sub": "1", "role": "admin"}, SECRET, algorithm="HS256")
print("token parts:", len(token.split(".")))
print("decoded:", jwt.decode(token, SECRET, algorithms=["HS256"]))
