import requests

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8000"
TIMEOUT = 30


def test_api_health_endpoint_responds():
    response = requests.get(f"{API_URL}/health", timeout=TIMEOUT)

    assert response.status_code == 200
    assert response.json().get("status") == "healthy"


def test_gallery_endpoint_returns_expected_shape():
    response = requests.get(f"{API_URL}/api/gallery", timeout=TIMEOUT)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("items"), list)
    assert isinstance(body.get("total"), int)
    assert isinstance(body.get("page"), int)
    assert isinstance(body.get("limit"), int)


def test_gallery_endpoint_rejects_invalid_status_filter():
    response = requests.get(
        f"{API_URL}/api/gallery",
        params={"status": "not-a-real-status"},
        timeout=TIMEOUT,
    )

    assert response.status_code == 422


def test_bulk_upload_requires_zip_archive():
    response = requests.post(
        f"{API_URL}/api/upload/bulk",
        files={"file": ("not-a-zip.txt", b"hello", "text/plain")},
        timeout=TIMEOUT,
    )

    assert response.status_code == 400
    assert "zip" in response.text.lower()


def test_frontend_core_pages_load():
    for path in ["/", "/gallery", "/search", "/clusters"]:
        response = requests.get(f"{BASE_URL}{path}", timeout=TIMEOUT)

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Find" in response.text or "FIND" in response.text


def test_frontend_upload_page_exposes_zip_mode():
    response = requests.get(BASE_URL, timeout=TIMEOUT)

    assert response.status_code == 200
    assert "Upload" in response.text
    assert "ZIP" in response.text


if __name__ == "__main__":
    test_api_health_endpoint_responds()
    test_gallery_endpoint_returns_expected_shape()
    test_gallery_endpoint_rejects_invalid_status_filter()
    test_bulk_upload_requires_zip_archive()
    test_frontend_core_pages_load()
    test_frontend_upload_page_exposes_zip_mode()
