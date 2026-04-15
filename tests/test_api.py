from fastapi.testclient import TestClient

from app.main import app


API_HEADERS = {'X-Tenant-Id': 'tenant-test', 'X-API-Key': 'dev-api-key'}


def test_models_endpoint():
    client = TestClient(app)
    response = client.get('/api/models', headers=API_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 4


def test_auth_required():
    client = TestClient(app)
    response = client.get('/api/models')
    assert response.status_code == 401


def test_dump_and_retrieve_flow():
    client = TestClient(app)
    dump_payload = {
        'type': 'interaction',
        'layer': 'dumps',
        'content': 'BrainDump capture first structure later',
        'trust': 1.0,
        'confidence': 0.8,
    }
    dump_response = client.post('/api/dump', json=dump_payload, headers=API_HEADERS)
    assert dump_response.status_code == 200

    decision_payload = {
        'context': 'capture first strategy',
        'action': 'use dump first',
        'reward': 0.9,
        'policy_name': 'capture_first_policy',
    }
    decision_response = client.post('/api/decisions', json=decision_payload, headers=API_HEADERS)
    assert decision_response.status_code == 200

    belief_response = client.post('/api/beliefs', json={'statement': 'capture first', 'reinforce': True}, headers=API_HEADERS)
    assert belief_response.status_code == 200

    policy_response = client.get('/api/policies', headers=API_HEADERS)
    assert policy_response.status_code == 200
    assert len(policy_response.json()['policies']) >= 1

    retrieve_response = client.post('/api/retrieve', json={'query': 'capture', 'k': 5}, headers=API_HEADERS)
    assert retrieve_response.status_code == 200
    assert len(retrieve_response.json()['results']) >= 1
