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
import re

# Global constants
PREVIEW_FRAME_DURATION_MS = 300  # Duration per frame in animated previews
PREVIEW_FRAME_COUNT = 11  # Number of frames to extract for previews (includes first and last)
CACHE_DIR = None  # Will be set to <base_dir>/.mediaviewer
WORD_COUNTS = {}  # Global word counter for all file paths
RATINGS = {}  # File path -> rating mapping (path: rating). Default -1 (unrated)
CORPUS = []  # All media files found (never changes)
MEDIA_FILES = []  # Current selection (can be filtered)

class MediaFile:
    def __init__(self, path):
        self.path = path
        self.file_size = self.get_file_size()
        self.is_video = self.check_is_video()
        self.file_type = os.path.splitext(path)[1][1:].upper()
        self._md5 = None
        # Extract words from path and update global counter
        self.extract_words_from_path()

    @property
    def rating(self):
        """Get rating for this file, default -1 (unrated)"""
        return RATINGS.get(self.path, -1)

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

    def extract_words_from_path(self):
        """Extract words from file path and update global word counter"""
        # Split on anything that's not alphanumeric or '-'
        words = re.findall(r'[A-Za-z0-9-]+', self.path)
        # Convert to lowercase and count
        for word in words:
            word_lower = word.lower()
            WORD_COUNTS[word_lower] = WORD_COUNTS.get(word_lower, 0) + 1

    def set_rating(self, rating):
        """Set rating for this file"""
        RATINGS[self.path] = rating

    def get_preview(self):
        """Return (content_type, content) for preview"""
        if self.is_video or self.path.lower().endswith('.gif'):
            # Videos and GIFs get .gif previews
            preview_path = f'{CACHE_DIR}/previews/{self.md5}.gif'
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
                preview_path = f'{CACHE_DIR}/previews/{self.md5}.png'
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
    preview_path = f'{CACHE_DIR}/previews/{md5}.png'
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
    preview_path = f'{CACHE_DIR}/previews/{md5}.gif'
    
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


