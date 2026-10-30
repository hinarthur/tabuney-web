# game/utils.py
import os
import uuid
from datetime import datetime
from django.core.files.storage import default_storage
from django.utils.deconstruct import deconstructible

@deconstructible
class UUIDFilenameGenerator:
    """
    Generate UUID-based filenames for uploaded files while preserving file extensions.
    This prevents filename conflicts and provides unique identifiers.
    """
    
    def __init__(self, path_prefix=''):
        self.path_prefix = path_prefix
    
    def __call__(self, instance, filename):
        """
        Generate a unique filename using UUID.
        
        Args:
            instance: The model instance
            filename: Original filename
            
        Returns:
            str: New filename with UUID
        """
        # Get file extension
        ext = os.path.splitext(filename)[1]
        
        # Generate UUID
        new_filename = str(uuid.uuid4())
        
        # Process path prefix with date formatting
        if self.path_prefix:
            # Format date strings like %Y, %m, %d
            path_prefix = datetime.now().strftime(self.path_prefix)
            return f"{path_prefix}/{new_filename}{ext}"
        else:
            return f"{new_filename}{ext}"

# Predefined generators for common use cases
edition_thumbnail_upload = UUIDFilenameGenerator("edition_thumbnails/%Y/%m")
rulebook_figure_upload = UUIDFilenameGenerator("rulebook_figures/%Y/%m")

def image_to_webp_bytes(img, max_side=400):
    """PIL Image -> 最長邊 max_side 的 WebP bytes（保留 ICC，透明底壓白，CMYK 轉 RGB）。"""
    import io
    from PIL import Image

    icc = img.info.get('icc_profile')
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    if width > max_side or height > max_side:
        if width > height:
            size = (max_side, int(height * (max_side / width)))
        else:
            size = (int(width * (max_side / height)), max_side)
        img = img.resize(size, Image.Resampling.LANCZOS)

    out = io.BytesIO()
    img.save(out, format='WEBP', quality=85, method=6, icc_profile=icc)
    return out.getvalue()
