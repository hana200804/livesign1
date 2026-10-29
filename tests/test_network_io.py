import io
import json
import urllib.error

import pytest

from survey.io import load_env
from survey.network import Http, Mapillary, SurveyError, canonical_id, safe_graph_url


@pytest.mark.parametrize("identity", ["../.env", "7/../8", True, None, 1.5])
def test_external_image_id_cannot_become_a_path(identity):
    with pytest.raises(SurveyError):
        canonical_id(identity)


def test_external_image_id_preserves_integer_precision():
    assert canonical_id(9_007_199_254_740_993) == "9007199254740993"


@pytest.mark.parametrize(
    "url",
    [
        "http://graph.mapillary.com/images",
        "https://graph.mapillary.com.evil.test/images",
        "https://user@graph.mapillary.com/images",
        "https://graph.mapillary.com:444/images",
    ],
)
def test_pagination_cannot_forward_secret_to_another_origin(url):
    with pytest.raises(SurveyError):
        safe_graph_url(url)


def test_pagination_removes_embedded_access_token():
    clean = safe_graph_url("https://graph.mapillary.com/images?after=abc&access_token=secret")
    assert "secret" not in clean
    assert "after=abc" in clean


def test_pagination_follows_all_pages_without_persisting_token():
    class FakeHttp:
        def __init__(self):
            self.calls = []

        def json(self, url, token):
            self.calls.append((url, token))
            return (
                {
                    "data": [{"id": "a"}],
                    "paging": {
                        "next": "https://graph.mapillary.com/images?after=2&access_token=secret"
                    },
                }
                if len(self.calls) == 1
                else {"data": [{"id": "b"}]}
            )

    http = FakeHttp()
    assert list(Mapillary("secret", http).pages("/images", {})) == [{"id": "a"}, {"id": "b"}]
    assert len(http.calls) == 2
    assert all("secret" not in url and token == "secret" for url, token in http.calls)


def test_http_error_body_never_reaches_logs():
    class BrokenOpener:
        def open(self, request, timeout):
            body = json.dumps({"error": {"message": "secret-token", "code": 190}}).encode()
            raise urllib.error.HTTPError(
                request.full_url, 401, "secret-token", {}, io.BytesIO(body)
            )

    client = Http(attempts=1)
    client.opener = BrokenOpener()
    with pytest.raises(SurveyError) as caught:
        client.read("https://graph.mapillary.com/images", token="secret-token")
    assert "secret-token" not in str(caught.value)
    assert "190" in str(caught.value)


def test_dotenv_does_not_override_existing_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MAPILLARY_TOKEN", "existing")
    path = tmp_path / ".env"
    path.write_text('MAPILLARY_TOKEN="replacement"\n# comment\n', encoding="utf-8")
    load_env(path)
    import os

    assert os.environ["MAPILLARY_TOKEN"] == "existing"


def test_invalid_dotenv_error_has_no_line_content(tmp_path):
    path = tmp_path / ".env"
    path.write_text("secret-token-value", encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_env(path)
    assert "secret-token-value" not in str(caught.value)
