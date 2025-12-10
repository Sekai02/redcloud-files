"""Unit tests for ControllerClient."""

import pytest
import httpx
from cli.controller_client import ControllerClient
from cli.config import Config


@pytest.fixture
def mock_transport_success():
    """Mock transport that returns successful responses."""
    def handler(request):
        if request.url.path == '/auth/register':
            return httpx.Response(201, json={'api_key': 'dfs_test123', 'user_id': 'user_abc'})
        elif request.url.path == '/auth/login':
            return httpx.Response(200, json={'api_key': 'dfs_newkey456'})

        elif request.url.path == '/files' and request.method == 'POST':
            return httpx.Response(201, json={
                'file_id': 'file123abc',
                'name': 'test.txt',
                'size': 100,
                'tags': ['tag1', 'tag2']
            })
        elif request.url.path == '/files' and request.method == 'GET':
            return httpx.Response(200, json={
                'files': [
                    {
                        'file_id': 'file123',
                        'name': 'test.txt',
                        'size': 100,
                        'tags': ['tag1'],
                        'owner_id': 'user1',
                        'created_at': '2024-01-01T00:00:00'
                    }
                ]
            })
        elif request.url.path == '/files' and request.method == 'DELETE':
            return httpx.Response(200, json={
                'deleted_count': 2,
                'file_ids': ['file123', 'file456']
            })
        elif request.url.path == '/files/tags' and request.method == 'POST':
            return httpx.Response(200, json={
                'updated_count': 3,
                'file_ids': ['file1', 'file2', 'file3']
            })
        elif request.url.path == '/files/tags' and request.method == 'DELETE':
            return httpx.Response(200, json={
                'updated_count': 1,
                'file_ids': ['file1']
            })

        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def client_with_mock(temp_config, mock_transport_success):
    """Create ControllerClient with mocked HTTP transport."""
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=mock_transport_success, base_url='http://test')
    return client


def test_register_success(client_with_mock, temp_config):
    """Test successful registration saves API key."""
    result = client_with_mock.register('testuser', 'password123')

    assert 'Registration successful' in result
    assert 'user_abc' in result
    assert temp_config.get_api_key() == 'dfs_test123'


def test_register_failure(temp_config):
    """Test registration failure with 400 error."""
    def error_handler(request):
        return httpx.Response(400, json={'detail': 'User exists', 'code': 'USER_ALREADY_EXISTS'})

    transport = httpx.MockTransport(error_handler)
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=transport, base_url='http://test')

    result = client.register('existinguser', 'pass')
    assert 'Username already taken' in result


def test_login_success(client_with_mock, temp_config):
    """Test successful login updates API key."""
    result = client_with_mock.login('testuser', 'password123')

    assert 'Login successful' in result
    assert temp_config.get_api_key() == 'dfs_newkey456'


def test_login_invalid_credentials(temp_config):
    """Test login with invalid credentials."""
    def error_handler(request):
        return httpx.Response(401, json={'detail': 'Invalid creds', 'code': 'INVALID_CREDENTIALS'})

    transport = httpx.MockTransport(error_handler)
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=transport, base_url='http://test')

    result = client.login('wronguser', 'wrongpass')
    assert 'Invalid username or password' in result


def test_add_files_success(client_with_mock, temp_config, sample_file):
    """Test successful file upload."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.add_files([str(sample_file)], ['tag1', 'tag2'])

    assert 'Added: test.txt' in result
    assert 'file123a' in result


def test_add_files_not_logged_in(client_with_mock, sample_file):
    """Test file upload without API key."""
    result = client_with_mock.add_files([str(sample_file)], ['tag1'])

    assert 'Not logged in' in result


def test_add_files_file_not_found(client_with_mock, temp_config):
    """Test file upload with non-existent file."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.add_files(['/nonexistent/file.txt'], ['tag1'])

    assert 'File not found' in result


