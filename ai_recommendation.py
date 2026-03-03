def generate_recommendations(detections):
    summary = {}

    # Count problems
    for d in detections:
        label = d["label"]
        conf = d["confidence"]

        if label not in summary:
            summary[label] = {"count": 0, "conf": []}

        summary[label]["count"] += 1
        summary[label]["conf"].append(conf)

    recommendations = []

    # 🧠 DECISION LOGIC
    for label, data in summary.items():
        avg_conf = sum(data["conf"]) / len(data["conf"])
        count = data["count"]

        if label == "caries":
            if count >= 2 and avg_conf >= 0.7:
                rec = "Multiple high-severity carious lesions detected. Restorative treatment or root canal therapy is strongly recommended."
            else:
                rec = "Early-stage caries detected. Preventive care and monitoring are advised."

        elif label == "stains":
            if avg_conf >= 0.6:
                rec = "Moderate dental staining detected. Professional scaling and polishing are recommended."
            else:
                rec = "Mild surface stains detected. Routine cleaning is sufficient."

        elif label == "malaligned":
            rec = "Tooth misalignment detected. Orthodontic consultation for braces or aligners is recommended."

        elif label == "pit_fissure":
            rec = "Pit and fissure caries detected. Preventive sealants or fillings may be required."

        else:
            rec = "Condition detected. Clinical consultation recommended."

        recommendations.append((label, rec))

    return recommendations