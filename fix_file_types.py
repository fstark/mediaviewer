#!/usr/bin/env python3
"""
File Type Fixer - Detects actual file types and renames files with incorrect extensions
Usage: python fix_file_types.py <directory_path>
"""

import os
import sys
import argparse
from pathlib import Path


def detect_file_type(file_path):
    """Detect actual file type by reading file header magic numbers"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)  # Read first 32 bytes
        
        # Check for empty files first
        if len(header) == 0:
            return 'empty'
        
        # Check for HTML files (case insensitive)
        if header.lower().startswith(b'<!doctype html>'):
            return 'html'
        
        # Check magic numbers for common formats
        if header.startswith(b'\xFF\xD8\xFF'):
            return 'jpg'
        elif header.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
            return 'gif'
        elif len(header) >= 12 and header[4:8] == b'ftyp':
            return 'mp4'
        elif header.startswith(b'RIFF') and b'WEBP' in header[:20]:
            return 'webp'
        elif header.startswith(b'BM'):
            return 'bmp'
        elif header.startswith(b'\x00\x00\x01\x00'):
            return 'ico'
        elif header.startswith(b'%PDF'):
            return 'pdf'
        
        return None  # Unrecognized type
        
    except (IOError, OSError) as e:
        print(f"Error reading {file_path}: {e}")
        return None


def get_current_extension(file_path):
    """Get the current file extension (without the dot)"""
    return os.path.splitext(file_path)[1][1:].lower()


def format_hex_dump(data):
    """Format binary data as hex and ASCII representation"""
    hex_str = ' '.join(f'{b:02x}' for b in data)
    ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)
    return f"{hex_str:<48} | {ascii_str}"


def rename_file(old_path, new_extension):
    """Rename file to have the correct extension
    
    Returns:
        tuple: (success: bool, new_path: str or None, reason: str or None)
    """
    directory = os.path.dirname(old_path)
    base_name = os.path.splitext(os.path.basename(old_path))[0]
    new_path = os.path.join(directory, f"{base_name}.{new_extension}")
    
    # Skip if target already exists
    if os.path.exists(new_path):
        return (False, new_path, "target_exists")
    
    try:
        os.rename(old_path, new_path)
        return (True, new_path, None)
    except OSError as e:
        return (False, None, f"rename_error: {e}")


def remove_file(file_path):
    """Remove a file
    
    Returns:
        tuple: (success: bool, reason: str or None)
    """
    try:
        os.remove(file_path)
        return (True, None)
    except OSError as e:
        return (False, f"remove_error: {e}")


def process_directory(directory, dry_run=False, prune=False):
    """Process all files in directory recursively"""
    # Common media file extensions to check
   
    skip_extensions = { '.txt' }

    files_processed = 0
    files_renamed = 0
    files_unrecognized = 0
    files_removed = 0
    
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                current_ext = get_current_extension(file_path)
                
                # Only process files with media extensions
                if f'.{current_ext}' in skip_extensions:
                    continue
                
                files_processed += 1
                actual_type = detect_file_type(file_path)
                
                if actual_type in ['html', 'empty']:
                    # HTML or empty files - remove if pruning
                    rel_path = os.path.relpath(file_path, directory)
                    if prune:
                        if dry_run:
                            print(f"WOULD REMOVE: {rel_path} ({actual_type.upper()} file)")
                        else:
                            success, reason = remove_file(file_path)
                            if success:
                                print(f"REMOVED: {rel_path} ({actual_type.upper()} file)")
                                files_removed += 1
                            else:
                                print(f"FAILED TO REMOVE: {rel_path}")
                                print(f"  Reason: {reason}")
                    else:
                        print(f"FOUND: {rel_path} ({actual_type.upper()} file - use --prune to remove)")
                
                elif actual_type is None:
                    # Unrecognized file type - log hex dump
                    try:
                        file_size = os.path.getsize(file_path)
                        with open(file_path, 'rb') as f:
                            first_16_bytes = f.read(16)
                        rel_path = os.path.relpath(file_path, directory)
                        hex_dump = format_hex_dump(first_16_bytes)
                        print(f"UNRECOGNIZED: {rel_path} ({file_size} bytes)")
                        print(f"  First 16 bytes: {hex_dump}")
                        files_unrecognized += 1
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
                
                elif actual_type != current_ext:
                    # File type mismatch - rename needed
                    rel_path = os.path.relpath(file_path, directory)
                    
                    if dry_run:
                        print(f"WOULD RENAME: {rel_path}")
                        print(f"  Content type: {actual_type.upper()}, Current extension: {current_ext.upper()}")
                        print(f"  Would rename to: {os.path.splitext(rel_path)[0]}.{actual_type}")
                    else:
                        success, new_path, reason = rename_file(file_path, actual_type)
                        if success:
                            rel_new_path = os.path.relpath(new_path, directory)
                            print(f"RENAMED: {rel_path} -> {rel_new_path}")
                            print(f"  Content type: {actual_type.upper()}, Old extension: {current_ext.upper()}")
                            files_renamed += 1
                        elif reason == "target_exists":
                            rel_target = os.path.relpath(new_path, directory)
                            print(f"SKIPPED: {rel_path}")
                            print(f"  Target file already exists: {rel_target}")
                        else:
                            print(f"FAILED TO RENAME: {rel_path}")
                            print(f"  Reason: {reason}")
    
    except PermissionError as e:
        print(f"Permission denied accessing: {e.filename}")
    except Exception as e:
        print(f"Error processing directory: {e}")
    
    # Summary
    print(f"\nSummary:")
    print(f"  Files processed: {files_processed}")
    print(f"  Files renamed: {files_renamed}")
    print(f"  Files removed: {files_removed}")
    print(f"  Unrecognized files: {files_unrecognized}")


def main():
    parser = argparse.ArgumentParser(description='Fix file extensions based on actual file content')
    parser.add_argument('directory', help='Directory to scan recursively for files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without actually renaming files')
    parser.add_argument('--prune', action='store_true', help='Remove HTML and empty files instead of just reporting them')
    args = parser.parse_args()

    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a valid directory")
        sys.exit(1)
    
    # Convert to absolute path
    directory = os.path.abspath(args.directory)
    
    print(f"Processing files in: {directory}")
    if args.dry_run:
        print("DRY RUN MODE - No files will be renamed or removed")
    if args.prune:
        print("PRUNE MODE - HTML and empty files will be removed")
    print()
    
    process_directory(directory, args.dry_run, args.prune)


if __name__ == '__main__':
    main()