def test_list_files_success(client_with_mock, temp_config):
    """Test successful file listing."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.list_files(['tag1'])

    assert 'Found 1 file(s)' in result
    assert 'test.txt' in result


def test_list_files_empty_query(client_with_mock, temp_config):
    """Test listing all files with empty query."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.list_files([])

    assert 'Found' in result or 'No files found' in result


def test_list_files_not_logged_in(client_with_mock):
    """Test file listing without API key."""
    result = client_with_mock.list_files(['tag1'])

    assert 'Not logged in' in result


def test_delete_files_success(client_with_mock, temp_config):
    """Test successful file deletion."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.delete_files(['tag1', 'tag2'])

    assert 'Deleted 2 file(s)' in result
    assert 'file123' in result


def test_delete_files_not_logged_in(client_with_mock):
    """Test file deletion without API key."""
    result = client_with_mock.delete_files(['tag1'])

    assert 'Not logged in' in result


def test_add_tags_success(client_with_mock, temp_config):
    """Test successful tag addition."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.add_tags(['tag1'], ['newtag'])

    assert 'Added tags [newtag] to 3 file(s)' in result


def test_add_tags_not_logged_in(client_with_mock):
    """Test tag addition without API key."""
    result = client_with_mock.add_tags(['tag1'], ['newtag'])

    assert 'Not logged in' in result


def test_delete_tags_success(client_with_mock, temp_config):
    """Test successful tag deletion."""
    temp_config.set_api_key('dfs_test')

    result = client_with_mock.delete_tags(['tag1'], ['oldtag'])

    assert 'Removed tags [oldtag] from 1 file(s)' in result


def test_delete_tags_not_logged_in(client_with_mock):
    """Test tag deletion without API key."""
    result = client_with_mock.delete_tags(['tag1'], ['oldtag'])

    assert 'Not logged in' in result


def test_retry_on_server_error(temp_config):
    """Test retry logic on 500 errors."""
    call_count = 0

    def failing_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(500, json={'detail': 'Server error', 'code': 'SERVER_ERROR'})
        return httpx.Response(200, json={'files': []})

    temp_config.data['max_retries'] = 3
    temp_config.data['retry_backoff_multiplier'] = 0.01
    temp_config.set_api_key('dfs_test')

    transport = httpx.MockTransport(failing_handler)
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=transport, base_url='http://test')

    result = client.list_files([])

    assert call_count == 3


def test_no_retry_on_client_error(temp_config):
    """Test no retry on 4xx errors."""
    call_count = 0

    def error_handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={'detail': 'Unauthorized', 'code': 'INVALID_API_KEY'})

    temp_config.set_api_key('dfs_invalid')

    transport = httpx.MockTransport(error_handler)
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=transport, base_url='http://test')

    result = client.list_files([])

    assert call_count == 1


def test_connection_error_handling(temp_config):
    """Test connection error handling."""
    def failing_handler(request):
        raise httpx.ConnectError("Connection refused")

    temp_config.data['max_retries'] = 1
    temp_config.data['retry_backoff_multiplier'] = 0.01

    transport = httpx.MockTransport(failing_handler)
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=transport, base_url='http://test')

    result = client.register('user', 'pass')

    assert 'Cannot connect to controller server' in result


def test_not_implemented_error_formatting(temp_config):
    """Test NotImplementedError (501) is formatted nicely."""
    def not_impl_handler(request):
        return httpx.Response(501, json={'detail': 'Not implemented', 'code': 'NOT_IMPLEMENTED'})

    temp_config.set_api_key('dfs_test')

    transport = httpx.MockTransport(not_impl_handler)
    client = ControllerClient(temp_config)
    client.session = httpx.Client(transport=transport, base_url='http://test')

    result = client.list_files(['tag1'])

    assert 'Feature not yet implemented' in result
    assert 'expected behavior' in result


def test_close_session(client_with_mock):
    """Test closing HTTP session."""
    client_with_mock.close()
    assert client_with_mock.session.is_closed
