"""Unit tests for DNS-based service discovery module."""

import socket
import pytest
from unittest.mock import patch

from common.dns_discovery import (
    discover_peers,
    discover_controller_peers,
    discover_chunkserver_peers,
    validate_dns_resolution,
    get_peer_count
)


class TestDiscoverPeers:
    """Tests for discover_peers function."""

    @patch('socket.getaddrinfo')
    def test_discover_peers_multiple(self, mock_getaddrinfo):
        """Test discovery of multiple peer instances."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.5', 8000)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.6', 8000)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.7', 8000)),
        ]

        result = discover_peers('controller', 8000)

        assert result == ['10.0.1.5:8000', '10.0.1.6:8000', '10.0.1.7:8000']
        mock_getaddrinfo.assert_called_once_with('controller', 8000, socket.AF_INET, socket.SOCK_STREAM)

    @patch('socket.getaddrinfo')
    def test_discover_peers_single(self, mock_getaddrinfo):
        """Test discovery of single peer instance."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.5', 8000)),
        ]

        result = discover_peers('controller', 8000)

        assert result == ['10.0.1.5:8000']

    @patch('socket.getaddrinfo')
    def test_discover_peers_empty(self, mock_getaddrinfo):
        """Test discovery when no peers are found."""
        mock_getaddrinfo.return_value = []

        result = discover_peers('controller', 8000)

        assert result == []

    @patch('socket.getaddrinfo')
    def test_discover_peers_dns_failure(self, mock_getaddrinfo):
        """Test that DNS resolution failures propagate as exceptions."""
        mock_getaddrinfo.side_effect = socket.gaierror(-2, 'Name or service not known')

        with pytest.raises(socket.gaierror):
            discover_peers('nonexistent', 8000)

    @patch('socket.getaddrinfo')
    def test_discover_peers_unique_filtering(self, mock_getaddrinfo):
        """Test that duplicate IPs are filtered out."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.5', 8000)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.5', 8000)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.6', 8000)),
        ]

        result = discover_peers('controller', 8000)

        assert result == ['10.0.1.5:8000', '10.0.1.6:8000']
        assert len(result) == 2

    @patch('socket.getaddrinfo')
    def test_discover_peers_sorted_output(self, mock_getaddrinfo):
        """Test that results are sorted for determinism."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.9', 8000)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.3', 8000)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.1.6', 8000)),
        ]

        result = discover_peers('controller', 8000)

        assert result == ['10.0.1.3:8000', '10.0.1.6:8000', '10.0.1.9:8000']

    def test_discover_peers_invalid_hostname(self):
        """Test that empty hostname raises ValueError."""
        with pytest.raises(ValueError, match="hostname cannot be empty"):
            discover_peers('', 8000)

    def test_discover_peers_invalid_port_zero(self):
        """Test that port 0 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid port number"):
            discover_peers('controller', 0)

    def test_discover_peers_invalid_port_negative(self):
        """Test that negative port raises ValueError."""
        with pytest.raises(ValueError, match="Invalid port number"):
            discover_peers('controller', -1)

    def test_discover_peers_invalid_port_too_large(self):
        """Test that port > 65535 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid port number"):
            discover_peers('controller', 70000)


class TestDiscoverControllerPeers:
    """Tests for discover_controller_peers function."""

    @patch('common.dns_discovery.discover_peers')
    def test_discover_controller_peers_calls_with_correct_params(self, mock_discover):
        """Test that discover_controller_peers uses correct hostname and port."""
        mock_discover.return_value = ['10.0.1.5:8000']

        result = discover_controller_peers()

        mock_discover.assert_called_once_with('controller', 8000)
        assert result == ['10.0.1.5:8000']

    @patch('common.dns_discovery.discover_peers')
    def test_discover_controller_peers_propagates_exception(self, mock_discover):
        """Test that DNS errors propagate from discover_controller_peers."""
        mock_discover.side_effect = socket.gaierror(-2, 'Name or service not known')

        with pytest.raises(socket.gaierror):
            discover_controller_peers()


