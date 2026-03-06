import cv2
import numpy as np
import urllib.request
import os

configs = [
    {
        "name": "turkey_2023_cctv.mp4",
        "url": "https://upload.wikimedia.org/wikipedia/commons/d/da/Ruins_of_the_Cathedral_of_the_Annunciation%2C_%C4%B0skenderun_1.jpg", 
        "text": "Antakya CCTV - REC"
    },
    {
        "name": "nepal_2015_cctv.mp4",
        "url": "https://upload.wikimedia.org/wikipedia/commons/9/93/BLMERS_-GIVINGBACK-_Earthquake_Relief_in_Nepal_%2823394679481%29.jpg",
        "text": "Kathmandu CCTV - REC"
    },
    {
        "name": "japan_2011_cctv.mp4",
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/An_aerial_view_of_tsunami_damage_in_an_area_north_of_Sendai%2C_Japan%2C_taken_from_a_U.S._Navy_helicopter-LF.jpg",
        "text": "Sendai CCTV - REC"
    }
]

fps = 30
duration = 5 # seconds
num_frames = fps * duration
target_w, target_h = 1280, 720

for config in configs:
    print(f"Generating {config['name']}...")
    try:
        req = urllib.request.Request(config['url'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            image_data = resp.read()
        
        image_array = np.asarray(bytearray(image_data), dtype=np.uint8)
        base_img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        
        if base_img is None:
            raise ValueError(f"Failed to decode image from {config['url']}")

        h, w = base_img.shape[:2]
        
        out = cv2.VideoWriter(config['name'], cv2.VideoWriter_fourcc(*'mp4v'), fps, (target_w, target_h))
        
        for i in range(num_frames):
            progress = i / max(1, (num_frames - 1))
            zoom = 1.0 + 0.3 * progress
            
            crop_w = int(w / zoom)
            crop_h = int(h / zoom)
            
            x = int(progress * (w - crop_w))
            y = int(progress * (h - crop_h))
            
            cropped = base_img[y:y+crop_h, x:x+crop_w]
            frame = cv2.resize(cropped, (target_w, target_h))
            
            cv2.putText(frame, config['text'], (40, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(frame, f"Frame {i:03d}", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            out.write(frame)
            
        out.release()
        print(f"Successfully generated {config['name']}")
    except Exception as e:
        print(f"Error generating {config['name']}: {e}")
