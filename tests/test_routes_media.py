import io, os

def test_stt_silence_guard(client):
    data = {"audio": (io.BytesIO(b"\x00"*1024), "s.webm")}
    r = client.post("/api/stt", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["text"] == ""

def test_tts_returns_audio(client):
    r = client.post("/api/tts", json={"text": "hello"})
    assert r.status_code == 200
    assert r.mimetype == "audio/mpeg"
    assert len(r.data) > 0

def test_image_generation_saves_file(client, app):
    r = client.post("/api/image", json={"prompt": "cover for A"})
    assert r.status_code == 200
    url = r.get_json()["url"]
    assert url.startswith("/static/gen/")
    path = os.path.join(app.static_folder, "gen", os.path.basename(url))
    assert os.path.exists(path)
