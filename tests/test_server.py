import pytest
import httpx2 as httpx
from types import SimpleNamespace
from fastmcp import Client
from fastmcp.server.auth.providers.github import GitHubProvider
from app.auth import allowed, build_auth
from app.jira import JiraClient, JiraError
from app.main import build_server

@pytest.fixture
def config(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    for key, value in {'MCP_PUBLIC_URL':'https://jira-mcp.example.com','GITHUB_ALLOWED_USER_ID':'123',
        'GITHUB_CLIENT_ID':'test','GITHUB_CLIENT_SECRET':'test','JWT_SIGNING_KEY':'a'*64,
        'STORAGE_ENCRYPTION_KEY':Fernet.generate_key().decode(),'OAUTH_STORAGE_DIR':str(tmp_path),
        'JIRA_BASE_URL':'https://jira.example.com/jira','JIRA_USERNAME':'test','JIRA_PASSWORD':'secret'}.items():
        monkeypatch.setenv(key, value)

@pytest.mark.asyncio
async def test_get_pagination():
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(200,json={'total':3,'startAt':0,'issues':[{'key':'AT-1','fields':{'summary':'Test'}}]})
    jira=JiraClient('https://jira.example.com/jira','user','pass',httpx.MockTransport(handler))
    result=await jira.search('assignee = currentUser()',max_results=1)
    assert result['next_start_at']==1
    assert result['issues'][0]['url']=='https://jira.example.com/jira/browse/AT-1'
    assert calls[0].method=='GET'
    assert calls[0].url.path=='/jira/rest/api/2/search'
    assert calls[0].headers['authorization'].startswith('Basic ')

@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint',['https://evil.example','../myself','issue/AT-1/comment','issue/AT-1?expand=all','issue/AT-1/../../project'])
async def test_allowlist(endpoint):
    def fail(req):
        pytest.fail('Must not request')
    jira=JiraClient('https://jira.example','u','p',httpx.MockTransport(fail))
    with pytest.raises(JiraError):
        await jira.get(endpoint)

@pytest.mark.asyncio
@pytest.mark.parametrize('code',[302,401,403,404,500])
async def test_errors_and_redirect(code):
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(code,text='SECRET BODY',headers={'location':'https://evil.example'})
    jira=JiraClient('https://jira.example','u','p',httpx.MockTransport(handler))
    with pytest.raises(JiraError) as exc:
        await jira.get('myself')
    assert 'SECRET' not in str(exc.value)
    assert len(calls)==1

@pytest.mark.asyncio
async def test_auth(config,monkeypatch):
    auth=build_auth()
    for subject in ['123','999',None]:
        async def fake(self,token):
            return SimpleNamespace(claims={'sub':subject})
        monkeypatch.setattr(GitHubProvider,'verify_token',fake)
        assert (await auth.verify_token('opaque') is not None)==(subject=='123')
    assert not allowed(None,'123')

@pytest.mark.asyncio
async def test_tools_guard(config):
    async with Client(build_server()) as client:
        tools=await client.list_tools()
        assert len(tools)==5
        assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools)
        for tool in tools:
            args={'jql':'project = AT'} if tool.name=='jira_search_issues' else {'issue_key':'AT-1'} if tool.name in {'jira_get_issue','jira_get_transitions'} else {}
            with pytest.raises(Exception,match='Access denied'):
                await client.call_tool(tool.name,args)

@pytest.mark.asyncio
async def test_http_discovery(config):
    app=build_server().http_app(path='/mcp',stateless_http=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://jira-mcp.example.com') as client:
        assert (await client.get('/healthz')).status_code==200
        metadata=await client.get('/.well-known/oauth-authorization-server')
        assert metadata.status_code==200
        assert metadata.json()['registration_endpoint'].startswith('https://jira-mcp.example.com/')
        response=await client.post('/mcp',json={'jsonrpc':'2.0','method':'initialize','id':1,'params':{}})
        assert response.status_code==401
        assert 'www-authenticate' in response.headers
