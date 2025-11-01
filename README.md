# DockInfo

A lightweight HTTP API service that provides Docker container and image information in JSON format. Designed to be called by other Docker containers, with label-based discovery and configuration similar to Watchtower's label system.

## Features

- Get container information by name
- Get image information
- List all containers
- Self-information endpoint
- Label-based container lookup

## Usage

Add to your `compose.yaml`:

```yaml
services:
  dockinfo:
    build: ./dockinfo
    container_name: dockinfo
    restart: always
    ports:
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - PORT=8080

  your-service:
    image: your-image:latest
    labels:
      - "package-info.service.url=http://dockinfo:8080"
```

## API Endpoints

### `GET /health`
Health check endpoint.

### `GET /container/<container_name>`
Get information about a specific container.

**Example:**
```bash
curl http://dockinfo:8080/container/my-container
```

**Response:**
```json
{
  "name": "my-container",
  "id": "abc123def456",
  "image": "my-image:latest",
  "image_id": "sha256:...",
  "status": "running",
  "labels": {...},
  "created": "2024-01-01T00:00:00Z",
  "ports": {...},
  "environment": [...]
}
```

### `GET /image/<image_name>`
Get information about a Docker image.

**Example:**
```bash
curl http://dockinfo:8080/image/my-image:latest
```

### `GET /self`
Get information about the container running this service.

### `GET /my-info`
Get information about the calling container (via headers).

**Example:**
```bash
curl -H "X-Container-Name: my-container" http://dockinfo:8080/my-info
```

### `GET /labels?container=<container_name>`
Get container information via query parameter or `X-Container-Name` header.

**Example:**
```bash
curl -H "X-Container-Name: my-container" http://dockinfo:8080/labels
# or
curl http://dockinfo:8080/labels?container=my-container
```

### `GET /by-label?label=<key>=<value>`
Find containers by label filter (useful for discovering containers with specific labels).

**Example:**
```bash
curl http://dockinfo:8080/by-label?label=package-info.enable=true
```

### `GET /list`
List all containers with basic information.

**Example:**
```bash
curl http://dockinfo:8080/list
```

## Label-Based Configuration

Containers can use labels to configure how they interact with the service:

### Enable a container to be queried
```yaml
your-service:
  image: your-image:latest
  labels:
    - "package-info.enable=true"
    - "package-info.service.url=http://dockinfo:8080"
```

### Query containers by label
```bash
# Find all containers with package-info.enable=true
curl http://dockinfo:8080/by-label?label=package-info.enable=true
```

## Calling from Other Containers

Other containers can call this service using the service name as hostname:

```bash
# From within another container - get info about another container
curl http://dockinfo:8080/container/my-container

# Get your own info (set container name in header)
curl -H "X-Container-Name: my-container" http://dockinfo:8080/my-info

# Find containers by label
curl http://dockinfo:8080/by-label?label=package-info.enable=true
```

### Example: Container calling the service

In your application code (running in a container), you can query the service:

```python
import requests
import os

# Get service URL from label or environment
service_url = os.getenv('PACKAGE_INFO_SERVICE_URL', 'http://dockinfo:8080')

# Get info about yourself
response = requests.get(
    f"{service_url}/my-info",
    headers={"X-Container-Name": os.getenv('HOSTNAME')}
)
my_info = response.json()

# Or find other containers with a specific label
response = requests.get(
    f"{service_url}/by-label",
    params={"label": "package-info.enable=true"}
)
enabled_containers = response.json()
```

## Environment Variables

- `PORT` - Port to listen on (default: 8080)
- `HOST` - Host to bind to (default: 0.0.0.0)
- `DOCKER_HOST` - Docker daemon URL (default: auto-detect, e.g., `unix:///var/run/docker.sock`)
- `DOCKER_SOCKET` - Custom Docker socket path inside container (default: `/var/run/docker.sock`)

### Custom Docker Socket Path

If you need to mount the Docker socket from a custom location on the host:

```yaml
services:
  dockinfo:
    build: ./dockinfo
    container_name: dockinfo
    restart: always
    ports:
      - "8080:8080"
    volumes:
      - ~/docker-volumes/dockerinfo/docker.sock:/var/run/docker.sock:ro
    environment:
      - PORT=8080
```

The host path doesn't matter - as long as it's mounted to `/var/run/docker.sock` inside the container (or you set `DOCKER_SOCKET` to your custom path), it will work correctly.

