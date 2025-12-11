"""HTTP client for communicating with Controller service."""

import os
import time
from typing import Optional
import httpx

from cli.config import Config


class ControllerClient:
    """HTTP client for Controller API with retry logic and error handling."""

    def __init__(self, config: Config):
        """
        Initialize controller client.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.session = httpx.Client(
            base_url=config.get_base_url(),
            timeout=config.get_timeout()
        )

    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        max_retries: Optional[int] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic on 5xx errors and network failures.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            max_retries: Max retry attempts (uses config default if None)
            **kwargs: Additional arguments to pass to httpx request

        Returns:
            HTTP response object

        Raises:
            ConnectionError: If max retries exceeded or connection fails
        """
        retry_config = self.config.get_retry_config()
        max_retries = max_retries if max_retries is not None else retry_config['max_retries']
        backoff = retry_config['retry_backoff_multiplier']

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(method, endpoint, **kwargs)

                if 400 <= response.status_code < 500:
                    return response

                if response.status_code >= 500 and attempt < max_retries:
                    time.sleep(backoff ** attempt)
                    continue

                return response

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < max_retries:
                    time.sleep(backoff ** attempt)
                    continue
        if last_exception:
            if isinstance(last_exception, httpx.ConnectError):
                raise ConnectionError("Cannot connect to controller server. Is it running?")
            elif isinstance(last_exception, httpx.TimeoutException):
                raise ConnectionError("Request timed out. Server may be overloaded.")
        else:
            raise ConnectionError("Max retries exceeded")

    def _format_error(self, response: httpx.Response) -> str:
        """
        Map HTTP errors to user-friendly messages.

        Args:
            response: HTTP response object

        Returns:
            User-friendly error message
        """
        try:
            error_data = response.json()
            detail = error_data.get('detail', 'Unknown error')
            code = error_data.get('code', 'UNKNOWN')
        except:
            detail = response.text if response.text else 'Unknown error'
            code = 'UNKNOWN'

        error_messages = {
            'NOT_IMPLEMENTED': 'Feature not yet implemented on the server (expected behavior).',
            'INVALID_API_KEY': 'Not authenticated. Please run: login <username> <password>',
            'USER_ALREADY_EXISTS': 'Username already taken. Try logging in or choose a different username.',
            'INVALID_CREDENTIALS': 'Invalid username or password.',
            'FILE_NOT_FOUND': 'File not found on server.',
            'UNAUTHORIZED_ACCESS': 'You do not have permission to access this file.',
            'CHUNKSERVER_UNAVAILABLE': 'Storage server is currently unavailable. Please try again later.',
            'INVALID_TAG_QUERY': 'Invalid tag query. Tags must be alphanumeric.',
            'STORAGE_FULL': 'Storage capacity exceeded. Please delete some files.',
            'CHECKSUM_MISMATCH': 'File integrity check failed during upload/download.',
        }

        if code in error_messages:
            return error_messages[code]

        status_messages = {
            400: 'Bad request',
            401: 'Not authenticated',
            403: 'Access forbidden',
            404: 'Not found',
            413: 'File too large',
            500: 'Server error',
            501: 'Feature not implemented (expected behavior)',
            503: 'Service unavailable',
            507: 'Insufficient storage',
        }

        message = status_messages.get(response.status_code, detail)
        return f"{message} (Code: {code})" if code != 'UNKNOWN' else message

    def _get_auth_header(self) -> dict:
        """
        Get Authorization header with API key.

        Returns:
            Dictionary with Authorization header

        Raises:
            ValueError: If no API key is configured
        """
        api_key = self.config.get_api_key()
        if not api_key:
            raise ValueError("Not logged in. Please run: login <username> <password>")
        return {'Authorization': f'Bearer {api_key}'}

    def register(self, username: str, password: str) -> str:
        """
        Register a new user account.

        Args:
            username: Username for new account
            password: Password for new account

        Returns:
            Success message with registration details
        """
        try:
            response = self._request_with_retry(
                'POST',
                '/auth/register',
                json={'username': username, 'password': password}
            )

            if response.status_code == 201:
                data = response.json()
                api_key = data['api_key']
                user_id = data['user_id']

                self.config.set_api_key(api_key)

                return f"Registration successful!\nUser ID: {user_id}\nAPI key saved to config."
            else:
                return f"Registration failed: {self._format_error(response)}"

        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Unexpected error during registration: {e}"

    def login(self, username: str, password: str) -> str:
        """
        Login and get new API key.

        Args:
            username: Username
            password: Password

        Returns:
            Success message with login details
        """
        try:
            response = self._request_with_retry(
                'POST',
                '/auth/login',
                json={'username': username, 'password': password}
            )

            if response.status_code == 200:
                data = response.json()
                api_key = data['api_key']

                self.config.set_api_key(api_key)

                return f"Login successful!\nAPI key updated in config."
            else:
                return f"Login failed: {self._format_error(response)}"

        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Unexpected error during login: {e}"

    def add_files(self, file_paths: list[str], tags: list[str]) -> str:
        """
        Upload files with tags.

        Args:
            file_paths: List of file paths to upload
            tags: List of tags to associate with files

        Returns:
            Formatted result message with upload status for each file
        """
        results = []

        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        for file_path in file_paths:
            if not os.path.exists(file_path):
                results.append(f"Error: File not found: {file_path}")
                continue

            if not os.path.isfile(file_path):
                results.append(f"Error: Not a file: {file_path}")
                continue

            if os.path.getsize(file_path) == 0:
                results.append(f"Error: File is empty: {file_path}")
                continue

            try:
                with open(file_path, 'rb') as f:
                    files = {'file': (os.path.basename(file_path), f)}
                    data = {'tags': ','.join(tags)}

                    response = self._request_with_retry(
                        'POST',
                        '/files',
                        files=files,
                        data=data,
                        headers=headers
                    )

                    if response.status_code == 201:
                        result = response.json()
                        results.append(
                            f"Added: {result['name']} "
                            f"(ID: {result['file_id'][:8]}..., "
                            f"Size: {result['size']} bytes, "
                            f"Tags: {', '.join(result['tags'])})"
                        )
                    else:
                        results.append(f"Error uploading {file_path}: {self._format_error(response)}")

            except ConnectionError as e:
                results.append(f"Error uploading {file_path}: {e}")
            except Exception as e:
                results.append(f"Error uploading {file_path}: {e}")

        return '\n'.join(results) if results else "No files uploaded."

    def list_files(self, tags: list[str]) -> str:
        """
        List files matching tag query.

        Args:
            tags: List of tags for AND query (empty list = all files)

        Returns:
            Formatted list of files
        """
        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        params = {}
        if tags:
            params['tags'] = ','.join(tags)
        else:
            params['tags'] = ''

        try:
            response = self._request_with_retry(
                'GET',
                '/files',
                headers=headers,
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                files = data['files']

                if not files:
                    query_str = " AND ".join(tags) if tags else "ALL"
                    return f"No files found matching query: {query_str}"

                output = [f"Found {len(files)} file(s):\n"]
                for file_meta in files:
                    output.append(
                        f"  - {file_meta['name']} (ID: {file_meta['file_id'][:8]}...)\n"
                        f"    Size: {file_meta['size']} bytes\n"
                        f"    Tags: {', '.join(file_meta['tags'])}\n"
                        f"    Created: {file_meta['created_at']}"
                    )

                return '\n'.join(output)
            else:
                return f"Error: {self._format_error(response)}"

        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Unexpected error listing files: {e}"

    def delete_files(self, tags: list[str]) -> str:
        """
        Delete files matching tag query.

        Args:
            tags: List of tags for AND query

        Returns:
            Formatted result with deletion count
        """
        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        params = {'tags': ','.join(tags)}

        try:
            response = self._request_with_retry(
                'DELETE',
                '/files',
                headers=headers,
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                deleted_count = data['deleted_count']
                file_ids = data['file_ids']

                if deleted_count == 0:
                    return "No files deleted. No files matched the query."

                file_ids_str = ', '.join([fid[:8] + '...' for fid in file_ids])
                return f"Deleted {deleted_count} file(s).\nFile IDs: {file_ids_str}"
            else:
                return f"Error: {self._format_error(response)}"

        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Unexpected error deleting files: {e}"

    def add_tags(self, query_tags: list[str], new_tags: list[str]) -> str:
        """
        Add tags to files matching query.

        Args:
            query_tags: Tags to query files (AND logic)
            new_tags: Tags to add to matching files

        Returns:
            Formatted result with update count
        """
        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        payload = {
            'query_tags': query_tags,
            'new_tags': new_tags
        }

        try:
            response = self._request_with_retry(
                'POST',
                '/files/tags',
                json=payload,
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                updated_count = data['updated_count']
                file_ids = data['file_ids']

                if updated_count == 0:
                    return "No files updated. No files matched the query."

                new_tags_str = ', '.join(new_tags)
                file_ids_str = ', '.join([fid[:8] + '...' for fid in file_ids])
                return f"Added tags [{new_tags_str}] to {updated_count} file(s).\nFile IDs: {file_ids_str}"
            else:
                return f"Error: {self._format_error(response)}"

        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Unexpected error adding tags: {e}"

    def delete_tags(self, query_tags: list[str], tags_to_remove: list[str]) -> str:
        """
        Remove tags from files matching query.

        Args:
            query_tags: Tags to query files (AND logic)
            tags_to_remove: Tags to remove from matching files

        Returns:
            Formatted result with update count
        """
        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        payload = {
            'query_tags': query_tags,
            'tags_to_remove': tags_to_remove
        }

        try:
            response = self._request_with_retry(
                'DELETE',
                '/files/tags',
                json=payload,
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                updated_count = data['updated_count']
                file_ids = data['file_ids']
                skipped_files = data.get('skipped_files', [])

                if updated_count == 0 and len(skipped_files) == 0:
                    return "No files updated. No files matched the query."

                output = []
                
                if updated_count > 0:
                    tags_str = ', '.join(tags_to_remove)
                    file_ids_str = ', '.join([fid[:8] + '...' for fid in file_ids])
                    output.append(f"Removed tags [{tags_str}] from {updated_count} file(s).")
                    output.append(f"File IDs: {file_ids_str}")
                
                if skipped_files:
                    output.append("\nSkipped files (would become tagless):")
                    for skip in skipped_files:
                        output.append(f"  - {skip['name']} (ID: {skip['file_id'][:8]}...)")
                        output.append(f"    Current tags: {', '.join(skip['current_tags'])}")
                
                return '\n'.join(output)
            else:
                return f"Error: {self._format_error(response)}"

        except ConnectionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Unexpected error removing tags: {e}"

    def download(self, filename: str, output_path: str | None = None) -> str:
        """
        Download a file by filename with progress feedback.

        Args:
            filename: Name of file to download
            output_path: Optional output path (defaults to current directory)

        Returns:
            Success message with download details
        """
        import sys
        from pathlib import Path
        
        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        try:
            url = f'/files/by-name/{filename}/download'
            
            with self.session.stream('GET', url, headers=headers) as response:
                if response.status_code == 200:
                    if output_path:
                        output_file = Path(output_path)
                        if output_file.is_dir():
                            output_file = output_file / filename
                    else:
                        output_file = Path(filename)
                    
                    total_size = int(response.headers.get('Content-Length', 0))
                    downloaded = 0
                    
                    with open(output_file, 'wb') as f:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                downloaded_mb = downloaded / (1024 * 1024)
                                total_mb = total_size / (1024 * 1024)
                                sys.stdout.write(
                                    f"\rDownloading {filename}: {downloaded_mb:.2f} MB / {total_mb:.2f} MB ({progress:.1f}%)"
                                )
                                sys.stdout.flush()
                            else:
                                downloaded_mb = downloaded / (1024 * 1024)
                                sys.stdout.write(
                                    f"\rDownloading {filename}: {downloaded_mb:.2f} MB"
                                )
                                sys.stdout.flush()
                    
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                    if total_size > 0:
                        size_mb = total_size / (1024 * 1024)
                        return f"Downloaded: {filename} ({size_mb:.2f} MB)\nSaved to: {output_file.absolute()}"
                    else:
                        downloaded_mb = downloaded / (1024 * 1024)
                        return f"Downloaded: {filename} ({downloaded_mb:.2f} MB)\nSaved to: {output_file.absolute()}"
                else:
                    response.read()
                    return f"Error: {self._format_error(response)}"

        except httpx.ConnectError:
            return "Error: Cannot connect to controller server. Is it running?"
        except httpx.TimeoutException:
            return "Error: Request timed out. Server may be overloaded."
        except IOError as e:
            return f"Error writing file: {e}"
        except Exception as e:
            return f"Unexpected error downloading file: {e}"

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
