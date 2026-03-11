
import httpx
import base64
import json

# Minimal 1x1 black pixel GIF in base64
IMG_B64 = "R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs="

def test_multimodal():
    url = "http://localhost:8000/v1/chat/completions"
    payload = {
        "model": "gemini-3.1-flash-lite-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/gif;base64,{IMG_B64}"
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        r = httpx.post(url, json=payload, timeout=30)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_multimodal()
