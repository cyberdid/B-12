import httpx

from b12.tools import network
from tests.integration import test_agent_loop as base

runtime_factory = base.runtime_factory


class Guard:
    def check(self):
        pass


async def test_search_returns_links_and_applies_network_policy():
    assert hasattr(network, 'web_search'), 'web_search tool is missing'
    rss = (
        b'<rss><channel><item><title>Example</title><link>https://example.org/a</link>'
        b'<description>Useful result</description></item></channel></rss>'
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=rss))
    args = network.SearchArgs(query='example')
    denied = await network.web_search(args, Guard(), allow=(), transport=transport)
    assert denied.error_code == 'network_denied'
    result = await network.web_search(args, Guard(), allow=('www.bing.com',), transport=transport)
    assert result.status == 'completed'
    assert result.content['results'][0]['url'] == 'https://example.org/a'
    assert result.content['results'][0]['title'] == 'Example'


async def test_search_reports_a_failed_remote_response_without_crashing():
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    result = await network.web_search(
        network.SearchArgs(query='example'), Guard(), allow=('www.bing.com',), transport=transport
    )
    assert result.status == 'unknown'
    assert result.error_code == 'network_failed'
    assert result.side_effects[0].kind == 'http_request'


async def test_html_challenge_is_not_treated_as_an_empty_search_result():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text='<html>challenge</html>')
    )
    result = await network.web_search(
        network.SearchArgs(query='example'), Guard(), allow=('www.bing.com',), transport=transport
    )
    assert result.status == 'unknown'
    assert result.error_code == 'network_failed'


async def test_search_extracts_direct_result_links_from_duckduckgo():
    html = (b"<table><tr><td><a rel='nofollow' "
            b"href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fresult' "
            b"class='result-link'>A result</a></td></tr><tr>"
            b"<td class='result-snippet'>A <b>useful</b> snippet.</td></tr></table>")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html.decode()))
    result = await network.web_search(
        network.SearchArgs(query='example'), Guard(), allow=('lite.duckduckgo.com',),
        transport=transport,
    )
    assert result.status == 'completed'
    assert result.content['results'] == [{
        'title': 'A result', 'url': 'https://example.org/result',
        'snippet': 'A useful snippet.',
    }]


async def test_agent_can_call_web_search_and_use_its_result(runtime_factory, monkeypatch):
    state, factory = runtime_factory
    runtime = factory(network_allow=('www.bing.com',))
    who = base.owner(runtime)
    original = network.web_search
    rss = (b'<rss><channel><item><title>Example</title>'
           b'<link>https://example.org/</link></item></channel></rss>')
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=rss))

    async def search(args, guard, allow):
        return await original(args, guard, allow, transport=transport)

    monkeypatch.setattr(network, 'web_search', search)
    state['script'] = [
        {'tool_calls': [('web_search', {'query': 'example'})]},
        {'content': 'Знайдено https://example.org/'},
    ]
    result, events = await base.run_turn(runtime, who, 'Знайди example в інтернеті')
    assert result.state == 'completed'
    assert result.tool_results[0].name == 'web_search'
    assert result.tool_results[0].content['results'][0]['url'] == 'https://example.org/'
    assert result.tool_results[0].side_effects[0]['kind'] == 'http_request'
    assert any(event.type == 'tool_result' for event in events)
