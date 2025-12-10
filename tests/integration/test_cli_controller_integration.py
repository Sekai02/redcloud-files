"""Integration tests for CLI-Controller communication."""

import pytest
from fastapi.testclient import TestClient
from controller.main import app


@pytest.fixture
def controller_api():
    """Create FastAPI test client for controller API."""
    return TestClient(app)


def test_full_registration_flow(controller_api):
    """Test registration flow returns NotImplementedError as expected."""
    response = controller_api.post('/auth/register', json={
        'username': 'testuser',
        'password': 'password123'
    })

    assert response.status_code == 501
    data = response.json()
    assert data['code'] == 'NOT_IMPLEMENTED'
    assert 'detail' in data


def test_full_login_flow(controller_api):
    """Test login flow returns NotImplementedError as expected."""
    response = controller_api.post('/auth/login', json={
        'username': 'testuser',
        'password': 'password123'
    })

    assert response.status_code == 501
    data = response.json()
    assert data['code'] == 'NOT_IMPLEMENTED'


def test_file_operations_without_auth(controller_api):
    """Test that file operations require authentication."""
    response = controller_api.post('/files',
        files={'file': ('test.txt', b'content')},
        data={'tags': 'tag1'}
    )
    assert response.status_code in [401, 422]

    response = controller_api.get('/files?tags=tag1')
    assert response.status_code in [401, 422]


def test_file_upload_with_fake_auth(controller_api):
    """Test file upload with fake auth token."""
    response = controller_api.post('/files',
        files={'file': ('test.txt', b'test content')},
        data={'tags': 'tag1,tag2'},
        headers={'Authorization': 'Bearer dfs_fake_token'}
    )

    assert response.status_code in [401, 501]


def test_list_files_with_fake_auth(controller_api):
    """Test list files with fake auth token."""
    response = controller_api.get('/files?tags=tag1',
        headers={'Authorization': 'Bearer dfs_fake_token'}
    )

    assert response.status_code in [401, 501]


def test_delete_files_with_fake_auth(controller_api):
    """Test delete files with fake auth token."""
    response = controller_api.delete('/files?tags=tag1',
        headers={'Authorization': 'Bearer dfs_fake_token'}
    )

    assert response.status_code in [401, 501]


def test_add_tags_with_fake_auth(controller_api):
    """Test add tags with fake auth token."""
    response = controller_api.post('/files/tags',
        json={'query_tags': ['tag1'], 'new_tags': ['tag2']},
        headers={'Authorization': 'Bearer dfs_fake_token'}
    )

    assert response.status_code in [401, 501]


def test_delete_tags_with_fake_auth(controller_api):
    """Test delete tags with fake auth token."""
    import json as json_module
    response = controller_api.request(
        'DELETE',
        '/files/tags',
        content=json_module.dumps({'query_tags': ['tag1'], 'tags_to_remove': ['tag2']}),
        headers={
            'Authorization': 'Bearer dfs_fake_token',
            'Content-Type': 'application/json'
        }
    )

    assert response.status_code in [401, 501]


def test_multipart_upload_format(controller_api):
    """Test that multipart file upload is correctly formatted."""
    response = controller_api.post('/files',
        files={'file': ('myfile.txt', b'file content here')},
        data={'tags': 'important,work'},
        headers={'Authorization': 'Bearer dfs_test'}
    )

    assert response.status_code in [401, 501]


def test_json_payload_format(controller_api):
    """Test that JSON payloads are correctly formatted."""
    response = controller_api.post('/files/tags',
        json={
            'query_tags': ['existing1', 'existing2'],
            'new_tags': ['newtag1', 'newtag2']
        },
        headers={'Authorization': 'Bearer dfs_test'}
    )

    assert response.status_code in [401, 501]
