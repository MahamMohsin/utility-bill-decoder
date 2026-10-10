import base64
import io
from PIL import Image, ImageOps

def image_parts(path, crops=False):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
        images = [image]
        if crops:
            w,h = image.size
            # Overlapping high-resolution views; original always retained.
            images.extend([image.crop((0,0,w,int(h*.6))),
                           image.crop((0,int(h*.4),w,h))])
        parts = []
        for view in images:
            data = io.BytesIO()
            view.save(data, format='PNG')
            parts.append({'inlineData':{'mimeType':'image/png',
                         'data':base64.b64encode(data.getvalue()).decode('ascii')}})
        return parts
