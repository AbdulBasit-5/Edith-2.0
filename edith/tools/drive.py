"""Google Drive tools with read-only OAuth and safety caps."""

import io
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from edith.tools.base import Tool, ToolResult

# Least-privilege read-only Drive scope
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class DriveServiceManager:
    """Manages authenticated Google Drive API service."""

    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json") -> None:
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._service = None

    def get_service(self):
        """Get or authenticate the Google Drive service."""
        if self._service is not None:
            return self._service

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, DRIVE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Google credentials file '{self.credentials_path}' not found. "
                        "Please provide OAuth 2.0 Client IDs credentials.json from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, DRIVE_SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self._service = build("drive", "v3", credentials=creds)
        return self._service


# Input Models
class SearchDriveInput(BaseModel):
    query: str = Field(..., description="Search term or file name to find in Google Drive (e.g. 'OS lecture notes')")
    max_results: int = Field(default=5, ge=1, le=20, description="Maximum number of files to return")


class FetchFileInput(BaseModel):
    file_id: str = Field(..., description="The unique Google Drive ID of the file to download")


class SendFileInput(BaseModel):
    file_id: str = Field(..., description="The Google Drive file ID to send to Telegram")
    file_name: str = Field(..., description="The name of the file being sent")
    caption: Optional[str] = Field(default=None, description="Optional caption for the file")


# Tools
class SearchDriveTool(Tool):
    """Search for files in Google Drive by name or text."""

    name = "search_drive"
    description = (
        "Search your Google Drive for files matching a query. Returns file names, IDs, "
        "MIME types, and last modified dates."
    )
    input_model = SearchDriveInput
    risk_level = "read"

    def __init__(self, service_manager: Optional[DriveServiceManager] = None) -> None:
        self.service_manager = service_manager or DriveServiceManager()

    def run(self, args: SearchDriveInput) -> ToolResult:
        try:
            service = self.service_manager.get_service()
            # Construct Google Drive API query for text/name search
            # Avoid SQL injection-like syntax errors in Google Drive query
            escaped_query = args.query.replace("'", "\\'")
            q = f"name contains '{escaped_query}' and trashed = false"

            results = (
                service.files()
                .list(
                    q=q,
                    pageSize=args.max_results,
                    fields="files(id, name, mimeType, modifiedTime, size)",
                )
                .execute()
            )
            files = results.get("files", [])
            if not files:
                return ToolResult(
                    success=True,
                    data=f"No files found matching query: '{args.query}'",
                )
            return ToolResult(success=True, data=files)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FetchFileTool(Tool):
    """Download a file from Google Drive to a local temp folder."""

    name = "fetch_file"
    description = "Downloads a file from Google Drive using its file_id so it can be inspected or prepared for sending."
    input_model = FetchFileInput
    risk_level = "read"

    def __init__(
        self,
        service_manager: Optional[DriveServiceManager] = None,
        max_size_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self.service_manager = service_manager or DriveServiceManager()
        self.max_size_bytes = max_size_bytes

    def run(self, args: FetchFileInput) -> ToolResult:
        try:
            from googleapiclient.http import MediaIoBaseDownload

            service = self.service_manager.get_service()
            meta = service.files().get(fileId=args.file_id, fields="id, name, size, mimeType").execute()
            file_name = meta.get("name", f"file_{args.file_id}")
            file_size = int(meta.get("size", 0)) if meta.get("size") else 0

            if file_size > self.max_size_bytes:
                return ToolResult(
                    success=False,
                    error=f"File exceeds maximum allowed size ({file_size} > {self.max_size_bytes} bytes).",
                )

            # Create temporary file
            temp_dir = Path(tempfile.gettempdir()) / "edith_downloads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_path = temp_dir / file_name

            request = service.files().get_media(fileId=args.file_id)
            with open(local_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            return ToolResult(
                success=True,
                data={
                    "file_id": args.file_id,
                    "name": file_name,
                    "local_path": str(local_path),
                    "size_bytes": local_path.stat().st_size,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SendFileTool(Tool):
    """Human-in-the-loop tool: sends a file to the user's Telegram chat.

    This tool is flagged with risk_level='send'. The agent loop will halt
    and request user confirmation via Telegram inline buttons before execution.
    """

    name = "send_file"
    description = (
        "Send a Google Drive file directly to your Telegram chat. "
        "Requires explicit user approval via inline Yes/No buttons before sending."
    )
    input_model = SendFileInput
    risk_level = "send"

    def __init__(self, fetch_tool: Optional[FetchFileTool] = None) -> None:
        self.fetch_tool = fetch_tool or FetchFileTool()

    def run(self, args: SendFileInput) -> ToolResult:
        # First ensure file is fetched locally
        fetch_res = self.fetch_tool.run(FetchFileInput(file_id=args.file_id))
        if not fetch_res.success:
            return ToolResult(success=False, error=f"Could not prepare file: {fetch_res.error}")

        file_info = fetch_res.data
        return ToolResult(
            success=True,
            data={
                "status": "ready_to_send",
                "file_path": file_info["local_path"],
                "file_name": args.file_name,
                "caption": args.caption,
            },
        )

