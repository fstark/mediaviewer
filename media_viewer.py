#!/usr/bin/env python3
"""
Simple Media Viewer - A web-based media gallery for images and videos
Usage: python media_viewer.py <directory_path>
"""

import os
import sys
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json
import mimetypes
import time

class MediaViewerHandler(BaseHTTPRequestHandler):
    def __init__(self, media_files, base_dir, *args, **kwargs):
        self.media_files = media_files
        self.base_dir = base_dir
        self.start_time = None
        self.response_size = 0
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.start_time = time.time()
        self.response_size = 0
        
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        
        if path == '/':
            page = int(query.get('page', [1])[0])
            self.serve_gallery(page)
        elif path == '/viewer':
            index = int(query.get('index', [0])[0])
            self.serve_viewer(index)
        elif path == '/api/media':
            self.serve_media_list()
        elif path == '/api/all-media':
            self.serve_all_media_list()
        elif path.startswith('/preview/'):
            try:
                media_id = int(path[9:])  # Remove '/preview/' prefix and convert to int
                self.serve_media_preview(media_id)
            except (ValueError, IndexError):
                self.send_error(404)
        elif path.startswith('/media/'):
            try:
                media_id = int(path[7:])  # Remove '/media/' prefix and convert to int
                self.serve_media_by_id(media_id)
            except (ValueError, IndexError):
                self.send_error(404)
        else:
            self.send_error(404)
        
        # Log request timing and response size
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            self.log_message(f"Response: {self.response_size} bytes, Duration: {duration_ms:.2f}ms")

    def write_response(self, data):
        """Write response data and track size"""
        if isinstance(data, str):
            data = data.encode()
        self.response_size += len(data)
        return self.wfile.write(data)

    def serve_gallery(self, page=1):
        """Serve the main gallery page with pagination"""
        html = self.get_gallery_html(page)
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.write_response(html.encode())

    def serve_viewer(self, index):
        """Serve the full-screen viewer page"""
        if 0 <= index < len(self.media_files):
            html = self.get_viewer_html(index)
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.write_response(html.encode())
        else:
            self.send_error(404)

    def serve_media_list(self):
        """Serve the media files list as JSON with pagination support"""
        page = int(self.headers.get('X-Page', 1))
        items_per_page = 500
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        total_items = len(self.media_files)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        media_data = []
        for i in range(start_idx, min(end_idx, total_items)):
            file_path = self.media_files[i]
            is_video = self.is_video_file(file_path)
            
            # Get file size
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                file_size = 0
            
            media_data.append({
                'index': i,
                'url': f'/media/{i}',
                'preview_url': f'/preview/{i}',
                'is_video': is_video,
                'file_size': file_size
            })
        
        response_data = {
            'media': media_data,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_items': total_items,
                'items_per_page': items_per_page
            }
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(response_data).encode())

    def serve_all_media_list(self):
        """Serve all media files list as JSON for viewer navigation"""
        media_data = []
        for i, file_path in enumerate(self.media_files):
            is_video = self.is_video_file(file_path)
            media_data.append({
                'index': i,
                'url': f'/media/{i}',
                'is_video': is_video
            })
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(media_data).encode())

    def serve_media_preview(self, media_id):
        """Serve a media preview - placeholder for large files, smaller version for others"""
        if 0 <= media_id < len(self.media_files):
            file_path = self.media_files[media_id]
            try:
                file_size = os.path.getsize(file_path)
                max_size = 2 * 1024 * 1024  # 2MB
                
                if file_size > max_size:
                    # Return a placeholder for large files
                    self.serve_placeholder(media_id, file_size)
                else:
                    # Serve the actual file for smaller files
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if mime_type is None:
                        mime_type = 'application/octet-stream'
                    
                    self.send_response(200)
                    self.send_header('Content-type', mime_type)
                    self.send_header('Content-Length', str(len(content)))
                    self.end_headers()
                    self.write_response(content)
            except IOError:
                self.send_error(404)
        else:
            self.send_error(404)

    def serve_placeholder(self, media_id, file_size):
        """Generate and serve a placeholder image for large media files"""
        is_video = self.is_video_file(self.media_files[media_id])
        size_mb = file_size / (1024 * 1024)
        
        # Create SVG placeholder with proper SVG icons instead of emoji
        if is_video:
            media_type = "Video"
            # Video camera icon
            icon_svg = '''
                <g fill="#666">
                    <rect x="130" y="70" width="50" height="35" rx="5" fill="none" stroke="#666" stroke-width="2"/>
                    <polygon points="180,80 195,87.5 180,95" fill="#666"/>
                    <circle cx="145" cy="82" r="2" fill="#666"/>
                </g>
            '''
        else:
            media_type = "Image"
            # Picture/image icon
            icon_svg = '''
                <g fill="#666">
                    <rect x="130" y="70" width="60" height="40" rx="3" fill="none" stroke="#666" stroke-width="2"/>
                    <circle cx="145" cy="85" r="5" fill="#666"/>
                    <polygon points="135,100 150,90 165,95 180,85 190,95 190,105 135,105" fill="#666"/>
                </g>
            '''
            
        svg_content = f'''<svg width="320" height="200" xmlns="http://www.w3.org/2000/svg">
            <rect width="320" height="200" fill="#f0f0f0" stroke="#ddd" stroke-width="2"/>
            {icon_svg}
            <text x="160" y="130" font-family="Arial, sans-serif" font-size="16" text-anchor="middle" fill="#666">{media_type}</text>
            <text x="160" y="150" font-family="Arial, sans-serif" font-size="14" text-anchor="middle" fill="#888">Media {media_id + 1}</text>
            <text x="160" y="170" font-family="Arial, sans-serif" font-size="12" text-anchor="middle" fill="#999">{size_mb:.1f} MB</text>
            <text x="160" y="185" font-family="Arial, sans-serif" font-size="11" text-anchor="middle" fill="#aaa">Click to view full size</text>
        </svg>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'image/svg+xml')
        self.send_header('Content-Length', str(len(svg_content)))
        self.end_headers()
        self.write_response(svg_content.encode())

    def serve_media_by_id(self, media_id):
        """Serve a media file by its numeric ID with Range Request support"""
        if 0 <= media_id < len(self.media_files):
            file_path = self.media_files[media_id]
            try:
                file_size = os.path.getsize(file_path)
                
                # Get Range header if present
                range_header = self.headers.get('Range')
                
                if range_header:
                    # Parse Range header (format: "bytes=start-end")
                    try:
                        ranges = range_header.replace('bytes=', '').split('-')
                        start = int(ranges[0]) if ranges[0] else 0
                        end = int(ranges[1]) if ranges[1] else file_size - 1
                        
                        # Ensure valid range
                        start = max(0, min(start, file_size - 1))
                        end = max(start, min(end, file_size - 1))
                        content_length = end - start + 1
                        
                        # Read the requested range
                        with open(file_path, 'rb') as f:
                            f.seek(start)
                            content = f.read(content_length)
                        
                        # Send 206 Partial Content response
                        self.send_response(206)
                        self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                        self.send_header('Accept-Ranges', 'bytes')
                        self.send_header('Content-Length', str(content_length))
                        
                        mime_type, _ = mimetypes.guess_type(file_path)
                        if mime_type is None:
                            mime_type = 'application/octet-stream'
                        self.send_header('Content-Type', mime_type)
                        
                        self.end_headers()
                        self.write_response(content)
                        
                    except (ValueError, IndexError):
                        # Invalid range, serve full file
                        self.serve_full_file(file_path, file_size)
                else:
                    # No range request, serve full file with range support headers
                    self.serve_full_file(file_path, file_size)
                    
            except IOError:
                self.send_error(404)
        else:
            self.send_error(404)

    def serve_full_file(self, file_path, file_size):
        """Serve a complete file with range support headers"""
        with open(file_path, 'rb') as f:
            content = f.read()
        
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = 'application/octet-stream'
        
        self.send_response(200)
        self.send_header('Content-Type', mime_type)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(file_size))
        self.end_headers()
        self.write_response(content)

    def serve_media_file(self, rel_path):
        """Serve a media file"""
        file_path = os.path.join(self.base_dir, rel_path)
        if os.path.exists(file_path) and file_path in self.media_files:
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                mime_type, _ = mimetypes.guess_type(file_path)
                if mime_type is None:
                    mime_type = 'application/octet-stream'
                
                self.send_response(200)
                self.send_header('Content-type', mime_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.write_response(content)
            except IOError:
                self.send_error(404)
        else:
            self.send_error(404)

    def is_video_file(self, file_path):
        """Check if file is a video"""
        return file_path.lower().endswith(('.mp4', '.m4v'))

    def get_gallery_html(self, page=1):
        """Generate the gallery HTML with pagination"""
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Viewer</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f0f0f0;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            margin-bottom: 30px;
            gap: 15px;
        }}
        .pagination button {{
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            transition: background 0.2s;
        }}
        .pagination button:hover:not(:disabled) {{
            background: #0056b3;
        }}
        .pagination button:disabled {{
            background: #6c757d;
            cursor: not-allowed;
        }}
        .page-info {{
            font-size: 16px;
            font-weight: bold;
            margin: 0 10px;
        }}
        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .media-item {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .media-item:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        }}
        .media-preview {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}
        .media-info {{
            background: #fff;
            color: #555;
            padding: 6px 8px;
            font-size: 12px;
            font-weight: bold;
            text-align: left;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-sizing: border-box;
        }}
        .play-overlay {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.7);
            color: white;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }}
        .media-container {{
            position: relative;
            aspect-ratio: 16 / 10;
        }}
        .loading {{
            text-align: center;
            padding: 40px;
            font-size: 18px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Media Viewer</h1>
        <p>Click on any image or video to view in full screen</p>
    </div>
    
    <div class="pagination" id="topPagination">
        <button id="topPrevBtn" onclick="changePage(-1)">← Previous</button>
        <div class="page-info" id="topPageInfo">Page 1 of 1</div>
        <button id="topNextBtn" onclick="changePage(1)">Next →</button>
    </div>
    
    <div class="loading" id="loading">Loading media...</div>
    <div class="gallery" id="gallery" style="display: none;"></div>
    
    <div class="pagination" id="bottomPagination">
        <button id="bottomPrevBtn" onclick="changePage(-1)">← Previous</button>
        <div class="page-info" id="bottomPageInfo">Page 1 of 1</div>
        <button id="bottomNextBtn" onclick="changePage(1)">Next →</button>
    </div>

    <script>
        let currentPage = {page};
        let totalPages = 1;
        let totalItems = 0;
        
        function formatFileSize(bytes) {{
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }}
        
        async function loadGallery(page = 1) {{
            try {{
                document.getElementById('loading').style.display = 'block';
                document.getElementById('gallery').style.display = 'none';
                
                const response = await fetch('/api/media', {{
                    headers: {{
                        'X-Page': page.toString()
                    }}
                }});
                const data = await response.json();
                
                const mediaFiles = data.media;
                const pagination = data.pagination;
                
                currentPage = pagination.current_page;
                totalPages = pagination.total_pages;
                totalItems = pagination.total_items;
                
                const gallery = document.getElementById('gallery');
                gallery.innerHTML = '';
                
                mediaFiles.forEach(media => {{
                    const item = document.createElement('div');
                    item.className = 'media-item';
                    item.onclick = () => window.location.href = `/viewer?index=${{media.index}}`;
                    
                    const container = document.createElement('div');
                    container.className = 'media-container';
                    
                    if (media.is_video) {{
                        const video = document.createElement('video');
                        video.src = media.preview_url;
                        video.className = 'media-preview';
                        video.muted = true;
                        container.appendChild(video);
                        
                        const playOverlay = document.createElement('div');
                        playOverlay.className = 'play-overlay';
                        playOverlay.innerHTML = '▶';
                        container.appendChild(playOverlay);
                    }} else {{
                        const img = document.createElement('img');
                        img.src = media.preview_url;
                        img.className = 'media-preview';
                        img.alt = `Media ${{media.index + 1}}`;
                        container.appendChild(img);
                    }}
                    
                    const info = document.createElement('div');
                    info.className = 'media-info';
                    const fileName = `Media ${{media.index + 1}}`;
                    const fileSize = formatFileSize(media.file_size);
                    info.innerHTML = `<span>${{fileName}}</span><span>${{fileSize}}</span>`;
                    
                    item.appendChild(container);
                    item.appendChild(info);
                    gallery.appendChild(item);
                }});
                
                updatePagination();
                document.getElementById('loading').style.display = 'none';
                document.getElementById('gallery').style.display = 'grid';
                
            }} catch (error) {{
                console.error('Error loading gallery:', error);
                document.getElementById('loading').innerHTML = 'Error loading media files';
            }}
        }}
        
        function updatePagination() {{
            const pageInfo = `Page ${{currentPage}} of ${{totalPages}} (Total: ${{totalItems}} items)`;
            document.getElementById('topPageInfo').textContent = pageInfo;
            document.getElementById('bottomPageInfo').textContent = pageInfo;
            
            const prevDisabled = currentPage <= 1;
            const nextDisabled = currentPage >= totalPages;
            
            document.getElementById('topPrevBtn').disabled = prevDisabled;
            document.getElementById('topNextBtn').disabled = nextDisabled;
            document.getElementById('bottomPrevBtn').disabled = prevDisabled;
            document.getElementById('bottomNextBtn').disabled = nextDisabled;
        }}
        
        function changePage(direction) {{
            const newPage = currentPage + direction;
            if (newPage >= 1 && newPage <= totalPages) {{
                window.location.href = `/?page=${{newPage}}`;
            }}
        }}
        
        // Load gallery on page load
        loadGallery(currentPage);
    </script>
</body>
</html>'''

    def get_viewer_html(self, index):
        """Generate the viewer HTML"""
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Viewer</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: black;
            color: white;
            font-family: Arial, sans-serif;
            overflow: hidden;
        }}
        .viewer-container {{
            position: relative;
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .media-display {{
            max-width: 100vw;
            max-height: 100vh;
            object-fit: contain;
        }}
        .controls {{
            position: absolute;
            top: 20px;
            left: 20px;
            right: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 100;
        }}
        .nav-button {{
            background: rgba(0,0,0,0.7);
            color: white;
            border: none;
            padding: 15px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            transition: background 0.2s;
        }}
        .nav-button:hover {{
            background: rgba(0,0,0,0.9);
        }}
        .nav-button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .side-nav {{
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(0,0,0,0.7);
            color: white;
            border: none;
            padding: 20px 15px;
            cursor: pointer;
            font-size: 24px;
            border-radius: 5px;
            transition: background 0.2s;
        }}
        .side-nav:hover {{
            background: rgba(0,0,0,0.9);
        }}
        .side-nav:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .prev-nav {{
            left: 20px;
        }}
        .next-nav {{
            right: 20px;
        }}
        .media-info {{
            position: absolute;
            bottom: 20px;
            left: 20px;
            right: 20px;
            text-align: center;
            background: rgba(0,0,0,0.7);
            padding: 10px;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="viewer-container">
        <div class="controls">
            <button class="nav-button" onclick="goBack()">← Back to Gallery</button>
            <div>
                <span id="counter">1 of 1</span>
            </div>
        </div>
        
        <button class="side-nav prev-nav" id="prevBtn" onclick="navigate(-1)">‹</button>
        <button class="side-nav next-nav" id="nextBtn" onclick="navigate(1)">›</button>
        
        <div id="mediaContainer"></div>
    </div>

    <script>
        let mediaFiles = [];
        let currentIndex = {index};
        
        async function loadMediaList() {{
            try {{
                const response = await fetch('/api/all-media');
                mediaFiles = await response.json();
                displayMedia(currentIndex);
                updateControls();
            }} catch (error) {{
                console.error('Error loading media list:', error);
            }}
        }}
        
        function displayMedia(index) {{
            const media = mediaFiles[index];
            if (!media) return;
            
            const container = document.getElementById('mediaContainer');
            container.innerHTML = '';
            
            if (media.is_video) {{
                const video = document.createElement('video');
                video.src = media.url;
                video.className = 'media-display';
                video.controls = true;
                video.autoplay = true;
                container.appendChild(video);
            }} else {{
                const img = document.createElement('img');
                img.src = media.url;
                img.className = 'media-display';
                img.alt = `Media ${{index + 1}}`;
                container.appendChild(img);
            }}
            
            document.getElementById('counter').textContent = `${{index + 1}} of ${{mediaFiles.length}}`;
        }}
        
        function updateControls() {{
            const prevBtn = document.getElementById('prevBtn');
            const nextBtn = document.getElementById('nextBtn');
            
            prevBtn.disabled = currentIndex <= 0;
            nextBtn.disabled = currentIndex >= mediaFiles.length - 1;
        }}
        
        function navigate(direction) {{
            const newIndex = currentIndex + direction;
            if (newIndex >= 0 && newIndex < mediaFiles.length) {{
                currentIndex = newIndex;
                displayMedia(currentIndex);
                updateControls();
                // Update URL without reloading
                history.pushState(null, '', `/viewer?index=${{currentIndex}}`);
            }}
        }}
        
        function goBack() {{
            // Calculate which page the current image is on
            const itemsPerPage = 500;
            const currentPage = Math.floor(currentIndex / itemsPerPage) + 1;
            window.location.href = `/?page=${{currentPage}}`;
        }}
        
        // Keyboard navigation
        document.addEventListener('keydown', function(e) {{
            switch(e.key) {{
                case 'ArrowLeft':
                    navigate(-1);
                    break;
                case 'ArrowRight':
                    navigate(1);
                    break;
                case 'Escape':
                    goBack();
                    break;
            }}
        }});
        
        // Load media on page load
        loadMediaList();
    </script>
</body>
</html>'''


def create_handler_with_media(media_files, base_dir):
    """Create a handler class with media files and base directory"""
    def handler(*args, **kwargs):
        return MediaViewerHandler(media_files, base_dir, *args, **kwargs)
    return handler


def scan_for_media_files(directory):
    """Recursively scan directory for media files"""
    media_extensions = {'.png', '.jpg', '.jpeg', '.mp4', '.m4v'}
    media_files = []
    
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if any(file.lower().endswith(ext) for ext in media_extensions):
                    full_path = os.path.join(root, file)
                    try:
                        # Skip 0-byte files
                        if os.path.getsize(full_path) > 0:
                            media_files.append(full_path)
                    except OSError:
                        # Skip files that can't be accessed (permissions, broken symlinks, etc.)
                        continue
    except PermissionError as e:
        print(f"Warning: Permission denied accessing {e.filename}")
    except Exception as e:
        print(f"Error scanning directory: {e}")
    
    return sorted(media_files)


def main():
    parser = argparse.ArgumentParser(description='Simple Media Viewer - Web-based media gallery')
    parser.add_argument('directory', help='Directory to scan for media files')
    parser.add_argument('-p', '--port', type=int, default=8000, help='Port to run server on (default: 8000)')
    
    args = parser.parse_args()
    
    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a valid directory")
        sys.exit(1)
    
    # Convert to absolute path
    base_dir = os.path.abspath(args.directory)
    
    # Scan for media files
    print(f"Scanning for media files in: {base_dir}")
    media_files = scan_for_media_files(base_dir)
    
    if not media_files:
        print("No media files found (looking for: png, jpg, jpeg, mp4, m4v)")
        sys.exit(1)
    
    print(f"Found {len(media_files)} media files")
    
    # Create handler with media files
    handler_class = create_handler_with_media(media_files, base_dir)
    
    # Start server
    server = HTTPServer(('0.0.0.0', args.port), handler_class)
    print(f"\nMedia viewer server running at:")
    print(f"  Local:    http://localhost:{args.port}")
    print(f"  Network:  http://0.0.0.0:{args.port}")
    print("Press Ctrl+C to stop the server")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == '__main__':
    main()
