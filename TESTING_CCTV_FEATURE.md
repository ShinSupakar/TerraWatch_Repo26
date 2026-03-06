# Testing the CCTV/Video Damage Assessment Feature

## Setup Complete ✅

The servers are running:
- **Frontend**: http://127.0.0.1:5173
- **Backend API**: http://127.0.0.1:8000
- **API Documentation**: http://127.0.0.1:8000/docs

---

## What's New

Three new input methods for damage assessment:

### 1. **Satellite/Drone Image** (Original)
- Existing functionality for single images
- Drop or upload `image/*` files

### 2. **CCTV / Video Assessment** (NEW)
- Upload video files: **MP4**, **AVI**, **MOV**
- Extracts frames at ~1 fps (configurable)
- Analyzes up to 100 frames per video
- Returns **worst-case damage** across all frames
- Shows representative frame with overlay

### 3. **IP Camera Stream** (NEW)
- Real-time stream URLs: `rtsp://...` or `http://...`
- Captures up to 30 frames from live feed
- Conservative worst-case damage reporting
- Perfect for disaster response scenarios

---

## Quick Test

### Using the Browser UI:

1. **Open the app**: http://127.0.0.1:5173

2. **Test Video Upload**:
   - A test video has been created: `test_video.mp4`
   - Scroll down to "CCTV / Video Assessment" section
   - Upload the video file
   - Click "ANALYSE VIDEO"
   - Results appear in the pipeline progress and damage panel

3. **Test Stream URL** (requires accessible RTSP/HTTP camera):
   - Go to "IP Camera Stream" section
   - Paste a stream URL (e.g., `rtsp://192.168.1.100/stream`)
   - Click "ANALYSE STREAM"

---

## API Testing with curl

### Test Video Endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/damage/video \
  -F "video=@test_video.mp4" \
  -F "latitude=28.23" \
  -F "longitude=84.73" \
  -F "fast_mode=1" | jq .
```

### Expected Response:
```json
{
  "video_id": "uuid-here",
  "frames_analyzed": 2,
  "frame_dimensions": [240, 320],
  "damage_boxes": [...],
  "aggregated_counts": {
    "no-damage": 0,
    "minor-damage": 0,
    "major-damage": 0,
    "destroyed": 0
  },
  "max_damage_class": 0,
  "causative_event_id": null,
  "representative_frame_b64": "base64-encoded-image",
  "overlay_image_b64": "base64-encoded-image",
  "notes": "..."
}
```

### Test Stream Endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/damage/stream \
  -F "stream_url=rtsp://192.168.1.100/stream" \
  -F "latitude=28.23" \
  -F "longitude=84.73" \
  -F "fast_mode=1" \
  -F "frame_limit=30" | jq .
```

---

## Implementation Details

### Backend Functions Added:

- **`extract_frames_from_video()`** - Handles MP4/AVI/MOV and RTSP/HTTP streams
- **`process_video_frames()`** - Runs damage pipeline on all frames
- **`POST /api/damage/video`** - File upload endpoint
- **`POST /api/damage/stream`** - Live stream endpoint

### Frontend Components Added:

- Video upload zone (accepts `.mp4`, `.mov`, `.avi`)
- Stream URL input field
- Separate "ANALYSE VIDEO" and "ANALYSE STREAM" buttons
- Video preview support

### Models Added:

- **`VideoDamageResponse`** - Response schema for video/stream processing

---

## Testing Scenarios

### Scenario 1: Uploaded Dashcam Footage
- Simulate earthquake damage from vehicle camera
- Upload any dashcam or phone video (with buildings/structures)
- System extracts frames, applies damage detection to each
- Reports worst-case damage found

### Scenario 2: Municipal CCTV Network
- Test with RTSP stream from local IP camera
- Scanner continuously monitors public spaces
- Provides instant damage assessment from existing camera feeds
- No satellite imagery delays (6-48 hours)

### Scenario 3: Real-time Response Coordination
- Multiple cameras feeding damage data simultaneously
- Worst-case reporting surfaces critical areas immediately
- Enables rescue prioritization before traditional assessment completes

---

## Feature Benefits

✅ **Closes gap from satellite to real-time**: 6-48 hours → immediate  
✅ **Reuses existing infrastructure**: Works with installed cameras  
✅ **Conservative reporting**: Worst-case damage appropriate for disaster response  
✅ **Same pipeline reuse**: Uses identical ESRGAN + YOLOv8n as static images  
✅ **Minimal computation**: 1 fps sampling (not all 30 fps redundant frames)  

---

## Troubleshooting

### Backend won't start:
```bash
# Check NumPy version (should be 1.26.4, not 2.x)
python -c "import numpy; print(numpy.__version__)"

# If wrong, reinstall:
pip install numpy==1.26.4
```

### Video not processing:
- Ensure video is MP4/AVI/MOV format
- Check file size isn't too large (max ~100 frames at 1 fps = ~100 MB for high-res)
- Look at backend logs for OpenCV errors

### Stream URL won't connect:
- Verify RTSP/HTTP URL is accessible
- Test with: `curl rtsp://url-here` or `ffprobe rtsp://url-here`
- Ensure firewall allows connection

---

## Files Changed

- `backend.py` - Added endpoints and frame processing functions
- `requirements.txt` - Added opencv-python==4.8.1.78
- `frontend/src/App.jsx` - Added video/stream UI components
- `frontend/src/styles.css` - Added stream input styling

---

## Branch Info

- **Branch**: `feature/cctv-video-assessment`
- **Status**: Ready for testing and code review
- **Commits**: 1 feature commit with all changes

---

## Next Steps

1. ✅ Test with provided `test_video.mp4`
2. Test with real dashcam footage or phone video
3. (Optional) Set up test RTSP stream if accessible
4. Review code changes in `git diff main`
5. Merge to main when approved

---

**Created**: 2026-03-06  
**Feature**: CCTV/Video Damage Assessment for TerraWatch
