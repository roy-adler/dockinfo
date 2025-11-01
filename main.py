#!/usr/bin/env python3
"""
Simple HTTP API service that returns package/container information in JSON format.
Can be called by other Docker containers via labels or HTTP requests.
"""

from flask import Flask, jsonify, request
import docker
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
docker_client = None


def get_docker_client():
    """Get Docker client, initializing it lazily if needed."""
    global docker_client
    if docker_client is None:
        try:
            # Allow custom Docker socket path via environment variable
            # Defaults to standard location: /var/run/docker.sock
            docker_socket = os.getenv('DOCKER_SOCKET', '/var/run/docker.sock')
            base_url = os.getenv('DOCKER_HOST')
            
            if base_url:
                # If DOCKER_HOST is set, use it (e.g., unix:///var/run/docker.sock)
                docker_client = docker.DockerClient(base_url=base_url)
            elif docker_socket != '/var/run/docker.sock':
                # If custom socket path is specified, construct unix socket URL
                docker_client = docker.DockerClient(base_url=f'unix://{docker_socket}')
            else:
                # Use default from_env() which looks for /var/run/docker.sock or DOCKER_HOST
                docker_client = docker.from_env()
            
            # Test the connection
            docker_client.ping()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise docker.errors.DockerException(f"Docker daemon not available: {e}")
    return docker_client


def get_service_info_from_labels(container_name: str) -> dict:
    """
    Get service information from labels only (no runtime Docker info).
    Returns name, url, description from labels.
    """
    try:
        client = get_docker_client()
        container = client.containers.get(container_name)
        labels = container.labels or {}
        
        return {
            'name': labels.get('package-info.name') or container.name,
            'url': labels.get('package-info.service.url') or labels.get('package-info.url', ''),
            'description': labels.get('package-info.description', ''),
        }
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return {'error': 'Docker daemon not available. Make sure Docker socket is mounted.'}
    except docker.errors.NotFound:
        return {'error': f'Container {container_name} not found'}
    except Exception as e:
        logger.error(f"Error getting service info: {e}")
        return {'error': str(e)}


def get_enabled_services() -> list:
    """
    Get all services that have package-info.enable=true label.
    Returns only label-based metadata (name, url, description).
    """
    try:
        client = get_docker_client()
        all_containers = client.containers.list(all=True)
        services = []
        
        for container in all_containers:
            labels = container.labels or {}
            
            # Only include containers with package-info.enable=true
            if labels.get('package-info.enable', '').lower() != 'true':
                continue
            
            # Extract service information from labels
            service = {
                'name': labels.get('package-info.name') or container.name,
                'url': labels.get('package-info.service.url') or labels.get('package-info.url', ''),
                'description': labels.get('package-info.description', ''),
            }
            
            # Only add if it has at least a name
            if service['name']:
                services.append(service)
        
        return services
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting enabled services: {e}")
        return []


def get_image_info(image_name: str) -> dict:
    """Get information about a Docker image."""
    try:
        client = get_docker_client()
        image = client.images.get(image_name)
        
        info = {
            'id': image.id,
            'tags': image.tags,
            'created': image.attrs.get('Created'),
            'size': image.attrs.get('Size'),
            'architecture': image.attrs.get('Architecture'),
            'os': image.attrs.get('Os'),
        }
        
        return info
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return {'error': 'Docker daemon not available. Make sure Docker socket is mounted.'}
    except docker.errors.ImageNotFound:
        return {'error': f'Image {image_name} not found'}
    except Exception as e:
        logger.error(f"Error getting image info: {e}")
        return {'error': str(e)}


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


@app.route('/package/<container_name>', methods=['GET'])
def package_info(container_name: str):
    """Get label-based information about a specific package/service."""
    info = get_service_info_from_labels(container_name)
    return jsonify(info)


@app.route('/image/<path:image_name>', methods=['GET'])
def image_info(image_name: str):
    """Get information about a specific image."""
    info = get_image_info(image_name)
    return jsonify(info)


@app.route('/self', methods=['GET'])
def self_info():
    """Get label-based information about this service container."""
    container_name = os.getenv('HOSTNAME', 'dockinfo')
    info = get_service_info_from_labels(container_name)
    return jsonify(info)


@app.route('/package', methods=['GET'])
def package_info_query():
    """
    Get label-based information about a package/service.
    Expects 'X-Container-Name' header or 'container' query parameter.
    """
    container_name = request.headers.get('X-Container-Name') or request.args.get('container')
    
    if not container_name:
        return jsonify({'error': 'Container name required (header X-Container-Name or query param container)'}), 400
    
    info = get_service_info_from_labels(container_name)
    return jsonify(info)


@app.route('/by-label', methods=['GET'])
def packages_by_label():
    """
    Find packages by label filter (returns label-based info only).
    Example: /by-label?label=package-info.enable=true
    """
    label_filter = request.args.get('label')
    if not label_filter:
        return jsonify({'error': 'Label filter required (e.g., ?label=package-info.enable=true)'}), 400
    
    try:
        # Parse label filter (format: key=value)
        if '=' not in label_filter:
            return jsonify({'error': 'Label filter must be in format key=value'}), 400
        
        label_key, label_value = label_filter.split('=', 1)
        
        # Get all containers
        client = get_docker_client()
        all_containers = client.containers.list(all=True)
        matching_services = []
        
        for container in all_containers:
            labels = container.labels or {}
            if labels.get(label_key) == label_value:
                service = {
                    'name': labels.get('package-info.name') or container.name,
                    'url': labels.get('package-info.service.url') or labels.get('package-info.url', ''),
                    'description': labels.get('package-info.description', ''),
                }
                if service['name']:
                    matching_services.append(service)
        
        return jsonify({
            'filter': label_filter,
            'count': len(matching_services),
            'packages': matching_services
        })
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return jsonify({'error': 'Docker daemon not available. Make sure Docker socket is mounted.'}), 503
    except Exception as e:
        logger.error(f"Error filtering packages by label: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/my-info', methods=['GET'])
def my_info():
    """
    Get label-based information about the calling container.
    Expects 'X-Container-Name' header or 'container' query parameter.
    """
    container_name = request.headers.get('X-Container-Name') or request.args.get('container')
    
    if not container_name:
        return jsonify({
            'error': 'Container name required',
            'hint': 'Set X-Container-Name header or container query parameter'
        }), 400
    
    info = get_service_info_from_labels(container_name)
    return jsonify(info)


@app.route('/packages', methods=['GET'])
def list_packages():
    """
    List all enabled packages/services based on labels.
    Only returns services with package-info.enable=true label.
    Returns name, url, and description from labels.
    """
    services = get_enabled_services()
    return jsonify({
        'count': len(services),
        'packages': services
    })


@app.route('/list', methods=['GET'])
def list_containers():
    """
    DEPRECATED: Use /packages instead.
    List all containers with basic information.
    """
    try:
        client = get_docker_client()
        all_containers = client.containers.list(all=True)
        containers = []
        
        for container in all_containers:
            containers.append({
                'name': container.name,
                'id': container.id[:12],
                'image': container.image.tags[0] if container.image.tags else container.image.id,
                'status': container.status,
            })
        
        return jsonify({
            'count': len(containers),
            'containers': containers
        })
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return jsonify({'error': 'Docker daemon not available. Make sure Docker socket is mounted.'}), 503
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    host = os.getenv('HOST', '0.0.0.0')
    logger.info("Starting package info service on %s:%s", host, port)
    app.run(host=host, port=port, debug=False)

