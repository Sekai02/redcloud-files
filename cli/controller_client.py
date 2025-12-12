"""HTTP client for communicating with Controller service."""

import os
import time
import uuid
from typing import Optional
from pathlib import Path
import httpx

from common.logging_config import get_logger
from cli.config import Config
from cli.constants import GREEN, RESET
from cli.utils import format_file_size

logger = get_logger(__name__)


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
        self.request_id = None
        logger.info(f"Initialized ControllerClient [base_url={config.get_base_url()}]")

    def _calculate_upload_timeout(self, file_size: int) -> float:
        """
        Calculate timeout for upload based on file size.

        Args:
            file_size: File size in bytes

        Returns:
            Timeout in seconds (30s base + 0.1s per MB)
        """
        base_timeout = 30.0
        size_mb = file_size / (1024 * 1024)
        size_factor = size_mb * 0.1
        return base_timeout + size_factor

    def _normalize_upload_path(self, file_path: str) -> tuple[str, str | None]:
        """
        Normalize upload path by validating mandatory uploads/ prefix.

        Args:
            file_path: Input file path (must start with uploads/ prefix)

        Returns:
            Tuple of (normalized_absolute_path, error_message)
            error_message is None if validation succeeds
        """
        base_dir = Path('/uploads').resolve()
        
        path_str = file_path.strip()
        if not path_str.startswith('uploads/'):
            return "", f"Upload path must start with 'uploads/' - did you mean 'uploads/{path_str}'?"
        
        path_str = path_str[8:]
        
        normalized_path = base_dir / path_str
        
        try:
            resolved_path = normalized_path.resolve()
            resolved_path.relative_to(base_dir)
        except (OSError, RuntimeError, ValueError):
            return "", f"Invalid path: '{file_path}' is outside uploads directory"
        
        return str(resolved_path), None

    def _normalize_download_path(self, output_path: str, filename: str) -> tuple[Path, str | None]:
        """
        Normalize download path by validating mandatory downloads/ prefix when specified.

        Args:
            output_path: Output path (must start with downloads/ prefix if provided)
            filename: Original filename for default naming

        Returns:
            Tuple of (normalized_path_object, error_message)
            error_message is None if validation succeeds
        """
        base_dir = Path('/downloads').resolve()
        
        if output_path:
            path_str = output_path.strip()
            if not path_str.startswith('downloads/'):
                return Path(), f"Download output path must start with 'downloads/' - did you mean 'downloads/{path_str}'?"
            
            path_str = path_str[10:]
            
            output_file = base_dir / path_str
            
            try:
                if output_file.exists() and output_file.is_dir():
                    output_file = output_file / filename
                
                resolved_path = output_file.resolve()
                resolved_path.relative_to(base_dir)
            except (OSError, RuntimeError, ValueError):
                return Path(), f"Invalid path: '{output_path}' is outside downloads directory"
        else:
            output_file = base_dir / filename
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        return output_file, None

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
        
        self.request_id = str(uuid.uuid4())
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers']['X-Request-ID'] = self.request_id
        
        logger.debug(
            f"Making request: {method} {endpoint} [request_id={self.request_id}]"
        )

        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(method, endpoint, **kwargs)
                
                logger.debug(
                    f"Response received: {method} {endpoint} status={response.status_code} [request_id={self.request_id}]"
                )

                if 400 <= response.status_code < 500:
                    if response.status_code >= 400:
                        logger.warning(
                            f"Client error: {method} {endpoint} status={response.status_code} [request_id={self.request_id}]"
                        )
                    return response

                if response.status_code >= 500 and attempt < max_retries:
                    delay = backoff ** attempt
                    logger.warning(
                        f"Server error (attempt {attempt + 1}/{max_retries + 1}): "
                        f"{method} {endpoint} status={response.status_code}, retrying in {delay}s [request_id={self.request_id}]"
                    )
                    time.sleep(delay)
                    continue

                return response

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < max_retries:
                    delay = backoff ** attempt
                    logger.warning(
                        f"Network error (attempt {attempt + 1}/{max_retries + 1}): "
                        f"{method} {endpoint} error={type(e).__name__}, retrying in {delay}s [request_id={self.request_id}]"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Network error (max retries exceeded): {method} {endpoint} error={e} [request_id={self.request_id}]"
                    )
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
        logger.info(f"Attempting to register user: {username}")
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
                logger.info(f"Registration successful for user: {username} [user_id={user_id}]")

                return f"Registration successful!\nUser ID: {user_id}\nAPI key saved to config."
            else:
                logger.warning(f"Registration failed for user: {username} status={response.status_code}")
                return f"Registration failed: {self._format_error(response)}"

        except ConnectionError as e:
            logger.error(f"Connection error during registration: {e}")
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}", exc_info=True)
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
        logger.info(f"Attempting to login user: {username}")
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
                logger.info(f"Login successful for user: {username}")

                return f"Login successful!\nAPI key updated in config."
            else:
                logger.warning(f"Login failed for user: {username} status={response.status_code}")
                return f"Login failed: {self._format_error(response)}"

        except ConnectionError as e:
            logger.error(f"Connection error during login: {e}")
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}", exc_info=True)
            return f"Unexpected error during login: {e}"

    def add_files(self, file_paths: list[str], tags: list[str]) -> str:
        """
        Upload files with tags.

        Args:
            file_paths: List of file paths to upload (can use uploads/ prefix, be relative, or absolute)
            tags: List of tags to associate with files

        Returns:
            Formatted result message with upload status for each file
        """
        import sys
        
        results = []

        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        for file_path in file_paths:
            normalized_path, error = self._normalize_upload_path(file_path)
            
            if error:
                results.append(f"Error: {error}")
                continue
            
            if not os.path.exists(normalized_path):
                results.append(f"Error: File not found: {file_path}")
                continue

            if not os.path.isfile(normalized_path):
                results.append(f"Error: Not a file: {file_path}")
                continue

            file_size = os.path.getsize(normalized_path)
            if file_size == 0:
                results.append(f"Error: File is empty: {file_path}")
                continue

            filename = os.path.basename(normalized_path)
            upload_timeout = self._calculate_upload_timeout(file_size)

            try:
                def file_stream_with_progress():
                    uploaded = 0
                    with open(normalized_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            uploaded += len(chunk)
                            
                            progress = (uploaded / file_size) * 100
                            sys.stdout.write(
                                f"\rUploading {filename}: {format_file_size(uploaded)} / {format_file_size(file_size)} ({GREEN}{progress:.1f}%{RESET})"
                            )
                            sys.stdout.flush()
                            
                            yield chunk
                    
                    sys.stdout.write('\n')
                    sys.stdout.flush()

                upload_headers = headers.copy()
                upload_headers['Content-Length'] = str(file_size)

                files = {'file': (filename, file_stream_with_progress())}
                data = {'tags': ','.join(tags)}

                with httpx.Client(
                    base_url=self.config.get_base_url(),
                    timeout=upload_timeout
                ) as upload_client:
                    response = upload_client.post(
                        '/files',
                        files=files,
                        data=data,
                        headers=upload_headers
                    )

                if response.status_code == 201:
                    result = response.json()
                    results.append(
                        f"Added: {result['name']} "
                        f"(ID: {result['file_id'][:8]}..., "
                        f"Size: {format_file_size(result['size'])}, "
                        f"Tags: {', '.join(result['tags'])})"
                    )
                else:
                    results.append(f"Error uploading {file_path}: {self._format_error(response)}")

            except httpx.ConnectError:
                sys.stdout.write('\r' + ' ' * 100 + '\r')
                sys.stdout.flush()
                results.append(f"Error uploading {file_path}: Cannot connect to controller server")
            except httpx.TimeoutException:
                sys.stdout.write('\r' + ' ' * 100 + '\r')
                sys.stdout.flush()
                results.append(f"Error uploading {file_path}: Upload timed out (file size: {format_file_size(file_size)}, timeout: {upload_timeout:.1f}s)")
            except Exception as e:
                sys.stdout.write('\r' + ' ' * 100 + '\r')
                sys.stdout.flush()
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
                        f"    Size: {format_file_size(file_meta['size'])}\n"
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
            output_path: Optional output path (can use downloads/ prefix, be relative to /downloads, or absolute)

        Returns:
            Success message with download details
        """
        import sys
        
        try:
            headers = self._get_auth_header()
        except ValueError as e:
            return f"Error: {e}"

        try:
            url = f'/files/by-name/{filename}/download'
            
            with self.session.stream('GET', url, headers=headers) as response:
                if response.status_code == 200:
                    output_file, error = self._normalize_download_path(output_path or "", filename)
                    
                    if error:
                        response.read()
                        return f"Error: {error}"
                    
                    total_size = int(response.headers.get('Content-Length', 0))
                    downloaded = 0
                    
                    with open(output_file, 'wb') as f:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                sys.stdout.write(
                                    f"\rDownloading {filename}: {format_file_size(downloaded)} / {format_file_size(total_size)} ({GREEN}{progress:.1f}%{RESET})"
                                )
                                sys.stdout.flush()
                            else:
                                sys.stdout.write(
                                    f"\rDownloading {filename}: {format_file_size(downloaded)}"
                                )
                                sys.stdout.flush()
                    
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    
                    if total_size > 0:
                        return f"Downloaded: {filename} ({format_file_size(total_size)})\nSaved to: {output_file.absolute()}"
                    else:
                        return f"Downloaded: {filename} ({format_file_size(downloaded)})\nSaved to: {output_file.absolute()}"
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
