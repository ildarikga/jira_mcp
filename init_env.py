"""Create .env once, with locally generated OAuth storage/signing secrets."""
import base64
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
text = (root / '.env.example').read_text()
text = text.replace('CHANGE_RANDOM_64_HEX_CHARACTERS', secrets.token_hex(32))
text = text.replace('CHANGE_FERNET_KEY', base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
try:
    fd = os.open(root / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit('.env already exists; left unchanged')
with os.fdopen(fd, 'w') as f:
    f.write(text)
print('Created .env. Fill domain, Jira and GitHub settings locally.')
