"""Tests for Controller API endpoints."""

import pytest
from fastapi.testclient import TestClient
from controller.main import app


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test health check endpoint."""
    response = client.get('/')
    assert response.status_code == 200
    assert response.json()['status'] == 'running'


def test_register_endpoint_exists(client):
    """Test register endpoint exists and returns NotImplementedError."""
    response = client.post('/auth/register', json={
        'username': 'testuser',
        'password': 'password123'
    })
    assert response.status_code == 501
    data = response.json()
    assert data['code'] == 'NOT_IMPLEMENTED'


def test_login_endpoint_exists(client):
    """Test login endpoint exists and returns NotImplementedError."""
    response = client.post('/auth/login', json={
        'username': 'testuser',
        'password': 'password123'
    })
    assert response.status_code == 501
    data = response.json()
    assert data['code'] == 'NOT_IMPLEMENTED'


def test_upload_file_endpoint_exists(client):
    """Test file upload endpoint exists."""
    response = client.post('/files',
        files={'file': ('test.txt', b'content')},
        data={'tags': 'tag1,tag2'},
        headers={'Authorization': 'Bearer dfs_fake_key'}
    )
    assert response.status_code in [401, 501]


def test_list_files_endpoint_exists(client):
    """Test list files endpoint exists."""
    response = client.get('/files?tags=tag1,tag2',
        headers={'Authorization': 'Bearer dfs_fake_key'}
    )
    assert response.status_code in [401, 501]


def test_list_files_empty_tags(client):
    """Test list files endpoint with empty tags parameter."""
    response = client.get('/files?tags=',
        headers={'Authorization': 'Bearer dfs_fake_key'}
    )
    assert response.status_code in [400, 401, 501]


def test_delete_files_endpoint_exists(client):
    """Test delete files endpoint exists."""
    response = client.delete('/files?tags=tag1,tag2',
        headers={'Authorization': 'Bearer dfs_fake_key'}
    )
    assert response.status_code in [401, 501]


def test_add_tags_endpoint_exists(client):
    """Test add tags endpoint exists."""
    response = client.post('/files/tags',
        json={'query_tags': ['tag1'], 'new_tags': ['tag2']},
        headers={'Authorization': 'Bearer dfs_fake_key'}
    )
    assert response.status_code in [401, 501]


def test_delete_tags_endpoint_exists(client):
    """Test delete tags endpoint exists."""
    import json as json_module
    response = client.request(
        'DELETE',
        '/files/tags',
        content=json_module.dumps({'query_tags': ['tag1'], 'tags_to_remove': ['tag2']}),
        headers={
            'Authorization': 'Bearer dfs_fake_key',
            'Content-Type': 'application/json'
        }
    )
    assert response.status_code in [401, 501]


def test_request_validation(client):
    """Test that request validation works (400 for invalid requests)."""
    response = client.post('/auth/register', json={
        'username': 'test'
    })
    assert response.status_code == 422
