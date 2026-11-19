import os
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.exceptions import ToolError
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper


def required(name):
    value = os.environ.get(name, '')
    if not value or value.startswith('CHANGE_'):
        raise ValueError(f'Set {name} in .env')
    return value


def allowed(token, user_id):
    return token is not None and str((token.claims or {}).get('sub', '')) == user_id


class RestrictedGitHubProvider(GitHubProvider):
    def __init__(self, *, allowed_user_id, **kwargs):
        self.allowed_user_id = allowed_user_id
        super().__init__(**kwargs)

    async def verify_token(self, token):
        result = await super().verify_token(token)
        return result if allowed(result, self.allowed_user_id) else None


def require_owner(user_id):
    if not allowed(get_access_token(), user_id):
        raise ToolError('Access denied')


def build_auth():
    public_url = required('MCP_PUBLIC_URL').rstrip('/')
    u = urlsplit(public_url)
    if u.scheme != 'https' or not u.hostname or u.path or u.query or u.fragment or u.username:
        raise ValueError('MCP_PUBLIC_URL must be HTTPS origin, e.g. https://jira-mcp.example.com')
    user_id = required('GITHUB_ALLOWED_USER_ID')
    if not user_id.isdigit():
        raise ValueError('GITHUB_ALLOWED_USER_ID must be a numeric GitHub account ID')
    jwt_key = required('JWT_SIGNING_KEY')
    if len(jwt_key) < 32:
        raise ValueError('JWT_SIGNING_KEY must contain at least 32 characters')
    store = FernetEncryptionWrapper(FileTreeStore(data_directory=os.environ.get('OAUTH_STORAGE_DIR', '/data/oauth')),
                                    fernet=Fernet(required('STORAGE_ENCRYPTION_KEY').encode()))
    return RestrictedGitHubProvider(allowed_user_id=user_id, client_id=required('GITHUB_CLIENT_ID'),
        client_secret=required('GITHUB_CLIENT_SECRET'), base_url=public_url,
        jwt_signing_key=jwt_key, client_storage=store, required_scopes=['read:user'],
        allowed_client_redirect_uris=['https://chatgpt.com/*', 'https://chat.openai.com/*'],
        enable_cimd=False, require_authorization_consent=True)
