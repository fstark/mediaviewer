# Simple Media Viewer

A web-based media gallery for viewing images and videos. This Python program recursively scans a directory for media files and creates a simple HTTP server to display them in a web interface.

## Features

- **Recursive Directory Scanning**: Automatically finds all media files in subdirectories
- **Supported Formats**: PNG, JPG, JPEG, MP4
- **Gallery View**: Displays all media as 320x200 thumbnails in a grid layout
- **Full-Screen Viewer**: Click any thumbnail to view in full screen
- **Navigation**: Use arrow keys or on-screen buttons to navigate between media
- **Video Support**: Videos can be played directly in the browser with controls
- **Responsive Design**: Works well on different screen sizes

## Requirements

- Python 3.6 or higher
- No additional packages required (uses only Python standard library)

## Usage

```bash
python media_viewer.py <directory_path> [options]
```

### Arguments

- `directory_path`: The directory to scan for media files (required)
- `-p, --port`: Port number to run the server on (default: 8000)

### Examples

```bash
# Scan current directory and start server on default port (8000)
python media_viewer.py .

# Scan a specific directory
python media_viewer.py /path/to/your/photos

# Use a custom port
python media_viewer.py /path/to/media --port 9000
```

## How to Use

1. Run the program with a directory path
2. Open your web browser and go to `http://localhost:8000` (or your custom port)
3. The server will be accessible on all network interfaces (0.0.0.0)
4. You'll see a gallery view with all your media files as thumbnails
5. Click on any thumbnail to view it in full screen
6. In full-screen mode:
   - Use arrow keys or click the navigation buttons to go to next/previous media
   - Press Escape or click "Back to Gallery" to return to the gallery view
   - Videos will have playback controls

## Keyboard Shortcuts (Full-Screen Mode)

- `←` (Left Arrow): Previous media
- `→` (Right Arrow): Next media
- `Escape`: Return to gallery view

## File Structure

```
mediaviewer/
├── media_viewer.py    # Main application file
├── requirements.txt   # Dependencies (none required)
└── README.md         # This file
```

## Security Note

**Important**: The server now binds to all network interfaces (0.0.0.0), making it accessible from other devices on your network. This means:

- ✅ **Local Access**: Available at `http://localhost:8000`
- ⚠️ **Network Access**: Available at `http://your-ip-address:8000` from other devices
- 🔒 **Security Consideration**: Any device on your network can access your media files

**Recommendations**:
- Use only on trusted networks (home/private networks)
- Consider using a firewall to restrict access if needed
- Be aware that media files will be accessible to anyone who can reach your IP address on the specified port

For localhost-only access, you can modify the code to bind to `('localhost', args.port)` instead of `('0.0.0.0', args.port)`.

## License

This is a simple utility program. Feel free to modify and use as needed.
