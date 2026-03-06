import cv2
import numpy as np
import urllib.request
import os

print("Downloading earthquake image...")
url = "https://upload.wikimedia.org/wikipedia/commons/e/e5/Sanfranciscoearthquake1906.jpg"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as resp:
        image_data = resp.read()
    
    # decode image
    image_array = np.asarray(bytearray(image_data), dtype=np.uint8)
    base_img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    
    if base_img is None:
        raise ValueError("Failed to decode image")

    # Image dimensions
    h, w = base_img.shape[:2]
    
    # Target video specs
    fps = 30
    duration = 5 # seconds
    num_frames = fps * duration
    
    # Setup video writer
    target_w, target_h = 1280, 720
    out = cv2.VideoWriter('test_video.mp4', cv2.VideoWriter_fourcc(*'mp4v'), fps, (target_w, target_h))
    
    print(f"Generating {num_frames} frames...")
    # Generate frames by applying panning and zooming
    for i in range(num_frames):
        # Progress from 0.0 to 1.0
        progress = i / max(1, (num_frames - 1))
        
        # Zoom from 1.0 to 1.5
        zoom = 1.0 + 0.5 * progress
        
        # Current crop size
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        
        # Pan slowly from left to right, top to bottom
        x = int(progress * (w - crop_w))
        y = int(progress * (h - crop_h))
        
        cropped = base_img[y:y+crop_h, x:x+crop_w]
        
        # Resize to target
        frame = cv2.resize(cropped, (target_w, target_h))
        
        # Optionally add some text overlay
        cv2.putText(frame, "CCTV Feed - REC", (40, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(frame, f"Frame {i:03d}", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        out.write(frame)
        
    out.release()
    print("test_video.mp4 created successfully.")

except Exception as e:
    print(f"Error: {e}")
