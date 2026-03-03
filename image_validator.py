import cv2
import numpy as np

def is_valid_teeth_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1️⃣ Brightness check (reject dark images)
    brightness = np.mean(gray)
    if brightness < 50:
        return False

    # 2️⃣ Blur check (reject unclear images)
    blur = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur < 80:
        return False

    # 3️⃣ Edge density (reject fan / wall / blank)
    edges = cv2.Canny(gray, 80, 160)
    edge_ratio = np.sum(edges > 0) / edges.size
    if edge_ratio < 0.02:
        return False

    return True