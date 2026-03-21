from ultralytics import YOLO
import cv2
import os

model = YOLO("model/best.pt")

CLASS_MAP = {
    0: "malaligned",
    1: "stains",
    2: "caries",
    3: "pit_fissure"
}


def run_yolo(input_image, output_image):
    """
    Run YOLO on image.
    Returns list of dicts: [{"label": "caries", "confidence": 0.87}, ...]
    Multiple detections of same label are all included (for avg confidence calc).
    """
    if not os.path.exists(input_image):
        return []

    img = cv2.imread(input_image)
    results = model(img, conf=0.3)

    detections = []   # list of {"label", "confidence"}

    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            label  = CLASS_MAP.get(cls_id, "unknown")

            detections.append({"label": label, "confidence": conf})

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

    return detections   # ← now returns full dicts, not just label strings