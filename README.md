# DockInfo

A lightweight HTTP API service that provides a label-based service registry. Services define their metadata (name, URL, description) via Docker Compose labels, and DockInfo exposes them via a simple REST API.

## Features

- **Label-based service registry** - Services register themselves via Docker Compose labels
- **Selective visibility** - Only services with `dockinfo.enable=true` appear in listings
- **No runtime Docker info** - Returns only label-based metadata, not container status/ports/etc.
- **Simple REST API** - Easy to query from other services or frontends

## Usage

Add to your `compose.yaml`:

```yaml
services:
  dockinfo:
    image: ghcr.io/royadler/dockinfo:latest
    container_name: dockinfo
    restart: always
    ports:
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - PORT=8080

  # Your services register themselves with labels
  my-service:
    image: my-image:latest
    labels:
      - "dockinfo.enable=true"
      - "dockinfo.name=My Service"
      - "dockinfo.service.url=https://myservice.royadler.de"
      - "dockinfo.description=Description of my service"

  another-service:
    image: another-image:latest
    labels:
      - "dockinfo.enable=true"
      - "dockinfo.name=Another Service"
      - "dockinfo.service.url=https://another.royadler.de"
      - "dockinfo.description=Another service description"
```

## Label Schema

Services must have the following labels to appear in the registry:

### Required Labels

- `dockinfo.enable=true` - Enables the service to appear in listings

### Optional Labels

- `dockinfo.name` - Display name (defaults to container name if not set)
- `dockinfo.service.url` or `dockinfo.url` - Service URL
- `dockinfo.description` - Service description

### Example

```yaml
services:
  my-app:
    image: my-app:latest
    labels:
      - "dockinfo.enable=true"
      - "dockinfo.name=My Application"
      - "dockinfo.service.url=https://myapp.royadler.de"
      - "dockinfo.description=A web application for managing tasks"
```

## API Endpoints

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

### `GET /packages`
List all enabled packages/services (only those with `dockinfo.enable=true`).

**Example:**
```bash
curl https://dockinfo.royadler.de/packages
```

**Response:**
```json
{
  "count": 2,
  "packages": [
    {
      "name": "My Service",
      "url": "https://myservice.royadler.de",
      "description": "Description of my service"
    },
    {
      "name": "Another Service",
      "url": "https://another.royadler.de",
      "description": "Another service description"
    }
  ]
}
```

### `GET /package/<container_name>`
Get label-based information about a specific package/service.

**Example:**
```bash
curl https://dockinfo.royadler.de/package/my-service
```

**Response:**
```json
{
  "name": "My Service",
  "url": "https://myservice.royadler.de",
  "description": "Description of my service"
}
```

### `GET /package?container=<container_name>`
Get label-based information via query parameter or `X-Container-Name` header.

**Example:**
```bash
curl "https://dockinfo.royadler.de/package?container=my-service"
# or
curl -H "X-Container-Name: my-service" https://dockinfo.royadler.de/package
```

### `GET /by-label?label=<key>=<value>`
Find packages by label filter (returns label-based info only).

**Example:**
```bash
curl "https://dockinfo.royadler.de/by-label?label=dockinfo.enable=true"
```

**Response:**
```json
{
  "filter": "dockinfo.enable=true",
  "count": 2,
  "packages": [
    {
      "name": "My Service",
      "url": "https://myservice.royadler.de",
      "description": "Description of my service"
    }
  ]
}
```

### `GET /self`
Get label-based information about the dockinfo container itself.

### `GET /my-info`
Get label-based information about the calling container.

**Example:**
```bash
curl -H "X-Container-Name: my-service" https://dockinfo.royadler.de/my-info
# or
curl "https://dockinfo.royadler.de/my-info?container=my-service"
```

## Calling from Other Services

Other services can query DockInfo to discover registered services:

```bash
# List all enabled packages
curl https://dockinfo.royadler.de/packages

# Get info about a specific package
curl https://dockinfo.royadler.de/package/my-service

# Find packages by label
curl "https://dockinfo.royadler.de/by-label?label=dockinfo.enable=true"
```

### Example: Python Client

```python
import requests

# Get all registered packages
response = requests.get('https://dockinfo.royadler.de/packages')
packages = response.json()

for package in packages['packages']:
    print(f"{package['name']}: {package['url']}")
    print(f"  {package['description']}")
```

### Example: Frontend Integration

```javascript
// Fetch all registered services
fetch('https://dockinfo.royadler.de/packages')
  .then(res => res.json())
  .then(data => {
    data.packages.forEach(pkg => {
      console.log(`${pkg.name}: ${pkg.url}`);
    });
  });
```

## Environment Variables

- `PORT` - Port to listen on (default: 8080)
- `HOST` - Host to bind to (default: 0.0.0.0)
- `DOCKER_HOST` - Docker daemon URL (default: auto-detect, e.g., `unix:///var/run/docker.sock`)
- `DOCKER_SOCKET` - Custom Docker socket path inside container (default: `/var/run/docker.sock`)

## Notes

- **Label-based only**: DockInfo reads only from Docker labels, not runtime container status
- **Selective registration**: Only services with `dockinfo.enable=true` appear in listings
- **No runtime info**: The API does not return container status, ports, or other runtime Docker information
- **Production ready**: Uses gunicorn WSGI server, not Flask's development server
