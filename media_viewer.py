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
import hashlib
from PIL import Image
import concurrent.futures
import struct
import cv2

# Global constants
PREVIEW_FRAME_DURATION_MS = 300  # Duration per frame in animated previews
PREVIEW_FRAME_COUNT = 11  # Number of frames to extract for previews (includes first and last)

class MediaFile:
    def __init__(self, path):
        self.path = path
        self.file_size = self.get_file_size()
        self.is_video = self.check_is_video()
        self.file_type = os.path.splitext(path)[1][1:].upper()
        self._md5 = None
        self.detect_actual_file_type()

    @property
    def md5(self):
        if self._md5 is None:
            self._md5 = hashlib.md5(self.path.encode('utf-8')).hexdigest()
        return self._md5

    def get_file_size(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def check_is_video(self):
        return self.path.lower().endswith(('.mp4', '.m4v'))

    def detect_actual_file_type(self):
        """Detect actual file type by reading file header magic numbers"""
        try:
            with open(self.path, 'rb') as f:
                header = f.read(32)  # Read first 32 bytes
            
            actual_type = None
            
            # Check magic numbers for common formats
            if header.startswith(b'\xFF\xD8\xFF'):
                actual_type = 'JPEG'
            elif header.startswith(b'\x89PNG\r\n\x1a\n'):
                actual_type = 'PNG'
            elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
                actual_type = 'GIF'
            elif len(header) >= 12 and header[4:8] == b'ftyp':
                actual_type = 'MP4'
            elif header.startswith(b'RIFF') and b'WEBP' in header[:20]:
                actual_type = 'WEBP'
            elif header.startswith(b'BM'):
                actual_type = 'BMP'
            
            if actual_type is None:
                print(f"Warning: File not recognized by content: {self.path}")
            # elif actual_type != self.file_type:
            #     print(f"Warning: File content ({actual_type}) doesn't match extension ({self.file_type}): {self.path}")
                
        except (IOError, OSError) as e:
            print(f"Warning: Could not read file header for {self.path}: {e}")

    def get_preview(self):
        """Return (content_type, content) for preview"""
        if self.is_video or self.path.lower().endswith('.gif'):
            # Videos and GIFs get .gif previews
            preview_path = f'/tmp/mediaviewercache/previews/{self.md5}.gif'
            if not os.path.exists(preview_path):
                try:
                    # Both videos and GIFs can be processed the same way
                    generate_video_preview(self.path, self.md5)
                except Exception as e:
                    print(f"Error generating preview for {self.path}: {e}")
            if os.path.exists(preview_path):
                try:
                    with open(preview_path, 'rb') as f:
                        content = f.read()
                    return ('image/gif', content)
                except Exception:
                    pass
        else:
            # Other image files get .png previews
            image_exts = ('.png', '.jpg', '.jpeg')
            if self.path.lower().endswith(image_exts):
                preview_path = f'/tmp/mediaviewercache/previews/{self.md5}.png'
                if not os.path.exists(preview_path):
                    try:
                        generate_preview(self.path, self.md5)
                    except Exception as e:
                        print(f"Error generating preview for {self.path}: {e}")
                if os.path.exists(preview_path):
                    try:
                        with open(preview_path, 'rb') as f:
                            content = f.read()
                        return ('image/png', content)
                    except Exception:
                        pass
        # If we can't generate or find a preview, return None
        # The caller will handle this by serving a placeholder
        return None

def generate_preview(image_path, md5):
    """Convert image to PNG, resize/crop to 320x200, and save in cache"""
    preview_path = f'/tmp/mediaviewercache/previews/{md5}.png'
    with Image.open(image_path) as img:
        # Calculate aspect ratios
        target_w, target_h = 320, 200
        src_w, src_h = img.size
        src_ratio = src_w / src_h
        target_ratio = target_w / target_h
        # Resize and crop
        if src_ratio > target_ratio:
            # Source is wider: resize by height, crop width
            scale = target_h / src_h
            new_w = int(src_w * scale)
            img = img.resize((new_w, target_h), Image.LANCZOS)
            left = (new_w - target_w) // 2
            img = img.crop((left, 0, left + target_w, target_h))
        else:
            # Source is taller: resize by width, crop height
            scale = target_w / src_w
            new_h = int(src_h * scale)
            img = img.resize((target_w, new_h), Image.LANCZOS)
            top = (new_h - target_h) // 2
            img = img.crop((0, top, target_w, top + target_h))
        img.save(preview_path, format='PNG')


def extract_video_frames(video_path, num_frames=PREVIEW_FRAME_COUNT):
    """Extract frames from video at evenly spaced intervals"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError(f"Video has no frames: {video_path}")
        
        frames = []
        frame_indices = []
        
        # Calculate frame positions evenly distributed from 0% to 100%
        if total_frames == 1:
            frame_indices = [0]
        elif total_frames < num_frames:
            # If video has fewer frames than requested, use all available
            frame_indices = list(range(total_frames))
        else:
            # Evenly distribute frames from 0% to 100%
            # For num_frames=5: positions 0, 0.25, 0.5, 0.75, 1.0 of total_frames-1
            frame_indices = []
            for i in range(num_frames):
                if num_frames == 1:
                    position = 0
                else:
                    position = i / (num_frames - 1)  # 0.0, 0.25, 0.5, 0.75, 1.0
                frame_idx = int(position * (total_frames - 1))
                frame_indices.append(frame_idx)
        
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                # Convert BGR to RGB for PIL
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                frames.append(pil_image)
        
        return frames
    
    finally:
        cap.release()


def resize_and_crop_frame(frame, target_w=320, target_h=200):
    """Resize and crop a frame to target dimensions"""
    src_w, src_h = frame.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h
    
    # Resize and crop (same logic as generate_preview)
    if src_ratio > target_ratio:
        # Source is wider: resize by height, crop width
        scale = target_h / src_h
        new_w = int(src_w * scale)
        frame = frame.resize((new_w, target_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        frame = frame.crop((left, 0, left + target_w, target_h))
    else:
        # Source is taller: resize by width, crop height
        scale = target_w / src_w
        new_h = int(src_h * scale)
        frame = frame.resize((target_w, new_h), Image.LANCZOS)
        top = (new_h - target_h) // 2
        frame = frame.crop((0, top, target_w, top + target_h))
    
    return frame


def generate_video_preview(video_path, md5):
    """Generate animated GIF preview for video"""
    preview_path = f'/tmp/mediaviewercache/previews/{md5}.gif'
    
    try:
        # Extract frames from video
        frames = extract_video_frames(video_path, PREVIEW_FRAME_COUNT)
        if not frames:
            raise ValueError("No frames extracted from video")
        
        # Resize and crop all frames
        processed_frames = []
        for frame in frames:
            processed_frame = resize_and_crop_frame(frame, 320, 200)
            processed_frames.append(processed_frame)
        
        # Save as animated GIF
        processed_frames[0].save(
            preview_path,
            format='GIF',
            save_all=True,
            append_images=processed_frames[1:],
            duration=PREVIEW_FRAME_DURATION_MS,
            loop=0  # infinite loop
        )
        
    except Exception as e:
        # If video processing fails, create a static placeholder frame
        print(f"Warning: Could not generate video preview for {video_path}: {e}")
        # Create a simple error placeholder
        placeholder = Image.new('RGB', (320, 200), color='#333333')
        placeholder.save(preview_path, format='GIF')


class MediaViewerHandler(BaseHTTPRequestHandler):
    def __init__(self, media_files, base_dir, verbose=False, *args, **kwargs):
        self.media_files = media_files
        self.base_dir = base_dir
        self.verbose = verbose
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
            media_file = self.media_files[i]
            media_data.append({
                'index': i,
                'url': f'/media/{i}',
                'preview_url': f'/preview/{i}',
                'is_video': media_file.is_video,
                'file_size': media_file.file_size,
                'file_type': media_file.file_type
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
        for i, media_file in enumerate(self.media_files):
            rel_path = os.path.relpath(media_file.path, self.base_dir)
            path_parts = rel_path.split(os.sep)
            if len(path_parts) > 2:
                display_path = os.path.join(path_parts[-3], path_parts[-2], path_parts[-1])
            elif len(path_parts) > 1:
                display_path = os.path.join(path_parts[-2], path_parts[-1])
            else:
                display_path = path_parts[-1]
            media_data.append({
                'index': i,
                'url': f'/media/{i}',
                'is_video': media_file.is_video,
                'display_path': display_path
            })
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(media_data).encode())

    def serve_media_preview(self, media_id):
        """Serve a media preview - placeholder for large files, smaller version for others"""
        if 0 <= media_id < len(self.media_files):
            media_file = self.media_files[media_id]
            
            # Log original filename if verbose mode is enabled
            if self.verbose:
                rel_path = os.path.relpath(media_file.path, self.base_dir)
                self.log_message(f"Serving preview for: {rel_path}")
            
            preview = media_file.get_preview()
            if preview is not None:
                mime_type, content = preview
                self.send_response(200)
                self.send_header('Content-type', mime_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.write_response(content)
            else:
                self.serve_placeholder(media_id, media_file.file_size)
        else:
            self.send_error(404)

    def serve_placeholder(self, media_id, file_size):
        """Generate and serve a placeholder image for large media files"""
        media_file = self.media_files[media_id]
        is_video = media_file.is_video
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
            media_file = self.media_files[media_id]
            
            # Log original filename if verbose mode is enabled
            if self.verbose:
                rel_path = os.path.relpath(media_file.path, self.base_dir)
                self.log_message(f"Serving file: {rel_path}")
            
            try:
                file_size = media_file.file_size
                
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
                        with open(media_file.path, 'rb') as f:
                            f.seek(start)
                            content = f.read(content_length)
                        
                        # Send 206 Partial Content response
                        self.send_response(206)
                        self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                        self.send_header('Accept-Ranges', 'bytes')
                        self.send_header('Content-Length', str(content_length))
                        
                        mime_type, _ = mimetypes.guess_type(media_file.path)
                        if mime_type is None:
                            mime_type = 'application/octet-stream'
                        self.send_header('Content-Type', mime_type)
                        
                        self.end_headers()
                        self.write_response(content)
                        
                    except (ValueError, IndexError):
                        # Invalid range, serve full file
                        self.serve_full_file(media_file.path, file_size)
                else:
                    # No range request, serve full file with range support headers
                    self.serve_full_file(media_file.path, file_size)
                    
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
        .current-path {{
            font-family: monospace;
            font-size: 14px;
            color: #666;
            margin-top: 10px;
            word-break: break-all;
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
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
        <div id="currentPath" class="current-path"></div>
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
                    
                    // All previews are now images (GIFs for videos, PNGs for images)
                    const img = document.createElement('img');
                    img.src = media.preview_url;
                    img.className = 'media-preview';
                    img.alt = `Media ${{media.index + 1}}`;
                    container.appendChild(img);
                    
                    const info = document.createElement('div');
                    info.className = 'media-info';
                    const fileName = `Media ${{media.index + 1}}`;
                    const fileSize = formatFileSize(media.file_size);
                    const fileType = media.file_type;
                    info.innerHTML = `<span>${{fileName}}</span><span>${{fileSize}} • ${{fileType}}</span>`;
                    
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
        .media-title {{
            font-family: monospace;
            font-size: 14px;
            color: rgba(255,255,255,0.8);
            text-align: center;
            word-break: break-all;
            max-width: 400px;
            line-height: 1.2;
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
            <div class="media-title" id="mediaTitle">Loading...</div>
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
            document.getElementById('mediaTitle').textContent = media.display_path || `Media ${{index + 1}}`;
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


def create_handler_with_media(media_files, base_dir, verbose=False):
    """Create a handler class with media files and base directory"""
    def handler(*args, **kwargs):
        return MediaViewerHandler(media_files, base_dir, verbose, *args, **kwargs)
    return handler


def scan_for_media_files(directory, verbose=False):
    """Recursively scan directory for media files"""
    media_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.mp4', '.m4v'}
    media_files = []
    unrecognized_files = []
    
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                full_path = os.path.join(root, file)
                try:
                    # Skip 0-byte files
                    file_size = os.path.getsize(full_path)
                    if file_size == 0:
                        continue
                        
                    if any(file.lower().endswith(ext) for ext in media_extensions):
                        media_files.append(MediaFile(full_path))
                    elif verbose:
                        # Track unrecognized files for verbose output
                        unrecognized_files.append(full_path)
                        
                except OSError:
                    continue
    except PermissionError as e:
        print(f"Warning: Permission denied accessing {e.filename}")
    except Exception as e:
        print(f"Error scanning directory: {e}")
    
    # In verbose mode, show all unrecognized files
    if verbose and unrecognized_files:
        print(f"\nFound {len(unrecognized_files)} files not recognized as media files:")
        for file_path in sorted(unrecognized_files):
            rel_path = os.path.relpath(file_path, directory)
            print(f"  {rel_path}")
        print()
    
    return sorted(media_files, key=lambda mf: mf.path)


def build_cache(media_files):
    """Build previews for all media files in the cache, with progress display and multithreading"""
    # Separate images and videos for different processing
    image_exts = ('.png', '.jpg', '.jpeg', '.gif')
    images = [mf for mf in media_files if not mf.is_video and mf.path.lower().endswith(image_exts)]
    videos = [mf for mf in media_files if mf.is_video]
    
    total_images = len(images)
    total_videos = len(videos)
    total = total_images + total_videos
    
    print(f"Building preview cache for {total} files ({total_images} images, {total_videos} videos) (multithreaded)...")
    
    def build_one(mf):
        mf.get_preview()
        return mf
    
    # Process all files together
    all_files = images + videos
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as executor:
        futures = {executor.submit(build_one, mf): mf for mf in all_files}
        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            mf = futures[future]
            file_type = "video" if mf.is_video else "image"
            print(f"  [{idx}/{total}] {file_type}: {os.path.basename(mf.path)}", end='\r', flush=True)
    print(f"\nBuilt {total} previews ({total_images} images, {total_videos} videos).")


def main():
    parser = argparse.ArgumentParser(description='Simple Media Viewer - Web-based media gallery')
    parser.add_argument('directory', help='Directory to scan for media files')
    parser.add_argument('-p', '--port', type=int, default=8000, help='Port to run server on (default: 8000)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Display original file names when serving files')
    parser.add_argument('--build-cache', action='store_true', help='Build image preview cache at startup')
    args = parser.parse_args()

    # Create cache directories
    cache_dir = '/tmp/mediaviewercache'
    previews_dir = os.path.join(cache_dir, 'previews')
    os.makedirs(previews_dir, exist_ok=True)

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a valid directory")
        sys.exit(1)
    
    # Convert to absolute path
    base_dir = os.path.abspath(args.directory)
    
    # Scan for media files
    print(f"Scanning for media files in: {base_dir}")
    media_files = scan_for_media_files(base_dir, args.verbose)

    if not media_files:
        print("No media files found (looking for: png, jpg, jpeg, gif, mp4, m4v)")
        sys.exit(1)

    print(f"Found {len(media_files)} media files")

    if args.build_cache:
        build_cache(media_files)

    # Create handler with media files
    handler_class = create_handler_with_media(media_files, base_dir, args.verbose)
    
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
