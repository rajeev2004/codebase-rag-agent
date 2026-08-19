import hashlib
path = "/home/rajeev/circlehealthNew/abhi-chord/packages/backend/src/routes/v1/claims.js"
with open(path, "rb") as f:
    content = f.read()
hash_value = hashlib.sha256(content).hexdigest()
print(hash_value)