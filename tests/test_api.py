from fastapi.testclient import TestClient

from app.main import app


def test_models_endpoint():
    client = TestClient(app)
    response = client.get('/api/models')
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 4


def test_dump_and_retrieve_flow():
    client = TestClient(app)
    dump_payload = {
        'type': 'interaction',
        'layer': 'dumps',
        'content': 'BrainDump capture first structure later',
        'trust': 1.0,
    }
    dump_response = client.post('/api/dump', json=dump_payload)
    assert dump_response.status_code == 200

    retrieve_response = client.post('/api/retrieve', json={'query': 'capture', 'k': 5})
    assert retrieve_response.status_code == 200
    assert len(retrieve_response.json()['results']) >= 1
