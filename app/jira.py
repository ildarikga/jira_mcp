import re
from urllib.parse import urlsplit
import httpx2 as httpx

FIELDS = 'summary,description,status,priority,assignee,duedate,project,updated,resolution'

class JiraError(Exception):
    pass

class JiraClient:
    def __init__(self, base_url, username, password, transport=None):
        parsed = urlsplit(base_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('JIRA_BASE_URL must be an HTTPS URL without credentials/query/fragment')
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.transport = transport

    @staticmethod
    def key(key):
        key = key.upper()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*-[1-9][0-9]*', key):
            raise JiraError('Invalid issue key; expected PROJECT-123')
        return key

    async def get(self, endpoint, params=None):
        # Fixed allowlist; no arbitrary URLs, write verbs, attachment downloads or redirects.
        if endpoint not in {'myself', 'search', 'project'} and not re.fullmatch(r'issue/[A-Z][A-Z0-9_]*-[1-9][0-9]*(/transitions)?', endpoint):
            raise JiraError('Endpoint is not allowed')
        try:
            async with httpx.AsyncClient(auth=(self.username, self.password), timeout=30,
                                         follow_redirects=False, transport=self.transport) as client:
                response = await client.get(f'{self.base_url}/rest/api/2/{endpoint}', params=params, headers={'Accept': 'application/json'})
        except httpx.RequestError:
            raise JiraError('Jira network/TLS error; check connectivity from MCP host') from None
        if response.status_code != 200:
            # Never expose upstream bodies, credentials, or URLs with JQL in errors.
            raise JiraError(f'Jira returned HTTP {response.status_code}; check permissions, auth and query')
        try:
            return response.json()
        except ValueError:
            raise JiraError('Jira returned non-JSON data; check base URL and SSO redirects') from None

    def issue_summary(self, issue, detailed=False):
        f = issue.get('fields', {})
        result = {'key': issue['key'], 'url': f"{self.base_url}/browse/{issue['key']}",
                  'summary': f.get('summary'), 'status': (f.get('status') or {}).get('name'),
                  'priority': (f.get('priority') or {}).get('name'),
                  'assignee': (f.get('assignee') or {}).get('name'), 'due_date': f.get('duedate'),
                  'project': (f.get('project') or {}).get('key'), 'updated': f.get('updated'),
                  'resolution': (f.get('resolution') or {}).get('name')}
        if detailed:
            result['description'] = (f.get('description') or '')[:30000]
        return result

    async def search(self, jql, start_at=0, max_results=50):
        if not 1 <= max_results <= 100 or start_at < 0 or not jql.strip() or len(jql) > 4000:
            raise JiraError('Use nonempty JQL <= 4000 chars, start_at >= 0, max_results 1..100')
        data = await self.get('search', {'jql': jql, 'startAt': start_at, 'maxResults': max_results, 'fields': FIELDS.replace('description,', '')})
        issues = data.get('issues', [])
        next_at = data.get('startAt', start_at) + len(issues)
        return {'total': data['total'], 'start_at': data.get('startAt', start_at),
                'next_start_at': next_at if issues and next_at < data['total'] else None,
                'issues': [self.issue_summary(i) for i in issues]}