class TestDiscoverChunkserverPeers:
    """Tests for discover_chunkserver_peers function."""

    @patch('common.dns_discovery.discover_peers')
    def test_discover_chunkserver_peers_calls_with_correct_params(self, mock_discover):
        """Test that discover_chunkserver_peers uses correct hostname and port."""
        mock_discover.return_value = ['10.0.1.10:50051', '10.0.1.11:50051']

        result = discover_chunkserver_peers()

        mock_discover.assert_called_once_with('chunkserver', 50051)
        assert result == ['10.0.1.10:50051', '10.0.1.11:50051']

    @patch('common.dns_discovery.discover_peers')
    def test_discover_chunkserver_peers_propagates_exception(self, mock_discover):
        """Test that DNS errors propagate from discover_chunkserver_peers."""
        mock_discover.side_effect = socket.gaierror(-2, 'Name or service not known')

        with pytest.raises(socket.gaierror):
            discover_chunkserver_peers()


class TestValidateDnsResolution:
    """Tests for validate_dns_resolution function."""

    @patch('common.dns_discovery.discover_peers')
    def test_validate_dns_resolution_success_single_peer(self, mock_discover):
        """Test validation returns True when one peer found."""
        mock_discover.return_value = ['10.0.1.5:8000']

        result = validate_dns_resolution('controller', 8000)

        assert result is True

    @patch('common.dns_discovery.discover_peers')
    def test_validate_dns_resolution_success_multiple_peers(self, mock_discover):
        """Test validation returns True when multiple peers found."""
        mock_discover.return_value = ['10.0.1.5:8000', '10.0.1.6:8000']

        result = validate_dns_resolution('controller', 8000)

        assert result is True

    @patch('common.dns_discovery.discover_peers')
    def test_validate_dns_resolution_failure_empty(self, mock_discover):
        """Test validation returns False when no peers found."""
        mock_discover.return_value = []

        result = validate_dns_resolution('controller', 8000)

        assert result is False

    @patch('common.dns_discovery.discover_peers')
    def test_validate_dns_resolution_failure_dns_error(self, mock_discover):
        """Test validation returns False on DNS error (non-throwing)."""
        mock_discover.side_effect = socket.gaierror(-2, 'Name or service not known')

        result = validate_dns_resolution('nonexistent', 8000)

        assert result is False

    @patch('common.dns_discovery.discover_peers')
    def test_validate_dns_resolution_failure_value_error(self, mock_discover):
        """Test validation returns False on ValueError (non-throwing)."""
        mock_discover.side_effect = ValueError("Invalid port")

        result = validate_dns_resolution('controller', -1)

        assert result is False


class TestGetPeerCount:
    """Tests for get_peer_count function."""

    @patch('common.dns_discovery.discover_peers')
    def test_get_peer_count_multiple(self, mock_discover):
        """Test peer count with multiple peers."""
        mock_discover.return_value = ['10.0.1.5:8000', '10.0.1.6:8000', '10.0.1.7:8000']

        result = get_peer_count('controller', 8000)

        assert result == 3

    @patch('common.dns_discovery.discover_peers')
    def test_get_peer_count_single(self, mock_discover):
        """Test peer count with single peer."""
        mock_discover.return_value = ['10.0.1.5:8000']

        result = get_peer_count('controller', 8000)

        assert result == 1

    @patch('common.dns_discovery.discover_peers')
    def test_get_peer_count_zero(self, mock_discover):
        """Test peer count when no peers found."""
        mock_discover.return_value = []

        result = get_peer_count('controller', 8000)

        assert result == 0

    @patch('common.dns_discovery.discover_peers')
    def test_get_peer_count_dns_error(self, mock_discover):
        """Test peer count returns 0 on DNS error (non-throwing)."""
        mock_discover.side_effect = socket.gaierror(-2, 'Name or service not known')

        result = get_peer_count('nonexistent', 8000)

        assert result == 0

    @patch('common.dns_discovery.discover_peers')
    def test_get_peer_count_value_error(self, mock_discover):
        """Test peer count returns 0 on ValueError (non-throwing)."""
        mock_discover.side_effect = ValueError("Invalid hostname")

        result = get_peer_count('', 8000)

        assert result == 0
