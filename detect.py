from ultralytics import YOLO
import cv2
import os

# Load YOLO model ONCE
model = YOLO("model/best.pt")

# Class index → label mapping (must match training)
CLASS_MAP = {
    0: "malaligned",
    1: "stains",
    2: "caries",
    3: "pit_fissure"
}


def run_yolo(input_image, output_image):
    """
    Runs YOLO on image
    Saves image with bounding boxes
    Returns detected labels list
    """

    if not os.path.exists(input_image):
        return []

    results = model(input_image, conf=0.3)

    detected_labels = set()

    img = cv2.imread(input_image)

    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])

            label = CLASS_MAP.get(cls_id, "unknown")
            detected_labels.add(label)

            # Bounding box
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                img,
                f"{label} {conf:.2f}",
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

    cv2.imwrite(output_image, img)

    return list(detected_labels)