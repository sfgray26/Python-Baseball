import os
from typing import Optional, Dict, Any, List
import pytest
import requests
from pathlib import Path
import time

# Assuming these are in your project structure
from config.settings import settings
from models.api_response import APIResponse
from utils.validators import validate_request, validate_user, validate_location_id
from utils.rate_limiter import RateLimiter
from utils.stringifier import stringify
from models.service_request import ServiceRequest

class ThirdPartyAPIFacade:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.token_expiry = 0
        self.proxies = {
            'http': 'http://proxy.abc.com:8080',
            'https': 'http://proxy.abc.com:8080'
        }
        self.session.proxies = self.proxies
        self.base_url = settings.API_BASE_URL
        self.rate_limiter = RateLimiter(limit=180, period=60)
        print(f"Initialized with base_url: {self.base_url}")
        print(f"Client ID: {settings.CLIENT_ID}")
        print(f"Client Secret: {settings.CLIENT_SECRET[:5]}... (hidden for security)")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Utility method to make HTTP requests with proper headers and token"""
        headers = kwargs.get('headers', {}) or {}
        print(f"Headers in _make_request (before token check): {headers} (type: {type(headers)})")
        data = kwargs.get('data', {})
        json_data = kwargs.get('json', None)
        print(f"Data in _make_request: {data} (type: {type(data)})")
        print(f"JSON in _make_request: {json_data} (type: {type(json_data)})")
        is_token_request = (
            ('grant_type' in data if isinstance(data, dict) else False) or
            (json_data is not None and isinstance(json_data, dict) and 'grant_type' in json_data)
        )
        print(f"Endpoint: {endpoint}")
        print(f"Checking if token is needed: 'Authorization' in headers: {'Authorization' in headers}, is_token_request: {is_token_request}")
        if endpoint.endswith('/v1/los/oauth/token'):
            print("This is a token request, skipping token fetch to avoid recursion")
        elif 'Authorization' not in headers and not is_token_request:
            print("Conditions met for token fetch:")
            print(f"  - 'Authorization' not in headers: {'Authorization' in headers}")
            print(f"  - is_token_request: {is_token_request}")
            print("Fetching token for request")
            token = self.get_access_token()
            headers['Authorization'] = f'Bearer {token}'
            print(f"Added Authorization header: {headers['Authorization']}")
        else:
            print("Skipping token fetch due to one of the following:")
            print(f"  - 'Authorization' in headers: {'Authorization' in headers}")
            print(f"  - is_token_request: {is_token_request}")
            print(f"  - Endpoint is token endpoint: {endpoint.endswith('/v1/los/oauth/token')}")
        full_url = endpoint if endpoint.startswith('http') else f"{self.base_url}{endpoint}"
        print(f"Making {method} request to: {full_url}")
        print(f"Final request headers: {headers}")
        print(f"Request kwargs: {kwargs}")
        try:
            response = self.session.request(method, full_url, headers=headers, verify=False, **kwargs)
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {response.headers}")
            print(f"Response content: {response.content.decode('utf-8', errors='replace')[:200]}")
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"Request failed: {str(e)}")
            raise

    def _get_access_token(self) -> str:
        if not self.token or time.time() > self.token_expiry:
            payload = {
                'grant_type': 'client_credentials',
                'client_id': settings.CLIENT_ID,
                'client_secret': settings.CLIENT_SECRET,
                'scope': '*'
            }
            endpoint = "/v1/los/oauth/token"
            print(f"Fetching new token from {endpoint}")
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            try:
                response = self._make_request('POST', endpoint, json=payload, headers=headers)
                response_json = response.json()
                print(f"Token endpoint response: {response_json}")
                if response_json.get('success', True) is False:
                    error_message = response_json.get('meta', {}).get('reason', 'Unknown error')
                    errors = response_json.get('meta', {}).get('errors', [])
                    error_details = errors[0].get('description', 'No details provided') if errors else 'No details provided'
                    raise ValueError(f"Token endpoint request failed: {error_message} - {error_details}")
                if 'data' not in response_json:
                    if 'access_token' not in response_json:
                        raise ValueError("Token endpoint response missing 'access_token' key")
                    if 'expires_in' not in response_json:
                        raise ValueError("Token endpoint response missing 'expires_in' key")
                    self.token = response_json['access_token']
                    self.token_expiry = time.time() + response_json['expires_in']
                else:
                    token_data = response_json['data']
                    if 'access_token' not in token_data:
                        raise ValueError("Token endpoint response missing 'access_token' key")
                    if 'expires_in' not in token_data:
                        raise ValueError("Token endpoint response missing 'expires_in' key")
                    self.token = token_data['access_token']
                    self.token_expiry = time.time() + token_data['expires_in']
                print(f"Token retrieved: {self.token[:10]}... (length: {len(self.token)})")
            except requests.RequestException as e:
                error_message = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_json = e.response.json()
                        error_message = error_json.get('meta', {}).get('reason', str(e))
                    except ValueError:
                        error_message = e.response.text
                print(f"Failed to get access token: {error_message}")
                raise Exception(f"Failed to get access token: {error_message}")
            except (ValueError, KeyError) as e:
                print(f"Failed to parse token response: {str(e)}")
                raise
        print(f"Returning cached token: {self.token[:10]}... (length: {len(self.token)})")
        return self.token

    def get_access_token(self) -> str:
        result = self._get_access_token()
        print(f"get_access_token result: {repr(result)} (type: {type(result)})")
        return result

    def upload_file(self, location_id: int, uploaded_by: str, file_path: str,
                    prepared_by: Optional[str] = None, report_title: Optional[str] = None,
                    report_date: Optional[str] = None, display_filename: Optional[str] = None,
                    service_groups: Optional[List[Dict[str, Any]]] = None,
                    service_types: Optional[List[Dict[str, Any]]] = None,
                    document_types: Optional[List[Dict[str, Any]]] = None,
                    document_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        print(f"upload_file called with self: {self}")
        try:
            print(f"Validating location_id: {location_id}")
            validate_location_id(location_id)
            print(f"Validating uploaded_by: {uploaded_by}")
            validate_user(uploaded_by)
        except Exception as e:
            print(f"Validation failed: {str(e)}")
            return {'status': 'error', 'error': f"Validation failed: {str(e)}"}

        print(f"Checking if file exists: {file_path}")
        if not os.path.isfile(file_path):
            return {'status': 'error', 'error': f"File not found at path: {file_path}"}

        try:
            print("Fetching access token")
            token = self.get_access_token()
            print(f"Token in upload_file: {repr(token)} (type: {type(token)})")
        except Exception as e:
            print(f"Failed to get access token: {str(e)}")
            return {'status': 'error', 'error': f"Authentication failed: {str(e)}"}

        data = {
            'preparedBy': prepared_by,
        }

        filename = display_filename if display_filename else os.path.basename(file_path)

        try:
            print(f"Opening file: {file_path}")
            with open(file_path, 'rb') as f:
                file_content = f.read()
            print(f"File read, size: {len(file_content)} bytes")
        except Exception as e:
            print(f"Failed to read file: {str(e)}")
            return {'status': 'error', 'error': f"Failed to read file: {str(e)}"}

        files = {
            'file': (filename, file_content, 'application/pdf')
        }

        endpoint = f"/v1/los/files/upload/locationId/{location_id}/uploadedBy/{uploaded_by}"

        # Add other parameters as URL parameters if needed and if the API supports it
        params = {}
        if report_title is not None:
            params['reportTitle'] = report_title
        if display_filename is not None:
            params['displayFileName'] = display_filename
        if service_groups is not None:
            params['serviceGroups'] = stringify(service_groups)
        if service_types is not None:
            params['serviceTypes'] = stringify(service_types)
        if document_types is not None:
            params['documentTypes'] = stringify(document_types)
        if document_status is not None:
            params['documentStatus'] = stringify(document_status)

        try:
            print("Checking rate limiter")
            if not self.rate_limiter.allow_request():
                return {'status': 'error', 'error': "Rate limit exceeded. Please wait before retrying."}
        except Exception as e:
            print(f"Rate limiter check failed: {str(e)}")
            return {'status': 'error', 'error': f"Rate limiter check failed: {str(e)}"}

        try:
            print("Making upload request")
            response = self._make_request(
                'POST',
                endpoint,
                params=params,  # Send other parameters as URL parameters
                data=data,
                files=files,
                timeout=10,
                proxies=self.proxies
            )
            # Check for Content-Disposition header to determine success
            try:
                response_json = response.json()
                print(f"Response JSON: {response_json}")
                if response_json.get('success', True) is False:
                    error_message = response_json.get('meta', {}).get('reason', 'Unknown error')
                    errors = response_json.get('meta', {}).get('errors', [])
                    error_details = errors[0].get('description', 'No details provided') if errors else 'No details provided'
                    return {
                        'status': 'error',
                        'error': f"File upload failed: {error_message} - {error_details}"
                    }
                elif response_json.get('success', True) is True:
                    return {
                        'status': 'success',
                        'locationId': location_id,
                        'uploadedBy': uploaded_by,
                        'displayFileName': filename,
                        'message': 'File uploaded successfully'
                    }
                else:
                    return {
                        'status': 'error',
                        'error': 'File upload failed: unexpected response'
                    }
            except ValueError:
                print("Response is not JSON-parsable, checking Content-Disposition header")
                content_disposition = response.headers.get('Content-Disposition', '').lower()
                print(f"Content-Disposition header: {content_disposition}")
                is_success = False
                if content_disposition:
                    value = content_disposition.split(';', 1)[0].strip()
                    if value == 'attachment':
                        is_success = True

                if is_success:
                    print("File upload successful based on Content-Disposition header")
                    return {
                        'status': 'success',
                        'locationId': location_id,
                        'uploadedBy': uploaded_by,
                        'displayFileName': filename,
                        'message': 'File uploaded successfully'
                    }
                else:
                    return {
                        'status': 'error',
                        'error': 'File upload failed: No Content-Disposition attachment header'
                    }
        except requests.RequestException as e:
            print(f"Upload request failed: {str(e)}")
            status_code = e.response.status_code if e.response else 'Unknown'
            print(f"HTTP Status Code: {status_code}")
            content = e.response.content.decode('utf-8', errors='replace') if e.response else 'No response'
            message = content
            if e.response is not None:
                try:
                    error_json = e.response.json()
                    message = error_json.get('message', content)
                except (ValueError, AttributeError):
                    pass
            return {
                'status': 'error',
                'error': f"File upload failed: {message} (HTTP {status_code})"
            }
        except Exception as e:
            print(f"Upload processing failed: {str(e)}")
            return {
                'status': 'error',
                'error': f"Upload processing failed: {str(e)}"
            }