def load_ratings(ratings_file):
    """Load ratings from text file. Format: path rating"""
    global RATINGS
    RATINGS = {}
    if os.path.exists(ratings_file):
        try:
            with open(ratings_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.rsplit(' ', 1)  # Split from right to get rating
                        if len(parts) == 2:
                            path, rating_str = parts
                            try:
                                rating = int(rating_str)
                                RATINGS[path] = rating
                            except ValueError:
                                pass
            print(f"Loaded {len(RATINGS)} ratings from {ratings_file}")
        except Exception as e:
            print(f"Error loading ratings: {e}")


def save_ratings(ratings_file):
    """Save ratings to text file. Format: path rating"""
    try:
        with open(ratings_file, 'w', encoding='utf-8') as f:
            for path in sorted(RATINGS.keys()):
                rating = RATINGS[path]
                f.write(f"{path} {rating}\n")
    except Exception as e:
        print(f"Error saving ratings: {e}")


class MediaViewerHandler(BaseHTTPRequestHandler):
    def __init__(self, base_dir, verbose=False, *args, **kwargs):
        self.base_dir = base_dir
        self.verbose = verbose
        self.start_time = None
        self.response_size = 0
        super().__init__(*args, **kwargs)
    
    @property
    def media_files(self):
        """Always use the current global MEDIA_FILES"""
        return MEDIA_FILES

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
        elif path == '/words':
            self.serve_words_page()
        elif path == '/api/media':
            self.serve_media_list()
        elif path == '/api/all-media':
            self.serve_all_media_list()
        elif path == '/api/words':
            self.serve_words_data()
        elif path == '/api/filter':
            word = query.get('word', [''])[0]
            ratings = query.get('ratings', [''])[0]
            self.serve_filter_by_word(word, ratings)
        elif path == '/api/reset':
            self.serve_reset_filter()
        elif path.startswith('/static/'):
            self.serve_static_file(path)
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

    def do_POST(self):
        """Handle POST requests"""
        self.start_time = time.time()
        self.response_size = 0
        
        path = urllib.parse.urlparse(self.path).path
        
        if path == '/api/set-rating':
            self.handle_set_rating()
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

    def serve_static_file(self, path):
        """Serve static files (CSS, JS, etc.)"""
        # Get the script directory to find static files relative to the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, path.lstrip('/'))
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-Type', mime_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.write_response(content)
            except IOError:
                self.send_error(404)
        else:
            self.send_error(404)

    def load_template(self, template_name):
        """Load an HTML template from the templates directory"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, 'templates', template_name)
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except IOError:
            return None

    def serve_gallery(self, page=1):
        """Serve the main gallery page with pagination"""
        template = self.load_template('gallery.html')
        if template is None:
            self.send_error(500, "Template not found")
            return
        
        # Replace template variables
        html = template.replace('{{PAGE}}', str(page))
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.write_response(html.encode())

    def serve_viewer(self, index):
        """Serve the full-screen viewer page"""
        if 0 <= index < len(MEDIA_FILES):
            template = self.load_template('viewer.html')
            if template is None:
                self.send_error(500, "Template not found")
                return
            
            # Replace template variables
            html = template.replace('{{INDEX}}', str(index))
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.write_response(html.encode())
        else:
            self.send_error(404)

    def serve_words_page(self):
        """Serve the words page"""
        template = self.load_template('words.html')
        if template is None:
            self.send_error(500, "Template not found")
            return
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.write_response(template.encode())

    def serve_words_data(self):
        """Serve the words data as JSON"""
        # Sort words by count (descending), then alphabetically
        sorted_words = sorted(WORD_COUNTS.items(), key=lambda x: (-x[1], x[0]))
        
        words_data = [
            {'word': word, 'count': count}
            for word, count in sorted_words
        ]
        
        response_data = {
            'words': words_data,
            'total_words': len(words_data),
            'total_occurrences': sum(WORD_COUNTS.values()),
            'current_selection': len(MEDIA_FILES),
            'corpus_size': len(CORPUS)
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(response_data).encode())

    def serve_filter_by_word(self, word, ratings_param=None):
        """Filter MEDIA_FILES by word and ratings"""
        global MEDIA_FILES
        
        # Parse ratings parameter (comma-separated list like "-1,0,1")
        selected_ratings = None
        if ratings_param:
            try:
                selected_ratings = [int(r) for r in ratings_param.split(',')]
            except ValueError:
                pass
        
        if word or selected_ratings is not None:
            word_lower = word.lower() if word else None
            filtered = []
            
            for mf in CORPUS:
                # Check word match
                word_match = (not word_lower) or (word_lower in mf.path.lower())
                
                # Check rating match
                rating_match = (selected_ratings is None) or (mf.rating in selected_ratings)
                
                if word_match and rating_match:
                    filtered.append(mf)
            
            MEDIA_FILES = filtered
            result = {'success': True, 'word': word, 'count': len(MEDIA_FILES)}
        else:
            result = {'success': False, 'error': 'No filter provided'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(result).encode())

    def serve_reset_filter(self):
        """Reset MEDIA_FILES to full corpus"""
        global MEDIA_FILES
        MEDIA_FILES = CORPUS[:]
        result = {'success': True, 'count': len(MEDIA_FILES)}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(result).encode())

    def handle_set_rating(self):
        """Handle POST request to set rating for a file"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            index = data.get('index')
            rating = data.get('rating')
            
            if index is None or rating is None:
                result = {'success': False, 'error': 'Missing index or rating'}
            elif index < 0 or index >= len(MEDIA_FILES):
                result = {'success': False, 'error': 'Invalid index'}
            elif rating not in [0, 1, 2, 3]:
                result = {'success': False, 'error': 'Invalid rating (must be 0, 1, 2, or 3)'}
            else:
                media_file = MEDIA_FILES[index]
                media_file.set_rating(rating)
                
                # Save ratings to file
                ratings_file = os.path.join(CACHE_DIR, 'ratings.txt')
                save_ratings(ratings_file)
                
                result = {'success': True, 'index': index, 'rating': rating}
        except Exception as e:
            result = {'success': False, 'error': str(e)}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(result).encode())

    def serve_media_list(self):
        """Serve the media files list as JSON with pagination support"""
        page = int(self.headers.get('X-Page', 1))
        items_per_page = 50
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        total_items = len(MEDIA_FILES)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        media_data = []
        for i in range(start_idx, min(end_idx, total_items)):
            media_file = MEDIA_FILES[i]
            media_data.append({
                'index': i,
                'url': f'/media/{i}',
                'preview_url': f'/preview/{i}',
                'is_video': media_file.is_video,
                'file_size': media_file.file_size,
                'file_type': media_file.file_type,
                'rating': media_file.rating
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
        for i, media_file in enumerate(MEDIA_FILES):
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
                'display_path': display_path,
                'rating': media_file.rating
            })
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.write_response(json.dumps(media_data).encode())

    def serve_media_preview(self, media_id):
        """Serve a media preview - placeholder for large files, smaller version for others"""
        if 0 <= media_id < len(MEDIA_FILES):
            media_file = MEDIA_FILES[media_id]
            
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
        media_file = MEDIA_FILES[media_id]
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
        if 0 <= media_id < len(MEDIA_FILES):
            media_file = MEDIA_FILES[media_id]
            
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


