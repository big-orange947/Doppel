"""Canary safety/shape: synthetic credentials and MockTransport only."""

import json
import sys

import httpx
import pytest

from scripts.smoke_aliyun_embedding import main, run_smoke


@pytest.mark.parametrize("failed", [False, True])
async def test_two_request_canary_is_bound_and_does_not_persist_sources_or_secrets(
    failed,
):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if failed and len(requests) == 2:
            return httpx.Response(401, text="synthetic-key and private upstream text")
        return httpx.Response(
            200,
            json={
                "output": {
                    "embeddings": [
                        {"text_index": i, "embedding": [0.1] * 2048} for i in range(2)
                    ]
                },
                "usage": {"total_tokens": 12},
            },
        )

    result = await run_smoke(
        api_key="synthetic-key",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
        transport=httpx.MockTransport(handler),
    )
    assert len(requests) == result["usage"]["attempts"] == result["attempt_cap"] == 2
    assert result["passed"] is not failed
    assert result["database_writes"] == 0 and not result["quality_score_available"]
    assert [r["parameters"]["text_type"] for r in requests] == ["document", "query"]
    encoded = json.dumps(result)
    assert all(
        secret not in encoded
        for secret in ("synthetic-key", "private upstream", "telescope", "光学仪器")
    )
    assert result["usage"]["failed"] == int(failed)
    assert result["usage"]["missing_usage"] == int(failed)
    if failed:
        assert result["http_status"] == 401


@pytest.mark.parametrize("fault", ["no_live", "existing", "missing_key", "bad_url"])
def test_cli_invalid_or_unapproved_configuration_never_runs_provider(
    tmp_path, monkeypatch, capsys, fault
):
    output = tmp_path / "receipt.json"
    if fault == "existing":
        output.write_text("preserved")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "synthetic-key")
    monkeypatch.setenv("DOPPEL_ALIYUN_BASE_URL", "https://evil.invalid/api/v1")
    if fault == "missing_key":
        monkeypatch.delenv("DASHSCOPE_API_KEY")
    monkeypatch.setattr(
        sys,
        "argv",
        ["smoke", "--output", str(output), *([] if fault == "no_live" else ["--live"])],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "synthetic-key" not in capsys.readouterr().err
    if fault == "existing":
        assert output.read_text() == "preserved"
    else:
        assert not output.exists()
