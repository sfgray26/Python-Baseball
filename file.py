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
            response = self._make_request(
                'POST',
                endpoint,
                params=params,  # Send other parameters as URL parameters
                data=data,
                files=files,
                timeout=10,
                proxies=self.proxies
            )
            # ... (rest of your response handling)
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