def create_handler_with_media(base_dir, verbose=False):
    """Create a handler class with base directory"""
    def handler(*args, **kwargs):
        return MediaViewerHandler(base_dir, verbose, *args, **kwargs)
    return handler


def scan_for_media_files(directory, verbose=False, select_filter=None):
    """Recursively scan directory for media files"""
    media_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.mp4', '.m4v'}
    media_files = []
    unrecognized_files = []
    
    try:
        for root, dirs, files in os.walk(directory):
            # Skip the cache directory
            if '.mediaviewer' in dirs:
                dirs.remove('.mediaviewer')
            
            for file in files:
                full_path = os.path.join(root, file)
                try:
                    # Skip 0-byte files
                    file_size = os.path.getsize(full_path)
                    if file_size == 0:
                        continue
                    
                    # Apply selection filter if provided (check full path)
                    if select_filter and select_filter not in full_path:
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
    # Ensure cache directory exists
    previews_dir = f'{CACHE_DIR}/previews'
    os.makedirs(previews_dir, exist_ok=True)
    
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
    global CACHE_DIR, CORPUS, MEDIA_FILES
    
    parser = argparse.ArgumentParser(description='Simple Media Viewer - Web-based media gallery')
    parser.add_argument('directory', help='Directory to scan for media files')
    parser.add_argument('-p', '--port', type=int, default=8000, help='Port to run server on (default: 8000)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Display original file names when serving files')
    parser.add_argument('--build-cache', action='store_true', help='Build image preview cache at startup')
    parser.add_argument('--select', type=str, default=None, help='Only include files containing this string in their filename')
    args = parser.parse_args()

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a valid directory")
        sys.exit(1)
    
    # Convert to absolute path
    base_dir = os.path.abspath(args.directory)
    
    # Set up cache directory inside the served path
    CACHE_DIR = os.path.join(base_dir, '.mediaviewer')
    previews_dir = os.path.join(CACHE_DIR, 'previews')
    os.makedirs(previews_dir, exist_ok=True)
    
    # Load ratings file
    ratings_file = os.path.join(CACHE_DIR, 'ratings.txt')
    load_ratings(ratings_file)
    
    # Scan for media files
    print(f"Scanning for media files in: {base_dir}")
    if args.select:
        print(f"Filtering files containing: '{args.select}'")
    scanned_files = scan_for_media_files(base_dir, args.verbose, args.select)

    if not scanned_files:
        print("No media files found (looking for: png, jpg, jpeg, gif, mp4, m4v)")
        sys.exit(1)

    print(f"Found {len(scanned_files)} media files")
    
    # Set up corpus and initial selection
    CORPUS = scanned_files
    MEDIA_FILES = scanned_files[:]

    if args.build_cache:
        build_cache(MEDIA_FILES)

    # Create handler with base directory
    handler_class = create_handler_with_media(base_dir, args.verbose)
    
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
