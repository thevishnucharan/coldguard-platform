from typing import Protocol
import os
import logging
from azure.storage.blob import BlobServiceClient
from app.core.config import settings

logger = logging.getLogger(__name__)

class ObjectStorage(Protocol):
    def upload(self, filename: str, content: bytes) -> str:
        """Uploads content and returns a URI or path."""
        ...
        
    def download(self, filename: str) -> bytes:
        """Downloads content by filename."""
        ...
        
    def delete(self, filename: str) -> bool:
        """Deletes a file, returns True if successful."""
        ...
        
    def exists(self, filename: str) -> bool:
        """Checks if a file exists."""
        ...
        
    def get_path(self, filename: str) -> str:
        """Returns the local path or remote URL for the file."""
        ...

class LocalFileStorage:
    def __init__(self):
        self.storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports")
        os.makedirs(self.storage_dir, exist_ok=True)
        
    def upload(self, filename: str, content: bytes) -> str:
        file_path = os.path.join(self.storage_dir, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"File uploaded locally to {file_path}")
        return file_path
        
    def download(self, filename: str) -> bytes:
        file_path = os.path.join(self.storage_dir, filename)
        if not self.exists(filename):
            raise FileNotFoundError(f"File {filename} not found.")
        with open(file_path, "rb") as f:
            return f.read()
            
    def delete(self, filename: str) -> bool:
        file_path = os.path.join(self.storage_dir, filename)
        if self.exists(filename):
            os.remove(file_path)
            return True
        return False
        
    def exists(self, filename: str) -> bool:
        return os.path.exists(os.path.join(self.storage_dir, filename))
        
    def get_path(self, filename: str) -> str:
        return os.path.join(self.storage_dir, filename)


class AzureBlobStorage:
    def __init__(self, connection_string: str, container_name: str):
        if not connection_string or not container_name:
            raise ValueError("Azure Blob Storage requires connection string and container name.")
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
        # Ensure container exists
        if not self.container_client.exists():
            self.container_client.create_container()

    def upload(self, filename: str, content: bytes) -> str:
        blob_client = self.container_client.get_blob_client(filename)
        blob_client.upload_blob(content, overwrite=True)
        logger.info(f"File uploaded to Azure Blob Storage: {filename}")
        return blob_client.url

    def download(self, filename: str) -> bytes:
        blob_client = self.container_client.get_blob_client(filename)
        if not blob_client.exists():
            raise FileNotFoundError(f"Blob {filename} not found.")
        return blob_client.download_blob().readall()
        
    def delete(self, filename: str) -> bool:
        blob_client = self.container_client.get_blob_client(filename)
        if blob_client.exists():
            blob_client.delete_blob()
            return True
        return False

    def exists(self, filename: str) -> bool:
        blob_client = self.container_client.get_blob_client(filename)
        return blob_client.exists()
        
    def get_path(self, filename: str) -> str:
        blob_client = self.container_client.get_blob_client(filename)
        return blob_client.url


# Dependency factory
def get_object_storage() -> ObjectStorage:
    # Use Azure if credentials exist, else fallback to Local
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container = os.getenv("AZURE_STORAGE_CONTAINER")
    
    if conn_str and container:
        try:
            return AzureBlobStorage(conn_str, container)
        except Exception as e:
            logger.warning(f"Failed to initialize Azure Blob Storage, falling back to LocalFileStorage: {e}")
            return LocalFileStorage()
    else:
        return LocalFileStorage()
