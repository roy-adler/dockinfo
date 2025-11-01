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


def get_container_info(container_name: str) -> dict:
    """Get information about a container."""
    try:
        client = get_docker_client()
        container = client.containers.get(container_name)
        attrs = container.attrs
        
        info = {
            'name': container.name,
            'id': container.id[:12],
            'image': container.image.tags[0] if container.image.tags else container.image.id,
            'image_id': container.image.id,
            'status': container.status,
            'labels': container.labels,
            'created': attrs.get('Created'),
            'ports': attrs.get('NetworkSettings', {}).get('Ports', {}),
            'environment': attrs.get('Config', {}).get('Env', []),
        }
        
        return info
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return {'error': 'Docker daemon not available. Make sure Docker socket is mounted.'}
    except docker.errors.NotFound:
        return {'error': f'Container {container_name} not found'}
    except Exception as e:
        logger.error(f"Error getting container info: {e}")
        return {'error': str(e)}


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


@app.route('/container/<container_name>', methods=['GET'])
def container_info(container_name: str):
    """Get information about a specific container."""
    info = get_container_info(container_name)
    return jsonify(info)


@app.route('/image/<path:image_name>', methods=['GET'])
def image_info(image_name: str):
    """Get information about a specific image."""
    info = get_image_info(image_name)
    return jsonify(info)


@app.route('/self', methods=['GET'])
def self_info():
    """Get information about the container running this service (via labels)."""
    # Try to get container name from environment variable or hostname
    container_name = os.getenv('HOSTNAME', 'package-info-service')
    
    # Check if running in Docker
    try:
        info = get_container_info(container_name)
        # Check if we got an error response
        if 'error' in info:
            raise Exception(info['error'])
        return jsonify(info)
    except (docker.errors.DockerException, docker.errors.NotFound, Exception):
        return jsonify({
            'error': 'Could not determine container information',
            'hostname': container_name
        })


@app.route('/labels', methods=['GET'])
def labels_info():
    """
    Get information based on labels from the calling container.
    Expects 'X-Container-Name' header or 'container' query parameter.
    """
    container_name = request.headers.get('X-Container-Name') or request.args.get('container')
    
    if not container_name:
        return jsonify({'error': 'Container name required (header X-Container-Name or query param container)'}), 400
    
    info = get_container_info(container_name)
    return jsonify(info)


@app.route('/by-label', methods=['GET'])
def containers_by_label():
    """
    Find containers by label filter.
    Example: /by-label?package-info.enable=true
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
        matching_containers = []
        
        for container in all_containers:
            labels = container.labels or {}
            if labels.get(label_key) == label_value:
                matching_containers.append({
                    'name': container.name,
                    'id': container.id[:12],
                    'image': container.image.tags[0] if container.image.tags else container.image.id,
                    'status': container.status,
                    'labels': labels,
                })
        
        return jsonify({
            'filter': label_filter,
            'count': len(matching_containers),
            'containers': matching_containers
        })
    except docker.errors.DockerException as e:
        logger.error(f"Docker connection error: {e}")
        return jsonify({'error': 'Docker daemon not available. Make sure Docker socket is mounted.'}), 503
    except Exception as e:
        logger.error(f"Error filtering containers by label: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/my-info', methods=['GET'])
def my_info():
    """
    Get information about the calling container.
    The calling container should set 'X-Container-Name' header or 
    have a label 'package-info.enable=true' and we'll try to match by hostname.
    """
    # Try to get container name from header first
    container_name = request.headers.get('X-Container-Name')
    
    # If not provided, try to infer from hostname (if calling container sets HOSTNAME)
    if not container_name:
        hostname = request.headers.get('X-Hostname') or os.getenv('HOSTNAME')
        if hostname:
            try:
                client = get_docker_client()
                container = client.containers.get(hostname)
                container_name = container.name
            except (docker.errors.DockerException, docker.errors.NotFound):
                pass
    
    if not container_name:
        return jsonify({
            'error': 'Could not determine container name',
            'hint': 'Set X-Container-Name header or X-Hostname header'
        }), 400
    
    info = get_container_info(container_name)
    return jsonify(info)


@app.route('/list', methods=['GET'])
def list_containers():
    """List all containers with basic information."""
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

