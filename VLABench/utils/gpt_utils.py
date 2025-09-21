'''
Lightweight OpenAI helpers used by agents.

- query_gpt4_v: text chat convenience wrapper
- generate_images: image generation (reference renders for missing assets)
- base64/image utilities
'''
from openai import OpenAI
import os
import base64
import json

def convert_base64_to_data_uri(base64_image):
    def _get_mime_type_from_data_uri(base64_image):
        # Decode the base64 string
        image_data = base64.b64decode(base64_image)
        # Check the first few bytes for known signatures
        if image_data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif image_data.startswith(b"GIF87a") or image_data.startswith(b"GIF89a"):
            return "image/gif"
        elif image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"  # use jpeg for unknown formats, best guess.

    mime_type = _get_mime_type_from_data_uri(base64_image)
    data_uri = f"data:{mime_type};base64,{base64_image}"
    return data_uri

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

def query_gpt4_v(prompt, history=[], model="gpt-4-turbo", **kwargs):
    client = OpenAI(
        api_key=kwargs.get("api_key", os.environ.get("OPENAI_API_KEY", None)), 
        base_url=kwargs.get("base_url", os.environ.get("OPENAI_BASE_URL", None))
    )
    
    while True:
        try:
            messages = []
            for q,a in history:
                messages.append({"role": "user", "content": q})
                messages.append({"role": "assistant", "content": a})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=1000,
                        )
            break
        except Exception as e:
            print(f"openai error, {e}")
    message = response.choices[0].message
    content = message.content
    return content

def build_prompts(text, image_paths):
    prompt = list()
    for image_path in image_paths:
        base64image = encode_image(image_path)
        uri = convert_base64_to_data_uri(base64image)
        prompt.append({"type": "image_url", "image_url": {"url": uri}})
    prompt.append({"type": "text", "text": text})
    return prompt

def build_prompt_with_tilist(text_image_list):
    prompt = list()
    for ti_context in text_image_list:
        if ti_context[0] == 'text':
            text = ti_context[1]
            prompt.append({"type": "text", "text": text})
        elif ti_context[0] == 'image':
            image_path = ti_context[1]
            base64image = encode_image(image_path)
            uri = convert_base64_to_data_uri(base64image)
            prompt.append({"type": "image_url", "image_url": {"url": uri}})
    return prompt


def generate_images(prompt: str, out_dir: str, n: int = 3, size: str = "1024x1024", model: str | None = None, **kwargs):
    """
    Generate reference images via OpenAI Images API and save to out_dir.

    Params:
      - prompt: text prompt for generation
      - out_dir: directory to save images
      - n: number of images
      - size: e.g., "1024x1024"
      - model: override model name (default from env OPENAI_IMAGE_MODEL or 'gpt-image-1')
      - kwargs: api_key, base_url optional overrides

    Returns: list of saved file paths
    """
    os.makedirs(out_dir, exist_ok=True)
    client = OpenAI(
        api_key=kwargs.get("api_key", os.environ.get("OPENAI_API_KEY", None)),
        base_url=kwargs.get("base_url", os.environ.get("OPENAI_BASE_URL", None)),
    )
    model = model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    # The OpenAI SDK returns base64 strings in response.data[i].b64_json
    resp = client.images.generate(model=model, prompt=prompt, size=size, n=n)
    saved = []
    for i, datum in enumerate(resp.data, 1):
        b64 = getattr(datum, "b64_json", None)
        if not b64:
            continue
        img_bytes = base64.b64decode(b64)
        path = os.path.join(out_dir, f"ref_{i:02d}.png")
        with open(path, "wb") as f:
            f.write(img_bytes)
        saved.append(path)
    return saved
